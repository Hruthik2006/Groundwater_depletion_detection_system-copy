import numpy as np
from typing import Dict, Any
from .base_provider import BaseDataProvider

REGION_PRESETS = {
    "illinois": {"name": "Illinois Glacial Aquifer System (USA)", "bounds": [-89.5, 39.5, -87.5, 41.5]},
    "north_german": {"name": "North German Basin (Europe)", "bounds": [9.0, 52.0, 13.0, 54.0]},
    "high_plains": {"name": "High Plains / Ogallala Aquifer (USA)", "bounds": [-102.0, 36.0, -98.0, 39.0]},
    "ganges": {"name": "Indo-Gangetic Aquifer Basin (India)", "bounds": [77.0, 25.0, 81.0, 28.0]},
}


class SyntheticDataProvider(BaseDataProvider):
    """
    Synthetic Hydroclimatic Data Generator reproducing realistic physical correlations,
    seasonal hydrological cycles, and aquifer dynamics for benchmarking and offline testing.
    """

    def __init__(
        self,
        grid_shape: tuple = (16, 16),
        mascon_grid_shape: tuple = (2, 2),
        region_key: str = "illinois",
        bounds: list = None,
        seed: int = 42,
    ):
        self.height, self.width = grid_shape
        self.mc_height, self.mc_width = mascon_grid_shape
        self.seed = seed
        
        self.region_key = region_key.lower() if region_key in REGION_PRESETS else "custom"
        if bounds:
            self.bounds = bounds
            self.region_name = "Custom Location Bounding Box"
        elif self.region_key in REGION_PRESETS:
            self.bounds = REGION_PRESETS[self.region_key]["bounds"]
            self.region_name = REGION_PRESETS[self.region_key]["name"]
        else:
            self.bounds = [-89.5, 39.5, -87.5, 41.5]
            self.region_name = "Illinois Glacial Aquifer System (USA)"

        np.random.seed(seed)

    def get_grid_metadata(self) -> Dict[str, Any]:
        return {
            "crs": "EPSG:4326",
            "resolution_km": 4.0,
            "grid_shape": (self.height, self.width),
            "mascon_grid_shape": (self.mc_height, self.mc_width),
            "region_key": self.region_key,
            "region_name": self.region_name,
            "bounds": self.bounds,  # [min_lon, min_lat, max_lon, max_lat]
        }

    def fetch_hydroclimate_rasters(self, timesteps: int = 36) -> Dict[str, np.ndarray]:
        np.random.seed(self.seed)
        t = np.arange(timesteps)
        H, W = self.height, self.width

        # Base seasonal atmospheric forcing
        seasonal = 15.0 + 10.0 * np.sin(2 * np.pi * t / 12.0)
        noise = np.random.gamma(shape=2.0, scale=1.5, size=(timesteps, H, W))
        P = np.zeros((timesteps, H, W))
        for i in range(timesteps):
            P[i] = seasonal[i] + noise[i]

        # Evapotranspiration (ET) lagging precipitation
        et_seasonal = 8.0 + 6.0 * np.sin(2 * np.pi * (t - 1) / 12.0)
        ET = np.zeros((timesteps, H, W))
        for i in range(timesteps):
            ET[i] = et_seasonal[i] + 0.3 * noise[i]

        # Shallow storage components anomalies (cm)
        SMSA = 2.0 * np.sin(2 * np.pi * (t - 2) / 12.0)[:, None, None] + np.random.normal(0, 0.5, (timesteps, H, W))
        SWEA = np.maximum(0, 1.5 * np.cos(2 * np.pi * t / 12.0))[:, None, None] + np.random.normal(0, 0.2, (timesteps, H, W))
        CWSA = 0.5 * np.sin(2 * np.pi * t / 12.0)[:, None, None] + np.random.normal(0, 0.1, (timesteps, H, W))
        Qs = 1.0 * np.maximum(0, P - ET) / 10.0

        # Coarse TWSA native (2x2 mascons covering the fine grid)
        # Aggregate fine net accumulation to mascon cells
        fine_net = P - ET - Qs
        scale_h = H // self.mc_height
        scale_w = W // self.mc_width
        
        TWSA_coarse = np.zeros((timesteps, self.mc_height, self.mc_width))
        for mh in range(self.mc_height):
            for mw in range(self.mc_width):
                sub_block = fine_net[:, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w]
                TWSA_coarse[:, mh, mw] = np.cumsum(np.mean(sub_block, axis=(1, 2)) - 5.0) / 2.0

        rasters = {
            "P": P,
            "ET": ET,
            "SMSA": SMSA,
            "SWEA": SWEA,
            "CWSA": CWSA,
            "Qs": Qs,
            "TWSA_native": TWSA_coarse,
        }
        # Provenance for status/report: every variable here is synthetic.
        self.variable_sources = {k: "synthetic" for k in rasters}
        return rasters

    def fetch_piezometer_observations(self, num_wells: int = 16, timesteps: int = 36) -> Dict[str, Any]:
        np.random.seed(self.seed + 1)
        H, W = self.height, self.width
        
        # Grid coordinates for monitoring wells
        well_rows = np.random.randint(0, H, size=num_wells)
        well_cols = np.random.randint(0, W, size=num_wells)
        coords = np.column_stack([well_rows, well_cols])

        t = np.arange(timesteps)
        G = np.zeros((num_wells, timesteps))
        for i in range(num_wells):
            base_head = 45.0 + (well_rows[i] + well_cols[i]) * 0.5
            seasonal_trend = 3.0 * np.sin(2 * np.pi * (t - 3) / 12.0) - 0.05 * t
            noise = np.random.normal(0, 0.3, timesteps)
            G[i] = base_head + seasonal_trend + noise

        # Inject 10% missing observation entries to test spline imputation
        missing_mask = np.random.rand(num_wells, timesteps) < 0.10
        G_obs = G.copy()
        G_obs[missing_mask] = np.nan

        return {
            "coords": coords,
            "G": G_obs,
            "G_true": G,
            "missing_mask": missing_mask,
        }

    def fetch_static_geophysics(self) -> Dict[str, np.ndarray]:
        np.random.seed(self.seed + 2)
        H, W = self.height, self.width
        
        y, x = np.ogrid[:H, :W]

        # SoilGrids Texture (Clay, Sand, Silt fractions in %)
        clay = np.clip(25.0 + 15.0 * np.sin(np.pi * y / H) + np.random.normal(0, 1.5, (H, W)), 5.0, 60.0)
        sand = np.clip(45.0 + 20.0 * np.cos(np.pi * x / W) + np.random.normal(0, 2.0, (H, W)), 10.0, 80.0)
        silt = np.maximum(0.0, 100.0 - clay - sand)

        # Pedotransfer Function (Rosetta / Wösten / Marçais et al.) for Specific Yield Sy
        theta_s = 0.427 - 0.001 * clay + 0.003 * sand
        theta_fc = 0.046 + 0.0025 * clay + 0.0005 * silt
        Sy = np.clip(theta_s - theta_fc, 0.02, 0.35)
        
        # Hydraulic conductivity K (m/day): 5.0 to 30.0
        K = 15.0 + 10.0 * np.cos(np.pi * x / W) + np.random.normal(0, 1.0, (H, W))
        K = np.clip(K, 1.0, 50.0)

        # Shangguan et al. Depth to Bedrock DTB (m)
        z_bedrock = np.clip(20.0 + 15.0 * (y / H) + np.random.normal(0, 1.5, (H, W)), 2.0, 100.0)
        DTB = z_bedrock

        # EarthEnv Topography suite: Elevation Z (m), Terrain Roughness Index (TRI), Topographic Position Index (TPI)
        elevation = 200.0 + 80.0 * np.sin(np.pi * x / W) + 40.0 * np.cos(np.pi * y / H)
        TRI = np.abs(np.gradient(elevation)[0]) + np.abs(np.gradient(elevation)[1])
        TPI = elevation - (elevation.mean())

        return {
            "Sy": Sy,
            "K": K,
            "z_bedrock": z_bedrock,
            "DTB": DTB,
            "clay": clay,
            "sand": sand,
            "silt": silt,
            "elevation": elevation,
            "TRI": TRI,
            "TPI": TPI,
        }
