import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import logging

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ingestion.data_loader import GroundwaterDataLoader
from src.downscaling.spatial_downscaler import SpatialDownscaler
from src.downscaling.vadose_delay import VadoseDelayEngine
from src.surrogates.gnn_lstm import GNNLSTMSurrogate
from src.surrogates.pinn import PINNSurrogate
from src.surrogates.fno import FNOSurrogate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TrainSurrogates")


def train_surrogate_models(epochs: int = 50, batch_size: int = 4, lr: float = 1e-3):
    checkpoint_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models", "checkpoints"))
    os.makedirs(checkpoint_dir, exist_ok=True)

    logger.info("Preparing hydrogeological dataset for surrogate model pre-training...")
    loader = GroundwaterDataLoader(data_mode="synthetic", grid_shape=(16, 16))
    dataset = loader.load_processed_dataset(timesteps=48, num_wells=16)

    downscaler = SpatialDownscaler(model_type="rf")
    downscaled = downscaler.fit_and_downscale(
        dataset["rasters_raw"],
        dataset["geophysics"],
        mascon_grid_shape=dataset["metadata"]["mascon_grid_shape"],
    )
    vadose = VadoseDelayEngine()
    Reff = vadose.compute_effective_recharge(
        dataset["rasters_raw"]["P"],
        dataset["rasters_raw"]["ET"],
        dataset["rasters_raw"]["Qs"],
    )

    G_filled = dataset["wells"]["G_filled"]  # (num_wells, T)
    num_wells, T = G_filled.shape
    coords = dataset["wells"]["coords"]
    Sy_vals = dataset["geophysics"]["Sy"][:num_wells, 0:1]
    K_vals = dataset["geophysics"]["K"][:num_wells, 0:1]
    z_bedrock_vals = dataset["geophysics"]["z_bedrock"][:num_wells, 0:1]
    static_feats = np.hstack([K_vals, Sy_vals, z_bedrock_vals])

    # Prepare sequences for GNN-LSTM
    seq_len = 12
    X_seq_list, Y_seq_list = [], []

    for t in range(T - seq_len):
        # Extract dynamic features per well: [G_t, E_t, Reff_t, GWLA_t]
        dyn_t = []
        for w in range(num_wells):
            r, c = int(coords[w][0]), int(coords[w][1])
            g_series = G_filled[w, t:t+seq_len]
            e_series = np.full(seq_len, 5.0)  # nominal extraction rate
            rf_series = Reff[t:t+seq_len, r, c]
            gwla_series = downscaled["GWLA"][t:t+seq_len, r, c]
            well_dyn = np.column_stack([g_series, e_series, rf_series, gwla_series])
            dyn_t.append(well_dyn)
        
        dyn_t = np.stack(dyn_t, axis=1)  # (seq_len, num_wells, 4)
        target_t = G_filled[:, t+1:t+seq_len+1].T  # (seq_len, num_wells)
        
        X_seq_list.append(dyn_t)
        Y_seq_list.append(target_t)

    X_seq = torch.tensor(np.array(X_seq_list), dtype=torch.float32)  # (N_samples, seq_len, num_wells, 4)
    Y_seq = torch.tensor(np.array(Y_seq_list), dtype=torch.float32)  # (N_samples, seq_len, num_wells)
    static_t = torch.tensor(static_feats, dtype=torch.float32)       # (num_wells, 3)

    # 1. Train GNN-LSTM Model
    logger.info("Training GNN-LSTM Surrogate Model...")
    gnn_model = GNNLSTMSurrogate(num_wells=num_wells)
    adj = gnn_model.compute_adjacency(coords)
    optimizer_gnn = optim.Adam(gnn_model.parameters(), lr=lr)
    criterion_mse = nn.MSELoss()

    gnn_model.train()
    best_gnn_loss = float("inf")

    for epoch in range(epochs):
        optimizer_gnn.zero_grad()
        preds = gnn_model(X_seq, static_t, adj)  # (N_samples, seq_len, num_wells)
        loss = criterion_mse(preds, Y_seq)
        loss.backward()
        optimizer_gnn.step()

        if loss.item() < best_gnn_loss:
            best_gnn_loss = loss.item()
            torch.save(gnn_model.state_dict(), os.path.join(checkpoint_dir, "gnn_lstm_best.pt"))

        if (epoch + 1) % 10 == 0 or epoch == epochs - 1:
            logger.info(f"  [GNN-LSTM] Epoch {epoch+1}/{epochs} - Loss: {loss.item():.4f}")

    logger.info(f"GNN-LSTM Training Complete. Best Loss: {best_gnn_loss:.4f}. Saved to gnn_lstm_best.pt")

    # 2. Train PINN Surrogate Model
    logger.info("Training PINN Surrogate Model (Data + Dupuit-Boussinesq PDE Loss)...")
    pinn_model = PINNSurrogate()
    optimizer_pinn = optim.Adam(pinn_model.parameters(), lr=lr)

    # Prepare collocation points
    num_samples = 200
    x_rand = torch.rand(num_samples, 1) * 10.0
    y_rand = torch.rand(num_samples, 1) * 10.0
    t_rand = torch.rand(num_samples, 1) * 36.0
    E_rand = torch.full((num_samples, 1), 5.0)
    R_rand = torch.full((num_samples, 1), 0.5)

    colloc_coords_t = torch.cat([x_rand, y_rand, t_rand, E_rand, R_rand], dim=-1)

    obs_coords_list = []
    obs_h_list = []
    for w in range(num_wells):
        for t_step in range(T):
            r, c = coords[w]
            obs_coords_list.append([float(r), float(c), float(t_step), 5.0, float(Reff[t_step, int(r), int(c)])])
            obs_h_list.append([float(G_filled[w, t_step])])

    obs_coords_t = torch.tensor(obs_coords_list, dtype=torch.float32)
    obs_h_t = torch.tensor(obs_h_list, dtype=torch.float32)

    best_pinn_loss = float("inf")
    for epoch in range(epochs):
        optimizer_pinn.zero_grad()
        total_loss, data_loss, pde_loss = pinn_model.compute_composite_loss(
            obs_coords_t, obs_h_t, colloc_coords_t, lambda_pde=0.01
        )
        total_loss.backward()
        optimizer_pinn.step()

        if total_loss.item() < best_pinn_loss:
            best_pinn_loss = total_loss.item()
            torch.save(pinn_model.state_dict(), os.path.join(checkpoint_dir, "pinn_best.pt"))

        if (epoch + 1) % 10 == 0 or epoch == epochs - 1:
            logger.info(f"  [PINN] Epoch {epoch+1}/{epochs} - Loss: {total_loss.item():.4f} (Data: {data_loss.item():.4f}, PDE: {pde_loss.item():.4f})")

    logger.info(f"PINN Training Complete. Best Loss: {best_pinn_loss:.4f}. Saved to pinn_best.pt")

    # 3. Train FNO Surrogate Model
    logger.info("Training FNO Surrogate Model...")
    fno_model = FNOSurrogate()
    optimizer_fno = optim.Adam(fno_model.parameters(), lr=lr)

    H, W = dataset["rasters_raw"]["P"].shape[1:]
    # Dynamic grid input (batch, H, W, 5) -> [G_t, E_t, Reff_t, GWLA_t, Sy]
    fno_inputs = []
    fno_targets = []

    for t_step in range(T - 1):
        # Create grid rasters
        g_grid = np.full((H, W), 40.0) + downscaled["GWLA"][t_step]
        e_grid = np.full((H, W), 5.0)
        rf_grid = Reff[t_step]
        gwla_grid = downscaled["GWLA"][t_step]
        sy_grid = dataset["geophysics"]["Sy"]

        input_grid = np.stack([g_grid, e_grid, rf_grid, gwla_grid, sy_grid], axis=-1)
        target_grid = np.full((H, W), 40.0) + downscaled["GWLA"][t_step + 1]

        fno_inputs.append(input_grid)
        fno_targets.append(target_grid)

    fno_in_t = torch.tensor(np.array(fno_inputs), dtype=torch.float32)    # (T-1, H, W, 5)
    fno_target_t = torch.tensor(np.array(fno_targets), dtype=torch.float32)  # (T-1, H, W)

    best_fno_loss = float("inf")
    fno_model.train()
    for epoch in range(epochs):
        optimizer_fno.zero_grad()
        out_fno = fno_model(fno_in_t)
        loss_fno = criterion_mse(out_fno, fno_target_t)
        loss_fno.backward()
        optimizer_fno.step()

        if loss_fno.item() < best_fno_loss:
            best_fno_loss = loss_fno.item()
            torch.save(fno_model.state_dict(), os.path.join(checkpoint_dir, "fno_best.pt"))

        if (epoch + 1) % 10 == 0 or epoch == epochs - 1:
            logger.info(f"  [FNO] Epoch {epoch+1}/{epochs} - Loss: {loss_fno.item():.4f}")

    logger.info(f"FNO Training Complete. Best Loss: {best_fno_loss:.4f}. Saved to fno_best.pt")
    logger.info("=== All Scientific Machine Learning Surrogates Trained & Saved Successfully ===")


if __name__ == "__main__":
    train_surrogate_models(epochs=40)
