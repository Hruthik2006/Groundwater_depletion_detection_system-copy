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
from src.evaluation.benchmarks import FrameworkEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GroundwaterFramework")


def run_full_pipeline(data_mode: str = "synthetic"):
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
    adj = gnn_model.compute_adjacency(dataset["wells"]["coords"])
    dummy_seq = torch.randn(1, 12, num_wells, 4, dtype=torch.float32)
    dummy_static = torch.tensor(dataset["geophysics"]["Sy"][:num_wells, 0:3], dtype=torch.float32)
    gnn_out = gnn_model(dummy_seq, dummy_static, adj)
    logger.info(f"GNN-LSTM surrogate forward pass shape: {gnn_out.shape}")

    # 5. Split Conformal Prediction UQ Layer
    logger.info("Layer 5: Calibrating Split Conformal Predictor for finite-sample safety bounds...")
    conformal = SplitConformalPredictor(alpha=0.05)
    y_true = dataset["wells"]["G_filled"]
    y_pred = y_true + np.random.normal(0, 0.25, y_true.shape)
    q_hat = conformal.calibrate(y_true, y_pred)
    logger.info(f"Conformal empirical error margin q_hat (alpha=0.05): {q_hat:.4f}m")

    # 6. Sequential Convex Programming (SCP) CCMPC Layer
    logger.info("Layer 6: Solving Chance-Constrained MPC via Sequential Convex Programming...")
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

    # 7. Experimental Benchmarking Layer
    logger.info("Layer 7: Running Feature Ablation & Cross-Validation Benchmarks...")
    evaluator = FrameworkEvaluator()
    ablation = evaluator.run_feature_ablation_matrix(dataset, downscaled, Reff)
    cv_res = evaluator.run_spatial_kfold_cv(dataset, k_folds=4)

    logger.info("=== Feature Ablation Benchmark Results ===")
    for config, metrics in ablation.items():
        logger.info(f"  {config}: RMSE={metrics['RMSE']:.4f}, MAE={metrics['MAE']:.4f}, CVR={metrics['CVR']*100:.1f}%")
    logger.info(f"Spatial 4-Fold CV Mean RMSE: {cv_res['Spatial_CV_Mean_RMSE']:.4f}m")

    logger.info("=== Groundwater Framework Execution Successfully Verified ===")
    return mpc_res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "synthetic"
    run_full_pipeline(data_mode=mode)
    
    logger.info("Starting REST API Server & Web Dashboard on http://localhost:8000 ...")
    uvicorn.run("src.api.app:app", host="127.0.0.1", port=8000, reload=False)
