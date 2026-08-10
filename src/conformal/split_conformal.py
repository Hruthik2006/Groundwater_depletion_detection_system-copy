import numpy as np
from typing import Tuple, Dict, Any


class SplitConformalPredictor:
    """
    Split Conformal Prediction Engine for Calibration-Free UQ.
    Computes distribution-free finite-sample empirical error margins q_{1-alpha}
    to reformulate stochastic chance constraints into tightened deterministic bounds.
    """

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha  # Target violation probability (e.g. 0.05 for 95% safety level)
        self.q_hat = 0.0
        self.residuals = np.array([])
        self.is_calibrated = False

    def calibrate(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """
        Calibrates predictor using residuals on calibration dataset D_calib.
        y_true: (N,) or (N, H, W) array of ground truth states
        y_pred: array of nominal neural surrogate forecasts
        """
        self.residuals = np.abs(y_true.ravel() - y_pred.ravel())
        N = len(self.residuals)

        if N == 0:
            self.q_hat = 0.0
            self.is_calibrated = True
            return 0.0

        # Empirical quantile formula: ceil((N + 1) * (1 - alpha)) / N
        quantile_level = np.ceil((N + 1) * (1.0 - self.alpha)) / N
        quantile_level = np.clip(quantile_level, 0.0, 1.0)

        self.q_hat = float(np.quantile(self.residuals, quantile_level))
        self.is_calibrated = True
        return self.q_hat

    def get_safety_threshold(self, h_min: float) -> float:
        """
        Returns tightened deterministic head threshold: h_min + q_{1-alpha}
        Ensures P(G >= h_min) >= 1 - alpha.
        """
        return h_min + self.q_hat

    def predict_interval(self, y_pred: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns (lower_bound, upper_bound) interval around nominal predictions.
        """
        lower = y_pred - self.q_hat
        upper = y_pred + self.q_hat
        return lower, upper

    def evaluate_coverage(self, y_test: np.ndarray, y_pred_test: np.ndarray) -> Dict[str, float]:
        """
        Evaluates empirical coverage probability on unseen test dataset.
        Target: >= 1 - alpha (e.g. 95%).
        """
        lower, upper = self.predict_interval(y_pred_test)
        coverage = np.mean((y_test >= lower) & (y_test <= upper))
        cvr = np.mean(y_test < lower)  # Constraint Violation Rate

        return {
            "target_confidence": 1.0 - self.alpha,
            "empirical_coverage": float(coverage),
            "constraint_violation_rate": float(cvr),
            "q_hat": float(self.q_hat),
        }
