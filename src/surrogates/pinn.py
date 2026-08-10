import torch
import torch.nn as nn
from typing import Dict, Any, Tuple


class PINNSurrogate(nn.Module):
    """
    Physics-Informed Neural Network (PINN) Dynamic Surrogate Model.
    Constrained by the 2D Non-Linear Dupuit-Boussinesq Groundwater Flow Equation:
    R_PDE(h) = Sy * (dh/dt) - d/dx(K_x * h * dh/dx) - d/dy(K_y * h * dh/dy) - R_eff + E
    """

    def __init__(self, hidden_dim: int = 64, num_layers: int = 4):
        super().__init__()
        # Input space: (x, y, t, E, R_eff) -> 5 dimensions
        layers = [nn.Linear(5, hidden_dim), nn.Tanh()]
        for _ in range(num_layers - 1):
            layers.extend([nn.Linear(hidden_dim, hidden_dim), nn.Tanh()])
        layers.append(nn.Linear(hidden_dim, 1))

        self.net = nn.Sequential(*layers)

    def forward(self, coords_t: torch.Tensor) -> torch.Tensor:
        """
        Inputs: coords_t of shape (batch, 5) -> [x, y, t, E, R_eff]
        Returns: h_pred of shape (batch, 1)
        """
        return self.net(coords_t)

    def compute_pde_residual(
        self,
        coords_t: torch.Tensor,
        Sy: float = 0.15,
        K: float = 10.0,
    ) -> torch.Tensor:
        """
        Evaluates 2D Dupuit-Boussinesq PDE residual using torch.autograd automatic differentiation.
        """
        x = coords_t[:, 0:1].detach().clone().requires_grad_(True)
        y = coords_t[:, 1:2].detach().clone().requires_grad_(True)
        t = coords_t[:, 2:3].detach().clone().requires_grad_(True)
        E = coords_t[:, 3:4].detach().clone()
        R_eff = coords_t[:, 4:5].detach().clone()

        coords_in = torch.cat([x, y, t, E, R_eff], dim=-1)
        h = self.forward(coords_in)

        # 1st order derivatives
        dh_dx = torch.autograd.grad(h, x, grad_outputs=torch.ones_like(h), create_graph=True, allow_unused=True)[0]
        dh_dy = torch.autograd.grad(h, y, grad_outputs=torch.ones_like(h), create_graph=True, allow_unused=True)[0]
        dh_dt = torch.autograd.grad(h, t, grad_outputs=torch.ones_like(h), create_graph=True, allow_unused=True)[0]

        dh_dx = dh_dx if dh_dx is not None else torch.zeros_like(h)
        dh_dy = dh_dy if dh_dy is not None else torch.zeros_like(h)
        dh_dt = dh_dt if dh_dt is not None else torch.zeros_like(h)

        # Flux terms: q_x = K * h * dh/dx, q_y = K * h * dh/dy
        q_x = K * h * dh_dx
        q_y = K * h * dh_dy

        # 2nd order spatial divergence
        dqx_dx = torch.autograd.grad(q_x, x, grad_outputs=torch.ones_like(q_x), create_graph=True, allow_unused=True)[0]
        dqy_dy = torch.autograd.grad(q_y, y, grad_outputs=torch.ones_like(q_y), create_graph=True, allow_unused=True)[0]

        dqx_dx = dqx_dx if dqx_dx is not None else torch.zeros_like(h)
        dqy_dy = dqy_dy if dqy_dy is not None else torch.zeros_like(h)

        # Dupuit-Boussinesq Residual
        residual = Sy * dh_dt - (dqx_dx + dqy_dy) - R_eff + E
        return residual

    def compute_composite_loss(
        self,
        obs_coords_t: torch.Tensor,
        obs_h: torch.Tensor,
        colloc_coords_t: torch.Tensor,
        lambda_pde: float = 0.1,
        Sy: float = 0.15,
        K: float = 10.0,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Computes composite loss L = L_data + lambda_pde * L_pde.
        """
        h_pred = self.forward(obs_coords_t)
        loss_data = torch.mean((h_pred - obs_h) ** 2)

        res_pde = self.compute_pde_residual(colloc_coords_t, Sy=Sy, K=K)
        loss_pde = torch.mean(res_pde ** 2)

        total_loss = loss_data + lambda_pde * loss_pde
        return total_loss, loss_data, loss_pde
