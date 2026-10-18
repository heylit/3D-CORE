"""SPEC 57 §5 — Öncelik DAG'ı ve takım değişimini azaltan sıralama (DP / sezgisel)."""

from __future__ import annotations

from cam.plan import PlannedOp


def precedence(ops: list[PlannedOp]) -> dict[int, set[int]]:
    """İşlem indeksi → öncülleri (SPEC 29 kurallarından açıkça kurulur)."""
    raise NotImplementedError("SPEC 57: precedence")


def order_ops(
    ops: list[PlannedOp],
    prec: dict[int, set[int]],
    c_tc: float = 1.0,
    c_rot: float = 0.1,
    exact_max: int = 12,
) -> tuple[list[int], int, int]:
    """Sıra, N_tc, N_rot; döngülü DAG → CamError."""
    raise NotImplementedError("SPEC 57: order_ops")
