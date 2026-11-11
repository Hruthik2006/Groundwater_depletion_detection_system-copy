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
    - GLDAS: NASA/GLDAS/V021/NOAH/G025/T3M (Soil Moisture, SWE, Canopy Storage)
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

    def fetch_hydroclimate_rasters(self, timesteps: int = 36) -> Dict[str, np.ndarray]:
        if self.ee_initialized:
            try:
                import ee
                logger.info(f"Ingesting live remote sensing rasters via GEE endpoints for region '{self.region_key}' ({self.bounds})...")
                
                # Live GEE Collection Sampling
                P = self._sample_gee_collection("UCSB-CHG/CHIRPS/PENTAD", "precipitation", timesteps)
                ET = self._sample_gee_collection("MODIS/061/MOD16A2", "ET", timesteps)
                SMSA = self._sample_gee_collection("NASA/GLDAS/V021/NOAH/G025/T3M", "SoilMoi0_10cm_tavg", timesteps)
                SWEA = self._sample_gee_collection("NASA/GLDAS/V021/NOAH/G025/T3M", "SWE_inst", timesteps)
                CWSA = self._sample_gee_collection("NASA/GLDAS/V021/NOAH/G025/T3M", "CanopInt_inst", timesteps)
                Qs = self._sample_gee_collection("NASA/GLDAS/V021/NOAH/G025/T3M", "Qs_acc", timesteps)

                fallback_rasters = self._fallback_provider.fetch_hydroclimate_rasters(timesteps)
                TWSA_native = fallback_rasters["TWSA_native"]

                logger.info("Successfully ingested live GEE satellite rasters!")
                return {
                    "P": P,
                    "ET": ET,
                    "SMSA": SMSA,
                    "SWEA": SWEA,
                    "CWSA": CWSA,
                    "Qs": Qs,
                    "TWSA_native": TWSA_native,
                }
            except Exception as e:
                logger.warning(f"Live GEE raster sampling encountered limitation ({e}). Falling back to calibrated provider rasters.")
                return self._fallback_provider.fetch_hydroclimate_rasters(timesteps)
        else:
            return self._fallback_provider.fetch_hydroclimate_rasters(timesteps)

    def _sample_gee_collection(self, collection_id: str, band_name: str, timesteps: int) -> np.ndarray:
        import ee
        from scipy.ndimage import zoom

        if not self.bounds:
            raise ValueError(
                f"No bounds resolved for region '{self.region_key}'; cannot sample GEE collections."
            )
        min_lon, min_lat, max_lon, max_lat = self.bounds
        region = ee.Geometry.BBox(min_lon, min_lat, max_lon, max_lat)

        col = (ee.ImageCollection(collection_id)
               .filterBounds(region)
               .select(band_name)
               .limit(timesteps))

        img_list = col.toList(timesteps)
        size = img_list.size().getInfo()
        if size == 0:
            raise ValueError(f"No images returned for collection {collection_id}")

        H, W = self.grid_shape
        rasters = []
        for i in range(min(size, timesteps)):
            img = ee.Image(img_list.get(i))
            rect = img.sampleRectangle(region=region, defaultValue=0.0)
            arr = np.array(rect.get(band_name).getInfo(), dtype=np.float32)

            if arr.shape != (H, W) and arr.size > 0:
                zoom_factors = (H / arr.shape[0], W / arr.shape[1])
                arr = zoom(arr, zoom_factors)
            elif arr.size == 0:
                arr = np.zeros((H, W))

            rasters.append(arr)

        while len(rasters) < timesteps:
            rasters.append(rasters[-1] if rasters else np.zeros((H, W)))

        return np.array(rasters[:timesteps])

    def fetch_piezometer_observations(self, num_wells: int = 16, timesteps: int = 36) -> Dict[str, Any]:
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
