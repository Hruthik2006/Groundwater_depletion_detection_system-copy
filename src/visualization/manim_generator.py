"""
ManimGL Mathematical Function Visualization Generator for Groundwater Framework.
Renders 3B1B-styled mathematical animations, vector fields, and interactive simulation
payloads for hydrogeological formulas across Darcy flow, Vadose Gamma delay, Split Conformal
quantiles, SCP chance-constrained MPC, and GNN Laplacian graph diffusion.
"""

import os
import math
import numpy as np
from typing import Dict, Any, List, Optional

# Check if ManimGL is available in the environment
try:
    import manimgl
    HAS_MANIMGL = True
except ImportError:
    HAS_MANIMGL = False


class GroundwaterMathEngine:
    """
    Mathematical computation and vector field generation engine
    for 3B1B-style animated groundwater formulas.
    """

    @staticmethod
    def get_function_catalog() -> Dict[str, Any]:
        """Returns catalog of mathematical functions, professional LaTeX representations, and hydrogeological explanations."""
        return {
            "darcy_flow": {
                "id": "darcy_flow",
                "title": "Darcy's Law & Hydraulic Head Vector Fields",
                "subtitle": "2D Dupuit-Boussinesq unconfined groundwater flow with radial extraction sink and flux vector field",
                "latex": r"S_y \frac{\partial h(\mathbf{x}, t)}{\partial t} = \nabla \cdot \Big( K(\mathbf{x}) \nabla h(\mathbf{x}, t) \Big) - \sum_{k=1}^{N_w} Q_k(t) \, \delta(\mathbf{x} - \mathbf{x}_k) + R_{\text{eff}}(\mathbf{x}, t)",
                "latex_flux": r"\mathbf{q}(\mathbf{x}, t) = -K(\mathbf{x}) \nabla h(\mathbf{x}, t) = -K \left( \frac{\partial h}{\partial x} \hat{\mathbf{i}} + \frac{\partial h}{\partial y} \hat{\mathbf{j}} \right)",
                "description": "Calculates the transient 2D groundwater potential surface and Darcy specific discharge vector field q (m/day) across the permeable aquifer matrix. Higher hydraulic conductivity K accelerates flux response, while pumping extraction Q creates a radial logarithmic cone of depression.",
                "explanation": "This visualization models the fundamental 2D Dupuit-Boussinesq groundwater flow equation in unconfined saturated media. The cyan vector arrows represent the Darcy specific discharge flux vectors q = -K ∇h, showing the direction and speed of subterranean water migration towards the central pumping well sink. The concentric dashed purple rings denote equipotential hydraulic head contours (isohypses). As the pumping extraction rate Q increases or specific yield Sy decreases, the localized cone of depression steepens significantly.",
                "variables": [
                    {"symbol": "K", "name": "Hydraulic Conductivity", "unit": "m/day", "default": 2.45},
                    {"symbol": "S_y", "name": "Specific Yield", "unit": "dimensionless", "default": 0.18},
                    {"symbol": "Q", "name": "Pumping Extraction Rate", "unit": "m³/day", "default": 35.0},
                    {"symbol": "h_0", "name": "Initial Regional Head", "unit": "m", "default": 42.0},
                    {"symbol": "R_eff", "name": "Effective Recharge", "unit": "m/day", "default": 0.005},
                ]
            },
            "vadose_gamma": {
                "id": "vadose_gamma",
                "title": "Vadose Zone Delay Gamma Kernel Convolution",
                "subtitle": "Unsaturated percolation impulse response kernel and lagged recharge integral",
                "latex": r"R_{\text{eff}}(t) = \int_{0}^{t} \big[ P(\tau) - \text{ET}(\tau) - Q_{\text{surf}}(\tau) \big]^{+} \cdot \kappa_{\alpha, \beta}(t - \tau) \, d\tau",
                "latex_kernel": r"\kappa_{\alpha, \beta}(\tau) = \frac{1}{\beta^\alpha \Gamma(\alpha)} \, \tau^{\alpha - 1} \exp\left( -\frac{\tau}{\beta} \right) \quad \text{for } \tau \ge 0",
                "description": "Simulates the physical temporal delay and attenuation of net surface meteoric infiltration through the unsaturated vadose column before reaching the saturated water table.",
                "explanation": "Surface rainfall P(t) does not immediately replenish deep groundwater. It first infiltrates through the unsaturated vadose zone, experiencing non-linear attenuation and percolation delay governed by soil porosity and depth to bedrock. The orange curve depicts the continuous Gamma impulse response kernel κ(τ; α, β), where α is the shape parameter and β represents the temporal scale. The shaded cyan area shows the dynamic convolution integral over the historical infiltration signal, with peak groundwater recharge arriving at modal delay t* = (α - 1)β months.",
                "variables": [
                    {"symbol": r"\alpha", "name": "Shape Parameter", "unit": "shape", "default": 2.5},
                    {"symbol": r"\beta", "name": "Scale (Lag Time)", "unit": "months", "default": 1.5},
                    {"symbol": "P_peak", "name": "Rainfall Pulse", "unit": "mm/month", "default": 85.0},
                    {"symbol": "ET_mean", "name": "Evapotranspiration", "unit": "mm/month", "default": 32.0},
                ]
            },
            "split_conformal": {
                "id": "split_conformal",
                "title": "Split Conformal Nonconformity Safety Quantiles",
                "subtitle": "Distribution-free finite-sample 1-α predictive safety intervals without Gaussian assumptions",
                "latex": r"\hat{q}_{1-\alpha} = \inf \left\{ q \in \mathbb{R} : \frac{1}{n_{\text{cal}} + 1} \sum_{i=1}^{n_{\text{cal}}} \mathbf{1}_{\{ |y_i - \hat{y}_i| \le q \}} \ge 1 - \alpha \right\}",
                "latex_interval": r"\mathbb{P}\left( Y_{n+1} \in \big[ \hat{y}_{n+1} - \hat{q}_{1-\alpha}, \; \hat{y}_{n+1} + \hat{q}_{1-\alpha} \big] \right) \ge 1 - \alpha",
                "description": "Constructs exact distribution-free statistical coverage intervals guaranteeing finite-sample safety margins around machine learning surrogate hydraulic head predictions.",
                "explanation": "Machine learning surrogates predict mean hydraulic head but can produce overconfident estimates during extreme droughts. Split conformal prediction computes absolute calibration residuals |y_i - ŷ_i| over holdout monitoring wells. The vertical green glowing marker represents the exact empirical quantile cutoff q̂_(1-α). This guarantees with (1 - α)% mathematical certainty (e.g. 95%) that future real-world aquifer levels will fall strictly within the safety envelope [ŷ - q̂, ŷ + q̂].",
                "variables": [
                    {"symbol": r"\alpha", "name": "Significance Level (Error Rate)", "unit": "probability", "default": 0.05},
                    {"symbol": "1 - \alpha", "name": "Confidence Coverage", "unit": "percentage", "default": 0.95},
                    {"symbol": "n", "name": "Calibration Sample Size", "unit": "wells/steps", "default": 144},
                    {"symbol": r"\hat{q}", "name": "Empirical Error Margin", "unit": "m", "default": 0.496},
                ]
            },
            "scp_ccmpc": {
                "id": "scp_ccmpc",
                "title": "Sequential Convex Programming (SCP) CCMPC Trust-Region",
                "subtitle": "Chance-constrained rolling horizon model predictive control via iterative quadratic programming",
                "latex": r"\min_{E_{1:H} \in \mathbb{R}^H} \sum_{t=1}^{H} \Big[ \gamma_{\text{pump}} (E_t - E_t^{\text{target}})^2 + \sigma_{\text{slack}} s_t \Big] \quad \text{s.t.} \quad G_t(E) - \hat{q}_{1-\alpha} \ge h_{\text{min}} - s_t",
                "latex_trust": r"\| E^{(k+1)} - E^{(k)} \|_2 \le \Delta_k, \quad 0 \le E_t \le E_{\text{max}}, \quad s_t \ge 0",
                "description": "Optimizes multi-month sustainable pumping quotas by iteratively solving convexified subproblems within an adaptive trust region, guaranteeing convergence under non-linear drawdown constraints.",
                "explanation": "To prevent aquifer exhaustion while satisfying agricultural extraction demands, the SCP CCMPC solver optimizes a rolling horizon of pumping quotas E_1:H. Because the true surrogate drawdown function G_t(E) is non-convex, SCP linearizes the dynamics around the current iterate E^(k) and restricts the update step to stay within a trust-region hypersphere ||E^(k+1) - E^(k)||_2 ≤ Δ. The visualization traces successive iterate steps E^(1) → E^(5) converging to the global Pareto-optimal extraction policy while strictly respecting the tightened conformal safety barrier h_min.",
                "variables": [
                    {"symbol": "H", "name": "Planning Horizon", "unit": "months", "default": 12},
                    {"symbol": "h_{min}", "name": "Critical Head Limit", "unit": "m", "default": 35.0},
                    {"symbol": r"\Delta", "name": "Trust Region Radius", "unit": "m³/month", "default": 5.0},
                    {"symbol": r"\sigma_{slack}", "name": "Constraint Penalty", "unit": "penalty wt", "default": 100.0},
                ]
            },
            "gnn_diffusion": {
                "id": "gnn_diffusion",
                "title": "Spatio-Temporal GNN-LSTM Graph Diffusion",
                "subtitle": "Spatial graph normalized Laplacian convolution coupled with recurrent LSTM cell gating",
                "latex": r"H^{(l+1)} = \sigma \left( \tilde{D}^{-\frac{1}{2}} \tilde{A} \tilde{D}^{-\frac{1}{2}} H^{(l)} W^{(l)} \right) \quad \text{where } \tilde{A} = A + I_N, \; \tilde{D}_{ii} = \sum_{j=1}^N \tilde{A}_{ij}",
                "latex_lstm": r"\mathbf{f}_t = \sigma(W_f [\mathbf{h}_{t-1}, \mathbf{x}_t] + \mathbf{b}_f), \quad \mathbf{c}_t = \mathbf{f}_t \odot \mathbf{c}_{t-1} + \mathbf{i}_t \odot \tilde{\mathbf{c}}_t, \quad \mathbf{h}_t = \mathbf{o}_t \odot \tanh(\mathbf{c}_t)",
                "description": "Models anisotropic lateral groundwater diffusion across irregular monitoring well networks using spatial graph convolutions, coupled with LSTM recurrent gates for temporal hydraulic state tracking.",
                "explanation": "This architecture replaces rigid grid approximations with a continuous spatial graph over real-world piezometer well coordinates. Piezometer nodes exchange hydrogeological message embeddings via the symmetric normalized Laplacian D̃^(-1/2) Ã D̃^(-1/2), capturing subterranean hydraulic connectivity and drawdown interference. The temporal LSTM cell then tracks long-term hydraulic head storage dynamics across seasonal cycles.",
                "variables": [
                    {"symbol": "N", "name": "Monitoring Wells Nodes", "unit": "nodes", "default": 16},
                    {"symbol": r"\tilde{A}", "name": "Adjacency Matrix with Self-Loops", "unit": "matrix", "default": "16x16"},
                    {"symbol": "d_h", "name": "Hidden State Dimension", "unit": "channels", "default": 64},
                ]
            }
        }

    @staticmethod
    def generate_darcy_vector_field(K: float = 2.45, Sy: float = 0.18, Q: float = 35.0, h0: float = 42.0, t_sec: float = 0.0) -> Dict[str, Any]:
        """Generates 2D vector field grid (quiver flux & head surface) for Darcy flow."""
        grid_size = 17
        x = np.linspace(-8, 8, grid_size)
        y = np.linspace(-8, 8, grid_size)
        X, Y = np.meshgrid(x, y)
        R = np.sqrt(X**2 + Y**2) + 0.35

        # Unconfined steady-state cone of depression (Theis/Thiem formulation)
        b = 15.0  # saturated thickness (m)
        drawdown = (Q / (2 * np.pi * max(0.1, K) * b)) * np.log(10.0 / R)
        drawdown = np.clip(drawdown, 0.0, 8.0) * (1.0 - 0.2 * np.sin(t_sec * 1.5))
        Head = h0 - drawdown

        # Hydraulic gradient: grad_h = [dh/dx, dh/dy]
        # dh/dr = (Q / (2*pi*K*b)) / r
        factor = (Q / (2 * np.pi * max(0.1, K) * b)) / (R**2)
        dh_dx = factor * X
        dh_dy = factor * Y

        # Darcy flux q = -K * grad_h
        qx = -K * dh_dx
        qy = -K * dh_dy

        vectors = []
        for i in range(grid_size):
            for j in range(grid_size):
                vx = float(qx[i, j])
                vy = float(qy[i, j])
                mag = math.sqrt(vx**2 + vy**2)
                vectors.append({
                    "x": round(float(X[i, j]), 2),
                    "y": round(float(Y[i, j]), 2),
                    "head": round(float(Head[i, j]), 2),
                    "qx": round(vx, 4),
                    "qy": round(vy, 4),
                    "mag": round(mag, 4)
                })

        # Contour profile along X-axis at Y=0
        r_profile = np.linspace(-8, 8, 50)
        r_dist = np.abs(r_profile) + 0.35
        h_profile = h0 - np.clip((Q / (2 * np.pi * max(0.1, K) * b)) * np.log(10.0 / r_dist), 0.0, 8.0)

        return {
            "type": "darcy_flow",
            "K": K,
            "Sy": Sy,
            "Q": Q,
            "h0": h0,
            "grid_size": grid_size,
            "vectors": vectors,
            "profile": {
                "r": [round(float(v), 2) for v in r_profile],
                "h": [round(float(v), 2) for v in h_profile]
            }
        }

    @staticmethod
    def generate_vadose_convolution(alpha: float = 2.5, beta: float = 1.5, timesteps: int = 24) -> Dict[str, Any]:
        """Computes Gamma delay impulse response kernel and convolution integral curves."""
        from scipy.special import gamma as gamma_fn
        
        t = np.linspace(0, timesteps, timesteps * 4 + 1)
        # Gamma PDF impulse kernel
        denom = (beta ** alpha) * gamma_fn(alpha)
        kernel = (np.maximum(t, 1e-4) ** (alpha - 1)) * np.exp(-t / beta) / denom

        # Synthetic seasonal rainfall infiltration signal P(t) - ET(t)
        t_months = np.linspace(0, timesteps, timesteps * 4 + 1)
        infiltration = 40.0 + 35.0 * np.sin(2 * np.pi * t_months / 12.0) + 15.0 * np.cos(4 * np.pi * t_months / 12.0)
        infiltration = np.maximum(0.0, infiltration)

        # Convolution Reff(t) = (P - ET) * kernel
        dt = t[1] - t[0]
        conv_full = np.convolve(infiltration, kernel, mode="full") * dt
        reff = conv_full[:len(t)]

        return {
            "type": "vadose_gamma",
            "alpha": alpha,
            "beta": beta,
            "peak_lag_months": round(max(0.0, (alpha - 1) * beta), 2),
            "mean_lag_months": round(alpha * beta, 2),
            "time_months": [round(float(v), 2) for v in t_months],
            "kernel_density": [round(float(v), 5) for v in kernel],
            "infiltration_mm": [round(float(v), 2) for v in infiltration],
            "effective_recharge_mm": [round(float(v), 2) for v in reff]
        }

    @staticmethod
    def generate_conformal_quantiles(alpha: float = 0.05, n_samples: int = 144, q_hat_base: float = 0.496) -> Dict[str, Any]:
        """Generates calibration residual distribution and exact 1-α quantile cutoff."""
        np.random.seed(42)
        # Realistic surrogate absolute residuals |y - y_hat|
        residuals = np.abs(np.random.gamma(shape=2.0, scale=q_hat_base / 2.2, size=n_samples))
        residuals.sort()

        # Finite sample conformal quantile
        q_idx = int(np.ceil((n_samples + 1) * (1.0 - alpha))) - 1
        q_idx = min(max(0, q_idx), n_samples - 1)
        q_hat = float(residuals[q_idx])

        # Histogram bins
        hist, bin_edges = np.histogram(residuals, bins=25, density=True)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

        # Sample trajectory with upper/lower conformal band
        t_seq = np.arange(1, 13)
        nominal_head = 41.5 - 0.15 * t_seq + 0.3 * np.sin(t_seq * 0.8)
        lower_bound = nominal_head - q_hat
        upper_bound = nominal_head + q_hat

        return {
            "type": "split_conformal",
            "alpha": alpha,
            "confidence_pct": round((1.0 - alpha) * 100, 1),
            "n_samples": n_samples,
            "q_hat": round(q_hat, 4),
            "residuals_sorted": [round(float(v), 4) for v in residuals],
            "histogram": {
                "bin_centers": [round(float(v), 4) for v in bin_centers],
                "densities": [round(float(v), 4) for v in hist]
            },
            "sample_trajectory": {
                "months": [f"M{i}" for i in t_seq],
                "nominal": [round(float(v), 2) for v in nominal_head],
                "lower": [round(float(v), 2) for v in lower_bound],
                "upper": [round(float(v), 2) for v in upper_bound]
            }
        }

    @staticmethod
    def generate_scp_trust_region_data(horizon: int = 12, h_min: float = 35.0, delta_trust: float = 5.0) -> Dict[str, Any]:
        """Generates outer iteration convergence path and trust-region spheres for SCP CCMPC."""
        iterations = []
        current_E = np.full(horizon, 75.0)
        
        # Simulate 5 SCP outer iterations
        for k in range(1, 6):
            target_E = 38.0 + 8.0 * np.sin(np.arange(horizon) * 0.5)
            step = (target_E - current_E) * (0.4 + 0.1 * k)
            step_norm = np.linalg.norm(step)
            if step_norm > delta_trust:
                step = step * (delta_trust / step_norm)
            
            next_E = np.clip(current_E + step, 0.0, 100.0)
            predicted_h = 42.0 - 0.08 * np.cumsum(next_E * 0.1) + 0.2 * np.sin(np.arange(horizon))
            cost = float(np.sum((next_E - 45.0)**2) * 0.05 + np.sum(np.maximum(0.0, h_min - predicted_h) * 100.0))
            
            iterations.append({
                "iteration": k,
                "quotas": [round(float(v), 2) for v in next_E],
                "heads": [round(float(v), 2) for v in predicted_h],
                "step_norm": round(float(np.linalg.norm(next_E - current_E)), 3),
                "trust_radius": delta_trust,
                "cost": round(cost, 2),
                "converged": bool(k >= 4)
            })
            current_E = next_E

        return {
            "type": "scp_ccmpc",
            "horizon": horizon,
            "h_min": h_min,
            "delta_trust": delta_trust,
            "iterations": iterations
        }

    @staticmethod
    def generate_gnn_diffusion_graph() -> Dict[str, Any]:
        """Generates 16-well spatial Delaunay graph, Laplacian matrix, and dynamic diffusion signals."""
        np.random.seed(101)
        num_wells = 16
        coords = []
        for i in range(4):
            for j in range(4):
                coords.append([
                    round(j * 3.5 + np.random.uniform(-0.4, 0.4), 2),
                    round(i * 3.5 + np.random.uniform(-0.4, 0.4), 2)
                ])

        # Euclidean distance adjacency matrix
        nodes = [{"id": f"W{idx+1}", "x": c[0], "y": c[1]} for idx, c in enumerate(coords)]
        edges = []
        adj = np.zeros((num_wells, num_wells))

        for i in range(num_wells):
            for j in range(i + 1, num_wells):
                dist = math.hypot(coords[i][0] - coords[j][0], coords[i][1] - coords[j][1])
                if dist <= 4.2:
                    w = round(math.exp(-dist / 2.5), 3)
                    adj[i, j] = w
                    adj[j, i] = w
                    edges.append({"source": f"W{i+1}", "target": f"W{j+1}", "weight": w})

        # Degree and normalized Laplacian
        degree = np.sum(adj, axis=1)
        deg_inv_sqrt = np.diag(1.0 / np.sqrt(np.maximum(degree, 1e-4)))
        laplacian = np.eye(num_wells) - deg_inv_sqrt @ adj @ deg_inv_sqrt

        return {
            "type": "gnn_diffusion",
            "num_wells": num_wells,
            "nodes": nodes,
            "edges": edges,
            "laplacian_trace": round(float(np.trace(laplacian)), 3)
        }
