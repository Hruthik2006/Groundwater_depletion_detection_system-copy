import torch
import torch.nn as nn
import torch.fft as fft


class SpectralConv2d(nn.Module):
    """
    2D Fourier Spectral Convolution Layer.
    Executes FFT, truncates high-frequency modes, multiplies parameterized complex weights,
    and projects back via inverse FFT.
    """

    def __init__(self, in_channels: int, out_channels: int, modes1: int = 4, modes2: int = 4):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.modes1 = modes1  # Number of Fourier modes along height
        self.modes2 = modes2  # Number of Fourier modes along width

        scale = 1.0 / (in_channels * out_channels)
        self.weights1 = nn.Parameter(scale * torch.rand(in_channels, out_channels, modes1, modes2, dtype=torch.cfloat))
        self.weights2 = nn.Parameter(scale * torch.rand(in_channels, out_channels, modes1, modes2, dtype=torch.cfloat))

    def _compl_mul2d(self, input_tensor: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
        # (batch, in_channel, x, y) * (in_channel, out_channel, x, y) -> (batch, out_channel, x, y)
        return torch.einsum("bixy,ioxy->boxy", input_tensor, weights)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batchsize, in_channels, H, W = x.shape
        
        # 1. 2D Real-to-Complex Fast Fourier Transform
        x_ft = fft.rfft2(x)

        # 2. Multiply relevant Fourier modes
        out_ft = torch.zeros(
            batchsize,
            self.out_channels,
            H,
            W // 2 + 1,
            dtype=torch.cfloat,
            device=x.device,
        )

        m1 = min(self.modes1, H // 2)
        m2 = min(self.modes2, W // 2 + 1)

        out_ft[:, :, :m1, :m2] = self._compl_mul2d(x_ft[:, :, :m1, :m2], self.weights1[:, :, :m1, :m2])
        out_ft[:, :, -m1:, :m2] = self._compl_mul2d(x_ft[:, :, -m1:, :m2], self.weights2[:, :, :m1, :m2])

        # 3. Inverse Fast Fourier Transform back to real spatial domain
        x_out = fft.irfft2(out_ft, s=(H, W))
        return x_out


class FNOSurrogate(nn.Module):
    """
    2D Fourier Neural Operator (FNO / U-FNO) Dynamic Surrogate Model.
    Discretization-invariant functional mapping of hydroclimate + extraction fields
    to future 2D hydraulic head rasters G_{t+1}(x,y).
    """

    def __init__(
        self,
        in_channels: int = 5,   # [G_t, E_t, Reff_t, GWLA_t, Sy]
        out_channels: int = 1,  # [G_{t+1}]
        width: int = 32,
        modes1: int = 4,
        modes2: int = 4,
    ):
        super().__init__()
        self.width = width
        self.fc0 = nn.Linear(in_channels, self.width)

        self.conv0 = SpectralConv2d(self.width, self.width, modes1, modes2)
        self.conv1 = SpectralConv2d(self.width, self.width, modes1, modes2)
        self.conv2 = SpectralConv2d(self.width, self.width, modes1, modes2)

        self.w0 = nn.Conv2d(self.width, self.width, 1)
        self.w1 = nn.Conv2d(self.width, self.width, 1)
        self.w2 = nn.Conv2d(self.width, self.width, 1)

        self.fc1 = nn.Linear(self.width, 128)
        self.fc2 = nn.Linear(128, out_channels)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Inputs: x of shape (batch, H, W, in_channels)
        Returns: G_next of shape (batch, H, W)
        """
        # Lift input to higher-dimensional channel space
        x_lift = self.fc0(x)
        x_lift = x_lift.permute(0, 3, 1, 2)  # (batch, width, H, W)

        # Spectral layer 0
        x1 = self.conv0(x_lift) + self.w0(x_lift)
        x1 = self.act(x1)

        # Spectral layer 1
        x2 = self.conv1(x1) + self.w1(x1)
        x2 = self.act(x2)

        # Spectral layer 2
        x3 = self.conv2(x2) + self.w2(x2)
        x3 = self.act(x3)

        # Projection back to output channel space
        x_proj = x3.permute(0, 2, 3, 1)  # (batch, H, W, width)
        out = self.fc1(x_proj)
        out = self.act(out)
        out = self.fc2(out).squeeze(-1)  # (batch, H, W)

        return out
