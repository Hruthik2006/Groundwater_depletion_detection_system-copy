import numpy as np
from scipy.stats import gamma


class VadoseDelayEngine:
    """
    Phase 5: Unsaturated Vadose Zone Delay Engine.
    Convolves net surface recharge (P - ET) with a parameterized Gamma kernel
    derived from sediment thickness and soil hydraulic conductivity to model
    vertical hydraulic delay to the saturated water table.
    """

    def __init__(self, alpha_lag: float = 2.5, beta_lag: float = 1.5, tau_max: int = 6):
        self.alpha_lag = alpha_lag
        self.beta_lag = beta_lag
        self.tau_max = tau_max

    def generate_gamma_kernel(self, alpha: float = None, beta: float = None) -> np.ndarray:
        """
        Generates normalized gamma lag kernel vector over tau = 0..tau_max.
        """
        a = alpha if alpha is not None else self.alpha_lag
        b = beta if beta is not None else self.beta_lag
        tau_grid = np.arange(self.tau_max + 1, dtype=float)
        kernel = gamma.pdf(tau_grid + 1.0, a=a, scale=b)
        kernel_sum = np.sum(kernel)
        return kernel / kernel_sum if kernel_sum > 0 else kernel

    def compute_effective_recharge(
        self,
        P: np.ndarray,
        ET: np.ndarray,
        Qs: np.ndarray = None,
        DTB: np.ndarray = None,
        clay: np.ndarray = None,
    ) -> np.ndarray:
        """
        Convolves net surface recharge across historical temporal dimension T.
        Inputs: P, ET, Qs of shape (T, H, W); optional DTB, clay of shape (H, W)
        Returns: R_eff of shape (T, H, W)
        """
        T, H, W = P.shape
        net_recharge = P - ET
        if Qs is not None:
            net_recharge -= Qs

        R_eff = np.zeros_like(net_recharge)

        if DTB is not None and clay is not None:
            # Spatially-varying Gamma kernel per cell (H, W) derived from DTB and clay fraction
            alpha_grid = np.clip(1.5 + 0.05 * DTB, 1.0, 10.0)
            beta_grid = np.clip(1.0 + 0.02 * clay, 0.5, 5.0)

            # Precompute 3D kernel matrix of shape (tau_max + 1, H, W)
            tau_grid = np.arange(self.tau_max + 1, dtype=float)[:, None, None]
            kernel_3d = gamma.pdf(tau_grid + 1.0, a=alpha_grid[None, :, :], scale=beta_grid[None, :, :])
            kernel_3d /= np.maximum(1e-6, np.sum(kernel_3d, axis=0, keepdims=True))

            for t in range(T):
                recharge_t = np.zeros((H, W))
                for tau in range(min(t + 1, self.tau_max + 1)):
                    recharge_t += kernel_3d[tau] * net_recharge[t - tau]
                R_eff[t] = recharge_t
        else:
            kernel = self.generate_gamma_kernel()
            for t in range(T):
                recharge_t = np.zeros((H, W))
                for tau in range(min(t + 1, self.tau_max + 1)):
                    recharge_t += kernel[tau] * net_recharge[t - tau]
                R_eff[t] = recharge_t

        return R_eff
