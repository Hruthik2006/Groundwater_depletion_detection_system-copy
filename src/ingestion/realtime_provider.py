import os
import numpy as np
import logging
from typing import Dict, Any
from .base_provider import BaseDataProvider
from .synthetic_provider import SyntheticDataProvider, REGION_PRESETS


def _resolve_bounds(region_key: str, bounds: list) -> list:
    """
    Returns usable [min_lon, min_lat, max_lon, max_lat] bounds for a region.

    The data loader passes bounds=None for preset regions. The synthetic
    provider resolves those from REGION_PRESETS itself, but this provider
    previously kept None — and the GEE sampler's first step unpacks the
    bounds, so every preset region crashed with "cannot unpack
    non-iterable NoneType object" and silently fell back to synthetic
    rasters. Resolve the same way the synthetic provider does.
    """
    if bounds:
        return bounds
    key = region_key.lower() if region_key else "illinois"
    if key in REGION_PRESETS:
        return list(REGION_PRESETS[key]["bounds"])
    return [-89.5, 39.5, -87.5, 41.5]

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


class RealtimeEarthEngineDataProvider(BaseDataProvider):
    """
    Realtime Geospatial Data Provider interfacing with Google Earth Engine (ee)
    and NASA EarthData protocols for operational remote sensing ingestion.

    Endpoints:
    - CHIRPS: UCSB-CHG/CHIRPS/PENTAD (Precipitation P)
    - MODIS: MODIS/061/MOD16A2 (Evapotranspiration ET)
    - GLDAS: NASA/GLDAS/V021/NOAH/G025/T3H, monthly composites (Soil Moisture, SWE, Canopy Storage) — the T3M monthly asset is not ingested by Earth Engine
    - CSR GRACE: CSR RL06.2 Mascon Solution grids

    Honest seam: the raster channel attempts live GEE sampling, everything else
    (piezometer observations and static geophysics) is served by the calibrated
    synthetic fallback. ``capabilities`` and ``is_synthetic`` reflect whichever
    of the two the active build actually used.
    """

    # Raster flips to live only when GEE initializes AND a fetch succeeds;
    # hydromet/static are always replica channels on this adapter.
    capabilities: Dict[str, str] = {
        "raster": "synthetic_standby",
        "hydromet": "synthetic_standby",
        "static": "synthetic_standby",
    }
    is_synthetic: bool = True

    def __init__(
        self,
        ee_project_id: str = None,
        grid_shape: tuple = (16, 16),
        mascon_grid_shape: tuple = (2, 2),
        region_key: str = "illinois",
        bounds: list = None,
        seed: int = 42,
        fallback_if_unauthenticated: bool = True,
    ):
        self.ee_project_id = ee_project_id or os.getenv("GEE_PROJECT_ID")
        self.grid_shape = grid_shape
        self.mascon_grid_shape = mascon_grid_shape
        self.region_key = region_key
        # NOTE: the fallback provider receives the raw `bounds` argument (it
        # resolves presets itself, and passing resolved bounds would make it
        # mislabel the region as a custom bounding box).
        self.bounds = _resolve_bounds(region_key, bounds)
        self.seed = seed
        self.fallback_if_unauthenticated = fallback_if_unauthenticated
        self.ee_initialized = False
        # Live ingestion progress, surfaced via /api/v1/status so the
        # loading UI can show what the sampler is doing instead of a
        # static spinner text (a full build takes minutes).
        self.progress = {"stage": "idle", "message": "", "percent": None}
        self._progress_done = 0
        self._progress_total = 0

        self._fallback_provider = SyntheticDataProvider(
            grid_shape=grid_shape,
            mascon_grid_shape=mascon_grid_shape,
            region_key=region_key,
            bounds=bounds,
            seed=seed,
        )

        # Attempt GEE Initialization
        try:
            import ee
            if self.ee_project_id:
                ee.Initialize(project=self.ee_project_id)
            else:
                ee.Initialize()
            self.ee_initialized = True
            logger.info(f"Google Earth Engine API successfully initialized (Project: {self.ee_project_id or 'default'}).")
        except Exception as e:
            logger.warning(
                f"Google Earth Engine API initialization skipped/failed ({e}). "
                "Operating in Realtime Standby mode with synthetic fallback."
            )

    def set_region(self, region_key: str = "illinois", bounds: list = None):
        """Dynamically update geographic study region preset or custom bounds."""
        self.region_key = region_key
        self.bounds = _resolve_bounds(region_key, bounds)
        self._fallback_provider = SyntheticDataProvider(
            grid_shape=self.grid_shape,
            mascon_grid_shape=self.mascon_grid_shape,
            region_key=region_key,
            bounds=bounds,
            seed=self.seed,
        )

    def get_grid_metadata(self) -> Dict[str, Any]:
        meta = self._fallback_provider.get_grid_metadata()
        meta["provider_mode"] = "realtime" if self.ee_initialized else "realtime_standby"
        meta["ee_initialized"] = self.ee_initialized
        meta["serves"] = self.serves()
        return meta

    def _set_progress(self, stage: str, message: str):
        percent = None
        if stage == "done":
            percent = 100
        elif stage == "sampling" and self._progress_total > 0:
            percent = int(round(100.0 * self._progress_done / self._progress_total))
        self.progress = {"stage": stage, "message": message, "percent": percent}

    def fetch_hydroclimate_rasters(self, timesteps: int = 12) -> Dict[str, np.ndarray]:
        self._progress_done = 0
        self._progress_total = 0
        if not self.ee_initialized:
            self._set_progress("fallback", "Earth Engine not connected \u2014 using calibrated benchmark data")
            return self._fallback_provider.fetch_hydroclimate_rasters(timesteps)

        self._set_progress("connecting", "Connecting to Earth Engine\u2026")

        logger.info(f"Ingesting live remote sensing rasters via GEE endpoints for region '{self.region_key}' ({self.bounds})...")
        fallback_rasters = self._fallback_provider.fetch_hydroclimate_rasters(timesteps)

        try:
            windows = self._gee_month_windows(timesteps)
        except Exception as e:
            logger.warning(f"Live GEE raster sampling unavailable ({e}). Falling back to calibrated provider rasters.")
            self._set_progress("fallback", "Live sampling unavailable \u2014 using calibrated benchmark data")
            return fallback_rasters

        self._set_progress("windows", f"Live GEE monthly windows: {windows[0][0]} \u2192 {windows[-1][1]}")

        # Per-variable sampling: one dead asset or band must not take the
        # whole live ingestion down with it (the GLDAS monthly asset
        # 'NASA/GLDAS/V021/NOAH/G025/T3M' does not exist in Earth Engine —
        # only the 3-hourly T3H product is ingested — and its failure
        # previously discarded two variables that had sampled fine).
        # GLDAS variables are monthly means of the 3-hourly product;
        # CHIRPS pentads and MODIS 8-day ET are summed to monthly totals.
        gldas = "NASA/GLDAS/V021/NOAH/G025/T3H"
        plan = [
            ("P", "UCSB-CHG/CHIRPS/PENTAD", "precipitation", "sum"),
            ("ET", "MODIS/061/MOD16A2", "ET", "sum"),
            ("SMSA", gldas, "SoilMoi0_10cm_inst", "mean"),
            ("SWEA", gldas, "SWE_inst", "mean"),
            ("CWSA", gldas, "CanopInt_inst", "mean"),
            ("Qs", gldas, "Qs_acc", "mean"),
        ]
        labels = {
            "P": "Precipitation (CHIRPS)",
            "ET": "Evapotranspiration (MODIS)",
            "SMSA": "Soil moisture (GLDAS)",
            "SWEA": "Snow water equivalent (GLDAS)",
            "CWSA": "Canopy water storage (GLDAS)",
            "Qs": "Surface runoff (GLDAS)",
        }
        self._progress_total = len(plan) * len(windows)
        rasters: Dict[str, np.ndarray] = {}
        live_vars = []
        fallback_vars = []
        for vi, (name, cid, band, agg) in enumerate(plan):
            base = vi * len(windows)
            try:
                arr = self._sample_gee_collection(
                    cid, band, windows, agg,
                    label=labels[name], progress_base=base,
                )
                if not np.any(arr):
                    raise ValueError("sampled raster is all zeros (band/property mismatch?)")
                rasters[name] = arr
                live_vars.append(name)
            except Exception as e:
                logger.warning(
                    f"Live GEE sampling for variable {name} unavailable ({e}); "
                    "using the calibrated fallback raster for this variable only."
                )
                rasters[name] = fallback_rasters[name]
                fallback_vars.append(name)
                self._progress_done = base + len(windows)
                self._set_progress("sampling", f"{labels[name]} unavailable \u2014 using calibrated data for this variable")

        # GRACE mascon grids are not sampled from Earth Engine in this
        # provider; TWSA_native stays on the calibrated raster (as before).
        rasters["TWSA_native"] = fallback_rasters["TWSA_native"]

        means = ", ".join(f"{k}={float(np.mean(v)):.3f}" for k, v in rasters.items())
        logger.info(f"Live GEE ingestion finished. Live variables: {live_vars or 'none'}. Raster means: {means}")
        done_msg = f"Live GEE ingestion finished \u2014 {len(live_vars)} of {len(plan)} variables live"
        if fallback_vars:
            done_msg += f"; calibrated fallback: {', '.join(fallback_vars)}"
        self._set_progress("done", done_msg)
        return rasters

    def _gee_month_windows(self, timesteps: int):
        """
        Shared monthly windows (oldest → newest) for all live collections,
        anchored to the SLOWEST collection's latest image so every window
        has data in every collection (GLDAS lags ~1.5 months, CHIRPS and
        MODIS much less). Returns a list of ('YYYY-MM-DD', 'YYYY-MM-DD').
        """
        import datetime

        import ee

        latest_ms = None
        for cid in ("UCSB-CHG/CHIRPS/PENTAD", "MODIS/061/MOD16A2", "NASA/GLDAS/V021/NOAH/G025/T3H"):
            first = (ee.ImageCollection(cid)
                     .sort("system:time_start", False)
                     .first())
            t = first.get("system:time_start").getInfo()
            if t is None:
                raise ValueError(f"Collection {cid} returned no images")
            latest_ms = t if latest_ms is None else min(latest_ms, t)

        anchor = datetime.datetime.utcfromtimestamp(latest_ms / 1000.0).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        def add_months(d, n):
            m = d.month - 1 + n
            return d.replace(year=d.year + m // 12, month=m % 12 + 1)

        windows = []
        for k in range(timesteps):
            start = add_months(anchor, k - (timesteps - 1))
            end = add_months(start, 1)
            windows.append((start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
        logger.info(f"Live GEE monthly windows: {windows[0][0]} → {windows[-1][1]} (anchored to slowest collection).")
        return windows

    def _sample_gee_collection(self, collection_id: str, band_name: str, windows, agg: str = "mean", label: str = "GEE data", progress_base: int = 0) -> np.ndarray:
        import ee

        if not self.bounds:
            raise ValueError(
                f"No bounds resolved for region '{self.region_key}'; cannot sample GEE collections."
            )
        min_lon, min_lat, max_lon, max_lat = self.bounds
        region = ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)

        base = (ee.ImageCollection(collection_id)
                .filterBounds(region)
                .select(band_name))

        H, W = self.grid_shape
        # Sample by reducing each image over the app's own 16x16 cell grid
        # (one reduceRegions call per image). sampleRectangle was tried
        # first and is a dead end here: at native resolution it exceeds
        # Earth Engine's 262144-pixel limit (MODIS over a region bbox =
        # 939463 px), and reprojecting before sampling made EE evaluate
        # the sample at a wildly wrong scale (2.4e12 px). Cell-mean
        # reduction has no such limit and matches the grid the rest of
        # the pipeline uses (row 0 = northernmost, as in latlon_to_grid).
        d_lon = (max_lon - min_lon) / W
        d_lat = (max_lat - min_lat) / H
        cells = []
        for r in range(H):
            cell_lat1 = max_lat - r * d_lat
            cell_lat0 = max_lat - (r + 1) * d_lat
            for c in range(W):
                cell_lon0 = min_lon + c * d_lon
                cell_lon1 = min_lon + (c + 1) * d_lon
                geom = ee.Geometry.Rectangle([cell_lon0, cell_lat0, cell_lon1, cell_lat1])
                cells.append(ee.Feature(geom, {"row": r, "col": c}))
        grid_fc = ee.FeatureCollection(cells)

        # Reduction scale (metres): roughly half a cell, clamped to a sane
        # range so both fine (500 m) and coarse (25 km) products reduce
        # without excessive pixel counts.
        mid_lat = np.radians((min_lat + max_lat) / 2.0)
        cell_m = max(
            (max_lon - min_lon) * 111320.0 * np.cos(mid_lat),
            (max_lat - min_lat) * 110540.0,
        ) / max(H, W)
        scale_m = float(np.clip(cell_m / 2.0, 1000.0, 30000.0))

        # One composite per shared month window: sub-monthly products
        # (CHIRPS pentads, MODIS 8-day, GLDAS 3-hourly) are aggregated to
        # the pipeline's monthly timestep — sum for accumulated fluxes
        # (precipitation, ET), mean for state/rate variables (GLDAS).
        rasters = []
        for wi, (start, end) in enumerate(windows):
            self._progress_done = progress_base + wi
            self._set_progress("sampling", f"Sampling {label} \u2014 month {wi + 1} of {len(windows)}")
            sub = base.filterDate(start, end)
            if sub.size().getInfo() == 0:
                rasters.append(np.zeros((H, W), dtype=np.float32))
                continue
            img = sub.sum() if agg == "sum" else sub.mean()
            reduced = img.reduceRegions(
                collection=grid_fc,
                reducer=ee.Reducer.mean(),
                scale=scale_m,
                tileScale=4,
            )
            data = reduced.getInfo()
            arr = np.zeros((H, W), dtype=np.float32)
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                v = props.get("mean")
                if v is not None:
                    arr[int(props["row"]), int(props["col"])] = float(v)
            rasters.append(arr)

        return np.array(rasters)

    def fetch_piezometer_observations(self, num_wells: int = 16, timesteps: int = 12) -> Dict[str, Any]:
        logger.warning(
            "Realtime provider has no live piezometer channel; serving synthetic fallback "
            "well observations (see provider serves.hydromet)."
        )
        return self._fallback_provider.fetch_piezometer_observations(num_wells, timesteps)

    def fetch_static_geophysics(self) -> Dict[str, np.ndarray]:
        logger.warning(
            "Realtime provider has no live static-geophysics channel; serving synthetic "
            "fallback properties (see provider serves.static)."
        )
        return self._fallback_provider.fetch_static_geophysics()
