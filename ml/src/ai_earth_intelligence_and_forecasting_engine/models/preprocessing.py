from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)

NUMERIC_FEATURE_COLUMNS: tuple[str, ...] = (
    "previous_24h_count",
    "previous_72h_count",
    "previous_7d_count",
    "previous_30d_count",
    "neighboring_previous_24h_count",
    "temperature_2m",
    "total_precipitation",
    "u_wind_10m",
    "v_wind_10m",
    "relative_humidity",
    "elevation_m",
    "slope_deg",
)

LAND_COVER_CLASSES: tuple[int, ...] = (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100)


@dataclass(frozen=True)
class Preprocessor:
    imputer: SimpleImputer
    scaler: StandardScaler
    feature_columns: tuple[str, ...] = NUMERIC_FEATURE_COLUMNS
    include_land_cover: bool = True


def _numeric_matrix(
    rows: list[DatasetRow], feature_columns: tuple[str, ...]
) -> np.ndarray:
    return np.array(
        [[getattr(row, column) for column in feature_columns] for row in rows],
        dtype=float,
    )


def _land_cover_one_hot(rows: list[DatasetRow]) -> np.ndarray:
    matrix = np.zeros((len(rows), len(LAND_COVER_CLASSES)), dtype=float)

    for row_index, row in enumerate(rows):
        if row.land_cover_class in LAND_COVER_CLASSES:
            class_index = LAND_COVER_CLASSES.index(row.land_cover_class)
            matrix[row_index, class_index] = 1.0

    return matrix


def fit_preprocessor(
    train_rows: list[DatasetRow],
    feature_columns: tuple[str, ...] = NUMERIC_FEATURE_COLUMNS,
    include_land_cover: bool = True,
) -> Preprocessor:
    if not train_rows:
        raise ValueError("cannot fit preprocessing on an empty training set")

    numeric_matrix = _numeric_matrix(train_rows, feature_columns)

    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    imputer.fit(numeric_matrix)

    scaler = StandardScaler()
    scaler.fit(imputer.transform(numeric_matrix))

    return Preprocessor(
        imputer=imputer,
        scaler=scaler,
        feature_columns=feature_columns,
        include_land_cover=include_land_cover,
    )


def transform(preprocessor: Preprocessor, rows: list[DatasetRow]) -> np.ndarray:
    numeric_matrix = _numeric_matrix(rows, preprocessor.feature_columns)
    numeric_imputed = preprocessor.imputer.transform(numeric_matrix)
    numeric_scaled = preprocessor.scaler.transform(numeric_imputed)

    if not preprocessor.include_land_cover:
        return numeric_scaled

    categorical = _land_cover_one_hot(rows)

    return np.hstack([numeric_scaled, categorical])


def extract_targets(rows: list[DatasetRow]) -> np.ndarray:
    return np.array([row.target for row in rows], dtype=int)


def feature_names(
    feature_columns: tuple[str, ...] = NUMERIC_FEATURE_COLUMNS,
    include_land_cover: bool = True,
) -> list[str]:
    names = list(feature_columns)

    if include_land_cover:
        names += [f"land_cover_{class_id}" for class_id in LAND_COVER_CLASSES]

    return names
