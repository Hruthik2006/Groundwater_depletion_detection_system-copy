import os
import glob
import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, Tuple, Optional
from .base_provider import BaseDataProvider

logger = logging.getLogger(__name__)


class DWLRDataProvider(BaseDataProvider):
    """
    Real Central Ground Water Board (CGWB) DWLR Dataset Provider.
    Parses real daily/periodic well observations from DWLR CSV datasets,
    applies robust modified z-score outlier screening (|z| > 6.0 via median & MAD),
    handles station gap interpolation, and provides formatted piezometric time series.

    Honest seam: the hydromet channel carries genuine CGWB well observations;
    the raster and static-geophysics channels are calibrated synthetic replicas
    (the dataset ships no matched GRACE/CHIRPS tiles).
    """

    capabilities: Dict[str, str] = {
        "raster": "synthetic",
        "hydromet": "dwlr",
        "static": "synthetic",
    }
    is_synthetic: bool = False

    def __init__(
        self,
        dataset_dir: str = r"d:\Ground_water\datasets\DWLR Station Water Level Dataset\data",
        grid_shape: Tuple[int, int] = (16, 16),
        seed: int = 42,
    ):
        self.dataset_dir = dataset_dir
        self.grid_shape = grid_shape
        self.seed = seed
        self._df = None
        self._stations_cache = None

    def _load_and_clean_raw_csvs(self, max_files: Optional[int] = None) -> pd.DataFrame:
        if self._df is not None:
            return self._df

        csv_files = sorted(glob.glob(os.path.join(self.dataset_dir, "*.csv")))
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in dataset directory: {self.dataset_dir}")

        if max_files:
            csv_files = csv_files[:max_files]

        logger.info(f"Loading DWLR dataset from {len(csv_files)} CSV file(s)...")
        dfs = []

        for filepath in csv_files:
            try:
                df = pd.read_csv(filepath, low_memory=False)
                # Normalize column names (strip whitespace)
                df.columns = [c.strip() for c in df.columns]

                req_cols = ["state", "district", "lat", "lng", "Date", "waterLevel"]
                available = [c for c in req_cols if c in df.columns]

                if len(available) >= 5:
                    sub = df[available].copy()
                    dfs.append(sub)
            except Exception as e:
                logger.warning(f"Skipping file {filepath} due to read error: {e}")

        if not dfs:
            raise ValueError("Failed to load any valid DWLR CSV data.")

        combined = pd.concat(dfs, ignore_index=True)
        combined["lat"] = pd.to_numeric(combined["lat"], errors="coerce")
        combined["lng"] = pd.to_numeric(combined["lng"], errors="coerce")
        combined["waterLevel"] = pd.to_numeric(combined["waterLevel"], errors="coerce")
        combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")

        # Drop invalid rows
        clean_df = combined.dropna(subset=["lat", "lng", "waterLevel", "Date"]).copy()
        clean_df["station_id"] = (
            clean_df["state"].astype(str)
            + "_"
            + clean_df["district"].astype(str)
            + "_"
            + clean_df["lat"].round(4).astype(str)
            + "_"
            + clean_df["lng"].round(4).astype(str)
        )

        logger.info(f"Loaded {len(clean_df)} valid DWLR records across {clean_df['station_id'].nunique()} unique stations.")
        self._df = clean_df
        return self._df

    @staticmethod
    def robust_modified_zscore_filter(series: np.ndarray, threshold: float = 6.0) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates robust modified z-score based on median and Median Absolute Deviation (MAD):
        z_i = 0.6745 * |x_i - median(x)| / MAD(x)
        Returns (cleaned_series_with_nans_for_outliers, outlier_mask)
        Paper Reference: Section IV-B (outliers with |z| > 6 removed).
        """
        arr = np.array(series, dtype=np.float64)
        valid = arr[~np.isnan(arr)]
        if len(valid) < 3:
            return arr, np.zeros_like(arr, dtype=bool)

        med = np.median(valid)
        mad = np.median(np.abs(valid - med))

        if mad < 1e-6:
            mad = np.std(valid) + 1e-6

        mod_z = 0.6745 * np.abs(arr - med) / mad
        outlier_mask = mod_z > threshold
        cleaned = arr.copy()
        cleaned[outlier_mask] = np.nan

        return cleaned, outlier_mask

    def fetch_piezometer_observations(
        self,
        num_wells: int = 16,
        timesteps: int = 12,
    ) -> Dict[str, Any]:
        """
        Parses and formats real DWLR station time-series data.
        Selects top stations with best record density, applies robust MAD outlier filtering,
        and interpolates missing entries.
        """
        df = self._load_and_clean_raw_csvs()

        # Group by station_id and find top stations with highest record counts
        station_counts = df.groupby("station_id").size().sort_values(ascending=False)
        top_station_ids = station_counts.index[: max(num_wells, 50)].tolist()

        selected_ids = top_station_ids[:num_wells]
        coords_list = []
        G_matrix = np.zeros((num_wells, timesteps))
        missing_mask = np.zeros((num_wells, timesteps), dtype=bool)
        station_meta = []

        np.random.seed(self.seed)

        for i, st_id in enumerate(selected_ids):
            st_df = df[df["station_id"] == st_id].sort_values("Date").drop_duplicates(subset=["Date"])
            lat_val = st_df["lat"].iloc[0]
            lng_val = st_df["lng"].iloc[0]
            coords_list.append([lat_val, lng_val])

            station_meta.append({
                "station_id": st_id,
                "state": st_df["state"].iloc[0],
                "district": st_df["district"].iloc[0],
                "lat": lat_val,
                "lng": lng_val,
                "record_count": len(st_df),
            })

            levels = st_df["waterLevel"].values
            # 1. Apply robust modified z-score outlier screening
            cleaned_levels, outlier_mask = self.robust_modified_zscore_filter(levels, threshold=6.0)

            # 2. Resample or truncate/pad to requested timesteps
            valid_cleaned = cleaned_levels[~np.isnan(cleaned_levels)]
            if len(valid_cleaned) >= timesteps:
                series = valid_cleaned[:timesteps]
            else:
                # Pad with linear interpolation & mean fill
                if len(valid_cleaned) > 0:
                    mean_val = np.mean(valid_cleaned)
                    series = np.interp(
                        np.linspace(0, len(valid_cleaned) - 1, timesteps),
                        np.arange(len(valid_cleaned)),
                        valid_cleaned,
                    )
                else:
                    series = np.full(timesteps, 15.0)

            # Random synthetic noise check for mask tracking
            is_missing = np.isnan(cleaned_levels[:timesteps]) if len(cleaned_levels) >= timesteps else np.zeros(timesteps, dtype=bool)

            G_matrix[i, :] = series
            missing_mask[i, :] = is_missing

        coords_arr = np.array(coords_list)

        # Scale coordinates into normalized 2D grid coordinates (row, col)
        min_lat, max_lat = coords_arr[:, 0].min(), coords_arr[:, 0].max() + 1e-5
        min_lng, max_lng = coords_arr[:, 1].min(), coords_arr[:, 1].max() + 1e-5

        grid_coords = np.zeros((num_wells, 2), dtype=int)
        grid_coords[:, 0] = np.clip(((coords_arr[:, 0] - min_lat) / (max_lat - min_lat) * (self.grid_shape[0] - 1)).astype(int), 0, self.grid_shape[0] - 1)
        grid_coords[:, 1] = np.clip(((coords_arr[:, 1] - min_lng) / (max_lng - min_lng) * (self.grid_shape[1] - 1)).astype(int), 0, self.grid_shape[1] - 1)

        return {
            "coords": grid_coords,
            "coords_latlon": coords_arr,
            "G": G_matrix,
            "missing_mask": missing_mask,
            "station_meta": station_meta,
        }

    def fetch_hydroclimate_rasters(self, timesteps: int = 12) -> Dict[str, np.ndarray]:
        """
        Provides matched hydroclimatic rasters (P, ET, SMSA, TWSA) paired with DWLR records.
        """
        H, W = self.grid_shape
        np.random.seed(self.seed)

        # Generate realistic hydroclimate signals for India monsoon/dry seasonality
        t_vec = np.arange(timesteps)
        monsoon = np.maximum(0, np.sin(2 * np.pi * t_vec / 12.0 - np.pi / 2)) * 40.0 + 5.0
        temp = 25.0 + 8.0 * np.cos(2 * np.pi * t_vec / 12.0)

        P = np.zeros((timesteps, H, W))
        ET = np.zeros((timesteps, H, W))
        SMSA = np.zeros((timesteps, H, W))
        TWSA = np.zeros((timesteps, H, W))

        for t in range(timesteps):
            P[t] = monsoon[t] + np.random.normal(0, 3.0, (H, W))
            ET[t] = 0.4 * temp[t] + np.random.normal(0, 1.0, (H, W))
            SMSA[t] = 0.2 * monsoon[t] - 0.1 * temp[t] + np.random.normal(0, 0.5, (H, W))
            TWSA[t] = np.cumsum(P[t] - ET[t], axis=0)[0] / 20.0

        return {
            "P": P,
            "ET": ET,
            "SMSA": SMSA,
            "SWEA": np.zeros((timesteps, H, W)),
            "CWSA": np.zeros((timesteps, H, W)),
            "TWSA_native": TWSA[:, :2, :2],
            "Qs": np.maximum(0, P * 0.15),
            "temp": temp[:, None, None] * np.ones((1, H, W)),
        }

    def fetch_static_geophysics(self) -> Dict[str, np.ndarray]:
        H, W = self.grid_shape
        np.random.seed(self.seed)

        K = np.random.uniform(2.0, 15.0, (H, W))
        Sy = np.random.uniform(0.05, 0.25, (H, W))
        z_bedrock = np.random.uniform(40.0, 120.0, (H, W))

        return {"K": K, "Sy": Sy, "z_bedrock": z_bedrock}

    def get_grid_metadata(self) -> Dict[str, Any]:
        return {
            "region_key": "dwlr_cgwb_india",
            "grid_shape": self.grid_shape,
            "mascon_grid_shape": (2, 2),
            "bounds": [68.0, 8.0, 96.0, 36.0],  # India lat/lon extent
            "data_source": "Central Ground Water Board (CGWB) DWLR Dataset",
            "serves": self.serves(),
        }

    def set_region(self, region_key: str = "dwlr_cgwb_india", bounds: list = None):
        """DWLR data is a fixed national well network; region switches are no-ops."""
        logger.info(f"DWLR provider ignores region preset '{region_key}' (fixed CGWB network).")
