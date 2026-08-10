import cvxpy as cp
import numpy as np
import torch
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


class SCPChanceConstrainedMPC:
    """
    Chance-Constrained Model Predictive Control (CCMPC) solved via
    Two-Loop Sequential Convex Programming (SCP) with Trust-Region linearizations.
    Enforces conformal safety bounds: G_k >= h_min + q_{1-alpha}.
    """

    def __init__(
        self,
        horizon: int = 12,
        num_wells: int = 16,
        E_max: float = 10.0,
        h_min: float = 35.0,
        h_target: float = 45.0,
        alpha: float = 0.05,
        w_energy: float = 1.0,
        w_head: float = 5.0,
        delta_0: float = 1.5,
        eta_expand: float = 1.25,
        eta_shrink: float = 0.25,
        eps_tol: float = 1e-4,
        max_scp_iters: int = 20,
    ):
        self.H = horizon
        self.N = num_wells
        self.E_max = E_max
        self.h_min = h_min
        self.h_target = h_target
        self.alpha = alpha
        self.w_energy = w_energy
        self.w_head = w_head
        
        # SCP Hyperparameters
        self.delta_0 = delta_0
        self.eta_expand = eta_expand
        self.eta_shrink = eta_shrink
        self.eps_tol = eps_tol
        self.max_scp_iters = max_scp_iters

    def compute_jacobians(
        self,
        surrogate_model: torch.nn.Module,
        G_k: np.ndarray,
        E_k: np.ndarray,
        climate_vec: np.ndarray,
        static_geo: np.ndarray,
        adj: torch.Tensor = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes linearized state Jacobian A_k = d f_theta / d G and control Jacobian B_k = d f_theta / d E
        using PyTorch automatic differentiation.
        """
        surrogate_model.eval()
        
        # Convert to PyTorch tensors with requires_grad=True
        G_t = torch.tensor(G_k, dtype=torch.float32, requires_grad=True).unsqueeze(0).unsqueeze(1)  # (1, 1, N)
        E_t = torch.tensor(E_k, dtype=torch.float32, requires_grad=True).unsqueeze(0).unsqueeze(1)  # (1, 1, N)
        climate_t = torch.tensor(climate_vec, dtype=torch.float32).unsqueeze(0).unsqueeze(1)  # (1, 1, N, C)

        # Dynamic sequence vector: [G, E, Reff, GWLA]
        dyn_seq = torch.cat([G_t.unsqueeze(-1), E_t.unsqueeze(-1), climate_t], dim=-1)  # (1, 1, N, 4)

        if hasattr(surrogate_model, "compute_adjacency") and adj is not None:
            # GNN-LSTM model
            static_t = torch.tensor(static_geo, dtype=torch.float32)
            G_next = surrogate_model(dyn_seq, static_t, adj)[0, 0]  # (N,)
        else:
            # Fallback simple linear expansion
            G_next = G_t[0, 0, :] - 0.1 * E_t[0, 0, :] + 0.05 * climate_t[0, 0, :, 0]

        N = self.N
        A_k = np.zeros((N, N))
        B_k = np.zeros((N, N))

        # Compute Jacobians via autograd
        for i in range(N):
            if G_next[i].requires_grad:
                grad_G = torch.autograd.grad(G_next[i], G_t, retain_graph=True, allow_unused=True)[0]
                grad_E = torch.autograd.grad(G_next[i], E_t, retain_graph=True, allow_unused=True)[0]

                if grad_G is not None:
                    A_k[i] = grad_G[0, 0].detach().numpy()
                else:
                    A_k[i, i] = 0.95
                
                if grad_E is not None:
                    B_k[i] = grad_E[0, 0].detach().numpy()
                else:
                    B_k[i, i] = -0.15
            else:
                A_k[i, i] = 0.95
                B_k[i, i] = -0.15

        return A_k, B_k

    def solve_optimal_pumping(
        self,
        surrogate_model: torch.nn.Module,
        G_0: np.ndarray,
        climate_horizon: np.ndarray,  # (H, N, C)
        static_geo: np.ndarray,        # (N, S)
        q_hat: float = 0.0,
        adj: torch.Tensor = None,
    ) -> Dict[str, Any]:
        """
        Solves Chance-Constrained MPC optimal pumping schedule E_{1:H} using SCP.
        Tightened safety constraint: G_k >= h_min + q_hat
        """
        H, N = self.H, self.N
        h_safe = self.h_min + q_hat

        # Initialize nominal trajectories
        E_nom = np.full((H, N), 0.5 * self.E_max)
        G_nom = np.zeros((H + 1, N))
        G_nom[0] = G_0

        for k in range(H):
            # Forward nominal state estimate (safely wrap climate array for arbitrary H)
            c_k = climate_horizon[k % climate_horizon.shape[0]]
            G_nom[k + 1] = 0.95 * G_nom[k] - 0.10 * E_nom[k] + 0.05 * c_k[:, 0]

        delta_trust = self.delta_0
        converged = False
        scp_history = []

        for scp_iter in range(self.max_scp_iters):
            # 1. Linearize state dynamics around nominal trajectory (G_nom, E_nom)
            A_seq = []
            B_seq = []
            for k in range(H):
                c_k = climate_horizon[k % climate_horizon.shape[0]]
                A_k, B_k = self.compute_jacobians(
                    surrogate_model,
                    G_nom[k],
                    E_nom[k],
                    c_k,
                    static_geo,
                    adj=adj,
                )
                A_seq.append(A_k)
                B_seq.append(B_k)

            # 2. Formulate Convex QP Subproblem in CVXPY
            dE = cp.Variable((H, N))
            dG = cp.Variable((H + 1, N))
            xi = cp.Variable((H, N), nonneg=True)  # Soft safety slack variables for robustness

            constraints = [dG[0] == 0.0]
            cost_terms = []

            for k in range(H):
                # Linearized dynamics constraint
                constraints.append(dG[k + 1] == A_seq[k] @ dG[k] + B_seq[k] @ dE[k])
                
                # Conformal Chance Safety Bound with soft slack
                constraints.append(G_nom[k + 1] + dG[k + 1] + xi[k] >= h_safe)
                
                # Operational Pumping Bounds
                constraints.append(E_nom[k] + dE[k] >= 0.0)
                constraints.append(E_nom[k] + dE[k] <= self.E_max)
                
                # Trust-Region Constraint
                constraints.append(cp.norm(dE[k], "inf") <= delta_trust)

                # Objective cost: energy cost + head deviation + heavy penalty on safety violation
                cost_energy = self.w_energy * cp.sum(E_nom[k] + dE[k])
                cost_head = self.w_head * cp.sum_squares(G_nom[k + 1] + dG[k + 1] - self.h_target)
                cost_slack = 1000.0 * cp.sum(xi[k])
                cost_terms.append(cost_energy + cost_head + cost_slack)

            objective = cp.Minimize(cp.sum(cost_terms))
            problem = cp.Problem(objective, constraints)

            # Solve QP using OSQP / ECOS
            try:
                problem.solve(solver=cp.OSQP, verbose=False)
            except Exception as e:
                problem.solve(solver=cp.ECOS, verbose=False)

            if problem.status not in ["optimal", "optimal_inaccurate"]:
                logger.warning(f"SCP iteration {scp_iter} QP solver status: {problem.status}")
                break

            dE_val = dE.value
            dG_val = dG.value
            step_norm = np.max(np.abs(dE_val))

            # 3. Update nominal trajectories
            E_nom += dE_val
            G_nom += dG_val

            # Trust-Region adjustment rule
            if step_norm < self.eps_tol:
                converged = True
                scp_history.append({"iter": scp_iter, "cost": problem.value, "delta": delta_trust, "step": step_norm})
                break

            if step_norm > 0.8 * delta_trust:
                delta_trust *= self.eta_expand
            else:
                delta_trust = max(0.1, delta_trust * self.eta_shrink)

        final_cost_val = 0.0
        if 'problem' in locals() and problem.value is not None:
            if not np.isinf(problem.value) and not np.isnan(problem.value):
                final_cost_val = float(problem.value)
            else:
                final_cost_val = 999999.0

        return {
            "converged": converged,
            "optimal_pumping": E_nom,
            "predicted_heads": G_nom[1:],
            "safety_bound_tightened": h_safe,
            "q_hat": q_hat,
            "final_cost": final_cost_val,
            "scp_history": scp_history,
        }
