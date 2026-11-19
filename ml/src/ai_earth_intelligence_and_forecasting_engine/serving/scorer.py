from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import xgboost

FORMAT_VERSION = 1


class PortableScorer:
    def __init__(
        self, model: dict[str, Any], device: str = "cpu", threads: int | None = None
    ):
        if model.get("format_version") != FORMAT_VERSION:
            raise ValueError("unsupported model format")
        self.device = device
        self.booster = xgboost.Booster()
        self.booster.load_model(bytearray(model["booster"], "utf-8"))
        parameters: dict[str, Any] = {"device": device}
        if threads:
            parameters["nthread"] = threads
        self.booster.set_param(parameters)
        self.iterations = (0, int(model["best_iteration"]) + 1)
        self.isotonic_x = np.asarray(model["isotonic_x"], dtype=np.float64)
        self.isotonic_y = np.asarray(model["isotonic_y"], dtype=np.float64)

    def raw(self, features: np.ndarray) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            values = self.booster.inplace_predict(
                features, iteration_range=self.iterations
            )
        return np.asarray(values, dtype=np.float64)

    def __call__(self, features: np.ndarray) -> np.ndarray:
        return np.interp(self.raw(features), self.isotonic_x, self.isotonic_y)
