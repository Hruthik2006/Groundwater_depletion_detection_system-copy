import numpy as np
import logging
from typing import Dict, Any, Optional
from scipy.optimize import linprog

logger = logging.getLogger(__name__)


class SingleStationLPSolver:
    """
    Single-Station Worked Linear Programming (LP) Extraction Solver.
    Implements Section IV-D of research paper (50) groundwater.docx for station CGWBHU2335.
    Solves Equation (2) via SciPy HiGHS solver to maximize total 30-day extraction
    subject to safety floor s = -7.61m and per-day extraction cap E_max = 2.0m/day.
    """

    def __init__(
        self,
        station_id: str = "CGWBHU2335",
        horizon: int = 30,
        a_recharge: float = 0.00353,    # Recharge slope (m/mm)
        b_discharge: float = -0.00529,  # Natural discharge rate (m/day)
        safety_floor: float = -7.61,    # 10th percentile historical level (m)
        max_daily_extraction: float = 2.0,  # Cap (m/day)
    ):
        self.station_id = station_id
        self.horizon = horizon
        self.a_recharge = a_recharge
        self.b_discharge = b_discharge
        self.safety_floor = safety_floor
        self.max_daily_extraction = max_daily_extraction

    def solve(
        self,
        rainfall_seq: Optional[np.ndarray] = None,
        initial_head: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Solves 30-day extraction optimization LP:
        max sum_{t=1}^T E_t
        subject to:
          H(t+1) = H(t) + a * Pr(t) + b - E_t >= safety_floor
          0 <= E_t <= max_daily_extraction
        """
        T = self.horizon
        if rainfall_seq is None:
            # Baseline rainfall sequence matching station CGWBHU2335 profile
            np.random.seed(2335)
            rainfall_seq = np.random.uniform(0.0, 12.0, T)
        else:
            rainfall_seq = np.array(rainfall_seq[:T], dtype=np.float64)

        # Objective: minimize -sum(E_t) <=> maximize sum(E_t)
        c = -np.ones(T)
        bounds = [(0.0, self.max_daily_extraction) for _ in range(T)]

        # Cumulative lower-triangle matrix for cumulative extraction bounds
        A_ub = np.tril(np.ones((T, T)))
        b_ub = np.zeros(T)

        cum_natural = np.cumsum(self.a_recharge * rainfall_seq + self.b_discharge)
        for t in range(T):
            b_ub[t] = initial_head + cum_natural[t] - self.safety_floor

        res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

        if not res.success:
            logger.warning(f"Single-Station LP Solver failed: {res.message}")
            return {
                "success": False,
                "status": res.message,
                "station_id": self.station_id,
                "total_extraction_m": 0.0,
                "daily_extractions": np.zeros(T).tolist(),
                "head_trajectory": np.zeros(T).tolist(),
            }

        E_opt = res.x
        total_extraction = float(-res.fun)

        # Calculate predicted groundwater head trajectory H(t)
        head_traj = np.zeros(T + 1)
        head_traj[0] = initial_head

        for t in range(T):
            head_traj[t + 1] = head_traj[t] + self.a_recharge * rainfall_seq[t] + self.b_discharge - E_opt[t]

        min_head = float(np.min(head_traj))
        safety_maintained = bool(min_head >= self.safety_floor - 1e-4)

        logger.info(
            f"Station {self.station_id} 30-Day LP Solved via HiGHS: "
            f"Total Extraction = {total_extraction:.2f}m, Min Head = {min_head:.2f}m (Floor = {self.safety_floor}m)"
        )

        return {
            "success": True,
            "solver": "SciPy HiGHS",
            "station_id": self.station_id,
            "horizon": T,
            "total_extraction_m": round(total_extraction, 2),
            "daily_extractions": np.round(E_opt, 3).tolist(),
            "head_trajectory": np.round(head_traj, 3).tolist(),
            "safety_floor_m": self.safety_floor,
            "min_head_reached_m": round(min_head, 3),
            "safety_maintained": safety_maintained,
            "rainfall_sequence_mm": np.round(rainfall_seq, 2).tolist(),
        }


def solve_station_cgwbhu2335_lp(rainfall_seq: Optional[np.ndarray] = None) -> Dict[str, Any]:
    solver = SingleStationLPSolver()
    return solver.solve(rainfall_seq=rainfall_seq)
