from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
import numpy as np


class BaseDataProvider(ABC):
    """
    Abstract base data provider interface for hydroclimatic remote sensing,
    satellite gravimetry, piezometer measurements, and static geophysics.
    """

    @abstractmethod
    def get_grid_metadata(self) -> Dict[str, Any]:
        """
        Returns grid spatial and temporal metadata:
        - crs: EPSG:4326
        - resolution_km: 4.0
        - grid_shape: (height, width)
        - mascon_res_km: 300.0
        """
        pass

    @abstractmethod
    def fetch_hydroclimate_rasters(self, timesteps: int) -> Dict[str, np.ndarray]:
        """
        Fetches multi-dimensional hydroclimatic raster tensors of shape (T, H, W):
        - P: Precipitation (cm)
        - ET: Evapotranspiration (cm)
        - SMSA: Soil Moisture Anomaly (cm)
        - SWEA: Snow Water Equivalent Anomaly (cm)
        - CWSA: Canopy Water Storage Anomaly (cm)
        - Qs: Surface Runoff Anomaly (cm)
        - TWSA_native: Coarse GRACE Mascon TWSA (cm) mapped to coarse cells (T, H_coarse, W_coarse)
        """
        pass

    @abstractmethod
    def fetch_piezometer_observations(self, num_wells: int, timesteps: int) -> Dict[str, Any]:
        """
        Fetches piezometer monitoring well network observations:
        - coords: (num_wells, 2) array of (lat, lon) or (row, col)
        - G: (num_wells, T) array of hydraulic head levels (meters)
        - missing_mask: boolean mask indicating missing observations needing spline fill
        """
        pass

    @abstractmethod
    def fetch_static_geophysics(self) -> Dict[str, np.ndarray]:
        """
        Fetches static 2D aquifer properties (H, W):
        - Sy: Specific yield (dimensionless, e.g. 0.05 - 0.25)
        - K: Hydraulic conductivity (m/day, e.g. 1.0 - 50.0)
        - z_bedrock: Aquifer bedrock elevation / depth (meters)
        """
        pass
