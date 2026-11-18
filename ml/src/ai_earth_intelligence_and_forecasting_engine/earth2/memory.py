from __future__ import annotations

from collections.abc import Callable

import torch

PIXEL_LAYER_CLASSES = ("MLP", "EncoderDecoder")
SPECTRAL_TRANSFORM_CLASSES = ("RealSHT", "InverseRealSHT")
ROWS_PER_CHUNK = 64
CHANNELS_PER_CHUNK = 32
ELEMENTWISE_LAYERS = (
    torch.nn.GELU,
    torch.nn.ReLU,
    torch.nn.SiLU,
    torch.nn.Identity,
    torch.nn.Dropout,
    torch.nn.Dropout2d,
)

Forward = Callable[[torch.Tensor], torch.Tensor]


def is_pixel_layer(layer: torch.nn.Sequential) -> bool:
    for part in layer:
        if isinstance(part, ELEMENTWISE_LAYERS):
            continue
        if not isinstance(part, torch.nn.Conv2d):
            return False
        if (
            part.kernel_size != (1, 1)
            or part.stride != (1, 1)
            or part.padding != (0, 0)
            or part.dilation != (1, 1)
        ):
            return False
    return True


def in_chunks(forward: Forward, dim: int, size: int) -> Forward:
    def chunked(x: torch.Tensor) -> torch.Tensor:
        length = x.shape[dim] if x.dim() == 4 else 0
        if length <= size:
            return forward(x)
        first = forward(x.narrow(dim, 0, size))
        shape = list(first.shape)
        shape[dim] = length
        output = first.new_empty(shape)
        output.narrow(dim, 0, size).copy_(first)
        del first
        for start in range(size, length, size):
            count = min(size, length - start)
            output.narrow(dim, start, count).copy_(forward(x.narrow(dim, start, count)))
        return output

    return chunked


def chunk_pixel_layers(model: torch.nn.Module, rows: int = ROWS_PER_CHUNK) -> int:
    if rows < 1:
        raise ValueError("rows must be at least 1")
    changed = 0
    for module in model.modules():
        layer = getattr(module, "fwd", None)
        if (
            type(module).__name__ in PIXEL_LAYER_CLASSES
            and isinstance(layer, torch.nn.Sequential)
            and is_pixel_layer(layer)
        ):
            module.forward = in_chunks(layer, -2, rows)
            changed += 1
    return changed


def chunk_spectral_transforms(
    model: torch.nn.Module, channels: int = CHANNELS_PER_CHUNK
) -> int:
    if channels < 1:
        raise ValueError("channels must be at least 1")
    changed = 0
    for module in model.modules():
        if type(module).__name__ in SPECTRAL_TRANSFORM_CLASSES:
            module.forward = in_chunks(module.forward, 1, channels)
            changed += 1
    return changed


def reduce_peak_memory(
    model: torch.nn.Module,
    rows: int = ROWS_PER_CHUNK,
    channels: int = CHANNELS_PER_CHUNK,
) -> dict[str, int]:
    return {
        "pixel_layers": chunk_pixel_layers(model, rows),
        "spectral_transforms": chunk_spectral_transforms(model, channels),
    }
