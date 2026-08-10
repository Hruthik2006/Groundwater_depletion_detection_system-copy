# Satellite-Enhanced Groundwater Forecasting and Chance-Constrained Extraction Management Framework

This document serves as an implementation guide and blueprint for building an operational framework that integrates satellite gravimetry (GRACE/GRACE-FO), hydroclimatic remote sensing, scientific machine learning surrogates, split conformal prediction, and chance-constrained model predictive control (CCMPC) solved via Sequential Convex Programming (SCP).

---

## 1. System Execution Environment & Pipeline Architecture

The framework consists of four main operational layers:
1. **Geospatial Ingestion Engine**: Fetches, masks, aligns, and synchronizes spatial/temporal data streams onto a $4\text{ km} \times 4\text{ km}$ grid (EPSG:4326).
2. **Multi-Phase Downscaling & Physical Delay Engine**: Refines $300\text{ km}$ GRACE/GRACE-FO $TWSA$ into fine-scale $GWSA$ / $GWLA$ and models unsaturated vadose transit delays via Gamma kernel convolution.
3. **Scientific ML Dynamic Surrogates**: Predicts temporal hydraulic head transitions using GNN-LSTM, PINN (Dupuit-Boussinesq), or FNO architectures.
4. **Optimization & Control Layer**: Executes Chance-Constrained Model Predictive Control using Split Conformal Prediction for distribution-free uncertainty bounds and two-loop Sequential Convex Programming (SCP) via CVXPY.

### Technology Stack & Dependencies

```python
# System Requirements
# Python 3.10+

# Geospatial Ingestion
import ee  # earthengine-api
import geemap
import xarray as xr
import rioxarray
import numpy as np

# Downscaling & Signal Processing
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
from scipy.stats import gamma
from scipy.ndimage import map_coordinates

# Scientific Machine Learning
import torch
import torch.nn as nn
import torch_geometric  # PyTorch Geometric for GNN-LSTM
# neuraloperator / fourier neural operator modules

# Optimization & Control
import cvxpy as cp
import jax
import jax.numpy as jnp
import osqp
```

---

## 2. Geospatial Ingestion, Reprojection, and Alignment

### Target Grid Definition
- **CRS**: EPSG:4326 (WGS84)
- **Spatial Resolution**: $4\text{ km} \times 4\text{ km}$ ($0.036^\circ \times 0.036^\circ$)
- **Temporal Cadence**: Monthly unified timestep ($t = 1, 2, \dots, T$)

### Input Data Stream Matrix

| Variable | Primary Source | Native Res. | Resampling / Aggregation Method | Model Representation |
| :--- | :--- | :--- | :--- | :--- |
| **Precipitation** ($P$) | CHIRPS v2.0 / v3.0 | $0.05^\circ$ (~5.5 km) | Bilinear Interpolation | $P(x,y,t)$ |
| **Evapotranspiration** ($ET$) | MODIS MOD16A2 | $500\text{ m}$ | Spatial accumulation & sum | $ET(x,y,t)$ |
| **Soil Moisture Anomaly** ($SMSA$) | GLDAS Noah L4 V2.1 | $0.25^\circ$ (~25 km) | Spatial mapping to fine sub-pixels | $SMSA(x,y,t)$ |
| **Snow Water Equivalent Anomaly** ($SWEA$) | GLDAS Noah L4 V2.1 | $0.25^\circ$ (~25 km) | Spatial mapping to fine sub-pixels | $SWEA(x,y,t)$ |
| **Canopy Water Storage Anomaly** ($CWSA$) | GLDAS Noah L4 V2.1 | $0.25^\circ$ (~25 km) | Spatial mapping to fine sub-pixels | $CWSA(x,y,t)$ |
| **Terrestrial Water Storage Anomaly** ($TWSA$) | CSR GRACE / GRACE-FO RL06.2 | $0.25^\circ$ Mascons | Native mascon masking | $TWSA_{\text{native}}(M,t)$ |
| **Groundwater Head Measurements** ($G$) | In-situ Piezometers | Point wells | Cubic spline temporal interpolation | $G_i(t)$ |
| **Specific Yield** ($S_y$) | Borehole log / Geophysics | Point / Grid | Kriging interpolation | $S_y(x,y)$ |

### Normalization Routine
Dynamic features across all grid cells are scaled via z-score normalization using historical baseline stats:
$$x_{\text{norm}}(x, y, t) = \frac{x(x, y, t) - \mu_x(x, y)}{\sigma_x(x, y)}$$

---

## 3. Multi-Phase Downscaling and Physical Delay Engineering

### Workflow Architecture
1. **Phase 1: Ensemble Spatial Regression**: Train $\mathcal{M}_{\text{spatial}}$ (Random Forest / XGBoost) on spatially aggregated hydroclimatic predictors $\mathbf{P}_{\text{aggregated}}(M,t)$ against coarse mascons $TWSA_{\text{coarse}}(M,t)$. Predict raw fine-scale anomalies $TWSA_{\text{down}}(x,y,t)$.
2. **Phase 2: Scale Preservation Correction**: Enforce regional mass conservation across each mascon footprint $M$:
   $$TWSA_{\text{scaled}}(x, y, t) = TWSA_{\text{down}}(x, y, t) \times \left( \frac{TWSA_{\text{native}}(M, t)}{\frac{1}{|M|} \sum_{(s,u) \in M} TWSA_{\text{down}}(s, u, t)} \right)$$
3. **Phase 3: Deep Storage Isolation**: Isolate Groundwater Storage Anomaly ($GWSA$):
   $$GWSA(x, y, t) = TWSA_{\text{scaled}}(x, y, t) - SMSA(x, y, t) - SWEA(x, y, t) - CWSA(x, y, t)$$
4. **Phase 4: Groundwater Level Anomaly ($GWLA$) Conversion**:
   $$GWLA(x, y, t) = \frac{GWSA(x, y, t)}{S_y(x, y)}$$
5. **Phase 5: Unsaturated Vadose Zone Delay**: Convolve surface net recharge ($P - ET$) with a parameterized Gamma kernel:
   $$\kappa(\tau; \boldsymbol{\theta}_v) = \frac{\tau^{\alpha_{\text{lag}}-1} e^{-\frac{\tau}{\beta_{\text{lag}}}}}{\Gamma(\alpha_{\text{lag}}) \beta_{\text{lag}}^{\alpha_{\text{lag}}}}$$
   $$R_{\text{eff}}(x, y, t) = \sum_{\tau=0}^{\tau_{\text{max}}} \kappa(\tau; \boldsymbol{\theta}_v) \Big[ P(x, y, t - \tau) - ET(x, y, t - \tau) \Big]$$

---

## 4. Scientific Machine Learning Dynamic Surrogates

State transition dynamics model hydraulic head updates:
$$G_{i, t+1} = f_\theta\left(G_{i,t}, E_{i,t}, \mathbf{w}_{i,t}, \mathbf{s}_i\right) + \epsilon_{i,t}$$
where $E_{i,t}$ is extraction volume, $\mathbf{w}_{i,t} = [R_{\text{eff}}, T, GWLA]^T$ is the dynamic climate vector, and $\mathbf{s}_i = [K, S_y, z_{\text{bedrock}}]^T$ represents static geophysics.

### Paradigm Comparison

| Model Paradigm | Spatial Representation | Temporal Mechanism | Physical Constraint | Operational Role |
| :--- | :--- | :--- | :--- | :--- |
| **GNN-LSTM** | Topological Graph $\mathcal{G}(\mathcal{V}, \mathcal{E})$ | Recurrent LSTM updates | Static feature conditioning | Networked well arrays & drawdown tracking |
| **PINN** | Continuous points $(x,y)$ | Continuous time $t$ | Dupuit-Boussinesq PDE loss penalty | Data-scarce boundary estimation & inversion |
| **FNO / U-FNO** | Functional spectral domain | Discrete step operator | Spectral mode regularization | Real-time digital twins & rapid SCP evaluation |

### Physics-Informed Neural Network (PINN) Loss Formulation
Enforces 2D Dupuit-Boussinesq groundwater flow equation:
$$\mathcal{R}_{\text{PDE}}(h) = S_y \frac{\partial h}{\partial t} - \frac{\partial}{\partial x}\left(K_x h \frac{\partial h}{\partial x}\right) - \frac{\partial}{\partial y}\left(K_y h \frac{\partial h}{\partial y}\right) - R_{\text{eff}} + E$$

Composite loss function:
$$\mathcal{L}_{\text{composite}}(\theta) = \frac{1}{N_{\text{obs}}} \sum_{i=1}^{N_{\text{obs}}} \left(G_{i,t} - \hat{f}_{\theta}(x_i, y_i, t)\right)^2 + \lambda_{\text{PDE}} \frac{1}{N_{\text{colloc}}} \sum_{j=1}^{N_{\text{colloc}}} \left( \mathcal{R}_{\text{PDE}}\left(\hat{f}_{\theta}(x_j, y_j, t_j)\right) \right)^2$$

---

## 5. Split Conformal Prediction for Calibration-Free UQ

To ensure distribution-free safety guarantees under a target violation probability $\alpha$ (e.g., $\alpha = 0.05$ for $95\%$ confidence):

1. Compute absolute non-conformity residuals on calibration dataset $\mathcal{D}_{\text{calib}}$ ($N$ samples):
   $$R_i = |G_i - \hat{f}_{\theta}(X_i)|, \quad i \in \mathcal{D}_{\text{calib}}$$
2. Compute the empirical quantile:
   $$q_{1-\alpha} = \text{Quantile}\left(\{R_i\}, \frac{\lceil (N+1)(1-\alpha) \rceil}{N}\right)$$
3. Reformulate stochastic chance constraint $\mathbb{P}(G_{i, t+k} \ge h_{\text{min}}) \ge 1 - \alpha$ into tightened deterministic bound:
   $$\hat{G}_{i, t+k} \ge h_{\text{min}} + q_{1-\alpha}$$

---

## 6. Chance-Constrained MPC via Sequential Convex Programming (SCP)

### Non-Convex Optimal Control Problem
$$\min_{E_{1:H}} \sum_{k=1}^H \left( c_k^T E_k + w_h \| G_k - G_{\text{target}} \|_2^2 \right)$$
Subject to:
$$G_{k+1} = f_\theta(G_k, E_k, \mathbf{w}_k, \mathbf{s})$$
$$\hat{G}_k - q_{1-\alpha} \ge h_{\text{min}}$$
$$0 \le E_k \le E_{\text{max}}$$

### SCP Trust-Region Linearization Loop
At outer iteration $j$, linearize state dynamics around nominal trajectory $(G^{(j)}, E^{(j)})$:
$$G_{k+1} \approx G_{k+1}^{(j)} + A_k^{(j)} \left(G_k - G_k^{(j)}\right) + B_k^{(j)} \left(E_k - E_k^{(j)}\right)$$
where Jacobians are computed via automatic differentiation:
$$A_k^{(j)} = \frac{\partial f_\theta}{\partial G}\Big|_{(G_k^{(j)}, E_k^{(j)})}, \quad B_k^{(j)} = \frac{\partial f_\theta}{\partial E}\Big|_{(G_k^{(j)}, E_k^{(j)})}$$

### Convex QP Subproblem Formulation (CVXPY)
$$\min_{\delta E_{1:H}, \delta G_{1:H}} \sum_{k=1}^H \left( c_k^T (E_k^{(j)} + \delta E_k) + w_h \| G_k^{(j)} + \delta G_k - G_{\text{target}} \|_2^2 \right)$$
Subject to:
$$\delta G_{k+1} = A_k^{(j)} \delta G_k + B_k^{(j)} \delta E_k$$
$$G_k^{(j)} + \delta G_k \ge h_{\text{min}} + q_{1-\alpha}$$
$$0 \le E_k^{(j)} + \delta E_k \le E_{\text{max}}$$
$$\| \delta E_k \|_\infty \le \Delta^{(j)} \quad \text{(Trust-Region Constraint)}$$

### Hyperparameter Settings
- **Horizon ($H$)**: 12 to 36 months
- **Safety Violation Limit ($\alpha$)**: 0.05
- **Initial Trust Region Radius ($\Delta_0$)**: $0.15 \times E_{\text{max}}$
- **Expansion Factor ($\eta_{\text{expand}}$)**: 1.25
- **Contraction Factor ($\eta_{\text{shrink}}$)**: 0.25
- **Convergence Tolerance ($\epsilon_{\text{tol}}$)**: $10^{-4}$

---

## 7. Operational Integration & API Endpoints

1. **GeoJSON Spatial Drawdown Map Endpoint**:
   - `GET /api/v1/forecast/spatial_drawdown`
   - Returns predicted basin-wide hydraulic head rasters across planning horizon $H$.
2. **Extraction Quota Endpoint**:
   - `POST /api/v1/control/pumping_quotas`
   - Computes optimal pumping allocation vectors $E_{1:H}^*$ subject to conformal safety margins $q_{1-\alpha}$.
3. **Depletion Warning Endpoint**:
   - `GET /api/v1/alerts/depletion`
   - Triggers automated alerts for well nodes where $\hat{G}_{i, t+k} - q_{1-\alpha} < h_{\text{threshold}}$.

