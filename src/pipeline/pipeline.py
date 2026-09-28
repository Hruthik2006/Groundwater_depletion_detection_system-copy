import logging
import os
from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .config import Config, DEFAULT_CONFIG
from .dataset import GroundwaterDataset
from ..ingestion.data_loader import GroundwaterDataLoader
from ..downscaling.spatial_downscaler import SpatialDownscaler
from ..downscaling.vadose_delay import VadoseDelayEngine
from ..surrogates.gnn_lstm import GNNLSTMSurrogate
from ..conformal.split_conformal import SplitConformalPredictor
from ..control.scp_mpc import SCPChanceConstrainedMPC

logger = logging.getLogger(__name__)

_DEFAULT_CHECKPOINT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "models", "checkpoints", "gnn_lstm_best.pt")
)


class Pipeline:
    """
    The single orchestration seam for the groundwater framework.

    Building the dataset -- ingest -> spatial downscale -> vadose delay ->
    split-conformal calibration -- is one operation, `build()`. Every entry
    point that changes the data context (data mode switch, region switch,
    recalibration) funnels back through `build()`, so a surrogate calibration
    can never be silently skipped the way the old route-local copies did.

    Consumers read state from the exposed object graph:
      pipeline.dataset        -> GroundwaterDataset (typed accessors)
      pipeline.downscaling_res
      pipeline.Reff
      pipeline.surrogate / pipeline.conformal / pipeline.mpc / pipeline.data_loader
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or DEFAULT_CONFIG
        c = self.config

        self.data_loader = GroundwaterDataLoader(
            data_mode=c.data_mode,
            grid_shape=c.grid_shape,
            mascon_grid_shape=c.mascon_grid_shape,
            region_key=c.region_key,
            bounds=c.bounds,
            seed=c.seed,
        )
        self.downscaler = SpatialDownscaler(model_type="rf")
        self.vadose_engine = VadoseDelayEngine(alpha_lag=2.5, beta_lag=1.5)
        self.surrogate = GNNLSTMSurrogate(num_wells=c.num_wells)
        self.conformal = SplitConformalPredictor(alpha=c.alpha)
        self.mpc = SCPChanceConstrainedMPC(
            horizon=c.horizon,
            num_wells=c.num_wells,
            E_max=c.e_max,
            h_min=c.h_min,
            h_target=c.h_target,
            alpha=c.alpha,
            w_energy=c.gamma_pump,
            sigma_slack=c.sigma_slack,
            delta_0=c.delta_trust,
            max_scp_iters=c.max_scp_iters,
        )

        self.dataset: Optional[GroundwaterDataset] = None
        self.downscaling_res: Optional[Dict[str, np.ndarray]] = None
        self.Reff: Optional[np.ndarray] = None

        # Benchmark caches are invalidated by any build().
        self.baseline_cache: Optional[Dict[str, Any]] = None
        self.ablation_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ build
    def build(self, timesteps: Optional[int] = None, num_wells: Optional[int] = None) -> GroundwaterDataset:
        """
        Executes the full ingest -> downscale -> vadose -> conformal chain.
        Always recalibrates the conformal predictor against the current data.
        """
        c = self.config
        t_steps = timesteps or c.timesteps
        n_wells = num_wells or c.num_wells

        raw = self.data_loader.load_processed_dataset(timesteps=t_steps, num_wells=n_wells)
        self.dataset = GroundwaterDataset(raw, loader=self.data_loader)

        self._maybe_load_checkpoint()

        self.downscaling_res = self.downscaler.fit_and_downscale(
            self.dataset.rasters_raw,
            self.dataset.geophysics,
            mascon_grid_shape=self.dataset.mascon_grid_shape,
        )
        self.Reff = self.vadose_engine.compute_effective_recharge(
            self.dataset.rasters_raw["P"],
            self.dataset.rasters_raw["ET"],
            self.dataset.rasters_raw["Qs"],
            DTB=self.dataset.geophysics.get("DTB"),
            clay=self.dataset.geophysics.get("clay"),
        )

        self.calibrate_conformal_from_surrogate()

        # Stale benchmark results no longer apply to the newly built data.
        self.baseline_cache = None
        self.ablation_cache = None

        return self.dataset

    def _maybe_load_checkpoint(self):
        path = self.config.checkpoint_path or _DEFAULT_CHECKPOINT
        if not os.path.exists(path):
            logger.debug(f"No GNN-LSTM checkpoint at {path}; using randomly-initialized weights.")
            return
        try:
            import torch
            self.surrogate.load_state_dict(torch.load(path, map_location=torch.device("cpu")))
            print(f"[Pipeline] Loaded pre-trained GNN-LSTM weights from {path}")
        except Exception as ex:
            print(f"[Pipeline] Failed to load checkpoint weights from {path}: {ex}")

    def calibrate_conformal_from_surrogate(self) -> float:
        """Runs a real surrogate forward pass and calibrates the conformal margin."""
        import torch

        dataset = self.dataset
        y_true = dataset.heads()  # (num_wells, T)
        num_wells, T = y_true.shape

        seq_len = min(self.config.seq_len, T - 1)
        dyn_seq = dataset.dynamic_sequence(
            self.Reff,
            self.downscaling_res["GWLA"],
            seq_len,
            e_nominal=self.config.nominal_extraction,
        )
        static_t = torch.tensor(dataset.static_features(num_wells), dtype=torch.float32)
        adj = self.surrogate.compute_adjacency(dataset.coords)

        self.surrogate.eval()
        with torch.no_grad():
            preds = self.surrogate(dyn_seq, static_t, adj)[0].numpy().T  # (num_wells, seq_len)

        y_true_seq = y_true[:, 1:seq_len + 1]
        return self.conformal.calibrate(y_true_seq, preds)

    # --------------------------------------------------------------- context switches
    def set_data_mode(self, mode: str, timesteps: Optional[int] = None, num_wells: Optional[int] = None) -> GroundwaterDataset:
        self.data_loader.set_data_mode(mode)
        self.config = replace(self.config, data_mode=self.data_loader.data_mode)
        return self.build(timesteps=timesteps, num_wells=num_wells)

    def set_region(self, region_key: str = "illinois", bounds: list = None, timesteps: Optional[int] = None, num_wells: Optional[int] = None) -> GroundwaterDataset:
        self.data_loader.set_region(region_key=region_key, bounds=bounds)
        self.config = replace(self.config, region_key=region_key, bounds=bounds)
        return self.build(timesteps=timesteps, num_wells=num_wells)

    def ensure_region_for_coords(self, lat: float, lon: float, timesteps: Optional[int] = None, num_wells: Optional[int] = None) -> Tuple[str, str]:
        """
        Auto-switches region based on (lat, lon) if the point belongs to a
        different hydrogeological preset, then rebuilds the whole chain.
        Returns (current_region, previous_region).
        """
        target_region, custom_bounds = self.data_loader.detect_region_key(lat, lon)
        current_region = self.dataset.metadata.get("region_key") if self.dataset else None
        if target_region != current_region:
            logger.info(f"Auto-switching region from '{current_region}' to '{target_region}' for pinned coordinates ({lat}, {lon})")
            self.set_region(region_key=target_region, bounds=custom_bounds, timesteps=timesteps, num_wells=num_wells)
        return target_region, current_region or target_region

    # ------------------------------------------------------------ projection helpers
    def analytic_forecast(self, lat: float, lon: float, horizon: int = 12) -> Dict[str, Any]:
        """
        Single analytic point forecast (G_base + gwla + recharge_coupling*reff)
        for a (lat, lon) query. Centralizes the analytic math that the API
        predict route and the HTML report used to duplicate, and returns the
        full bundle they both render from:

          row/col, geophysics, q_hat, gwla/reff series, heads, lower/upper
          conformal bounds, recommended pumping quota, and a risk status
          derived from the sealed Config thresholds.
        """
        c = self.config
        row, col = self.data_loader.lat_lon_to_grid_index(lat, lon)
        GWLA = self.downscaling_res["GWLA"]
        Reff = self.Reff
        Sy = float(self.dataset.geophysics["Sy"][row, col])
        K = float(self.dataset.geophysics["K"][row, col])
        q_hat = self.conformal.q_hat
        G_base = c.g_base_offset + (row + col) * c.g_base_slope

        horizon = max(1, int(horizon))
        T_max = GWLA.shape[0]

        gwla_series = [float(GWLA[t % T_max, row, col]) for t in range(horizon)]
        reff_series = [float(Reff[t % T_max, row, col]) for t in range(horizon)]
        heads = [G_base + g + c.recharge_coupling * rf for g, rf in zip(gwla_series, reff_series)]
        lower_bounds = [h - q_hat for h in heads]
        upper_bounds = [h + q_hat for h in heads]
        recommended_quota = max(0.0, (heads[-1] - c.h_min - q_hat) * Sy * c.quota_factor)

        if lower_bounds[-1] < c.critical_hard_threshold:
            risk_status = "CRITICAL"
        elif lower_bounds[-1] < c.critical_threshold:
            risk_status = "WARNING"
        else:
            risk_status = "SAFE"

        return {
            "row": row,
            "col": col,
            "latitude": lat,
            "longitude": lon,
            "region_key": self.dataset.metadata.get("region_key", "custom"),
            "region_name": self.dataset.metadata.get("region_name", "Aquifer Region"),
            "geophysics": {"Sy": Sy, "K_m_per_day": K},
            "conformal_q_hat": q_hat,
            "G_base": G_base,
            "gwla_series": gwla_series,
            "reff_series": reff_series,
            "heads": heads,
            "lower_bounds": lower_bounds,
            "upper_bounds": upper_bounds,
            "recommended_quota": recommended_quota,
            "risk_status": risk_status,
        }

    def hydrograph_series(self, lat: float, lon: float, horizon: int = 24) -> Dict[str, Any]:
        """
        Live rainfall / recharge / head series at (lat, lon) for report
        hydrographs, read from the current dataset rasters instead of canned
        sine waves.
        """
        meta = self.dataset.metadata
        min_lon, min_lat, max_lon, max_lat = meta["bounds"]
        H, W = meta["grid_shape"]

        r = int(np.clip((max_lat - lat) / (max_lat - min_lat + 1e-8) * (H - 1), 0, H - 1))
        col = int(np.clip((lon - min_lon) / (max_lon - min_lon + 1e-8) * (W - 1), 0, W - 1))

        P_all = self.dataset.rasters_raw["P"][:, r, col]
        ET_all = self.dataset.rasters_raw["ET"][:, r, col]
        Reff_all = self.Reff[:, r, col] if self.Reff.ndim == 3 else self.Reff[:, 0]
        G_all = self.dataset.spatial_heads()[:, r, col]

        T_max = len(P_all)
        h_len = max(1, horizon)
        return {
            "grid_row": r,
            "grid_col": col,
            "labels": [f"M{t + 1}" for t in range(h_len)],
            "precipitation_mm": [float(P_all[t % T_max]) for t in range(h_len)],
            "evapotranspiration_mm": [float(ET_all[t % T_max]) for t in range(h_len)],
            "effective_recharge_mm": [float(Reff_all[t % T_max]) for t in range(h_len)],
            "head_level_m": [float(G_all[t % T_max] - 0.01 * (t // T_max)) for t in range(h_len)],
        }