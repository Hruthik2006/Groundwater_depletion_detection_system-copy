# Actionable Improvement Roadmap to Production

**Project**: Satellite-Enhanced Groundwater Level Prediction and Sustainable Extraction Modeling System  
**Date**: August 2026  

---

## 1. Roadmap Overview & Timeline

This roadmap outlines a 4-phase engineering plan to upgrade the groundwater framework from an initial functional implementation to a full production-grade operational system.

```
Phase 1: Real Data Ingestion (Weeks 1–2) ──────► Phase 2: Surrogate Pre-Training (Weeks 3–4)
                                                                       │
                                                                       ▼
Phase 4: Production GIS UI (Weeks 7–8) ◄────── Phase 3: Calibrated Risk Control (Weeks 5–6)
```

---

## 2. Phase-by-Phase Development Milestones

### Phase 1: Real Remote Sensing & Piezometric Data Pipeline (Weeks 1–2)
- **Objective**: Replace synthetic fallbacks with live remote sensing data streams.
- **Tasks**:
  1. Complete Google Earth Engine (`ee`) data extraction pipelines for CHIRPS precipitation, MODIS ET, and GLDAS soil moisture/SWE.
  2. Implement local NASA JPL PO.DAAC NetCDF downloader for native GRACE/GRACE-FO CSR RL06.2 mascon grids.
  3. Integrate USGS NWIS `dataretrieval` API to fetch real piezometer time series for the Glacial Aquifer System of Illinois and High Plains Ogallala Aquifer.
  4. Implement Ordinary Kriging spatial interpolation for unmonitored piezometric grid cells.
- **Deliverables**: `src/ingestion/gee_pipeline.py`, `src/ingestion/usgs_provider.py`.

---

### Phase 2: Neural Surrogate Model Training & Checkpointing (Weeks 3–4)
- **Objective**: Pre-train dynamic neural surrogate models on historical hydrological data.
- **Tasks**:
  1. Build offline training pipeline script `scripts/train_surrogates.py`.
  2. Train `GNNLSTMSurrogate` on 2005–2025 spatiotemporal piezometric sequences with MSE loss + Adam optimizer.
  3. Train `PINNSurrogate` using multi-task loss $\mathcal{L} = \mathcal{L}_{\mathrm{data}} + \lambda_{\mathrm{pde}} \mathcal{L}_{\mathrm{pde}}$ with Dupuit-Boussinesq residual.
  4. Train `FNOSurrogate` on 2D groundwater flow field grid simulations.
  5. Save trained weights to `models/checkpoints/` (`gnn_lstm_best.pt`, `pinn_best.pt`, `fno_best.pt`).
- **Deliverables**: `scripts/train_surrogates.py`, `models/checkpoints/*.pt`.

---

### Phase 3: Calibrated Conformal Risk Control & SCP Optimization (Weeks 5–6)
- **Objective**: Ensure distribution-free safety guarantees and robust SCP convergence.
- **Tasks**:
  1. Calibrate `SplitConformalPredictor` using actual forward pass predictions from `GNNLSTMSurrogate` on held-out validation set $D_{\mathrm{calib}}$.
  2. Add exact automatic differentiation Jacobian computation in `SCPChanceConstrainedMPC` without linear fallbacks.
  3. Support CLARABEL / ECOS / OSQP convex solvers in CVXPY with dynamic trust-region expansion ($\eta_{\mathrm{expand}} = 1.25$) and shrinking ($\eta_{\mathrm{shrink}} = 0.25$).
  4. Implement rolling-origin evaluation metrics (RMSE, MAE, CVR) in `FrameworkEvaluator`.
- **Deliverables**: Updated `src/conformal/split_conformal.py`, `src/control/scp_mpc.py`.

---

### Phase 4: Production GIS Web Interface & Policy Support (Weeks 7–8)
- **Objective**: Deliver a web interface for policy-makers and water resource managers.
- **Tasks**:
  1. Integrate Leaflet.js / Mapbox GL in `web/app.js` to render interactive geospatial raster layers over satellite maps.
  2. Implement location search bar with geocoding (search by city, address, or lat/lon).
  3. Enhance PDF/HTML report generator to include custom district logos, hydrograph plots, and compliance sign-off blocks.
  4. Add CSV/GeoJSON export buttons for optimal pumping quota schedules.
- **Deliverables**: Upgraded `web/index.html`, `web/app.js`, `src/api/app.py`.

---

## 3. Summary of Deliverables & Validation Criteria

| Phase | Core Deliverable | Target Completion | Key Validation Metric |
|---|---|:---:|---|
| **Phase 1** | GEE & USGS Real Data Ingestion | Week 2 | Successful ingestion of 20-year monthly rasters & well observations without synthetic fallbacks. |
| **Phase 2** | Pre-trained Neural Surrogates | Week 4 | GNN-LSTM & PINN validation RMSE $<\,0.35\text{ m}$ across test wells. |
| **Phase 3** | Calibrated SCP CCMPC Solver | Week 6 | Empirical coverage $\ge 95\%$ on $D_{\mathrm{test}}$; SCP convergence rate $> 98\%$. |
| **Phase 4** | Production GIS Web Dashboard | Week 8 | Sub-second point forecast response time; interactive Leaflet raster rendering. |
