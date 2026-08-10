# Dataset Specification & Data Pipeline Guide

**Project**: Satellite-Enhanced Groundwater Level Prediction and Sustainable Extraction Modeling System  
**Date**: August 2026  

---

## 1. Remote Sensing & Piezometric Datasets Summary

To bridge macro-scale satellite observations with micro-scale well dynamics, the system processes six distinct geospatial data streams:

| Feature Name | Primary Data Source | Native Spatial Resolution | Native Temporal Resolution | Physical Units | Physical Role in Hydrodynamic System |
|---|---|---|---|---|---|
| **Precipitation ($P$)** | CHIRPS / ERA5-Land | 0.05° (~5 km grid) | Pentad / Monthly | mm / month | Primary mass input driving surface infiltration and vertical aquifer recharge flux. |
| **Evapotranspiration ($\mathrm{ET}$)** | MODIS (MOD16A2) / WaPOR | 500 m / 250 m | 8-Day / Monthly | mm / month | Primary atmospheric output depleting soil moisture and shallow unconfined storage. |
| **Soil Moisture Anomaly ($\mathrm{SMSA}$)** | GLDAS Noah / SMAP | 0.25° (~25 km grid) | Monthly | cm equivalent water | Direct measurement of unsaturated vadose zone storage variations. |
| **Snow Water Equivalent ($\mathrm{SWEA}$)** | GLDAS / SNODAS | 0.25° (~25 km grid) | Monthly | cm equivalent water | Surface frozen storage anomaly contributing to spring snowmelt infiltration. |
| **Canopy Water Storage ($\mathrm{CWSA}$)** | GLDAS Noah LSM | 0.25° (~25 km grid) | Monthly | cm equivalent water | Intercepted vegetation moisture storage anomaly. |
| **Terrestrial Water Storage ($\mathrm{TWSA}$)** | NASA GRACE / GRACE-FO CSR Mascons | 0.25° / 3° mascons (~300 km native) | Monthly | cm equivalent water | Total vertical column mass anomaly integrating surface, soil, snow, and groundwater storage. |
| **Piezometric Head ($G$)** | USGS NWIS / State Water Surveys | Point Well Locations | Monthly / Daily | meters (MSL or depth) | Localized ground truth target variable tracking piezometric head changes. |
| **Volumetric Extraction ($E$)** | Flow Meters / Agricultural Records | Point / District Aggregated | Monthly | m³ / month | Active anthropogenic pumping discharge vector acting as the control input. |

---

## 2. Mathematical Preprocessing Pipeline

### 2.1 Cubic Spline Temporal Interpolation for Piezometer Data
Piezometric well observation records often contain missing values due to sensor maintenance or manual measurement gaps. For each well $i$, missing time points are interpolated using a clamped **Cubic Spline**:

$$G_i(t) = \mathrm{CubicSpline}\left(t_{\mathrm{obs}}, \, G_i(t_{\mathrm{obs}})\right)$$

When fewer than 4 valid observations exist, the pipeline falls back to a hydrogeological regional mean baseline fill:

$$G_i(t) = \begin{cases} \mathrm{CubicSpline}(t), & \text{if } N_{\mathrm{obs}} \ge 4 \\ \mathrm{mean}(G_i), & \text{otherwise} \end{cases}$$

### 2.2 Spatial Z-Score Normalization
Hydroclimate rasters are normalized per spatial cell across the historical timeline to preserve spatial heterogeneity while scaling inputs for neural surrogate stability:

$$\tilde{X}(t, x, y) = \frac{X(t, x, y) - \mu_X(x, y)}{\sigma_X(x, y) + \epsilon}$$

where $\mu_X(x, y)$ and $\sigma_X(x, y)$ represent the pixel-wise mean and standard deviation over time $T$.

### 2.3 Scale Preservation Mass Conservation Formula
During spatial downscaling, coarse GRACE mascons $M$ are refined into high-resolution 4 km cells. To prevent volume distortion, downscaled grids are scaled to strictly preserve original satellite mass totals:

$$\mathrm{TWSA}_{\mathrm{scaled}}(x, y, t) = \mathrm{TWSA}_{\mathrm{down}}(x, y, t) \cdot \left[ \frac{\mathrm{TWSA}_{\mathrm{native}}(M, t)}{\frac{1}{|M|} \sum_{(s, u) \in M} \mathrm{TWSA}_{\mathrm{down}}(s, u, t)} \right]$$

### 2.4 Groundwater Storage Anomaly ($\mathrm{GWSA}$) Isolation
Shallow water storage anomalies are subtracted from total mass column variations using GLDAS LSM simulations:

$$\mathrm{GWSA}(x, y, t) = \mathrm{TWSA}_{\mathrm{scaled}}(x, y, t) - \mathrm{SMSA}(x, y, t) - \mathrm{SWEA}(x, y, t) - \mathrm{CWSA}(x, y, t)$$

Converted to well-scale Groundwater Level Anomaly ($\mathrm{GWLA}$) via localized specific yield $S_y(x, y)$:

$$\mathrm{GWLA}(x, y, t) = \frac{\mathrm{GWSA}(x, y, t)}{100 \cdot S_y(x, y)} \quad \text{[meters]}$$

---

## 3. Study Regions & Hydrogeological Presets

The codebase includes configuration presets for four major global aquifer basins:

1. **Illinois Glacial Aquifer System (USA)**:
   - Unconfined glaciofluvial sand and gravel deposits.
   - High piezometer density (~16–64 wells per watershed), high seasonal agricultural pumping.
2. **High Plains / Ogallala Aquifer (USA)**:
   - Deep unconfined tertiary sand/gravel aquifer.
   - Severe drawdown rates (>1 m/yr), thick vadose zone (30–60 m).
3. **Indo-Gangetic Aquifer Basin (India)**:
   - Heavy alluvial aquifer system supporting intensive double-crop irrigation.
   - High monsoonal recharge pulses paired with extreme summer extraction.
4. **North German Basin (Europe)**:
   - Slow-responding porous media aquifer system with long multi-year lag responses (~3,000 reference wells).

---

## 4. Real Data Acquisition Checklist for Production Execution

To transition from synthetic mode (`data_mode: "synthetic"`) to full real-data execution (`data_mode: "realtime"`), complete the following steps:

- [ ] Register a Google Earth Engine (GEE) project ID and run `earthengine authenticate`.
- [ ] Ingest CHIRPS dataset: `ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD")`.
- [ ] Ingest MODIS ET dataset: `ee.ImageCollection("MODIS/061/MOD16A2")`.
- [ ] Ingest GLDAS Noah dataset: `ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3M")`.
- [ ] Download CSR GRACE RL06.2 Mascon NetCDF files from NASA JPL PO.DAAC.
- [ ] Ingest USGS NWIS piezometric head time series using `dataretrieval` Python library.
