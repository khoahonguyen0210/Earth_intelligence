from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.earth2.memory import (  # noqa: E402
    chunk_pixel_layers,
    chunk_spectral_transforms,
    is_pixel_layer,
    reduce_peak_memory,
)


class MLP(torch.nn.Module):
    def __init__(self, channels: int, hidden: int):
        super().__init__()
        self.fwd = torch.nn.Sequential(
            torch.nn.Conv2d(channels, hidden, 1),
            torch.nn.GELU(),
            torch.nn.Dropout2d(0.0),
            torch.nn.Conv2d(hidden, channels, 1),
        )

    def forward(self, x):
        return self.fwd(x)


class EncoderDecoder(MLP):
    pass


def smoothing_mlp() -> torch.nn.Module:
    class MLP(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.fwd = torch.nn.Sequential(torch.nn.Conv2d(2, 2, 3, padding=1))

    return MLP()


class RealSHT(torch.nn.Module):
    def __init__(self, height: int, modes: int):
        super().__init__()
        self.register_buffer("weights", torch.randn(modes, height))
        self.calls: list[int] = []

    def forward(self, x):
        self.calls.append(x.shape[1])
        spectrum = torch.fft.rfft(x, dim=-1)
        return torch.einsum("lh,bchm->bclm", self.weights.to(spectrum.dtype), spectrum)


class InverseRealSHT(torch.nn.Module):
    def __init__(self, height: int, modes: int, width: int):
        super().__init__()
        self.register_buffer("weights", torch.randn(height, modes))
        self.width = width

    def forward(self, x):
        grid = torch.einsum("hl,bclm->bchm", self.weights.to(x.dtype), x)
        return torch.fft.irfft(grid, n=self.width, dim=-1)


class Network(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = EncoderDecoder(5, 8)
        self.norm = torch.nn.InstanceNorm2d(5)
        self.mlp = MLP(5, 16)
        self.transform = RealSHT(23, 6)
        self.inverse = InverseRealSHT(23, 6, 12)
        self.decoder = EncoderDecoder(5, 4)

    def forward(self, x):
        x = self.mlp(self.norm(self.encoder(x)))
        x = x + self.inverse(self.transform(x))
        return self.decoder(x)


def test_chunked_network_gives_the_same_output():
    torch.manual_seed(0)
    network = Network().eval()
    x = torch.randn(2, 5, 23, 12)
    with torch.inference_mode():
        expected = network(x)
        counts = reduce_peak_memory(network, rows=4, channels=2)
        result = network(x)
    assert counts == {"pixel_layers": 3, "spectral_transforms": 2}
    torch.testing.assert_close(result, expected, rtol=1e-5, atol=1e-5)


def test_spectral_transforms_run_in_channel_chunks():
    transform = RealSHT(9, 4)
    x = torch.randn(1, 7, 9, 10)
    with torch.inference_mode():
        expected = transform(x)
        assert chunk_spectral_transforms(transform, channels=3) == 1
        transform.calls.clear()
        result = transform(x)
    assert transform.calls == [3, 3, 1]
    torch.testing.assert_close(result, expected)


def test_each_chunk_has_at_most_the_given_rows():
    network = MLP(3, 6).eval()
    heights = []
    network.fwd[0].register_forward_hook(
        lambda module, inputs, output: heights.append(inputs[0].shape[-2])
    )
    chunk_pixel_layers(network, rows=5)
    with torch.inference_mode():
        network(torch.randn(1, 3, 12, 7))
    assert heights == [5, 5, 2]


def test_small_inputs_run_in_one_piece():
    network = MLP(3, 6).eval()
    chunk_pixel_layers(network, rows=64)
    x = torch.randn(1, 3, 10, 4)
    with torch.inference_mode():
        torch.testing.assert_close(network(x), network.fwd(x))


def test_layers_that_mix_neighbors_are_left_alone():
    smoother = smoothing_mlp()
    assert not is_pixel_layer(smoother.fwd)
    assert chunk_pixel_layers(smoother, rows=2) == 0


def test_chunk_sizes_must_be_positive():
    with pytest.raises(ValueError):
        chunk_pixel_layers(MLP(2, 2), rows=0)
    with pytest.raises(ValueError):
        chunk_spectral_transforms(RealSHT(3, 2), channels=0)
