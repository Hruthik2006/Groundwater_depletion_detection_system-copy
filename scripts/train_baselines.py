import sys
import os
import logging
import json

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.data_loader import GroundwaterDataLoader
from src.evaluation.benchmarks import FrameworkEvaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TrainBaselines")


def main():
    data_mode = sys.argv[1] if len(sys.argv) > 1 else "dwlr"
    logger.info(f"=== Starting Research Paper Baseline Models & Ablation Suite (Data Mode: {data_mode}) ===")

    # 1. Load Dataset
    loader = GroundwaterDataLoader(data_mode=data_mode, grid_shape=(16, 16))
    dataset = loader.load_processed_dataset(timesteps=36, num_wells=16)
    logger.info(f"Dataset Loaded. Piezometer Wells Shape: {dataset['wells']['G_filled'].shape}")

    # 2. Instantiate Evaluator
    evaluator = FrameworkEvaluator()

    # 3. Fit Paper Baseline Models (Table 2 & 3)
    logger.info("--- Fitting Paper ML Baselines (Linear Regression, Random Forest, SVR, XGBoost-style, LSTM) ---")
    baseline_results = evaluator.fit_paper_baselines(dataset)

    print("\n" + "="*60)
    print("      RESEARCH PAPER TABLE 3: HELD-OUT BASELINE PERFORMANCE")
    print("="*60)
    print(f"{'Model':<25} | {'RMSE (m)':<10} | {'MAE (m)':<10} | {'CVR (%)':<10}")
    print("-" * 60)
    for model_name, metrics in baseline_results.items():
        print(f"{model_name:<25} | {metrics['RMSE']:<10.4f} | {metrics['MAE']:<10.4f} | {metrics['CVR']*100:<10.1f}")
    print("="*60 + "\n")

    # 4. Run Autoregressive Ablation Suite (Table 4)
    logger.info("--- Running Historical Autoregressive Term Ablation Experiment ---")
    ablation_results = evaluator.run_autoregressive_ablation(dataset)

    print("="*60)
    print("      RESEARCH PAPER TABLE 4: AUTOREGRESSIVE TERM ABLATION")
    print("="*60)
    for config_name, metrics in ablation_results.items():
        print(f" {config_name}: {json.dumps(metrics)}")
    print("="*60 + "\n")

    logger.info("=== Baseline Benchmark Execution Completed Successfully ===")


if __name__ == "__main__":
    main()
