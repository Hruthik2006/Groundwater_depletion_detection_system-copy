import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Any, Tuple


class GraphConvLayer(nn.Module):
    """
    Message-Passing Spatial Graph Convolutional Layer.
    Aggregate neighbor node features scaled by normalized distance adjacency matrix.
    """

    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        self.linear_self = nn.Linear(in_features, out_features)
        self.linear_neigh = nn.Linear(in_features, out_features)
        self.act = nn.SiLU()

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        # x: (batch, N, in_features)
        # adj: (N, N) normalized adjacency matrix
        out_self = self.linear_self(x)
        out_neigh = self.linear_neigh(torch.matmul(adj, x))
        return self.act(out_self + out_neigh)


class GNNLSTMSurrogate(nn.Module):
    """
    Static-Conditioned GNN-LSTM Dynamic Surrogate Model.
    Models spatio-temporal hydraulic head transitions G_{i, t+1} over monitoring well networks.
    Conditioned directly on static geophysics (K, Sy, z_bedrock).
    """

    def __init__(
        self,
        num_wells: int,
        dynamic_dim: int = 4,   # [G_t, E_t, Reff_t, GWLA_t]
        static_dim: int = 3,    # [K, Sy, z_bedrock]
        hidden_dim: int = 64,
        num_gnn_layers: int = 2,
    ):
        super().__init__()
        self.num_wells = num_wells
        in_dim = dynamic_dim + static_dim

        self.gnn_layers = nn.ModuleList([
            GraphConvLayer(in_dim if i == 0 else hidden_dim, hidden_dim)
            for i in range(num_gnn_layers)
        ])
        
        self.lstm = nn.LSTMCell(hidden_dim, hidden_dim)
        self.head_pred = nn.Linear(hidden_dim, 1)

    def compute_adjacency(self, coords: np.ndarray, radius: float = 10.0) -> torch.Tensor:
        """
        Computes distance-based normalized graph adjacency matrix.
        coords: (N, 2)
        """
        N = coords.shape[0]
        diff = coords[:, None, :] - coords[None, :, :]
        dist = np.sqrt(np.sum(diff**2, axis=-1))
        
        adj = np.exp(-dist / radius)
        adj[dist > radius] = 0.0
        
        # Degree normalization D^(-0.5) A D^(-0.5)
        deg = np.sum(adj, axis=1)
        deg_inv_sqrt = np.power(np.maximum(deg, 1e-8), -0.5)
        adj_norm = deg_inv_sqrt[:, None] * adj * deg_inv_sqrt[None, :]
        return torch.tensor(adj_norm, dtype=torch.float32)

    def forward(
        self,
        dynamic_seq: torch.Tensor,
        static_feats: torch.Tensor,
        adj: torch.Tensor,
    ) -> torch.Tensor:
        """
        Inputs:
        - dynamic_seq: (batch_size, seq_len, N, dynamic_dim)
        - static_feats: (N, static_dim) or (batch_size, N, static_dim)
        - adj: (N, N)
        Returns:
        - G_pred_seq: (batch_size, seq_len, N)
        """
        batch_size, seq_len, N, _ = dynamic_seq.shape

        if static_feats.ndim == 2:
            static_expanded = static_feats.unsqueeze(0).unsqueeze(1).expand(batch_size, seq_len, N, -1)
        else:
            static_expanded = static_feats

        concat_input = torch.cat([dynamic_seq, static_expanded], dim=-1)

        h_t = torch.zeros(batch_size * N, self.lstm.hidden_size, device=dynamic_seq.device)
        c_t = torch.zeros(batch_size * N, self.lstm.hidden_size, device=dynamic_seq.device)

        preds = []
        for t in range(seq_len):
            x_t = concat_input[:, t, :, :]  # (batch_size, N, in_dim)
            
            # GNN Spatial Message Passing
            h_gnn = x_t
            for gnn in self.gnn_layers:
                h_gnn = gnn(h_gnn, adj)  # (batch_size, N, hidden_dim)

            # Reshape for LSTM cell
            h_gnn_flat = h_gnn.reshape(batch_size * N, -1)
            h_t, c_t = self.lstm(h_gnn_flat, (h_t, c_t))
            
            # Output head prediction
            out_t = self.head_pred(h_t).reshape(batch_size, N)
            preds.append(out_t)

        return torch.stack(preds, dim=1)  # (batch_size, seq_len, N)
