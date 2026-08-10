# Removal & Refactoring Guide

**Project**: Satellite-Enhanced Groundwater Level Prediction and Sustainable Extraction Modeling System  
**Date**: August 2026  

---

## 1. Summary of Items to Remove or Refactor

To elevate the codebase from a functional prototype to a clean, production-ready scientific computing framework, several mock fallbacks, hardcoded noise injections, and redundant code structures should be refactored or eliminated.

---

## 2. Itemized Refactoring & Removal List

### 2.1 Remove Synthetic Noise Injection in Conformal Calibration (`src/api/app.py`)
- **Location**: `src/api/app.py`, Line 48 & Line 749.
- **Current Code**:
  ```python
  # Calibrate conformal predictor
  y_true = self.dataset["wells"]["G_filled"]
  y_pred = y_true + np.random.normal(0, 0.2, y_true.shape)
  self.conformal.calibrate(y_true, y_pred)
  ```
- **Why Remove**: Adding artificial Gaussian noise `np.random.normal(0, 0.2)` mocks model error instead of measuring actual surrogate network residuals.
- **Refactoring Target**:
  ```python
  # Pass actual neural surrogate forecasts over calibration split D_calib
  y_true = self.dataset["wells"]["G_filled"]
  with torch.no_grad():
      y_pred_tensor = self.surrogate(dynamic_seq, static_feats, adj)
      y_pred = y_pred_tensor.numpy()
  self.conformal.calibrate(y_true, y_pred)
  ```

---

### 2.2 Refactor Linear Fallback Dynamics in SCP MPC (`src/control/scp_mpc.py`)
- **Location**: `src/control/scp_mpc.py`, Lines 77–79 & Lines 92–98.
- **Current Code**:
  ```python
  else:
      # Fallback simple linear expansion
      G_next = G_t[0, 0, :] - 0.1 * E_t[0, 0, :] + 0.05 * climate_t[0, 0, :, 0]
  ```
- **Why Refactor**: If the surrogate model fails to attach PyTorch gradients, the solver silently falls back to a hand-coded linear equation, bypassing the GNN-LSTM / PINN physics.
- **Refactoring Target**: Raise an explicit warning or error when `requires_grad=True` is lost, ensuring state transition Jacobians $A_k = \frac{\partial f}{\partial G}$ and $B_k = \frac{\partial f}{\partial E}$ are always computed directly from the neural network computational graph.

---

### 2.3 Clarify Realtime GEE Diagnostic Status (`src/ingestion/realtime_provider.py`)
- **Location**: `src/ingestion/realtime_provider.py`, Lines 43–47 & Lines 67–70.
- **Current Code**:
  ```python
  except Exception as e:
      logger.warning(
          f"Google Earth Engine API initialization skipped/failed ({e}). "
          "Operating in Realtime Standby mode with synthetic fallback."
      )
  ```
- **Why Refactor**: When running in `realtime` mode without GEE credentials, the code silently reverts to synthetic data without alerting web UI users.
- **Refactoring Target**: Return an explicit diagnostic status flag (`"GEE_UNAUTHENTICATED"`) in `get_grid_metadata()`, prompting the user in the UI to run `earthengine authenticate`.

---

### 2.4 Cleanup Static Inspection Images (`src/insp/`)
- **Location**: `d:/Ground_water/src/insp/` (`home_page_2.png`, `landing_page.png`, etc.).
- **Action**: These images were initial UI wireframes. If they are no longer rendered in `web/index.html` or `web/app.js`, remove them from `src/insp/` to keep the repository lightweight.

---

## 3. Recommended Code Hygiene Checklist

- [ ] Eliminate `np.random.normal` calibration mocks in `app.py`.
- [ ] Add explicit gradient attachment assertions in `scp_mpc.py`.
- [ ] Add GEE status indicator badge in `web/index.html` header.
- [ ] Prune unused image assets in `src/insp/`.
- [ ] Add docstrings and type hints to any newly added utility functions.
