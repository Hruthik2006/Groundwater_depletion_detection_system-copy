from dataclasses import dataclass, field, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class Config:
    """
    Sealed operating parameters for the groundwater forecasting pipeline.

    Single source of truth for the numbers that used to float as literals
    across main.py, the API state container, and the train scripts:
      * grid_shape / mascon_grid_shape / timesteps / num_wells
      * conformal alpha and the model sequence length
      * the MPC planning horizon and safety floor h_min
      * the web/report depletion alert line critical_threshold
    """

    # Data pipeline
    data_mode: str = "synthetic"          # synthetic | realtime | dwlr
    region_key: str = "illinois"
    bounds: Optional[list] = None
    grid_shape: Tuple[int, int] = (16, 16)
    mascon_grid_shape: Tuple[int, int] = (2, 2)
    timesteps: int = 36
    num_wells: int = 16
    seed: int = 42

    # Scientific ML surrogates
    seq_len: int = 12                     # autoregressive window for GNN-LSTM
    nominal_extraction: float = 5.0       # E_t baseline used in dyn sequences

    # Split conformal prediction
    alpha: float = 0.05

    # SCP-CCMPC control
    horizon: int = 12
    h_min: float = 35.0                   # chance-constraint safety floor h_min + q_hat
    h_target: float = 45.0
    e_max: float = 10.0
    # Tunables exposed through the /control/pumping_quotas request schema so the
    # solver's operating point comes from one sealed source. The frontend posts
    # these every SCP run; None in a request means "keep the Config default".
    gamma_pump: float = 1.0               # w_energy: pumping-cost weight in the SCP objective
    sigma_slack: float = 1000.0           # cost_slack: heavy penalty on safety-violation slack s_t
    delta_trust: float = 1.5              # delta_0: initial trust-region radius for SCP linearization
    max_scp_iters: int = 20

    # Web / report depletion alerts
    # The dashboard reports 36.0 m as the critical head threshold; the MPC
    # safety floor sits at h_min (35.0 m). Keep both named here so they cannot
    # drift apart again: h_min feeds the solver/quota math, critical_threshold
    # feeds the fix "risk status" banners and depletion alerts.
    critical_threshold: float = 36.0
    critical_hard_threshold: float = 34.0  # critical_threshold - 2.0 in alerts/risk

    # Analytical point-forecast formula (G_base + gwla + 0.02 * reff)
    g_base_offset: float = 40.0
    g_base_slope: float = 0.3
    recharge_coupling: float = 0.02
    quota_factor: float = 50.0
    drawdown_ramp_per_cycle: float = 0.015  # spatial drawdown drift per GWLA cycle (m)

    # Model checkpoint
    checkpoint_path: Optional[str] = None


DEFAULT_CONFIG = Config()