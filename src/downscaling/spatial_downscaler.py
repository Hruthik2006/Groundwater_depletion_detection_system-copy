import numpy as np
import logging
from typing import Dict, Any
from sklearn.ensemble import RandomForestRegressor

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

logger = logging.getLogger(__name__)


class SpatialDownscaler:
    """
    Multi-Phase GRACE Spatial Downscaling Engine.
    Executes ensemble regression, regional scale-preservation mass conservation,
    deep storage isolation, and hydraulic head anomaly conversion.
    """

    def __init__(self, model_type: str = "rf", n_estimators: int = 100):
        self.model_type = model_type.lower()
        self.n_estimators = n_estimators
        
        if self.model_type == "xgb" and HAS_XGB:
            self.model = xgb.XGBRegressor(n_estimators=n_estimators, max_depth=6, random_state=42)
        else:
            if self.model_type == "xgb" and not HAS_XGB:
                logger.warning("XGBoost not installed; defaulting to RandomForestRegressor.")
            self.model = RandomForestRegressor(n_estimators=n_estimators, max_depth=8, random_state=42)

    def fit_and_downscale(
        self,
        rasters: Dict[str, np.ndarray],
        geophysics: Dict[str, np.ndarray],
        mascon_grid_shape: tuple = (2, 2),
    ) -> Dict[str, np.ndarray]:
        """
        Executes Downscaling Phases 1 through 4:
        Phase 1: Ensemble spatial regression
        Phase 2: Scale preservation mass conservation correction
        Phase 3: Deep storage isolation (GWSA = TWSA_scaled - SMSA - SWEA - CWSA)
        Phase 4: Groundwater Level Anomaly (GWLA = GWSA / Sy)
        """
        P = rasters["P"]        # (T, H, W)
        ET = rasters["ET"]      # (T, H, W)
        SMSA = rasters["SMSA"]  # (T, H, W)
        SWEA = rasters["SWEA"]  # (T, H, W)
        CWSA = rasters["CWSA"]  # (T, H, W)
        TWSA_native = rasters["TWSA_native"]  # (T, McH, McW)
        Sy = geophysics["Sy"]   # (H, W)

        T, H, W = P.shape
        mc_H, mc_W = mascon_grid_shape
        scale_h = H // mc_H
        scale_w = W // mc_W

        # Phase 1: Aggregate fine predictor features to coarse mascon scale to train regressor
        X_train_list = []
        y_train_list = []

        for t_idx in range(T):
            for mh in range(mc_H):
                for mw in range(mc_W):
                    p_sub = np.mean(P[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w])
                    et_sub = np.mean(ET[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w])
                    sm_sub = np.mean(SMSA[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w])
                    sw_sub = np.mean(SWEA[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w])
                    cw_sub = np.mean(CWSA[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w])

                    X_train_list.append([p_sub, et_sub, sm_sub, sw_sub, cw_sub])
                    y_train_list.append(TWSA_native[t_idx, mh, mw])

        X_train = np.array(X_train_list)
        y_train = np.array(y_train_list)

        # Fit model M_spatial
        self.model.fit(X_train, y_train)

        # Predict raw high-resolution TWSA_down (T, H, W)
        TWSA_down = np.zeros((T, H, W))
        for t_idx in range(T):
            X_fine = np.column_stack([
                P[t_idx].ravel(),
                ET[t_idx].ravel(),
                SMSA[t_idx].ravel(),
                SWEA[t_idx].ravel(),
                CWSA[t_idx].ravel(),
            ])
            pred_flat = self.model.predict(X_fine)
            TWSA_down[t_idx] = pred_flat.reshape(H, W)

        # Phase 2: Enforce regional mass conservation scale preservation
        TWSA_scaled = np.zeros((T, H, W))
        for t_idx in range(T):
            for mh in range(mc_H):
                for mw in range(mc_W):
                    sub_down = TWSA_down[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w]
                    mean_down = np.mean(sub_down)
                    target_native = TWSA_native[t_idx, mh, mw]

                    scaling_factor = target_native / (mean_down + 1e-8) if abs(mean_down) > 1e-6 else 1.0
                    TWSA_scaled[t_idx, mh*scale_h:(mh+1)*scale_h, mw*scale_w:(mw+1)*scale_w] = sub_down * scaling_factor

        # Phase 3: Deep Storage Isolation (GWSA = TWSA_scaled - SMSA - SWEA - CWSA)
        GWSA = TWSA_scaled - SMSA - SWEA - CWSA  # Equivalent water height anomaly (cm)

        # Phase 4: Hydraulic Head Anomaly (GWLA in meters)
        # GWSA (cm) -> GWLA (m) using Sy
        GWLA = (GWSA / 100.0) / np.maximum(Sy[None, :, :], 0.01)

        return {
            "TWSA_down": TWSA_down,
            "TWSA_scaled": TWSA_scaled,
            "GWSA": GWSA,
            "GWLA": GWLA,
        }
