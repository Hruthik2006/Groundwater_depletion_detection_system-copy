# System Architecture & Class Diagrams

**Project**: Satellite-Enhanced Groundwater Level Prediction and Sustainable Extraction Modeling System  
**Date**: August 2026  

---

## 1. High-Level System Architecture Diagram

```mermaid
graph TD
    subgraph Data Acquisition & Ingestion Layer
        A1["CHIRPS Precipitation"] --> B["GroundwaterDataLoader"]
        A2["MODIS Evapotranspiration"] --> B
        A3["GLDAS Soil/Snow/Canopy"] --> B
        A4["GRACE/GRACE-FO TWSA"] --> B
        A5["Piezometer Well Network"] --> B
    end

    subgraph Downscaling & Physics Engine
        B --> C1["SpatialDownscaler<br/>Ensemble RF/XGBoost"]
        C1 --> C2["Scale Preservation<br/>Mass Conservation"]
        C2 --> C3["GWSA Isolation &<br/>GWLA Conversion"]
        B --> C4["VadoseDelayEngine<br/>Gamma Convolution Kernel"]
    end

    subgraph Scientific Machine Learning Surrogates
        C3 --> D1["GNNLSTMSurrogate<br/>Spatiotemporal Graph Net"]
        C4 --> D1
        C3 --> D2["PINNSurrogate<br/>Dupuit-Boussinesq PDE Regularization"]
        C3 --> D3["FNOSurrogate<br/>2D Spectral Conv FFT"]
    end

    subgraph Risk Control & Optimization
        D1 --> E1["SplitConformalPredictor<br/>Distribution-Free UQ"]
        E1 --> E2["SCPChanceConstrainedMPC<br/>Sequential Convex Programming"]
    end

    subgraph Decision Support & API Layer
        E2 --> F1["FastAPI REST Server"]
        F1 --> F2["Web Dashboard / GIS UI"]
        F1 --> F3["HTML Assessment Reports"]
        F1 --> F4["Automated Risk Alerts"]
    end
```

---

## 2. Comprehensive UML Class Diagram

```mermaid
classDiagram
    class BaseDataProvider {
        <<abstract>>
        +get_grid_metadata() Dict
        +fetch_hydroclimate_rasters(timesteps) Dict
        +fetch_piezometer_observations(num_wells, timesteps) Dict
        +fetch_static_geophysics() Dict
    }

    class SyntheticDataProvider {
        +grid_shape: Tuple
        +mascon_grid_shape: Tuple
        +region_key: str
        +bounds: List
        +get_grid_metadata() Dict
        +fetch_hydroclimate_rasters(timesteps) Dict
        +fetch_piezometer_observations(num_wells, timesteps) Dict
        +fetch_static_geophysics() Dict
    }

    class RealtimeEarthEngineDataProvider {
        +ee_project_id: str
        +ee_initialized: bool
        +get_grid_metadata() Dict
        +fetch_hydroclimate_rasters(timesteps) Dict
    }

    class GroundwaterDataLoader {
        +data_mode: str
        +grid_shape: Tuple
        +provider: BaseDataProvider
        +set_data_mode(mode)
        +set_region(region_key, bounds)
        +load_processed_dataset(timesteps, num_wells) Dict
        +lat_lon_to_grid_index(lat, lon) Tuple
        +grid_index_to_lat_lon(row, col) Tuple
    }

    class SpatialDownscaler {
        +model_type: str
        +n_estimators: int
        +model: Regressor
        +fit_and_downscale(rasters, geophysics, mascon_grid_shape) Dict
    }

    class VadoseDelayEngine {
        +alpha_lag: float
        +beta_lag: float
        +compute_gamma_kernel(max_lag) ndarray
        +compute_effective_recharge(P, ET, Qs) ndarray
    }

    class GraphConvLayer {
        +linear_self: nn.Linear
        +linear_neigh: nn.Linear
        +forward(x, adj) Tensor
    }

    class GNNLSTMSurrogate {
        +num_wells: int
        +gnn_layers: ModuleList
        +lstm: LSTMCell
        +head_pred: nn.Linear
        +compute_adjacency(coords, radius) Tensor
        +forward(dynamic_seq, static_feats, adj) Tensor
    }

    class PINNSurrogate {
        +net: Sequential
        +forward(coords_t) Tensor
        +compute_pde_residual(coords_t, Sy, K) Tensor
        +compute_composite_loss(obs_coords_t, obs_h, colloc_coords_t) Tuple
    }

    class SpectralConv2d {
        +modes1: int
        +modes2: int
        +weights1: Parameter
        +weights2: Parameter
        +forward(x) Tensor
    }

    class FNOSurrogate {
        +conv0: SpectralConv2d
        +conv1: SpectralConv2d
        +conv2: SpectralConv2d
        +w0: Conv2d
        +w1: Conv2d
        +w2: Conv2d
        +forward(x) Tensor
    }

    class SplitConformalPredictor {
        +alpha: float
        +q_hat: float
        +calibrate(y_true, y_pred) float
        +get_safety_threshold(h_min) float
        +predict_interval(y_pred) Tuple
        +evaluate_coverage(y_test, y_pred_test) Dict
    }

    class SCPChanceConstrainedMPC {
        +horizon: int
        +num_wells: int
        +h_min: float
        +compute_jacobians(surrogate, G_k, E_k, climate_vec, static_geo, adj) Tuple
        +solve_optimal_pumping(surrogate, G_0, climate_horizon, static_geo, q_hat, adj) Dict
    }

    class FrameworkEvaluator {
        +compute_metrics(y_true, y_pred, h_min) Dict
        +run_feature_ablation_matrix(dataset, downscaler_results, Reff) Dict
        +run_spatial_kfold_cv(dataset, k_folds) Dict
    }

    BaseDataProvider <|-- SyntheticDataProvider
    BaseDataProvider <|-- RealtimeEarthEngineDataProvider
    GroundwaterDataLoader o-- BaseDataProvider
    GNNLSTMSurrogate *-- GraphConvLayer
    FNOSurrogate *-- SpectralConv2d
    SCPChanceConstrainedMPC ..> GNNLSTMSurrogate : autograd Jacobians
    SCPChanceConstrainedMPC ..> SplitConformalPredictor : safety bound
```

---

## 3. Data Flow Diagram (DFD - Level 1)

```
[Satellite Data (GRACE, CHIRPS, MODIS)] ───► (1. Data Ingestion & Spline Interpolation)
                                                            │
                                                            ▼
                                                [Normalized Rasters & Wells]
                                                            │
                                                            ▼
                                                (2. Spatial Downscaling & Vadose Delay)
                                                            │
                                                            ▼
                                                [GWLA Rasters & Effective Recharge R_eff]
                                                            │
                                                            ▼
                                                (3. Dynamic Surrogates: GNN / PINN / FNO)
                                                            │
                                                            ▼
                                                [Forecast Hydraulic Heads G_{t+1}]
                                                            │
                                                            ▼
                                                (4. Split Conformal UQ Calibration)
                                                            │
                                                            ▼
                                                [Empirical Error Margin q_hat]
                                                            │
                                                            ▼
                                                (5. SCP CCMPC Pumping Optimizer)
                                                            │
                                                            ▼
                                                [Optimal Pumping Quotas E_{1:H}*]
                                                            │
                                                            ▼
                                                (6. FastAPI Dashboard & HTML Reports)
```

---

## 4. Sequence Diagram: Real-Time Location Query & SCP Control Loop

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Policymaker
    participant UI as Web Dashboard
    participant API as FastAPI Server (app.py)
    participant Loader as GroundwaterDataLoader
    participant Surrogate as GNNLSTMSurrogate
    participant Conformal as SplitConformalPredictor
    participant MPC as SCPChanceConstrainedMPC

    User->>UI: Select Location (Lat, Lon) & Horizon H
    UI->>API: POST /api/v1/forecast/location_predict
    API->>Loader: lat_lon_to_grid_index(lat, lon)
    Loader-->>API: Return (row, col)
    API->>Surrogate: forward(dynamic_seq, static_feats, adj)
    Surrogate-->>API: Predicted Head Series G_hat
    API->>Conformal: predict_interval(G_hat)
    Conformal-->>API: Bounds [G_hat - q_hat, G_hat + q_hat]
    API-->>UI: Location Forecast Payload & Risk Status

    User->>UI: Click "Solve Pumping Quota"
    UI->>API: POST /api/v1/control/pumping_quotas
    API->>MPC: solve_optimal_pumping(surrogate, G_0, climate_horizon, static_geo, q_hat, adj)
    loop Sequential Convex Programming (SCP)
        MPC->>Surrogate: compute_jacobians(G_nom, E_nom) via autograd
        Surrogate-->>MPC: State Jacobians A_k, Control Jacobians B_k
        MPC->>MPC: Formulate Convex QP Subproblem in CVXPY
        MPC->>MPC: Solve QP & update trust region delta_k
    end
    MPC-->>API: Return Optimal Quota E* & Predicted Safe Heads
    API-->>UI: Render Quota Schedule & Risk Alerts
```
