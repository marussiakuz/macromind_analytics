"""Benchmark arithmetic is independent of servers and corpus ingestion."""

import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "scripts" / "bench_recall_at_10.py"
spec = importlib.util.spec_from_file_location("bench_recall", path)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_precision_at_ten_is_not_precision_of_short_response():
    assert bench.precision_at_k(["d1"], ["d1"]) == 0.1
    assert bench.recall_at_k(["d1"], ["d1"]) == 1.0
    assert bench.precision_at_k(["d1"], []) == 0.0
