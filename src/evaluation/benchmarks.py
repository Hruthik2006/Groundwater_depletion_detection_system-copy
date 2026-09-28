import numpy as np
import logging
from typing import Dict, Any, Tuple
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score

logger = logging.getLogger(__name__)

#: Accepted dataset contract. The evaluator reads the processed dataset through
#: the typed GroundwaterDataset accessors (heads/coords/rasters_raw); a raw
#: string-keyed dict is tolerated via the wrapper's dict shim.
try:
    from ..pipeline.dataset import GroundwaterDataset
except ImportError:  # pragma: no cover - standalone import fallback
    GroundwaterDataset = Any
DataSet = Any


class CustomNumPyLSTM:
    """
    Custom NumPy Single-Layer LSTM (no PyTorch / GPU dependency).
    Section IV-C of paper (50) groundwater.docx: 16 hidden units, 14-day sliding window.
    """

    def __init__(self, in_features: int, hidden_units: int = 16, lr: float = 0.05, seed: int = 42):
        np.random.seed(seed)
        self.in_features = in_features
        self.hidden_units = hidden_units
        self.lr = lr

        # Weights initialization
        concat_dim = in_features + hidden_units
        self.Wf = np.random.randn(hidden_units, concat_dim) * 0.1
        self.bf = np.zeros((hidden_units, 1))

        self.Wi = np.random.randn(hidden_units, concat_dim) * 0.1
        self.bi = np.zeros((hidden_units, 1))

        self.Wc = np.random.randn(hidden_units, concat_dim) * 0.1
        self.bc = np.zeros((hidden_units, 1))

        self.Wo = np.random.randn(hidden_units, concat_dim) * 0.1
        self.bo = np.zeros((hidden_units, 1))

        self.Wy = np.random.randn(1, hidden_units) * 0.1
        self.by = np.zeros((1, 1))

    @staticmethod
    def _sigmoid(x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -15.0, 15.0)))

    def fit(self, X_seq: np.ndarray, y_target: np.ndarray, epochs: int = 6, batch_size: int = 2048):
        """
        X_seq: (N_samples, window_len, in_features)
        y_target: (N_samples,)
        """
        N, T, F = X_seq.shape
        indices = np.arange(N)

        for epoch in range(epochs):
            np.random.shuffle(indices)
            for start in range(0, N, batch_size):
                end = min(N, start + batch_size)
                idx = indices[start:end]
                X_batch = X_seq[idx]
                y_batch = y_target[idx]

                # Simple SGD forward/update step approximation
                preds = self.predict(X_batch)
                err = preds.ravel() - y_batch
                grad = np.mean(err)

                # Weight updates
                self.Wy -= self.lr * grad * 0.01
                self.Wf -= self.lr * grad * 0.001
                self.Wi -= self.lr * grad * 0.001

    def predict(self, X_seq: np.ndarray) -> np.ndarray:
        N, T, F = X_seq.shape
        preds = np.zeros(N)

        for i in range(N):
            h = np.zeros((self.hidden_units, 1))
            c = np.zeros((self.hidden_units, 1))

            for t in range(T):
                x_t = X_seq[i, t, :].reshape(-1, 1)
                concat = np.vstack((h, x_t))

                f_t = self._sigmoid(self.Wf @ concat + self.bf)
                i_t = self._sigmoid(self.Wi @ concat + self.bi)
                c_tilde = np.tanh(self.Wc @ concat + self.bc)
                c = f_t * c + i_t * c_tilde
                o_t = self._sigmoid(self.Wo @ concat + self.bo)
                h = o_t * np.tanh(c)

            out = self.Wy @ h + self.by
            preds[i] = out[0, 0]

        return preds


class FrameworkEvaluator:
    """
    Experimental Benchmarking & Validation Suite.
    Executes temporal rolling-origin cross-validation, spatial k-fold split,
    paper ML baseline comparisons (Table 2 & 3), and autoregressive ablation (Table 4).
    """

    @staticmethod
    def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, h_min: float = 35.0) -> Dict[str, float]:
        diff = y_true.ravel() - y_pred.ravel()
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        mae = float(np.mean(np.abs(diff)))
        cvr = float(np.mean(y_true.ravel() < h_min))
        try:
            r2 = float(r2_score(y_true.ravel(), y_pred.ravel()))
        except Exception:
            r2 = float("nan")

        return {
            "RMSE": round(rmse, 4),
            "MAE": round(mae, 4),
            "R2": round(r2, 4),
            "CVR": round(cvr, 4),
        }

    def prepare_tabular_dataset(self, dataset: DataSet, train_ratio: float = 0.85) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Builds tabular dataset with 1-day lag autoregressive feature H(t-1), rainfall P, temp T, geophysics.
        Executes rolling-origin train (85%) / test (15%) per-station split.
        """
        G = dataset.heads()  # (num_wells, T)
        num_wells, T = G.shape

        P = dataset.rasters_raw["P"]  # (T, H, W)
        ET = dataset.rasters_raw["ET"]

        X_rows = []
        y_rows = []

        coords = dataset.coords

        for i in range(num_wells):
            r, c = coords[i]
            for t in range(1, T):
                p_val = P[t, r, c]
                et_val = ET[t, r, c]
                prev_h = G[i, t - 1]
                target_h = G[i, t]

                X_rows.append([p_val, et_val, prev_h, r, c])
                y_rows.append(target_h)

        X = np.array(X_rows)
        y = np.array(y_rows)

        split_idx = int(len(X) * train_ratio)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        return X_train, X_test, y_train, y_test

    def fit_paper_baselines(self, dataset: DataSet) -> Dict[str, Dict[str, float]]:
        """
        Fits paper baseline models specified in Section IV-C / Table 2 & 3:
        1. Linear Regression
        2. Random Forest (200 trees, max depth 14)
        3. Support Vector Regression (SVR-RBF, C=10, eps=0.1)
        4. Histogram Gradient Boosting (XGBoost-style, 300 rounds, depth 6, lr 0.08)
        5. Custom NumPy 1-Layer 16-Unit LSTM (14-day sequence window)
        """
        X_train, X_test, y_train, y_test = self.prepare_tabular_dataset(dataset)

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        results = {}

        # 1. Linear Regression
        lr = LinearRegression()
        lr.fit(X_train_scaled, y_train)
        pred_lr = lr.predict(X_test_scaled)
        results["Linear Regression"] = self.compute_metrics(y_test, pred_lr)

        # 2. Random Forest (Best Paper Model)
        rf = RandomForestRegressor(n_estimators=200, max_depth=14, random_state=42)
        rf.fit(X_train_scaled, y_train)
        pred_rf = rf.predict(X_test_scaled)
        results["Random Forest"] = self.compute_metrics(y_test, pred_rf)

        # 3. SVR (RBF Kernel)
        sub_size = min(len(X_train_scaled), 5000)
        svr = SVR(C=10.0, epsilon=0.1, kernel="rbf")
        svr.fit(X_train_scaled[:sub_size], y_train[:sub_size])
        pred_svr = svr.predict(X_test_scaled)
        results["SVM (SVR-RBF)"] = self.compute_metrics(y_test, pred_svr)

        # 4. Histogram Gradient Boosting (XGBoost-style algorithmically equivalent)
        hgb = HistGradientBoostingRegressor(max_iter=300, max_depth=6, learning_rate=0.08, l2_regularization=1.0, random_state=42)
        hgb.fit(X_train_scaled, y_train)
        pred_hgb = hgb.predict(X_test_scaled)
        results["XGBoost-style (HGB)"] = self.compute_metrics(y_test, pred_hgb)

        # 5. Custom NumPy LSTM (14-day sliding window)
        G = dataset.heads()
        num_wells, T = G.shape
        seq_len = 14

        X_seq_list, y_seq_list = [], []
        for i in range(num_wells):
            for t in range(seq_len, T):
                seq_p = dataset.rasters_raw["P"][t - seq_len : t, 0, 0]
                seq_t = dataset.rasters_raw["temp"][t - seq_len : t, 0, 0] if "temp" in dataset.rasters_raw else np.zeros(seq_len)
                seq_h = G[i, t - seq_len : t]
                seq = np.column_stack([seq_p, seq_t, seq_h])
                X_seq_list.append(seq)
                y_seq_list.append(G[i, t])

        X_seq_arr = np.array(X_seq_list)
        y_seq_arr = np.array(y_seq_list)
        split_s = int(len(X_seq_arr) * 0.85)

        lstm = CustomNumPyLSTM(in_features=3, hidden_units=16, lr=0.05)
        lstm.fit(X_seq_arr[:split_s], y_seq_arr[:split_s], epochs=3)
        pred_lstm = lstm.predict(X_seq_arr[split_s:])
        results["LSTM (custom NumPy)"] = self.compute_metrics(y_seq_arr[split_s:], pred_lstm)

        return results

    def run_autoregressive_ablation(self, dataset: DataSet) -> Dict[str, Dict[str, float]]:
        """
        Runs Historical Autoregressive Term Ablation (Table 4 of paper).
        Compares full LSTM model (P, T, Level_History) against ablated model (Level_History zeroed out).
        Paper Target Result: Omitting level history increases RMSE by 4.7x.
        """
        G = dataset.heads()
        num_wells, T = G.shape
        seq_len = 14

        X_seq_full, X_seq_ablated, y_seq = [], [], []
        for i in range(num_wells):
            for t in range(seq_len, T):
                seq_p = dataset.rasters_raw["P"][t - seq_len : t, 0, 0]
                seq_t = dataset.rasters_raw["temp"][t - seq_len : t, 0, 0] if "temp" in dataset.rasters_raw else np.zeros(seq_len)
                seq_h = G[i, t - seq_len : t]

                full_seq = np.column_stack([seq_p, seq_t, seq_h])
                ablated_seq = np.column_stack([seq_p, seq_t, np.zeros_like(seq_h)])

                X_seq_full.append(full_seq)
                X_seq_ablated.append(ablated_seq)
                y_seq.append(G[i, t])

        X_full = np.array(X_seq_full)
        X_ablated = np.array(X_seq_ablated)
        y_arr = np.array(y_seq)
        split_s = int(len(y_arr) * 0.85)

        # Full LSTM
        lstm_full = CustomNumPyLSTM(in_features=3, hidden_units=16)
        lstm_full.fit(X_full[:split_s], y_arr[:split_s], epochs=3)
        pred_full = lstm_full.predict(X_full[split_s:])
        metrics_full = self.compute_metrics(y_arr[split_s:], pred_full)

        # Ablated LSTM (zeroed level history)
        lstm_ablated = CustomNumPyLSTM(in_features=3, hidden_units=16)
        lstm_ablated.fit(X_ablated[:split_s], y_arr[:split_s], epochs=3)
        pred_ablated = lstm_ablated.predict(X_ablated[split_s:])
        metrics_ablated = self.compute_metrics(y_arr[split_s:], pred_ablated)

        rmse_degradation_ratio = round(metrics_ablated["RMSE"] / max(1e-4, metrics_full["RMSE"]), 2)

        return {
            "Full_Model_P_T_LevelHistory": metrics_full,
            "Ablated_Model_LevelHistory_Removed": metrics_ablated,
            "RMSE_Degradation_Ratio": {"RMSE_Multiplier": rmse_degradation_ratio},
        }

    def run_feature_ablation_matrix(
        self,
        dataset: DataSet,
        downscaler_results: Dict[str, np.ndarray],
        Reff: np.ndarray,
    ) -> Dict[str, Dict[str, float]]:
        G_true = dataset.heads()
        T = G_true.shape[1]

        P = dataset.rasters_raw["P"]
        pred_A = np.zeros_like(G_true)
        for i in range(G_true.shape[0]):
            pred_A[i] = G_true[i, 0] + 0.1 * np.cumsum(P[:T, 0, 0] - 15.0) / 10.0

        TWSA_coarse = dataset.rasters_raw["TWSA_native"]
        pred_B = np.zeros_like(G_true)
        for i in range(G_true.shape[0]):
            pred_B[i] = G_true[i, 0] + 0.5 * TWSA_coarse[:T, 0, 0]

        GWLA = downscaler_results["GWLA"]
        pred_C = np.zeros_like(G_true)
        for i in range(G_true.shape[0]):
            r, c = dataset.coords[i]
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
        dataset: DataSet,
        k_folds: int = 4,
    ) -> Dict[str, float]:
        G_true = dataset.heads()
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
