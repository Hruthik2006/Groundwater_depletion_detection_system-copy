import pytest
import numpy as np
import torch
from fastapi.testclient import TestClient

from src.ingestion.data_loader import GroundwaterDataLoader
from src.downscaling.spatial_downscaler import SpatialDownscaler
from src.downscaling.vadose_delay import VadoseDelayEngine
from src.surrogates.gnn_lstm import GNNLSTMSurrogate
from src.surrogates.pinn import PINNSurrogate
from src.surrogates.fno import FNOSurrogate
from src.conformal.split_conformal import SplitConformalPredictor
from src.control.scp_mpc import SCPChanceConstrainedMPC
from src.api.app import app


def test_data_ingestion():
    loader = GroundwaterDataLoader(data_mode="synthetic", grid_shape=(16, 16))
    dataset = loader.load_processed_dataset(timesteps=24, num_wells=12)

    assert "P" in dataset["rasters_norm"]
    assert dataset["rasters_norm"]["P"].shape == (24, 16, 16)
    assert dataset["wells"]["G_filled"].shape == (12, 24)
    assert not np.isnan(dataset["wells"]["G_filled"]).any()


def test_spatial_downscaler():
    loader = GroundwaterDataLoader(data_mode="synthetic", grid_shape=(16, 16))
    dataset = loader.load_processed_dataset(timesteps=12, num_wells=8)

    downscaler = SpatialDownscaler(model_type="rf")
    res = downscaler.fit_and_downscale(
        dataset["rasters_raw"],
        dataset["geophysics"],
        mascon_grid_shape=(2, 2),
    )

    assert "TWSA_scaled" in res
    assert "GWLA" in res
    assert res["GWLA"].shape == (12, 16, 16)


def test_vadose_delay():
    engine = VadoseDelayEngine(alpha_lag=2.5, beta_lag=1.5)
    kernel = engine.generate_gamma_kernel()
    assert abs(np.sum(kernel) - 1.0) < 1e-5

    P = np.ones((12, 8, 8)) * 10.0
    ET = np.ones((12, 8, 8)) * 5.0
    Reff = engine.compute_effective_recharge(P, ET)
    assert Reff.shape == (12, 8, 8)


def test_pytorch_surrogates():
    num_wells = 10
    gnn = GNNLSTMSurrogate(num_wells=num_wells)
    pinn = PINNSurrogate()
    fno = FNOSurrogate()

    # GNN forward
    adj = torch.eye(num_wells)
    dyn_seq = torch.randn(2, 6, num_wells, 4)
    static_feats = torch.randn(num_wells, 3)
    out_gnn = gnn(dyn_seq, static_feats, adj)
    assert out_gnn.shape == (2, 6, num_wells)

    # PINN residual
    coords = torch.randn(16, 5, requires_grad=True)
    res_pde = pinn.compute_pde_residual(coords)
    assert res_pde.shape == (16, 1)

    # FNO forward
    x_fno = torch.randn(2, 16, 16, 5)
    out_fno = fno(x_fno)
    assert out_fno.shape == (2, 16, 16)


def test_split_conformal():
    conformal = SplitConformalPredictor(alpha=0.05)
    y_true = np.array([40.0, 42.0, 44.0, 46.0, 48.0])
    y_pred = np.array([40.1, 41.8, 44.2, 45.9, 48.3])

    q_hat = conformal.calibrate(y_true, y_pred)
    assert q_hat >= 0.0
    assert conformal.get_safety_threshold(35.0) == 35.0 + q_hat


def test_scp_mpc_solver():
    mpc = SCPChanceConstrainedMPC(horizon=6, num_wells=8)
    surrogate = GNNLSTMSurrogate(num_wells=8)
    
    G_0 = np.full(8, 42.0)
    climate = np.zeros((6, 8, 2))
    static = np.ones((8, 3))

    res = mpc.solve_optimal_pumping(
        surrogate,
        G_0=G_0,
        climate_horizon=climate,
        static_geo=static,
        q_hat=0.2,
    )

    assert "optimal_pumping" in res
    assert res["optimal_pumping"].shape == (6, 8)


def test_fastapi_endpoints():
    client = TestClient(app)

    res_status = client.get("/api/v1/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "operational"

    res_drawdown = client.get("/api/v1/forecast/spatial_drawdown?horizon=6")
    assert res_drawdown.status_code == 200
    assert len(res_drawdown.json()["forecasts"]) == 6

    res_drawdown_48 = client.get("/api/v1/forecast/spatial_drawdown?horizon=48")
    assert res_drawdown_48.status_code == 200
    assert len(res_drawdown_48.json()["forecasts"]) == 48

    res_hydrograph = client.get("/api/v1/forecast/location_hydrograph?lat=40.15&lon=-88.25&horizon=24")
    assert res_hydrograph.status_code == 200
    assert len(res_hydrograph.json()["precipitation_mm"]) == 24

    res_alerts = client.get("/api/v1/alerts/depletion")
    assert res_alerts.status_code == 200

    res_mode = client.post("/api/v1/config/data_source", json={"data_mode": "synthetic"})
    assert res_mode.status_code == 200


def test_admin_endpoints():
    client = TestClient(app)

    res_telemetry = client.get("/api/v1/admin/telemetry")
    assert res_telemetry.status_code == 200
    assert "total_scp_solves" in res_telemetry.json()

    res_history = client.get("/api/v1/admin/history")
    assert res_history.status_code == 200
    assert "history" in res_history.json()

    res_recal = client.post("/api/v1/admin/recalibrate?alpha=0.05")
    assert res_recal.status_code == 200
    assert "new_q_hat" in res_recal.json()

    res_csv = client.get("/api/v1/admin/export_history")
    assert res_csv.status_code == 200
    assert "Timestamp,Event Type" in res_csv.text

    res_admin_html = client.get("/admin")
    assert res_admin_html.status_code == 200
    assert "Admin Control Center" in res_admin_html.text


def test_location_endpoints():
    client = TestClient(app)

    res_loc = client.post("/api/v1/config/location", json={"region_key": "north_german"})
    assert res_loc.status_code == 200
    assert "metadata" in res_loc.json()

    res_pred = client.post("/api/v1/forecast/location_predict", json={"lat": 53.0, "lon": 10.5, "horizon": 6})
    assert res_pred.status_code == 200
    res_data = res_pred.json()
    assert "forecast" in res_data
    assert len(res_data["forecast"]["predicted_heads_m"]) == 6
    assert "depletion_risk" in res_data
    assert "recommended_pumping_quota_m3" in res_data


def test_report_generation():
    client = TestClient(app)

    res_report = client.get("/api/v1/reports/view?lat=40.15&lon=-88.25&horizon=12")
    assert res_report.status_code == 200
    assert "Detailed Groundwater Location Assessment" in res_report.text
    assert "Recommended Pumping Allocation" in res_report.text

    res_report_24 = client.get("/api/v1/reports/view?lat=40.15&lon=-88.25&horizon=24")
    assert res_report_24.status_code == 200
    assert "24-Month Projected Head" in res_report_24.text
    assert "Month 24" in res_report_24.text

    res_report_48 = client.get("/api/v1/reports/view?lat=40.15&lon=-88.25&horizon=48")
    assert res_report_48.status_code == 200
    assert "48-Month Projected Head" in res_report_48.text
    assert "Month 48" in res_report_48.text


def test_3d_endpoint():
    client = TestClient(app)

    res_3d = client.get("/api/v1/forecast/spatial_drawdown_3d?horizon=12")
    assert res_3d.status_code == 200
    res_json = res_3d.json()
    assert "vertices" in res_json
    assert len(res_json["vertices"]) == 256


def test_custom_report_generation():
    client = TestClient(app)

    # Test report with specific prediction suites enabled and custom horizons
    res_custom = client.get(
        "/api/v1/reports/view?"
        "lat=40.15&lon=-88.25"
        "&sec_summary=1"
        "&sec_stratigraphy=1"
        "&sec_conformal=1&horizon_conformal=18"
        "&sec_lp30day=1"
        "&sec_baselines=1"
        "&sec_ablation=1"
        "&sec_pumping=1&horizon_pumping=6"
        "&sec_hydrograph=1&horizon_hydrograph=36"
        "&sec_math=1"
        "&sec_table=1"
        "&sec_recommendations=1"
    )
    assert res_custom.status_code == 200
    assert "Prediction 1: Piezometric Head Forecast &amp; Split Conformal Bounds (18 Months)" in res_custom.text
    assert "Prediction 2: Station CGWBHU2335 Worked 30-Day LP Extraction &amp; Head Trajectory" in res_custom.text
    assert "Prediction 3: Paper Baseline ML Models Performance Comparison" in res_custom.text
    assert "Prediction 4: Historical Level Autoregressive Ablation Suite" in res_custom.text
    assert "Prediction 5: Multi-Well SCP Chance-Constrained Pumping Quotas (6 Months)" in res_custom.text
    assert "Prediction 6: Hydrograph (Rainfall, Vadose Delay Recharge &amp; Head Dynamics - 36 Months)" in res_custom.text
    assert "18-Month Projected Head" in res_custom.text


def test_dataset_typed_accessors():
    from src.pipeline.dataset import GroundwaterDataset

    loader = GroundwaterDataLoader(data_mode="synthetic", grid_shape=(16, 16))
    raw = loader.load_processed_dataset(timesteps=12, num_wells=8)
    dataset = GroundwaterDataset(raw, loader=loader)

    assert dataset.heads().shape == (8, 12)
    assert len(dataset.coords) == 8
    assert "grid_shape" in dataset.metadata
    assert dataset.geophysics["K"].shape == (16, 16)
    assert dataset.static_features(8).shape == (8, 3)


def test_provider_contract_dwlr_and_realtime():
    from src.ingestion.base_provider import BaseDataProvider
    from src.ingestion.dwlr_provider import DWLRDataProvider
    from src.ingestion.realtime_provider import RealtimeEarthEngineDataProvider

    assert issubclass(DWLRDataProvider, BaseDataProvider)
    dwlr = DWLRDataProvider()
    assert dwlr.is_synthetic is False
    assert dwlr.serves()["mode"] == "hybrid"
    assert dwlr.serves()["channels"] == {
        "raster": "synthetic",
        "hydromet": "dwlr",
        "static": "synthetic",
    }

    realtime = RealtimeEarthEngineDataProvider()
    assert realtime.is_synthetic is True
    served = realtime.serves()
    assert served["mode"] == "synthetic"
    assert all(v == "synthetic_standby" for v in served["channels"].values())

    loader = GroundwaterDataLoader(data_mode="dwlr")
    dataset = loader.load_processed_dataset(timesteps=12, num_wells=8)
    assert dataset["metadata"]["serves"]["channels"]["hydromet"] == "dwlr"


def test_mpc_tunables_wired_from_config():
    from src.api.app import state

    cfg = state.pipeline.config
    mpc = state.pipeline.mpc
    assert mpc.sigma_slack == cfg.sigma_slack
    assert mpc.delta_0 == cfg.delta_trust
    assert mpc.w_energy == cfg.gamma_pump
    assert mpc.max_scp_iters == cfg.max_scp_iters


def test_scp_mpc_sigma_slack_default():
    from src.control.scp_mpc import SCPChanceConstrainedMPC

    mpc_default = SCPChanceConstrainedMPC(horizon=6, num_wells=8)
    assert mpc_default.sigma_slack == 1000.0

    mpc_custom = SCPChanceConstrainedMPC(horizon=6, num_wells=8, sigma_slack=2500.0)
    assert mpc_custom.sigma_slack == 2500.0


def test_report_contains_live_solver_data():
    client = TestClient(app)

    res = client.get("/api/v1/reports/view?lat=40.15&lon=-88.25&horizon=12")
    assert res.status_code == 200
    html = res.text
    assert "Random Forest" in html
    assert "Linear Regression" in html
    assert "RMSE Degradation Ratio" in html
    assert "Day 1" in html
    assert "0.84 m" not in html


def test_pumping_quotas_full_tunables():
    client = TestClient(app)

    res = client.post(
        "/api/v1/control/pumping_quotas",
        json={
            "horizon": 4,
            "h_min": 35.0,
            "h_target": 45.0,
            "alpha": 0.05,
            "e_max": 8.0,
            "gamma_pump": 2.0,
            "sigma_slack": 2000.0,
            "delta_trust": 2.0,
            "max_iter": 10,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["converged"] is True
    assert np.asarray(body["pumping_quotas"]).shape == (4, 16)
    assert body["status"] == "success"




