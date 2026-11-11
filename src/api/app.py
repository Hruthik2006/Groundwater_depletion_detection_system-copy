import os
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import numpy as np

from src.api.presentation import render_location_report, HELP_GUIDE_HTML
from src.pipeline.pipeline import Pipeline
from src.pipeline.config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Satellite-Enhanced Groundwater Forecasting & SCP-CCMPC API",
    description="Operational REST API for satellite gravimetry downscaling, conformal UQ, and non-convex SCP model predictive control.",
    version="1.0.0",
)

# Global State Container
class SystemState:
    """State container wrapped around the deep pipeline seam.

    The ``Pipeline`` owns the single ingest -> downscale -> vadose -> conformal
    chain. ``SystemState`` keeps the handles existing routes and tests read
    (``dataset``, ``downscaling_res``, ``Reff``, ``surrogate``, ...) as live
    aliases into the pipeline so any rebuild is automatically reflected, plus
    the operational event log.
    """

    def __init__(self):
        self.pipeline = Pipeline()

        # Stable object graph handles (never replaced by a rebuild).
        self.data_loader = self.pipeline.data_loader
        self.downscaler = self.pipeline.downscaler
        self.vadose_engine = self.pipeline.vadose_engine
        self.surrogate = self.pipeline.surrogate
        self.conformal = self.pipeline.conformal
        self.mpc = self.pipeline.mpc

        self.history_log: List[Dict[str, Any]] = []
        self._mpc_cache: Dict[tuple, Dict[str, Any]] = {}

        # Build the chain once: loads pre-trained weights, downscales,
        # computes effective recharge, recalibrates the conformal predictor
        # against the current data, and stamps the event log.
        self.pipeline.build()

        self.log_event(
            "SYSTEM_INIT",
            "System initialized with pre-trained dynamic surrogate and real conformal calibration.",
        )

    # -- live aliases into the pipeline so context switches stay in sync ------
    @property
    def dataset(self):
        return self.pipeline.dataset

    @property
    def downscaling_res(self):
        return self.pipeline.downscaling_res

    @property
    def Reff(self):
        return self.pipeline.Reff

    @property
    def baseline_cache(self):
        return self.pipeline.baseline_cache

    @baseline_cache.setter
    def baseline_cache(self, value):
        self.pipeline.baseline_cache = value

    @property
    def ablation_cache(self):
        return self.pipeline.ablation_cache

    @ablation_cache.setter
    def ablation_cache(self, value):
        self.pipeline.ablation_cache = value

    def calibrate_conformal_from_surrogate(self) -> float:
        return self.pipeline.calibrate_conformal_from_surrogate()

    def log_event(self, event_type: str, detail: str, extra: Optional[Dict[str, Any]] = None):
        import datetime
        entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": event_type,
            "data_mode": self.data_loader.data_mode,
            "detail": detail,
        }
        if extra:
            entry.update(extra)
        self.history_log.insert(0, entry)
        if len(self.history_log) > 200:
            self.history_log.pop()

    def ensure_evaluation(self):
        """Computes (baselines, ablation) once per dataset build and reuses caches."""
        from src.evaluation.benchmarks import FrameworkEvaluator
        evaluator = FrameworkEvaluator()
        if getattr(self, "baseline_cache", None) is None:
            self.baseline_cache = evaluator.fit_paper_baselines(self.dataset)
        if getattr(self, "ablation_cache", None) is None:
            self.ablation_cache = evaluator.run_autoregressive_ablation(self.dataset)
        return self.baseline_cache, self.ablation_cache

    def resolve_mpc(
        self,
        horizon: int,
        alpha: float,
        h_min: float,
        h_target: float,
        e_max: Optional[float] = None,
        gamma_pump: Optional[float] = None,
        sigma_slack: Optional[float] = None,
        delta_trust: Optional[float] = None,
        max_iter: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Memoized SCP-CCMPC solve for report rendering. The cache key folds in
        every tunable plus the live conformal margin, so stale data or a
        recalibration can never serve an outdated quota schedule.
        """
        c = self.pipeline.config
        if e_max is None:
            e_max = c.e_max
        if gamma_pump is None:
            gamma_pump = c.gamma_pump
        if sigma_slack is None:
            sigma_slack = c.sigma_slack
        if delta_trust is None:
            delta_trust = c.delta_trust
        if max_iter is None:
            max_iter = c.max_scp_iters

        mpc = self.pipeline.mpc
        q_hat = float(self.conformal.q_hat)
        key = (
            int(horizon),
            round(float(alpha), 6),
            round(float(h_min), 4),
            round(float(h_target), 4),
            round(float(e_max), 4),
            round(float(gamma_pump), 4),
            round(float(sigma_slack), 2),
            round(float(delta_trust), 4),
            int(max_iter),
            round(q_hat, 4),
        )
        if key in self._mpc_cache:
            return self._mpc_cache[key]

        snapshot = (
            mpc.H, mpc.alpha, mpc.h_min, mpc.h_target, mpc.E_max,
            mpc.w_energy, mpc.sigma_slack, mpc.delta_0, mpc.max_scp_iters,
        )
        mpc.H, mpc.alpha = int(horizon), float(alpha)
        mpc.h_min, mpc.h_target = float(h_min), float(h_target)
        mpc.E_max = float(e_max)
        mpc.w_energy = float(gamma_pump)
        mpc.sigma_slack = float(sigma_slack)
        mpc.delta_0 = float(delta_trust)
        mpc.max_scp_iters = int(max_iter)

        dataset = self.dataset
        G_0 = dataset.heads()[:, -1]
        num_wells = len(G_0)
        climate_horizon = np.zeros((int(horizon), num_wells, 2))
        T_max = self.Reff.shape[0]
        for ts in range(int(horizon)):
            if self.Reff.ndim == 3:
                climate_horizon[ts, :, 0] = self.Reff[ts % T_max, :num_wells, 0]
            else:
                climate_horizon[ts, :, 0] = 0.5
        static_geo = dataset.static_features(num_wells)

        adj = self.surrogate.compute_adjacency(dataset.coords)
        try:
            res = mpc.solve_optimal_pumping(
                self.surrogate,
                G_0=G_0,
                climate_horizon=climate_horizon,
                static_geo=static_geo,
                q_hat=q_hat,
                adj=adj,
            )
        except Exception as ex:
            logger.warning(f"MPC solve failed for report rendering ({ex}); returning flat quota fallback.")
            res = {
                "converged": False,
                "optimal_pumping": np.zeros((int(horizon), num_wells)),
                "predicted_heads": np.full((int(horizon), num_wells), float(np.mean(G_0))),
                "safety_bound_tightened": float(h_min) + q_hat,
                "q_hat": q_hat,
                "final_cost": None,
                "scp_history": [],
            }

        (mpc.H, mpc.alpha, mpc.h_min, mpc.h_target, mpc.E_max,
         mpc.w_energy, mpc.sigma_slack, mpc.delta_0, mpc.max_scp_iters) = snapshot

        self._mpc_cache[key] = res
        return res

state = SystemState()


# Request Schemas
class DataSourceConfigRequest(BaseModel):
    data_mode: str  # 'synthetic' or 'realtime'

class LocationConfigRequest(BaseModel):
    region_key: str = "ganges"  # illinois, north_german, high_plains, ganges, custom
    bounds: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat]

class LocationPredictRequest(BaseModel):
    lat: float
    lon: float
    horizon: int = 12

class PumpingQuotaRequest(BaseModel):
    horizon: int = 12
    h_min: float = DEFAULT_CONFIG.h_min
    h_target: float = DEFAULT_CONFIG.h_target
    alpha: float = DEFAULT_CONFIG.alpha
    # SCP tunables posted by the frontend; None keeps the sealed Config default.
    e_max: Optional[float] = None
    gamma_pump: Optional[float] = None
    sigma_slack: Optional[float] = None
    delta_trust: Optional[float] = None
    max_iter: Optional[int] = None




@app.get("/api/v1/status")
def get_system_status():
    meta = state.dataset.metadata
    return {
        "status": "operational",
        "data_mode": state.data_loader.data_mode,
        "provider_metadata": meta,
        "conformal_q_hat": state.conformal.q_hat,
        "grid_shape": meta["grid_shape"],
        "provider_serves": meta.get("serves"),
        # Live GEE ingestion progress (realtime provider only; None for
        # providers that do not report it) — polled by the loading UI.
        "ingestion_progress": getattr(state.data_loader.provider, "progress", None),
    }


@app.post("/api/v1/config/data_source")
def set_data_source_mode(req: DataSourceConfigRequest):
    valid_modes = ["synthetic", "realtime", "dwlr"]
    if req.data_mode.lower() not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"data_mode must be one of: {', '.join(valid_modes)}",
        )

    old_mode = state.data_loader.data_mode
    state.pipeline.set_data_mode(req.data_mode.lower())

    state.log_event("DATA_CHANNEL_SWITCH", f"Data source mode switched from {old_mode} to {req.data_mode.lower()}.")

    return {
        "message": f"Data source mode updated to {req.data_mode}",
        "metadata": state.dataset["metadata"],
    }


@app.post("/api/v1/config/location")
def set_location_config(req: LocationConfigRequest):
    """
    Sets geographic hydrogeological region preset or custom bounding box [min_lon, min_lat, max_lon, max_lat].
    """
    state.pipeline.set_region(region_key=req.region_key, bounds=req.bounds)

    state.log_event("LOCATION_SWITCH", f"Location region set to {req.region_key} (Name: {state.dataset['metadata'].get('region_name', 'N/A')}).")

    return {
        "message": f"Location updated to region: {req.region_key}",
        "metadata": state.dataset["metadata"],
    }


def _ensure_region_for_coords(lat: float, lon: float):
    target_region, previous_region = state.pipeline.ensure_region_for_coords(lat, lon)
    if target_region != previous_region:
        state.log_event("AUTO_REGION_SWITCH", f"Auto-switched region to '{target_region}' for pinned coordinates ({lat}, {lon}).")


@app.post("/api/v1/forecast/location_predict")
def predict_location_groundwater(req: LocationPredictRequest):
    """
    Predicts localized groundwater level time series G(lat, lon, t) and projects 2D grid rasters.
    """
    _ensure_region_for_coords(req.lat, req.lon)
    forecast = state.pipeline.analytic_forecast(req.lat, req.lon, max(1, req.horizon))

    q_hat = forecast["conformal_q_hat"]
    depletion_risk = forecast["risk_status"]

    GWLA = state.pipeline.downscaling_res["GWLA"]  # (T, H, W)
    T_max = GWLA.shape[0]
    horizon = max(1, req.horizon)

    state.log_event("LOCATION_PREDICTION", f"Point prediction query for Lat={req.lat}, Lon={req.lon} (Grid cell R:{forecast['row']}, C:{forecast['col']}).")

    return {
        "query_coordinates": {"lat": req.lat, "lon": req.lon},
        "grid_cell": {"row": forecast["row"], "col": forecast["col"]},
        "region_key": forecast["region_key"],
        "region_name": forecast["region_name"],
        "geophysics": forecast["geophysics"],
        "conformal_q_hat": q_hat,
        "depletion_risk": depletion_risk,
        "recommended_pumping_quota_m3": round(forecast["recommended_quota"], 2),
        "forecast": {
            "predicted_heads_m": [round(h, 4) for h in forecast["heads"]],
            "conformal_lower_bounds_m": [round(h, 4) for h in forecast["lower_bounds"]],
            "conformal_upper_bounds_m": [round(h, 4) for h in forecast["upper_bounds"]],
            "gwla_anomalies_m": [round(g, 4) for g in forecast["gwla_series"]],
            "effective_recharge_cm": [round(r, 4) for r in forecast["reff_series"]],
        },
        "raster_slice": GWLA[(horizon - 1) % T_max].tolist(),
    }


@app.get("/api/v1/reports/view")
def view_location_report(
    lat: float = 40.15,
    lon: float = -88.25,
    horizon: int = 12,
    sec_summary: int = 1,
    sec_stratigraphy: int = 1,
    sec_conformal: int = 1,
    horizon_conformal: int = 12,
    sec_lp30day: int = 0,
    sec_baselines: int = 0,
    sec_ablation: int = 1,
    sec_pumping: int = 0,
    horizon_pumping: int = 12,
    sec_hydrograph: int = 1,
    horizon_hydrograph: int = 24,
    sec_math: int = 1,
    sec_table: int = 1,
    sec_recommendations: int = 1,
    labels: Optional[str] = None,
    vals: Optional[str] = None,
    lower: Optional[str] = None,
    upper: Optional[str] = None,
):
    """
    Renders a comprehensive, printable HTML Location Groundwater Assessment Report with MathJax LaTeX rendering
    and dynamic selection of analytical prediction suites and custom forecast horizons.

    The optional labels/vals/lower/upper params carry the exact series shown
    in the dashboard's Prediction 1 chart (the Generate-PDF flow in app.js
    extracts them from the home chart) so the printed chart matches the home
    screen. Without them, the chart falls back to the analytic point forecast.
    """
    _ensure_region_for_coords(lat, lon)
    row, col = state.data_loader.lat_lon_to_grid_index(lat, lon)

    c = state.pipeline.config

    # The report table shows `horizon_conformal` months by default, but a
    # request for horizon != 12 promotes it (matching the original report math).
    eff_conformal = horizon if (horizon != 12 and horizon_conformal == 12) else horizon_conformal
    h_len = max(1, eff_conformal if sec_conformal else horizon)

    forecast = state.pipeline.analytic_forecast(lat, lon, h_len)

    # Validate the optional dashboard chart series (JSON arrays of numbers,
    # equal lengths, sane size). Anything malformed is ignored, not fatal.
    chart_series = None
    if vals:
        try:
            _v = json.loads(vals)
            _lo = json.loads(lower) if lower else None
            _up = json.loads(upper) if upper else None
            _lb = json.loads(labels) if labels else None

            def _numlist(x):
                return (
                    isinstance(x, list)
                    and 0 < len(x) <= 60
                    and all(isinstance(i, (int, float)) and not isinstance(i, bool) for i in x)
                )

            if (
                _numlist(_v)
                and (_lo is None or (_numlist(_lo) and len(_lo) == len(_v)))
                and (_up is None or (_numlist(_up) and len(_up) == len(_v)))
            ):
                chart_series = {
                    "labels": (
                        [str(x) for x in _lb]
                        if isinstance(_lb, list) and len(_lb) == len(_v)
                        else [f"Month {t + 1}" for t in range(len(_v))]
                    ),
                    "heads": [float(x) for x in _v],
                    "lower_bounds": [float(x) for x in _lo] if _lo is not None else None,
                    "upper_bounds": [float(x) for x in _up] if _up is not None else None,
                }
        except Exception:
            chart_series = None

    region_name = forecast["region_name"]
    q_hat = forecast["conformal_q_hat"]
    Sy = forecast["geophysics"]["Sy"]
    K = forecast["geophysics"]["K_m_per_day"]

    # Removed from the printed report (2026-11-11): Prediction 2 (30-day LP),
    # Prediction 3 (paper baselines) and Prediction 5 (SCP pumping quotas).
    # They are global, not location-specific, so the report no longer runs
    # those solvers at all — the params above are accepted but ignored.
    sec_lp30day = 0
    sec_baselines = 0
    sec_pumping = 0
    lp_result = None
    mpc_result = None

    # Live framework ablation metrics (baselines are computed alongside
    # by ensure_evaluation but are no longer rendered in the report)
    baselines = None
    ablation = None
    if sec_ablation:
        baselines, ablation = state.ensure_evaluation()

    # Live hydrograph rasters at the query cell
    hydrograph = None
    if sec_hydrograph:
        try:
            hydrograph = state.pipeline.hydrograph_series(lat, lon, max(1, horizon_hydrograph))
        except Exception as ex:
            logger.warning(f"Live hydrograph series failed for report ({ex}); omitting hydrograph data.")

    html_content = render_location_report(
        lat=lat,
        lon=lon,
        row=row,
        col=col,
        region_name=region_name,
        sy=Sy,
        k=K,
        q_hat=q_hat,
        forecast=forecast,
        lp_result=lp_result,
        mpc_result=mpc_result,
        baselines=baselines,
        ablation=ablation,
        hydrograph=hydrograph,
        chart_series=chart_series,
        data_mode=c.data_mode,
        horizon=horizon,
        sec_summary=sec_summary,
        sec_stratigraphy=sec_stratigraphy,
        sec_conformal=sec_conformal,
        horizon_conformal=horizon_conformal,
        sec_lp30day=sec_lp30day,
        sec_baselines=sec_baselines,
        sec_ablation=sec_ablation,
        sec_pumping=sec_pumping,
        horizon_pumping=horizon_pumping,
        sec_hydrograph=sec_hydrograph,
        horizon_hydrograph=horizon_hydrograph,
        sec_math=sec_math,
        sec_table=sec_table,
        sec_recommendations=sec_recommendations,
        critical_threshold=c.critical_threshold,
        critical_hard_threshold=c.critical_hard_threshold,
        h_min=c.h_min,
    )
    return HTMLResponse(content=html_content)


@app.get("/api/v1/forecast/spatial_drawdown")
def get_spatial_drawdown_forecast(horizon: int = 12, lat: float = None, lon: float = None):
    """
    Serves GeoJSON / JSON raster payload detailing spatial hydraulic head predictions
    across the target basin grid over specified planning horizon H.

    When lat/lon are supplied, the pipeline region is first aligned to those
    coordinates (same auto-switch as location_predict / reports). Without
    this, the dashboard chart silently served the previously active region's
    rasters under newly pinned coordinates until some other action happened
    to trigger the region rebuild — the graph appeared to "change" on its own.
    """
    if lat is not None and lon is not None:
        _ensure_region_for_coords(lat, lon)
    GWLA = state.downscaling_res["GWLA"]  # (T, H, W)
    H, W = GWLA.shape[1], GWLA.shape[2]
    T_max = GWLA.shape[0]
    
    h_len = max(1, horizon)
    ramp = state.pipeline.config.drawdown_ramp_per_cycle
    forecast_rasters = []
    for t_step in range(h_len):
        base_slice = GWLA[t_step % T_max]
        cycle = t_step // T_max
        if cycle > 0:
            slice_adj = np.clip(base_slice - (ramp * cycle), 0.0, 50.0)
            raster_slice = slice_adj.tolist()
        else:
            raster_slice = base_slice.tolist()

        forecast_rasters.append({
            "timestep": t_step + 1,
            "mean_gwla_m": float(np.mean(raster_slice)),
            "raster": raster_slice,
        })

    return {
        "type": "FeatureCollection",
        "horizon": h_len,
        "grid_shape": [H, W],
        "resolution_km": 4.0,
        "crs": "EPSG:4326",
        "forecasts": forecast_rasters,
    }


@app.get("/api/v1/forecast/spatial_drawdown_3d")
def get_spatial_drawdown_3d(horizon: int = 12, lat: float = None, lon: float = None):
    """
    Returns location-specific 3D hydrogeological stratigraphic vertex meshes
    and depth profiles (Terrain, Vadose, Water Table, Aquifer, Aquitard, Sea Level, Bedrock).
    Aligns the pipeline region to lat/lon when supplied (see spatial_drawdown).
    """
    if lat is not None and lon is not None:
        _ensure_region_for_coords(lat, lon)
    GWLA = state.downscaling_res["GWLA"]  # (T, H, W)
    H, W = GWLA.shape[1], GWLA.shape[2]
    Sy = state.dataset.geophysics["Sy"]
    z_bedrock = state.dataset.geophysics["z_bedrock"]
    region_key = state.data_loader.region_key

    # Location-specific hydrogeological stratigraphic profiles
    region_profiles = {
        "high_plains": {
            "terrain_base": 4.8,
            "vadose_base": 2.8,
            "water_base": 0.4,
            "aquifer_base": -1.2,
            "aquitard_base": -2.8,
            "bedrock_base": -4.8,
            "name": "High Plains / Ogallala Aquifer (USA)",
        },
        "north_german": {
            "terrain_base": 2.2,
            "vadose_base": 1.1,
            "water_base": 0.2,
            "aquifer_base": -0.5,
            "aquitard_base": -1.5,
            "bedrock_base": -2.8,
            "name": "North German Basin (Europe)",
        },
        "ganges": {
            "terrain_base": 3.4,
            "vadose_base": 1.8,
            "water_base": 0.1,
            "aquifer_base": -0.8,
            "aquitard_base": -2.2,
            "bedrock_base": -3.8,
            "name": "Indo-Gangetic Aquifer Basin (India)",
        },
        "illinois": {
            "terrain_base": 3.6,
            "vadose_base": 1.9,
            "water_base": 0.0,
            "aquifer_base": -0.9,
            "aquitard_base": -2.0,
            "bedrock_base": -3.5,
            "name": "Illinois Glacial Aquifer System (USA)",
        },
    }
    prof = region_profiles.get(region_key, region_profiles["illinois"])

    t_idx = min(horizon - 1, GWLA.shape[0] - 1)
    gwla_slice = GWLA[t_idx]

    vertices_3d = []
    for r in range(H):
        for c in range(W):
            x = -7.0 + (c / float(W - 1)) * 14.0
            y = 7.0 - (r / float(H - 1)) * 14.0

            topo_elev = prof["terrain_base"] + 0.6 * np.sin(r * 0.4) * np.cos(c * 0.4)
            z_water = float(prof["water_base"] + (gwla_slice[r, c] - 2.5) * 0.6)
            z_floor = float(prof["bedrock_base"] - (z_bedrock[r, c] - 20.0) * 0.08)

            vertices_3d.append({
                "row": r,
                "col": c,
                "x": round(x, 3),
                "y": round(y, 3),
                "z_terrain": round(float(topo_elev), 3),
                "z_water": round(z_water, 3),
                "z_bedrock": round(z_floor, 3),
                "gwla_m": float(gwla_slice[r, c]),
                "sy": float(Sy[r, c]),
            })

    return {
        "region_key": region_key,
        "region_name": prof["name"],
        "profile": prof,
        "horizon": horizon,
        "grid_shape": [H, W],
        "vertices": vertices_3d,
    }


@app.post("/api/v1/control/pumping_quotas")
def compute_pumping_quotas(req: PumpingQuotaRequest):
    """
    Computes optimal sustainable pumping quota vectors E_{1:H}^*
    bounded by conformal safety margins q_{1-alpha}.
    """
    c = state.pipeline.config
    state.conformal.alpha = req.alpha
    q_hat = state.conformal.q_hat

    # Apply every sealed up frontend-posted SCP tunable (None -> Config default).
    state.mpc.H = max(1, req.horizon)
    state.mpc.h_min = req.h_min
    state.mpc.h_target = req.h_target
    state.mpc.E_max = req.e_max if req.e_max is not None else c.e_max
    state.mpc.w_energy = req.gamma_pump if req.gamma_pump is not None else c.gamma_pump
    state.mpc.sigma_slack = req.sigma_slack if req.sigma_slack is not None else c.sigma_slack
    state.mpc.delta_0 = req.delta_trust if req.delta_trust is not None else c.delta_trust
    state.mpc.max_scp_iters = req.max_iter if req.max_iter is not None else c.max_scp_iters

    dataset = state.dataset
    G_0 = dataset.heads()[:, -1]
    num_wells = len(G_0)

    climate_horizon = np.zeros((state.mpc.H, num_wells, 2))
    T_max = state.Reff.shape[0]
    for t_step in range(state.mpc.H):
        climate_horizon[t_step, :, 0] = state.Reff[t_step % T_max, :num_wells, 0] if state.Reff.ndim == 3 else 0.5

    static_geo = dataset.static_features(num_wells)
    adj = state.surrogate.compute_adjacency(dataset.coords)

    res = state.mpc.solve_optimal_pumping(
        state.surrogate,
        G_0=G_0,
        climate_horizon=climate_horizon,
        static_geo=static_geo,
        q_hat=q_hat,
        adj=adj,
    )

    avg_quota = float(np.mean(res["optimal_pumping"]))
    state.log_event(
        "SCP_OPTIMIZATION",
        f"Solved SCP CCMPC (Horizon={state.mpc.H}, Alpha={req.alpha}, h_min={req.h_min}, h_target={req.h_target}, E_max={state.mpc.E_max}). Status: {'Converged' if res['converged'] else 'Completed'}.",
        extra={
            "horizon": state.mpc.H,
            "alpha": req.alpha,
            "h_min": req.h_min,
            "h_target": req.h_target,
            "e_max": state.mpc.E_max,
            "q_hat": q_hat,
            "avg_quota": round(avg_quota, 3),
            "final_cost": res["final_cost"],
            "converged": res["converged"],
        }
    )

    return {
        "status": "success",
        "converged": res["converged"],
        "q_hat_conformal": q_hat,
        "tightened_safety_threshold": res["safety_bound_tightened"],
        "pumping_quotas": res["optimal_pumping"].tolist(),
        "predicted_heads": res["predicted_heads"].tolist(),
        "final_cost": res["final_cost"],
    }


@app.get("/api/v1/alerts/depletion")
def check_depletion_warnings(threshold: float = 36.0):
    """
    Triggers automated multi-dimensional depletion warnings for monitoring wells.
    Evaluates conformal safety bounds (G_i - q_hat), temporal drawdown trend rates (m/mo),
    time-to-critical depletion (months), and mitigation pumping quota recommendations.
    """
    G_history = state.dataset.heads()  # (num_wells, time_steps)
    G_latest = G_history[:, -1]
    q_hat = float(state.conformal.q_hat)
    safe_heads = G_latest - q_hat
    coords = state.dataset.coords
    Sy_grid = state.dataset.geophysics["Sy"]
    K_grid = state.dataset.geophysics["K"]

    warnings = []
    critical_count = 0
    warning_count = 0
    watch_count = 0
    total_drawdown_rate = 0.0

    for idx, (head, safe_h) in enumerate(zip(G_latest, safe_heads)):
        r, c = int(coords[idx][0]), int(coords[idx][1])
        lat, lon = state.data_loader.grid_index_to_lat_lon(r, c)
        
        # Calculate recent drawdown trend (m/month over last 6 timesteps)
        if G_history.shape[1] >= 6:
            trend_rate = float((G_history[idx, -1] - G_history[idx, -6]) / 5.0)
        else:
            trend_rate = float(G_history[idx, -1] - G_history[idx, 0])
            
        total_drawdown_rate += abs(trend_rate)

        # Time to critical failure estimation (months)
        head_margin = safe_h - threshold
        if trend_rate < 0 and head_margin > 0:
            time_to_depletion = round(float(abs(head_margin / trend_rate)), 1)
        elif head_margin <= 0:
            time_to_depletion = 0.0
        else:
            time_to_depletion = 99.0  # Stable or recovering

        # Risk Classification & Pumping Quota Cut Recommendation
        if safe_h < threshold - 2.0 or time_to_depletion <= 2.0:
            risk_level = "CRITICAL"
            critical_count += 1
            rec_cut_pct = min(60.0, max(25.0, round((threshold - safe_h) * 15.0 + 20.0, 1)))
            action_text = f"CRITICAL HAZARD: Enforce immediate {rec_cut_pct}% pumping quota reduction."
        elif safe_h < threshold or time_to_depletion <= 6.0:
            risk_level = "HIGH WARNING"
            warning_count += 1
            rec_cut_pct = min(35.0, max(15.0, round((threshold - safe_h) * 10.0 + 10.0, 1)))
            action_text = f"WARNING: Implement {rec_cut_pct}% seasonal extraction curtailment."
        elif safe_h < threshold + 1.5 or trend_rate < -0.3:
            risk_level = "MODERATE WATCH"
            watch_count += 1
            rec_cut_pct = 10.0
            action_text = "WATCH: Increase piezometric monitoring frequency to bi-weekly."
        else:
            risk_level = None

        if risk_level is not None:
            warnings.append({
                "well_id": f"WELL-{idx+1:03d}",
                "row": r,
                "col": c,
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "nominal_head_m": round(float(head), 2),
                "conformal_safe_head_m": round(float(safe_h), 2),
                "threshold_m": threshold,
                "head_margin_m": round(float(head_margin), 2),
                "drawdown_trend_m_mo": round(trend_rate, 3),
                "time_to_depletion_months": time_to_depletion,
                "sy": round(float(Sy_grid[r, c]), 3),
                "k_m_day": round(float(K_grid[r, c]), 2),
                "rec_quota_cut_pct": rec_cut_pct,
                "risk_level": risk_level,
                "action_recommendation": action_text
            })

    total_wells = len(G_latest)
    active_alerts = len(warnings)
    network_health_score = round(max(0.0, (1.0 - (critical_count * 2 + warning_count) / total_wells) * 100.0), 1)
    avg_drawdown_rate = round(total_drawdown_rate / max(1, total_wells), 3)

    return {
        "total_wells": total_wells,
        "alert_count": active_alerts,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "watch_count": watch_count,
        "network_health_score_pct": network_health_score,
        "avg_drawdown_rate_m_mo": avg_drawdown_rate,
        "conformal_q_hat": q_hat,
        "threshold_m": threshold,
        "depletion_alerts": warnings,
    }


@app.post("/api/v1/control/single_station_lp")
def solve_single_station_lp():
    from src.control.single_station_lp import solve_station_cgwbhu2335_lp
    res = solve_station_cgwbhu2335_lp()
    state.log_event(
        "SINGLE_STATION_LP",
        f"Solved 30-day LP for station {res['station_id']}: Total Extraction = {res['total_extraction_m']}m",
        extra=res,
    )
    return res


@app.get("/api/v1/evaluation/paper_baselines")
def get_paper_baselines():
    baselines, _ = state.ensure_evaluation()
    return {"status": "success", "baselines": baselines}


@app.get("/api/v1/evaluation/ablation")
def get_autoregressive_ablation():
    _, ablation = state.ensure_evaluation()
    return {"status": "success", "ablation": ablation}


@app.get("/api/v1/forecast/location_hydrograph")
def get_location_hydrograph(lat: float = 40.15, lon: float = -88.25, horizon: int = 12):
    h_series = state.pipeline.hydrograph_series(lat, lon, max(1, horizon))
    r = int(h_series.get("grid_row", 0))
    c = int(h_series.get("grid_col", 0))
    return {
        "lat": lat,
        "lon": lon,
        "horizon": len(h_series["precipitation_mm"]),
        "grid_row": r,
        "grid_col": c,
        "precipitation_mm": h_series["precipitation_mm"],
        "evapotranspiration_mm": h_series["evapotranspiration_mm"],
        "effective_recharge_mm": h_series["effective_recharge_mm"],
        "water_table_head_m": h_series["head_level_m"],
    }





# Admin API Endpoints
@app.get("/api/v1/admin/telemetry")
def get_admin_telemetry():
    scp_runs = [e for e in state.history_log if e["event_type"] == "SCP_OPTIMIZATION"]
    total_solves = len(scp_runs)
    avg_cost = float(np.mean([e["final_cost"] for e in scp_runs])) if total_solves > 0 else 0.0

    return {
        "data_mode": state.data_loader.data_mode,
        "grid_shape": state.dataset.metadata["grid_shape"],
        "total_wells": state.dataset.heads().shape[0],
        "conformal_q_hat": state.conformal.q_hat,
        "conformal_alpha": state.conformal.alpha,
        "total_scp_solves": total_solves,
        "avg_scp_cost": round(avg_cost, 2),
        "history_count": len(state.history_log),
    }


@app.get("/api/v1/admin/history")
def get_admin_history():
    return {
        "total": len(state.history_log),
        "history": state.history_log,
    }


@app.post("/api/v1/admin/recalibrate")
def recalibrate_conformal_model(alpha: float = 0.05):
    state.conformal.alpha = alpha
    state.calibrate_conformal_from_surrogate()
    new_q_hat = state.conformal.q_hat
    
    state.log_event("RECALIBRATE_CONFORMAL", f"Conformal predictor recalibrated with alpha={alpha}. New q̂ = {new_q_hat:.4f}m.")

    return {
        "status": "success",
        "message": f"Conformal model recalibrated successfully.",
        "new_q_hat": new_q_hat,
        "alpha": alpha,
    }


@app.get("/api/v1/admin/export_history")
def export_history_csv():
    from fastapi.responses import PlainTextResponse
    import csv, io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Event Type", "Data Mode", "Detail", "Horizon", "Alpha", "q_hat", "Avg Quota", "Final Cost", "Converged"])

    for entry in state.history_log:
        writer.writerow([
            entry.get("timestamp", ""),
            entry.get("event_type", ""),
            entry.get("data_mode", ""),
            entry.get("detail", ""),
            entry.get("horizon", ""),
            entry.get("alpha", ""),
            entry.get("q_hat", ""),
            entry.get("avg_quota", ""),
            entry.get("final_cost", ""),
            entry.get("converged", ""),
        ])

    return PlainTextResponse(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=groundwater_history_log.csv"})


@app.middleware("http")
async def _static_no_cache(request, call_next):
    # The dashboard HTML is already served no-store, but /static assets
    # were not — browsers kept running a cached app.js after code updates
    # (the asset URL's ?v= tag only changes when someone remembers to bump
    # it, which is why the ingestion-progress UI once appeared "not
    # working": the page was running the old script). Force revalidation
    # of every /static response; unchanged files still come back as
    # cheap 304s via the ETag StaticFiles sends.
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


# Static web UI mount
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web")
if os.path.exists(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/")
    def serve_dashboard():
        index_path = os.path.join(web_dir, "index.html")
        return FileResponse(index_path, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        })

    @app.get("/admin")
    def serve_admin_dashboard():
        admin_path = os.path.join(web_dir, "admin.html")
        if os.path.exists(admin_path):
            return FileResponse(admin_path)
        raise HTTPException(status_code=404, detail="Admin panel HTML not found.")

    @app.get("/help", response_class=HTMLResponse)
    def serve_help_guide():
        return HTMLResponse(content=HELP_GUIDE_HTML)
