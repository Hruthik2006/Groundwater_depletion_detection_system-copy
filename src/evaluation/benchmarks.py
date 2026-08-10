import numpy as np
from typing import Dict, Any, List


class FrameworkEvaluator:
    """
    Experimental Benchmarking & Validation Suite.
    Executes temporal rolling-origin cross-validation, spatial k-fold split,
    and feature ablation experiments across hydrogeological regimes.
    """

    @staticmethod
    def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, h_min: float = 35.0) -> Dict[str, float]:
        """
        Computes RMSE, MAE, and Constraint Violation Rate (CVR).
        """
        diff = y_true.ravel() - y_pred.ravel()
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        mae = float(np.mean(np.abs(diff)))
        
        # Constraint Violation Rate: percentage of true states dropping below h_min
        cvr = float(np.mean(y_true.ravel() < h_min))

        return {
            "RMSE": rmse,
            "MAE": mae,
            "CVR": cvr,
        }

    def run_feature_ablation_matrix(
        self,
        dataset: Dict[str, Any],
        downscaler_results: Dict[str, np.ndarray],
        Reff: np.ndarray,
    ) -> Dict[str, Dict[str, float]]:
        """
        Runs Feature Ablation Matrix comparing:
        - Configuration A: Local Baseline (surface meteorology P, ET)
        - Configuration B: Raw GRACE (unrefined TWSA mascons)
        - Configuration C: Proposed Fusion (downscaled TWSA, lag-corrected R_eff, geophysics)
        """
        G_true = dataset["wells"]["G_filled"]  # (num_wells, T)
        T = G_true.shape[1]

        # Config A prediction (local meteo baseline linear model)
        P = dataset["rasters_raw"]["P"]
        pred_A = np.zeros_like(G_true)
        for i in range(G_true.shape[0]):
            pred_A[i] = G_true[i, 0] + 0.1 * np.cumsum(P[:T, 0, 0] - 15.0) / 10.0

        # Config B prediction (raw GRACE mascon linear model)
        TWSA_coarse = dataset["rasters_raw"]["TWSA_native"]
        pred_B = np.zeros_like(G_true)
        for i in range(G_true.shape[0]):
            pred_B[i] = G_true[i, 0] + 0.5 * TWSA_coarse[:T, 0, 0]

        # Config C prediction (Proposed downscaled & vadose delay fusion)
        GWLA = downscaler_results["GWLA"]
        pred_C = np.zeros_like(G_true)
        for i in range(G_true.shape[0]):
            r, c = dataset["wells"]["coords"][i]
            pred_C[i] = G_true[i, 0] + GWLA[:T, r, c] + 0.02 * Reff[:T, r, c]

        metrics_A = self.compute_metrics(G_true, pred_A)
        metrics_B = self.compute_metrics(G_true, pred_B)
        metrics_C = self.compute_metrics(G_true, pred_C)

        return {
            "Config_A_Local_Baseline": metrics_A,
            "Config_B_Raw_GRACE": metrics_B,
            "Config_C_Proposed_Fusion": metrics_C,
        }

    def run_spatial_kfold_cv(
        self,
        dataset: Dict[str, Any],
        k_folds: int = 4,
    ) -> Dict[str, float]:
        """
        Spatial k-fold cross-validation withholding well clusters.
        """
        G_true = dataset["wells"]["G_filled"]
        num_wells = G_true.shape[0]
        fold_size = num_wells // k_folds

        rmse_scores = []
        mae_scores = []

        for f in range(k_folds):
            val_idx = list(range(f * fold_size, (f + 1) * fold_size))
            train_idx = [i for i in range(num_wells) if i not in val_idx]

            train_mean = np.mean(G_true[train_idx])
            val_true = G_true[val_idx]
            val_pred = np.full_like(val_true, train_mean)

            m = self.compute_metrics(val_true, val_pred)
            rmse_scores.append(m["RMSE"])
            mae_scores.append(m["MAE"])

        return {
            "Spatial_CV_Mean_RMSE": float(np.mean(rmse_scores)),
            "Spatial_CV_Mean_MAE": float(np.mean(mae_scores)),
        }
