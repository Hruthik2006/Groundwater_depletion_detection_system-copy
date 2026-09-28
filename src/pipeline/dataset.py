from typing import Any, Dict, Optional

import numpy as np


class GroundwaterDataset:
    """
    Typed accessor over the processed dataset produced by
    GroundwaterDataLoader.load_processed_dataset.

    Previously every consumer poked the raw string-keyed dict
    (dataset["wells"]["G_filled"], dataset["geophysics"]["Sy"][:N, 0:1], ...).
    This wrapper exposes those slices as named properties/accessors and keeps
    the "grid cells vs. well columns" and "2D vs 3D recharge" decisions in one
    place.

    It is still dict-compatible (__getitem__ / keys / get) so downstream code
    such as FrameworkEvaluator keeps working unchanged.
    """

    def __init__(self, data: Dict[str, Any], loader: Any = None):
        self._data = data
        self.loader = loader

    # -- dict compatibility ------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def keys(self):
        return self._data.keys()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    # -- metadata sections --------------------------------------------------
    @property
    def metadata(self) -> Dict[str, Any]:
        return self._data["metadata"]

    @property
    def rasters_raw(self) -> Dict[str, np.ndarray]:
        return self._data["rasters_raw"]

    @property
    def rasters_norm(self) -> Dict[str, np.ndarray]:
        return self._data["rasters_norm"]

    @property
    def wells(self) -> Dict[str, Any]:
        return self._data["wells"]

    @property
    def geophysics(self) -> Dict[str, np.ndarray]:
        return self._data["geophysics"]

    @property
    def grid_shape(self):
        return tuple(self.metadata["grid_shape"])

    @property
    def mascon_grid_shape(self):
        return tuple(self.metadata["mascon_grid_shape"])

    # -- well-level accessors ------------------------------------------------
    @property
    def coords(self) -> np.ndarray:
        """(num_wells, 2) integer grid indices per well."""
        return self.wells["coords"]

    @property
    def num_wells(self) -> int:
        return self.heads().shape[0]

    @property
    def timesteps(self) -> int:
        return self.heads().shape[1]

    def heads(self) -> np.ndarray:
        """(num_wells, T) temporally-interpolated piezometric heads G_filled."""
        return self.wells["G_filled"]

    def spatial_heads(self) -> np.ndarray:
        """(T, H, W) spatial IDW-interpolated head rasters."""
        return self.wells["G_spatial_idw"]

    def static_features(self, num_wells: Optional[int] = None) -> np.ndarray:
        """
        Column-stacked static geophysics [K, S_y, z_bedrock] in (num_wells, 3)
        order matching the GNN-LSTM feature contract (matches existing
        column_stack/hstack usage across main, app, and training code).
        """
        if num_wells is None:
            num_wells = self.num_wells
        K = self.geophysics["K"][:num_wells, 0:1]
        Sy = self.geophysics["Sy"][:num_wells, 0:1]
        z_bedrock = self.geophysics["z_bedrock"][:num_wells, 0:1]
        return np.column_stack([K, Sy, z_bedrock])

    def recharge_at_wells(self, Reff: np.ndarray, seq_len: int) -> np.ndarray:
        """
        Samples effective recharge at well grid cells for the first seq_len
        timesteps. Reff may be (T, H, W) or (T, N); the sampling strategy is
        chosen by rank so callers never dereference its dimensionality again.
        """
        if Reff.ndim == 3:
            coords = self.coords
            return Reff[:seq_len, coords[:, 0], coords[:, 1]]
        return Reff[:seq_len, : self.num_wells]

    def gwla_at_wells(self, GWLA: np.ndarray, seq_len: int) -> np.ndarray:
        """Samples downscaled GWLA (T, H, W) at well grid cells for seq_len steps."""
        coords = self.coords
        return GWLA[:seq_len, coords[:, 0], coords[:, 1]]

    def dynamic_sequence(
        self,
        Reff: np.ndarray,
        GWLA: np.ndarray,
        seq_len: int,
        e_nominal: float = 5.0,
    ):
        """
        Builds the (1, seq_len, num_wells, 4) tensor feed [G_t, E_t, R_eff, GWLA]
        required by the GNN-LSTM surrogate forward pass.
        """
        import torch

        num_wells = self.num_wells
        heads = self.heads()[:, :seq_len]                     # (N, seq_len)
        g_series = torch.tensor(heads, dtype=torch.float32).T.unsqueeze(0).unsqueeze(-1)
        e_series = torch.full((1, seq_len, num_wells, 1), e_nominal, dtype=torch.float32)

        rf_vals = self.recharge_at_wells(Reff, seq_len)
        gwla_vals = self.gwla_at_wells(GWLA, seq_len)

        rf_series = torch.tensor(rf_vals, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)
        gwla_series = torch.tensor(gwla_vals, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)

        return torch.cat([g_series, e_series, rf_series, gwla_series], dim=-1)