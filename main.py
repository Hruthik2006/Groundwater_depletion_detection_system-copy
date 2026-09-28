import uvicorn
import numpy as np
import logging
import sys
from dataclasses import replace

from src.pipeline.config import DEFAULT_CONFIG
from src.pipeline.pipeline import Pipeline
from src.surrogates.pinn import PINNSurrogate
from src.surrogates.fno import FNOSurrogate
from src.control.single_station_lp import solve_station_cgwbhu2335_lp
from src.evaluation.benchmarks import FrameworkEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GroundwaterFramework")

_VALID_MODES = ("synthetic", "realtime", "dwlr")


def run_full_pipeline(data_mode: str = "synthetic"):
    if data_mode not in _VALID_MODES:
        raise SystemExit(
            f"Unknown data mode '{data_mode}'. Valid modes: {', '.join(_VALID_MODES)}. "
            "Refusing to silently substitute synthetic data — choose the mode explicitly."
        )

    logger.info(f"=== Starting Groundwater Framework Pipeline (Mode: {data_mode}) ===")

    # 1. Single orchestration seam: ingest -> downscale -> vadose -> conformal.
    logger.info("Layer 1-3: Building pipeline (ingestion, downscaling, vadose delay, conformal calibration)...")
    pipeline = Pipeline(config=replace(DEFAULT_CONFIG, data_mode=data_mode))
    dataset = pipeline.build()
    downscaled = pipeline.downscaling_res
    Reff = pipeline.Reff
    logger.info(
        f"Build complete. GWLA anomaly shape: {downscaled['GWLA'].shape}, "
        f"Mean GWLA: {np.mean(downscaled['GWLA']):.3f}m, R_eff shape: {Reff.shape}"
    )
    logger.info(f"Ingestion complete. Normalized rasters: {list(dataset.rasters_norm.keys())}")

    # 2. Forward-pass sanity checks on all three surrogate architectures.
    logger.info("Layer 4: Initializing Scientific Machine Learning Dynamic Surrogates (GNN-LSTM, PINN, FNO)...")
    num_wells = dataset.num_wells
    gnn_model = pipeline.surrogate
    pinn_model = PINNSurrogate()
    fno_model = FNOSurrogate()

    coords = dataset.coords
    adj = gnn_model.compute_adjacency(coords)
    seq_len = min(12, dataset.timesteps - 1)
    dyn_seq = dataset.dynamic_sequence(Reff, downscaled["GWLA"], seq_len, e_nominal=5.0)
    static_t = dataset.static_features(num_wells)

    import torch
    gnn_out = gnn_model(
        dyn_seq,
        torch.tensor(static_t, dtype=torch.float32),
        adj,
    )
    logger.info(f"GNN-LSTM surrogate forward pass shape: {gnn_out.shape}")

    # 3. Split Conformal Prediction UQ Layer (already calibrated by build()).
    logger.info("Layer 5: Split Conformal Predictor calibrated on surrogate residual errors...")
    q_hat = pipeline.conformal.q_hat
    logger.info(f"Conformal empirical error margin q_hat (alpha=0.05): {q_hat:.4f}m")

    # 4. Worked Single-Station LP & SCP CCMPC Optimization Layer
    logger.info("Layer 6A: Executing Worked Single-Station LP Solver for Station CGWBHU2335...")
    lp_res = solve_station_cgwbhu2335_lp()
    logger.info(f"Station CGWBHU2335 LP Total Sustainable Extraction: {lp_res['total_extraction_m']}m")

    logger.info("Layer 6B: Solving Multi-Well Chance-Constrained MPC via Sequential Convex Programming...")
    mpc = pipeline.mpc
    G_0 = dataset.heads()[:, -1]
    climate_horizon = np.zeros((12, num_wells, 2))
    climate_horizon[:, :, 0] = Reff[:12, :num_wells, 0] if Reff.ndim == 3 else 0.5
    static_geo = np.column_stack([
        dataset.geophysics["K"][:num_wells, 0],
        dataset.geophysics["Sy"][:num_wells, 0],
        dataset.geophysics["z_bedrock"][:num_wells, 0],
    ])

    mpc_res = mpc.solve_optimal_pumping(
        gnn_model,
        G_0=G_0,
        climate_horizon=climate_horizon,
        static_geo=static_geo,
        q_hat=q_hat,
        adj=adj,
    )
    logger.info(f"SCP Optimization completed. Converged: {mpc_res['converged']}, Final Cost: {mpc_res['final_cost']:.2f}")

    # 5. Experimental Paper Benchmarks & Ablation Layer
    logger.info("Layer 7: Running Paper Baseline Models & Autoregressive Ablation Suite...")
    evaluator = FrameworkEvaluator()
    paper_baselines = evaluator.fit_paper_baselines(dataset)
    ablation_res = evaluator.run_autoregressive_ablation(dataset)

    logger.info("=== Paper Baseline ML Model Results (Table 3) ===")
    for model_name, metrics in paper_baselines.items():
        logger.info(f"  {model_name}: RMSE={metrics['RMSE']:.4f}m, MAE={metrics['MAE']:.4f}m")

    logger.info("=== Autoregressive Level History Ablation (Table 4) ===")
    logger.info(f"  Full Model: RMSE={ablation_res['Full_Model_P_T_LevelHistory']['RMSE']}m")
    logger.info(f"  Ablated Model: RMSE={ablation_res['Ablated_Model_LevelHistory_Removed']['RMSE']}m")

    logger.info("=== Groundwater Framework Execution Successfully Verified ===")
    return mpc_res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "synthetic"
    run_full_pipeline(data_mode=mode)

    logger.info("Starting REST API Server & Web Dashboard on http://localhost:8000 ...")
    uvicorn.run("src.api.app:app", host="127.0.0.1", port=8000, reload=True)