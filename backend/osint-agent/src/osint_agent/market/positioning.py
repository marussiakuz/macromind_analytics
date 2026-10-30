"""Classical metric MDS on comparable numeric features (plan §13).

Pure Python — no numpy. Enough for 4–20 objects in v1.
Euclidean distance matrix → double centering → top-2 eigenvectors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class MDSInputError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or []


MIN_OBJECTS = 4
MIN_FEATURES = 2


@dataclass
class FeatureSpec:
    name: str
    scale: float  # > 0
    weight: float = 1.0
    reference: float = 0.0


@dataclass
class MDSResult:
    status: str  # ok | degenerate | insufficient_data
    object_ids: list[str] = field(default_factory=list)
    coordinates: list[tuple[float, float]] = field(default_factory=list)
    distance_matrix: list[list[float]] = field(default_factory=list)
    map_distances: list[list[float]] = field(default_factory=list)
    relative_distance_error: float | None = None
    excluded: list[dict[str, Any]] = field(default_factory=list)
    features_used: list[str] = field(default_factory=list)
    message: str = ""
    method: str = "classical_mds_euclidean"


def _jacobi_eigen(matrix: list[list[float]], iterations: int = 100) -> tuple[list[float], list[list[float]]]:
    """Symmetric eigendecomposition (Jacobi). Returns (eigenvalues, eigenvectors as columns)."""
    n = len(matrix)
    a = [row[:] for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(iterations):
        off = 0.0
        p, q = 0, 1
        for i in range(n):
            for j in range(i + 1, n):
                if abs(a[i][j]) > off:
                    off = abs(a[i][j])
                    p, q = i, j
        if off < 1e-12:
            break
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        if abs(apq) < 1e-15:
            continue
        tau = (aqq - app) / (2 * apq)
        t = math.copysign(1.0, tau) / (abs(tau) + math.sqrt(1 + tau * tau))
        c = 1 / math.sqrt(1 + t * t)
        s = t * c
        for k in range(n):
            akp, akq = a[k][p], a[k][q]
            a[k][p] = c * akp - s * akq
            a[k][q] = s * akp + c * akq
        for k in range(n):
            apk, aqk = a[p][k], a[q][k]
            a[p][k] = c * apk - s * aqk
            a[q][k] = s * apk + c * aqk
        for k in range(n):
            vkp, vkq = v[k][p], v[k][q]
            v[k][p] = c * vkp - s * vkq
            v[k][q] = s * vkp + c * vkq
    eigenvalues = [a[i][i] for i in range(n)]
    # eigenvectors: column j is [v[i][j] for i in range(n)]
    eigenvectors = [[v[i][j] for i in range(n)] for j in range(n)]
    order = sorted(range(n), key=lambda i: eigenvalues[i], reverse=True)
    return [eigenvalues[i] for i in order], [eigenvectors[i] for i in order]


def _pairwise_dists(rows: list[list[float]], weights: list[float], scales: list[float], refs: list[float]) -> list[list[float]]:
    n = len(rows)
    d = [[0.0] * n for _ in range(n)]
    for a in range(n):
        for b in range(a + 1, n):
            acc = 0.0
            for j in range(len(weights)):
                za = (rows[a][j] - refs[j]) / scales[j]
                zb = (rows[b][j] - refs[j]) / scales[j]
                acc += weights[j] * (za - zb) ** 2
            val = math.sqrt(acc)
            d[a][b] = d[b][a] = val
    return d


def run_mds(
    object_ids: list[str],
    values: list[list[float | None]],
    features: list[FeatureSpec],
    *,
    require_full: bool = True,
) -> MDSResult:
    """Plan §13: минимум 4 объекта и 2 признака; пропуски не заполнять нулём."""
    if len(features) < MIN_FEATURES:
        return MDSResult(
            status="insufficient_data",
            message=f"Нужно минимум {MIN_FEATURES} пригодных признака",
            features_used=[f.name for f in features],
        )
    for f in features:
        if not math.isfinite(f.scale) or f.scale <= 0:
            raise MDSInputError("INVALID_SCALE", f"scale признака {f.name} должен быть > 0", [f.name])
        if f.weight < 0:
            raise MDSInputError("INVALID_WEIGHT", f"weight признака {f.name} неотрицателен", [f.name])
    total_w = sum(f.weight for f in features)
    if total_w <= 0:
        raise MDSInputError("INVALID_WEIGHT", "Сумма весов должна быть положительной", ["weight"])
    if abs(total_w - 1.0) > 1e-9:
        # plan: сумма весов = 1 — нормируем явно
        features = [
            FeatureSpec(f.name, f.scale, f.weight / total_w, f.reference) for f in features
        ]

    kept_ids: list[str] = []
    kept_rows: list[list[float]] = []
    excluded: list[dict[str, Any]] = []
    for oid, row in zip(object_ids, values):
        if len(row) != len(features):
            excluded.append({"id": oid, "reason": "число признаков не совпадает"})
            continue
        if require_full and any(v is None for v in row):
            excluded.append({"id": oid, "reason": "пропуск признака — не подставляем 0"})
            continue
        kept_ids.append(oid)
        kept_rows.append([float(v) for v in row])  # type: ignore[arg-type]

    if len(kept_ids) < MIN_OBJECTS:
        return MDSResult(
            status="insufficient_data",
            object_ids=kept_ids,
            excluded=excluded,
            features_used=[f.name for f in features],
            message=f"После исключений осталось {len(kept_ids)} объектов при минимуме {MIN_OBJECTS}",
        )

    # сначала — полные расстояния, чтобы поймать вырожденный случай (M04)
    full_d = _pairwise_dists(
        kept_rows,
        [f.weight for f in features],
        [f.scale for f in features],
        [f.reference for f in features],
    )
    if all(full_d[i][j] == 0 for i in range(len(full_d)) for j in range(i + 1, len(full_d))):
        coords = [(0.0, 0.0) for _ in kept_ids]
        return MDSResult(
            status="degenerate",
            object_ids=kept_ids,
            coordinates=coords,
            distance_matrix=full_d,
            map_distances=full_d,
            relative_distance_error=None,
            excluded=excluded,
            features_used=[f.name for f in features],
            message="Все попарные расстояния нулевые — вырожденная карта",
        )

    # признаки без вариации исключаем с пояснением
    used_idx = []
    for j, f in enumerate(features):
        col = [r[j] for r in kept_rows]
        if max(col) - min(col) < 1e-12:
            excluded.append({"id": f.name, "reason": "признак без вариации исключён"})
        else:
            used_idx.append(j)
    if len(used_idx) < MIN_FEATURES:
        return MDSResult(
            status="insufficient_data",
            object_ids=kept_ids,
            excluded=excluded,
            message="Слишком мало признаков с вариацией",
        )
    feats = [features[j] for j in used_idx]
    rows = [[r[j] for j in used_idx] for r in kept_rows]

    d = _pairwise_dists(
        rows,
        [f.weight for f in feats],
        [f.scale for f in feats],
        [f.reference for f in feats],
    )

    n = len(d)
    # classical MDS
    d2 = [[d[i][j] ** 2 for j in range(n)] for i in range(n)]
    row_mean = [sum(d2[i]) / n for i in range(n)]
    total_mean = sum(sum(r) for r in d2) / (n * n)
    b = [[-0.5 * (d2[i][j] - row_mean[i] - row_mean[j] + total_mean) for j in range(n)] for i in range(n)]
    eigenvalues, eigenvectors = _jacobi_eigen(b)

    coords: list[tuple[float, float]] = []
    for i in range(n):
        x = math.sqrt(max(eigenvalues[0], 0.0)) * eigenvectors[0][i] if eigenvalues[0] > 0 else 0.0
        y = math.sqrt(max(eigenvalues[1], 0.0)) * eigenvectors[1][i] if len(eigenvalues) > 1 and eigenvalues[1] > 0 else 0.0
        coords.append((x, y))

    # map distances + relative_distance_error (plan §13)
    map_d = [[0.0] * n for _ in range(n)]
    num = 0.0
    den = 0.0
    for a in range(n):
        for b2 in range(a + 1, n):
            dx = coords[a][0] - coords[b2][0]
            dy = coords[a][1] - coords[b2][1]
            md = math.hypot(dx, dy)
            map_d[a][b2] = map_d[b2][a] = md
            num += (md - d[a][b2]) ** 2
            den += d[a][b2] ** 2
    rde = math.sqrt(num / den) if den > 1e-15 else None

    return MDSResult(
        status="ok",
        object_ids=kept_ids,
        coordinates=coords,
        distance_matrix=d,
        map_distances=map_d,
        relative_distance_error=rde,
        excluded=excluded,
        features_used=[f.name for f in feats],
        message="Карта построена",
        method="classical_mds_euclidean",
    )


def mds_from_rows(
    rows: list[dict[str, Any]],
    feature_names: list[str],
    scales: dict[str, float],
    weights: dict[str, float] | None = None,
) -> MDSResult:
    """rows: [{id, f1, f2, ...}] — удобный вход из API."""
    features = [
        FeatureSpec(
            name=f,
            scale=float(scales.get(f, 1.0)),
            weight=float((weights or {}).get(f, 1.0 / max(len(feature_names), 1))),
        )
        for f in feature_names
    ]
    values = [[r.get(f) for f in feature_names] for r in rows]
    ids = [str(r.get("id", i)) for i, r in enumerate(rows)]
    return run_mds(ids, values, features)
