from __future__ import annotations

from collections.abc import Callable

import torch

PIXEL_LAYER_CLASSES = ("MLP", "EncoderDecoder")
ROWS_PER_CHUNK = 64
ELEMENTWISE_LAYERS = (
    torch.nn.GELU,
    torch.nn.ReLU,
    torch.nn.SiLU,
    torch.nn.Identity,
    torch.nn.Dropout,
    torch.nn.Dropout2d,
)


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


def in_row_chunks(
    layer: torch.nn.Module, rows: int
) -> Callable[[torch.Tensor], torch.Tensor]:
    def forward(x: torch.Tensor) -> torch.Tensor:
        height = x.shape[-2]
        if x.dim() != 4 or height <= rows:
            return layer(x)
        first = layer(x[..., :rows, :])
        output = first.new_empty((*first.shape[:-2], height, first.shape[-1]))
        output[..., :rows, :] = first
        del first
        for start in range(rows, height, rows):
            block = slice(start, start + rows)
            output[..., block, :] = layer(x[..., block, :])
        return output

    return forward


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
            module.forward = in_row_chunks(layer, rows)
            changed += 1
    return changed
