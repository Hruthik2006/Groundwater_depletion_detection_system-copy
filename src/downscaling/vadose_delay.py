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

    def generate_gamma_kernel(self) -> np.ndarray:
        """
        Generates normalized gamma lag kernel vector over tau = 0..tau_max.
        """
        tau_grid = np.arange(self.tau_max + 1, dtype=float)
        # Gamma PDF evaluated at tau + 1 to avoid zero evaluation
        kernel = gamma.pdf(tau_grid + 1.0, a=self.alpha_lag, scale=self.beta_lag)
        kernel_norm = kernel / np.sum(kernel)
        return kernel_norm

    def compute_effective_recharge(
        self,
        P: np.ndarray,
        ET: np.ndarray,
        Qs: np.ndarray = None,
    ) -> np.ndarray:
        """
        Convolves net surface recharge across historical temporal dimension T.
        Inputs: P, ET, Qs of shape (T, H, W)
        Returns: R_eff of shape (T, H, W)
        """
        T, H, W = P.shape
        net_recharge = P - ET
        if Qs is not None:
            net_recharge -= Qs

        kernel = self.generate_gamma_kernel()
        R_eff = np.zeros_like(net_recharge)

        for t in range(T):
            recharge_t = np.zeros((H, W))
            for tau in range(min(t + 1, self.tau_max + 1)):
                w = kernel[tau]
                recharge_t += w * net_recharge[t - tau]
            R_eff[t] = recharge_t

        return R_eff
