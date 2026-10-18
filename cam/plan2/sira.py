"""SPEC 57 §5 — Öncelik DAG'ı ve takım değişimini azaltan sıralama (DP / sezgisel).

Maliyet J = c_tc·N_tc + c_rot·N_rot; N_tc = ardışık farklı takım geçişi + ilk takım (SPEC 29 `tool_changes`),
N_rot = ardışık farklı yönelim (`PlannedOp.setup`) geçişi. Eşit maliyette özgün (29) sıraya sözlük sırasında
en yakın sıra seçilir.
"""

from __future__ import annotations

import math
import re
from functools import cache

from cam.model import CamError
from cam.plan import PlannedOp

ALAN = {"acik_bolge", "cep", "cep_kalan"}
DELME = {"punta", "delik", "kilavuz", "havsa", "lamba"}
SONRA = {"kilavuz", "havsa", "lamba"}  # matkaptan sonra
EPS = 1e-9  # maliyet eşitliği


def _delikler(adres: str) -> set[int] | None:
    """'holes[0,1]' → {0, 1}; delik adresi değilse None."""
    m = re.fullmatch(r"holes\[([\d,\s]+)\]", adres)
    return None if m is None else {int(v) for v in m.group(1).split(",")}


def precedence(ops: list[PlannedOp]) -> dict[int, set[int]]:
    """İşlem indeksi → öncülleri (SPEC 29 kurallarından açıkça kurulur; durum/57 netleştirme 2).

    Aynı yönelimde: yuz_alma → diğer her işlem; {acik_bolge, cep, cep_kalan} → delme işlemleri;
    aynı adreste cep → cep_kalan; aynı delikte (kesişen indeksler) punta → delik → {kilavuz, havsa, lamba}.
    """
    prec: dict[int, set[int]] = {i: set() for i in range(len(ops))}
    for i, a in enumerate(ops):
        for j, b in enumerate(ops):
            if i == j or a.setup != b.setup:
                continue
            if a.kind == "yuz_alma" and b.kind != "yuz_alma":
                prec[j].add(i)
            elif a.kind in ALAN and b.kind in DELME:
                prec[j].add(i)
            elif a.kind == "cep" and b.kind == "cep_kalan" and a.feature == b.feature:
                prec[j].add(i)
            elif a.kind in DELME and b.kind in DELME:
                ha, hb = _delikler(a.feature), _delikler(b.feature)
                if ha is None or hb is None or not ha & hb:
                    continue
                if (a.kind == "punta" and b.kind != "punta") or (a.kind == "delik" and b.kind in SONRA):
                    prec[j].add(i)
    return prec


def _denetle(n: int, prec: dict[int, set[int]]) -> list[int]:
    """Öncülleri bit maskesi olarak döndürür; geçersiz indeks ya da döngü → CamError."""
    maske = [0] * n
    for i, ps in prec.items():
        if not (isinstance(i, int) and 0 <= i < n):
            raise CamError(f"Sıralama: geçersiz işlem indeksi {i!r}")
        for p in ps:
            if not (isinstance(p, int) and 0 <= p < n):
                raise CamError(f"Sıralama: geçersiz öncül indeksi {p!r}")
            maske[i] |= 1 << p
    yapilan, kalan = 0, set(range(n))
    while kalan:  # Kahn: döngü denetimi
        hazir = [i for i in kalan if maske[i] & ~yapilan == 0]
        if not hazir:
            raise CamError(f"Sıralama: öncelik ilişkisi döngülü (işlemler {sorted(kalan)})")
        for i in hazir:
            yapilan |= 1 << i
            kalan.discard(i)
    return maske


def _sayim(ops: list[PlannedOp], sira: list[int]) -> tuple[int, int]:
    tc = rot = 0
    for k, i in enumerate(sira):
        if k == 0 or ops[i].tool_id != ops[sira[k - 1]].tool_id:
            tc += 1
        if k > 0 and ops[i].setup != ops[sira[k - 1]].setup:
            rot += 1
    return tc, rot


def _tam(ops: list[PlannedOp], maske: list[int], c_tc: float, c_rot: float) -> list[int]:
    """Alt kümeler üzerinde DP: durum (yapılmış küme, son işlem); eşitlikte en küçük indeks."""
    n = len(ops)
    hepsi = (1 << n) - 1

    def gecis(son: int, j: int) -> float:
        if son < 0:
            return c_tc
        a, b = ops[son], ops[j]
        return c_tc * (a.tool_id != b.tool_id) + c_rot * (a.setup != b.setup)

    @cache
    def f(yapilan: int, son: int) -> float:
        if yapilan == hepsi:
            return 0.0
        best = math.inf
        for j in range(n):
            if not yapilan >> j & 1 and maske[j] & ~yapilan == 0:
                best = min(best, gecis(son, j) + f(yapilan | 1 << j, j))
        return best

    sira, yapilan, son = [], 0, -1
    while yapilan != hepsi:
        hedef = f(yapilan, son)
        for j in range(n):
            if not yapilan >> j & 1 and maske[j] & ~yapilan == 0:
                if gecis(son, j) + f(yapilan | 1 << j, j) <= hedef + EPS:
                    sira.append(j)
                    yapilan |= 1 << j
                    son = j
                    break
    f.cache_clear()
    return sira


def _sezgisel(ops: list[PlannedOp], maske: list[int]) -> list[int]:
    """Aynı takım (ve aynı yönelim) ile devam; yoksa en çok hazır işlemi olan takım; eşitlikte 29 sırası."""
    n = len(ops)
    sira: list[int] = []
    yapilan = 0
    while len(sira) < n:
        hazir = [j for j in range(n) if not yapilan >> j & 1 and maske[j] & ~yapilan == 0]
        if sira:
            son = ops[sira[-1]]
            ayni = [j for j in hazir if ops[j].tool_id == son.tool_id]
            if ayni:
                ayni_yon = [j for j in ayni if ops[j].setup == son.setup]
                j = (ayni_yon or ayni)[0]
            else:
                say: dict[int, int] = {}
                for k in hazir:
                    say[ops[k].tool_id] = say.get(ops[k].tool_id, 0) + 1
                j = min(hazir, key=lambda k: (-say[ops[k].tool_id], k))
        else:
            say = {}
            for k in hazir:
                say[ops[k].tool_id] = say.get(ops[k].tool_id, 0) + 1
            j = min(hazir, key=lambda k: (-say[ops[k].tool_id], k))
        sira.append(j)
        yapilan |= 1 << j
    return sira


def order_ops(
    ops: list[PlannedOp],
    prec: dict[int, set[int]],
    c_tc: float = 1.0,
    c_rot: float = 0.1,
    exact_max: int = 12,
) -> tuple[list[int], int, int]:
    """Sıra, N_tc, N_rot; döngülü DAG → CamError.

    n ≤ exact_max tam DP, aksi sezgisel (sonuç 29 sırasından kötü değil).
    """
    for ad, v in (("c_tc", c_tc), ("c_rot", c_rot)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise CamError(f"Sıralama: {ad} sonlu ve ≥ 0 olmalı ({v!r})")
    if isinstance(exact_max, bool) or not isinstance(exact_max, int) or exact_max < 0:
        raise CamError(f"Sıralama: exact_max ≥ 0 tam sayı olmalı ({exact_max!r})")
    ops = list(ops)
    n = len(ops)
    maske = _denetle(n, prec)
    if n == 0:
        return [], 0, 0
    if n <= exact_max:
        sira = _tam(ops, maske, c_tc, c_rot)
    else:
        sira = _sezgisel(ops, maske)
        ozgun = list(range(n))
        if all(maske[i] & ~((1 << i) - 1) == 0 for i in range(n)):  # özgün sıra DAG'ı karşılıyorsa
            J = [c_tc * tc + c_rot * rot for tc, rot in (_sayim(ops, sira), _sayim(ops, ozgun))]
            if J[1] < J[0] - EPS:
                sira = ozgun
    tc, rot = _sayim(ops, sira)
    return sira, tc, rot
