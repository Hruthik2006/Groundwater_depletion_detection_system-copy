import uvicorn
import numpy as np
import torch
import logging
import sys

from src.ingestion.data_loader import GroundwaterDataLoader
from src.downscaling.spatial_downscaler import SpatialDownscaler
from src.downscaling.vadose_delay import VadoseDelayEngine
from src.surrogates.gnn_lstm import GNNLSTMSurrogate
from src.surrogates.pinn import PINNSurrogate
from src.surrogates.fno import FNOSurrogate
from src.conformal.split_conformal import SplitConformalPredictor
from src.control.scp_mpc import SCPChanceConstrainedMPC
from src.control.single_station_lp import solve_station_cgwbhu2335_lp
from src.evaluation.benchmarks import FrameworkEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GroundwaterFramework")


def run_full_pipeline(data_mode: str = "dwlr"):
    logger.info(f"=== Starting Groundwater Framework Pipeline (Mode: {data_mode}) ===")

    # 1. Ingestion Layer
    logger.info("Layer 1: Ingesting multi-source geospatial tensors and piezometers...")
    loader = GroundwaterDataLoader(data_mode=data_mode, grid_shape=(16, 16))
    dataset = loader.load_processed_dataset(timesteps=36, num_wells=16)
    logger.info(f"Ingestion complete. Normalized rasters: {list(dataset['rasters_norm'].keys())}")

    # 2. Downscaling Layer
    logger.info("Layer 2: Executing multi-phase GRACE downscaling & scale preservation...")
    downscaler = SpatialDownscaler(model_type="rf")
    downscaled = downscaler.fit_and_downscale(
        dataset["rasters_raw"],
        dataset["geophysics"],
        mascon_grid_shape=dataset["metadata"]["mascon_grid_shape"],
    )
    logger.info(f"GWLA anomaly shape: {downscaled['GWLA'].shape}, Mean GWLA: {np.mean(downscaled['GWLA']):.3f}m")

    # 3. Unsaturated Vadose Zone Delay Layer
    logger.info("Layer 3: Convolving net surface recharge with Gamma vadose delay kernel...")
    vadose = VadoseDelayEngine(alpha_lag=2.5, beta_lag=1.5)
    Reff = vadose.compute_effective_recharge(
        dataset["rasters_raw"]["P"],
        dataset["rasters_raw"]["ET"],
        dataset["rasters_raw"]["Qs"],
    )
    logger.info(f"Effective recharge R_eff computed. Shape: {Reff.shape}")

    # 4. Scientific Machine Learning Surrogates Layer
    logger.info("Layer 4: Initializing Scientific Machine Learning Dynamic Surrogates (GNN-LSTM, PINN, FNO)...")
    num_wells = dataset["wells"]["G_filled"].shape[0]
    gnn_model = GNNLSTMSurrogate(num_wells=num_wells)
    pinn_model = PINNSurrogate()
    fno_model = FNOSurrogate()

    # Forward pass sanity checks
    coords = dataset["wells"]["coords"]
    adj = gnn_model.compute_adjacency(coords)
    seq_len = 12
    g_seq = torch.tensor(dataset["wells"]["G_filled"][:, :seq_len], dtype=torch.float32).T.unsqueeze(0).unsqueeze(-1)
    e_seq = torch.full((1, seq_len, num_wells, 1), 5.0, dtype=torch.float32)
    rf_vals = Reff[:seq_len, coords[:,0], coords[:,1]] if Reff.ndim == 3 else Reff[:seq_len, :num_wells]
    gwla_vals = downscaled["GWLA"][:seq_len, coords[:,0], coords[:,1]]
    rf_seq = torch.tensor(rf_vals, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
    gwla_seq = torch.tensor(gwla_vals, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
    dyn_seq = torch.cat([g_seq, e_seq, rf_seq, gwla_seq], dim=-1)

    Sy_t = torch.tensor(dataset["geophysics"]["Sy"][:num_wells, 0:1], dtype=torch.float32)
    K_t = torch.tensor(dataset["geophysics"]["K"][:num_wells, 0:1], dtype=torch.float32)
    z_bedrock_t = torch.tensor(dataset["geophysics"]["z_bedrock"][:num_wells, 0:1], dtype=torch.float32)
    static_t = torch.cat([K_t, Sy_t, z_bedrock_t], dim=-1)

    gnn_out = gnn_model(dyn_seq, static_t, adj)
    logger.info(f"GNN-LSTM surrogate forward pass shape: {gnn_out.shape}")

    # 5. Split Conformal Prediction UQ Layer (Real Surrogate Residual Calibration)
    logger.info("Layer 5: Calibrating Split Conformal Predictor on surrogate residual errors...")
    conformal = SplitConformalPredictor(alpha=0.05)
    y_true = dataset["wells"]["G_filled"][:, 1:seq_len+1]
    y_pred = gnn_out[0].detach().numpy().T
    q_hat = conformal.calibrate(y_true, y_pred)
    logger.info(f"Conformal empirical error margin q_hat (alpha=0.05): {q_hat:.4f}m")

    # 6. Worked Single-Station LP & SCP CCMPC Optimization Layer
    logger.info("Layer 6A: Executing Worked Single-Station LP Solver for Station CGWBHU2335...")
    lp_res = solve_station_cgwbhu2335_lp()
    logger.info(f"Station CGWBHU2335 LP Total Sustainable Extraction: {lp_res['total_extraction_m']}m")

    logger.info("Layer 6B: Solving Multi-Well Chance-Constrained MPC via Sequential Convex Programming...")
    mpc = SCPChanceConstrainedMPC(horizon=12, num_wells=num_wells, h_min=35.0)
    G_0 = dataset["wells"]["G_filled"][:, -1]
    climate_horizon = np.zeros((12, num_wells, 2))
    climate_horizon[:, :, 0] = Reff[:12, :num_wells, 0] if Reff.ndim == 3 else 0.5
    static_geo = np.column_stack([
        dataset["geophysics"]["K"][:num_wells, 0],
        dataset["geophysics"]["Sy"][:num_wells, 0],
        dataset["geophysics"]["z_bedrock"][:num_wells, 0],
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

    # 7. Experimental Paper Benchmarks & Ablation Layer
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
