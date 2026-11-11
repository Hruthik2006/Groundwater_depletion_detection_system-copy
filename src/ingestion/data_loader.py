import numpy as np
import logging
from typing import Dict, Any, Optional, Tuple
from scipy.interpolate import CubicSpline
from .synthetic_provider import SyntheticDataProvider
from .realtime_provider import RealtimeEarthEngineDataProvider
from .dwlr_provider import DWLRDataProvider

logger = logging.getLogger(__name__)


class GroundwaterDataLoader:
    """
    Unified Geospatial Data Loader Engine.
    Coordinates spatial alignment, piezometer cubic spline interpolation,
    and baseline z-score normalization across multi-source streams.
    """

    def __init__(
        self,
        data_mode: str = "synthetic",
        grid_shape: tuple = (16, 16),
        mascon_grid_shape: tuple = (2, 2),
        region_key: str = "illinois",
        bounds: list = None,
        seed: int = 42,
    ):
        self.data_mode = data_mode.lower()
        self.grid_shape = grid_shape
        self.mascon_grid_shape = mascon_grid_shape
        self.region_key = region_key
        self.bounds = bounds
        self.seed = seed

        self._init_provider()

    def _init_provider(self):
        if self.data_mode == "realtime":
            self.provider = RealtimeEarthEngineDataProvider(
                grid_shape=self.grid_shape,
                mascon_grid_shape=self.mascon_grid_shape,
                region_key=self.region_key,
                bounds=self.bounds,
                seed=self.seed,
            )
        elif self.data_mode == "dwlr":
            self.provider = DWLRDataProvider(
                grid_shape=self.grid_shape,
                seed=self.seed,
            )
        else:
            self.provider = SyntheticDataProvider(
                grid_shape=self.grid_shape,
                mascon_grid_shape=self.mascon_grid_shape,
                region_key=self.region_key,
                bounds=self.bounds,
                seed=self.seed,
            )

    def set_data_mode(self, mode: str):
        """Dynamically switch between 'synthetic' and 'realtime' data modes."""
        self.data_mode = mode.lower()
        self._init_provider()
        logger.info(f"Data loader mode switched to: {self.data_mode}")

    def set_region(self, region_key: str = "illinois", bounds: list = None):
        """Dynamically update geographic study region preset or custom bounds."""
        self.region_key = region_key
        self.bounds = bounds
        self._init_provider()
        logger.info(f"Data loader location set to region: {region_key}, bounds: {bounds}")

    def detect_region_key(self, lat: float, lon: float) -> Tuple[str, Optional[list]]:
        """
        Determines matching hydrogeological region preset or custom bounds based on (lat, lon) coordinates.
        """
        lat_f = float(lat)
        lon_f = float(lon)

        # Ganges / Indo-Gangetic Basin (India)
        if 65.0 <= lon_f <= 95.0 and 8.0 <= lat_f <= 36.0:
            return "ganges", None
        # High Plains / Ogallala Aquifer (USA)
        elif -106.0 <= lon_f <= -94.0 and 31.0 <= lat_f <= 44.0:
            return "high_plains", None
        # North German Basin (Europe)
        elif 5.0 <= lon_f <= 16.0 and 47.0 <= lat_f <= 58.0:
            return "north_german", None
        # Illinois Glacial Aquifer System (USA)
        elif -92.5 <= lon_f <= -85.0 and 36.5 <= lat_f <= 43.0:
            return "illinois", None
        else:
            # Custom bounding box centered on (lat, lon)
            custom_bounds = [
                float(np.clip(lon_f - 1.5, -180.0, 180.0)),
                float(np.clip(lat_f - 1.0, -90.0, 90.0)),
                float(np.clip(lon_f + 1.5, -180.0, 180.0)),
                float(np.clip(lat_f + 1.0, -90.0, 90.0)),
            ]
            return "custom", custom_bounds

    def load_processed_dataset(
        self,
        timesteps: int = 36,
        num_wells: int = 16,
    ) -> Dict[str, Any]:
        """
        Ingests, interpolates, and normalizes hydroclimatic tensors and piezometer wells.
        """
        # Fetch raw provider outputs
        metadata = self.provider.get_grid_metadata()
        metadata["data_mode"] = self.data_mode
        if hasattr(self.provider, "serves"):
            metadata["serves"] = self.provider.serves()
        rasters = self.provider.fetch_hydroclimate_rasters(timesteps=timesteps)
        wells = self.provider.fetch_piezometer_observations(num_wells=num_wells, timesteps=timesteps)
        static_geo = self.provider.fetch_static_geophysics()

        # 1. Cubic spline temporal interpolation for missing piezometer entries
        G_raw = wells["G"].copy()  # (num_wells, T)
        T = timesteps
        t_arr = np.arange(T)
        G_filled = np.zeros_like(G_raw)

        for i in range(wells["coords"].shape[0]):
            series = G_raw[i]
            valid_mask = ~np.isnan(series)
            if np.sum(valid_mask) >= 4:
                cs = CubicSpline(t_arr[valid_mask], series[valid_mask], extrapolate=True)
                G_filled[i] = cs(t_arr)
            else:
                # Fallback to mean fill if insufficient points
                mean_val = np.nanmean(series) if np.any(valid_mask) else 45.0
                G_filled[i] = np.where(valid_mask, series, mean_val)

        # 2. Inverse Distance Weighting (IDW) spatial piezometer interpolation over 2D grid
        H, W = self.grid_shape
        G_spatial_idw = self.interpolate_spatial_idw(wells["coords"], G_filled, (H, W))

        # 3. Z-Score Normalization per spatial grid cell across historical timeline
        normalized_rasters = {}
        raster_stats = {}

        for var_name, tensor in rasters.items():
            if tensor.ndim == 3:  # (T, H, W)
                mean_map = np.mean(tensor, axis=0, keepdims=True)  # (1, H, W)
                std_map = np.std(tensor, axis=0, keepdims=True)
                std_map = np.where(std_map == 0, 1.0, std_map)
                norm_tensor = (tensor - mean_map) / std_map

                normalized_rasters[var_name] = norm_tensor
                raster_stats[var_name] = {"mean": mean_map[0], "std": std_map[0]}
            else:
                normalized_rasters[var_name] = tensor

        return {
            "metadata": metadata,
            "rasters_raw": rasters,
            "rasters_norm": normalized_rasters,
            "raster_stats": raster_stats,
            "wells": {
                "coords": wells["coords"],
                "G_raw": G_raw,
                "G_filled": G_filled,
                "G_spatial_idw": G_spatial_idw,
                "missing_mask": wells["missing_mask"],
            },
            "geophysics": static_geo,
        }

    def interpolate_spatial_idw(self, coords: np.ndarray, G_filled: np.ndarray, grid_shape: Tuple[int, int], power: float = 2.0) -> np.ndarray:
        """
        Executes Inverse Distance Weighting (IDW) spatial interpolation from point piezometers to 2D grid rasters.
        coords: (num_wells, 2) row/col positions
        G_filled: (num_wells, T)
        returns: G_spatial (T, H, W)
        """
        H, W = grid_shape
        num_wells, T = G_filled.shape
        G_spatial = np.zeros((T, H, W))

        rows, cols = np.indices((H, W))
        grid_pts = np.stack([rows.ravel(), cols.ravel()], axis=1)  # (H*W, 2)

        for t in range(T):
            obs_vals = G_filled[:, t]  # (num_wells,)
            # Distance matrix (H*W, num_wells)
            diff = grid_pts[:, None, :] - coords[None, :, :]
            dist = np.sqrt(np.sum(diff**2, axis=-1))
            dist = np.maximum(dist, 1e-6)

            weights = 1.0 / (dist ** power)
            weights_sum = np.sum(weights, axis=1, keepdims=True)
            idw_flat = np.sum(weights * obs_vals[None, :], axis=1) / weights_sum.squeeze(-1)

            G_spatial[t] = idw_flat.reshape(H, W)

        return G_spatial

    def lat_lon_to_grid_index(self, lat: float, lon: float) -> Tuple[int, int]:
        """
        Maps (lat, lon) query point to 2D grid (row, col) within region bounds [min_lon, min_lat, max_lon, max_lat].
        """
        meta = self.provider.get_grid_metadata()
        min_lon, min_lat, max_lon, max_lat = meta["bounds"]
        H, W = meta["grid_shape"]

        norm_x = (lon - min_lon) / (max_lon - min_lon + 1e-8)
        norm_y = (max_lat - lat) / (max_lat - min_lat + 1e-8)

        col = int(np.clip(round(norm_x * (W - 1)), 0, W - 1))
        row = int(np.clip(round(norm_y * (H - 1)), 0, H - 1))
        return row, col

    def grid_index_to_lat_lon(self, row: int, col: int) -> Tuple[float, float]:
        """
        Maps 2D grid (row, col) back to (lat, lon) within region bounds.
        """
        meta = self.provider.get_grid_metadata()
        min_lon, min_lat, max_lon, max_lat = meta["bounds"]
        H, W = meta["grid_shape"]

        lon = min_lon + (col / max(1, W - 1)) * (max_lon - min_lon)
        lat = max_lat - (row / max(1, H - 1)) * (max_lat - min_lat)
        return float(lat), float(lon)
