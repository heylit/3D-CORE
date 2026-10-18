"""
Geçici ısı iletimi, tet4 ağı üzerinde (SPEC 68b).

C Ṫ + K T = F(t), θ-yöntemi (sabit Δt):
    (C/Δt + θ K) T_{n+1} = (C/Δt − (1 − θ) K) T_n + θ F_{n+1} + (1 − θ) F_n
Sınır koşulları SPEC 56'nın kayıtlarıdır (core.isil); her birine isteğe bağlı bir zaman çarpanı f(t) eklenir.
Birimler: ρ t/mm³, cp mJ/(t·K), k mW/(mm·K), zaman s, enerji mJ.

Teori: specs/68b-gecici-isil-termomekanik.md (Incropera bölüm 5; Zienkiewicz–Taylor cilt 1).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from core.elements import tet4
from core.isil import (
    _HH,
    Convection,
    HeatFlux,
    Temperature,
    _denetle,
    _malzeme_degeri,
    _sonlu,
    _ucgenler,
    conductivity_matrix,
)
from core.model import Model, ModelError

# Zaman karşılaştırmalarında göreli tolerans (kayan nokta ile üretilen adım zamanları için)
_ZAMAN_TOL = 1e-9


@dataclass(frozen=True)
class TransientResult:
    t: np.ndarray  # (s,) s, t[0] = 0
    T: np.ndarray  # (s, n) °C, model.nodes sırası
    node_ids: np.ndarray  # (n,)
    E_in: np.ndarray  # (s,) mJ, birikimli net giriş (enerji dengesi için)

    def at(self, t: float) -> np.ndarray:
        """t anındaki sıcaklık alanı (n,), kayıtlı zamanlar arası doğrusal. Aralık dışı → ModelError."""
        t = float(t)
        t0, t1 = float(self.t[0]), float(self.t[-1])
        tol = _ZAMAN_TOL * max(1.0, abs(t1))
        if not np.isfinite(t) or t < t0 - tol or t > t1 + tol:
            raise ModelError(f"Zaman aralık dışı: t={t}, kayıt [{t0}, {t1}]")
        t = min(max(t, t0), t1)
        j = int(np.searchsorted(self.t, t, side="right"))
        if j >= len(self.t):
            return self.T[-1].copy()
        if j == 0:
            return self.T[0].copy()
        ta, tb = self.t[j - 1], self.t[j]
        w = (t - ta) / (tb - ta)
        return (1.0 - w) * self.T[j - 1] + w * self.T[j]


# ---------- birleştirme ----------


def _rho_cp(model: Model, rho_cp) -> list[float]:
    degerler = _malzeme_degeri(model, rho_cp, "rho_cp")
    for v in degerler:
        if v <= 0.0:
            raise ModelError(f"Isıl kapasite ρ·cp > 0 olmalı (rho_cp={v})")
    return degerler


def _C_kapasite(model: Model, rcler: list[float], lumped: bool) -> sp.csr_matrix:
    """Global ısıl kapasite matrisi Σ Ce (n x n)."""
    n = len(model.nodes)
    satir, sutun, deger = [], [], []
    for e, rc in zip(model.elements, rcler, strict=True):
        idx = [model.node_index(nid) for nid in e.nodes]
        c_e = tet4.ct(e, model, rc, lumped)
        satir += np.repeat(idx, 4).tolist()
        sutun += np.tile(idx, 4).tolist()
        deger += c_e.ravel().tolist()
    return sp.coo_matrix((deger, (satir, sutun)), shape=(n, n)).tocsr()


def _baslangic(model: Model, T0) -> np.ndarray:
    n = len(model.nodes)
    if isinstance(T0, Mapping):
        T = np.full(n, np.nan)
        for nid, v in T0.items():
            T[model.node_index(int(nid))] = _sonlu(f"T0[{nid}]", v)
        if np.any(np.isnan(T)):
            eksik = [model.nodes[i].id for i in np.flatnonzero(np.isnan(T))]
            raise ModelError(f"T0 şu düğümler için verilmedi: {eksik[:10]}")
        return T
    return np.full(n, _sonlu("T0", T0))


def _zaman_carpanlari(zaman, n_kayit: int) -> dict[int, Callable[[float], float]]:
    if zaman is None:
        return {}
    sonuc = {}
    for i, f in zaman.items():
        i = int(i)
        if not 0 <= i < n_kayit:
            raise ModelError(f"zaman: sınır kaydı sırası {i} yok (0..{n_kayit - 1})")
        if not callable(f):
            raise ModelError(f"zaman[{i}] çağrılabilir bir f(t) olmalı")
        sonuc[i] = f
    return sonuc


def _carpan(fler: dict, i: int, t: float) -> float:
    if i not in fler:
        return 1.0
    return _sonlu(f"zaman[{i}]({t})", fler[i](t))


def _adim_zamanlari(t_end: float, dt: float) -> np.ndarray:
    """0, Δt, 2Δt, ..., t_end. Son adım t_end'e kısaltılır (en çok bir kısa adım)."""
    N = math.floor(t_end / dt * (1.0 + _ZAMAN_TOL))
    t = dt * np.arange(N + 1)
    if t_end - t[-1] > _ZAMAN_TOL * t_end:
        t = np.append(t, t_end)
    else:
        t[-1] = t_end
    return t


# ---------- çözüm ----------


def solve_transient(
    model: Model,
    k: float | Mapping[str, float],
    rho_cp: float | Mapping[str, float],
    *,
    T0: float | Mapping[int, float],
    t_end: float,
    dt: float,
    theta: float = 1.0,
    lumped: bool = False,
    temperatures: Sequence[Temperature] = (),
    fluxes: Sequence[HeatFlux] = (),
    convection: Sequence[Convection] = (),
    Q: float | Mapping[str, float] = 0.0,
    zaman: Mapping[int, Callable[[float], float]] | None = None,
    kaydet: Sequence[float] | None = None,
) -> TransientResult:
    """
    Geçici ısıl çözüm. `zaman`: sınır kaydı sırası (temperatures + fluxes + convection, bu sırayla)
    → çarpan f(t). rho_cp: ρ·cp, malzeme adına göre de verilebilir.
    f(t) değeri çarpar: T̄(t) = f(t) T̄, q̄(t) = f(t) q̄, T∞(t) = f(t) T∞ (h sabit).
    θ ∉ [0.5, 1], dt ≤ 0, t_end < dt → ModelError.

    Her adımda, R tutulu düğüm tepkisi (serbest düğümde 0) olmak üzere tam olarak sağlanır:
        C (T_{n+1} − T_n)/Δt + θ K T_{n+1} + (1 − θ) K T_n = θ F_{n+1} + (1 − θ) F_n + R_{n+1}
    E_in = Σ Δt · 1ᵀ(sağ taraf − K terimleri) = 1ᵀ C (T − T0).
    """
    _denetle(model)
    theta = _sonlu("theta", theta)
    if not 0.5 <= theta <= 1.0:
        raise ModelError(f"θ [0.5, 1] aralığında olmalı (koşulsuz kararlılık), θ={theta}")
    dt = _sonlu("dt", dt)
    t_end = _sonlu("t_end", t_end)
    if dt <= 0.0:
        raise ModelError(f"Zaman adımı dt > 0 olmalı (dt={dt})")
    if t_end < dt:
        raise ModelError(f"t_end ≥ dt olmalı (t_end={t_end}, dt={dt})")

    n = len(model.nodes)
    K = conductivity_matrix(model, k).tolil()
    C = _C_kapasite(model, _rho_cp(model, rho_cp), lumped)
    Qler = _malzeme_degeri(model, Q, "Q")
    temperatures, fluxes, convection = list(temperatures), list(fluxes), list(convection)
    n_T, n_q = len(temperatures), len(fluxes)
    fler = _zaman_carpanlari(zaman, n_T + n_q + len(convection))

    # Sabit sıcaklıklar: düğüm indeksi → (kayıt sırası, T̄)
    sabit: dict[int, tuple[int, float]] = {}
    for r, tp in enumerate(temperatures):
        i = model.node_index(tp.node)
        T = _sonlu(f"Düğüm {tp.node} sıcaklığı", tp.T)
        if i in sabit and sabit[i][1] != T:
            raise ModelError(f"Düğüm {tp.node}: iki farklı sıcaklık ({sabit[i][1]} ve {T})")
        sabit[i] = (r, T)

    # Zamandan bağımsız üretim yükü: fQ = Q V / 4
    F_Q = np.zeros(n)
    for e, Qe in zip(model.elements, Qler, strict=True):
        if Qe != 0.0:
            V = tet4.volume(e, model)
            for nid in e.nodes:
                F_Q[model.node_index(nid)] += Qe * V / 4.0

    # Birim yük vektörleri (çarpanla ölçeklenecek): (kayıt sırası, vektör)
    birim: list[tuple[int, np.ndarray]] = []
    for j, fl in enumerate(fluxes):
        q = _sonlu("q", fl.q)
        idx, A = _ucgenler(model, fl.tris)
        v = np.zeros(n)
        np.add.at(v, idx, (q * A / 3.0)[:, None] * np.ones((1, 3)))
        birim.append((n_T + j, v))
    for j, cv in enumerate(convection):
        h = _sonlu("h", cv.h)
        if h <= 0.0:
            raise ModelError(f"Film katsayısı h > 0 olmalı (h={h})")
        T_inf = _sonlu("T_inf", cv.T_inf)
        idx, A = _ucgenler(model, cv.tris)
        for tri, a in zip(idx, A, strict=True):
            for p in range(3):
                for s in range(3):
                    K[tri[p], tri[s]] += h * a * _HH[p, s]
        v = np.zeros(n)
        np.add.at(v, idx, (h * T_inf * A / 3.0)[:, None] * np.ones((1, 3)))
        birim.append((n_T + n_q + j, v))
    K = K.tocsr()

    def F(t: float) -> np.ndarray:
        f = F_Q.copy()
        for r, v in birim:
            f += _carpan(fler, r, t) * v
        return f

    c = np.array(sorted(sabit), dtype=int)
    f_ = np.setdiff1d(np.arange(n), c)

    def T_sabit(t: float) -> np.ndarray:
        return np.array([_carpan(fler, sabit[i][0], t) * sabit[i][1] for i in c])

    t_adim = _adim_zamanlari(t_end, dt)
    T_n = _baslangic(model, T0)
    F_n = F(0.0)
    TT = np.empty((len(t_adim), n))
    E = np.zeros(len(t_adim))
    TT[0] = T_n
    bir = np.ones(n)
    carpanlar: dict[float, object] = {}  # Δt → splu(A_ff)

    for m in range(1, len(t_adim)):
        h_t = float(t_adim[m] - t_adim[m - 1])
        anahtar = round(h_t, 15)
        A = (C / h_t + theta * K).tocsr()
        if anahtar not in carpanlar and len(f_):
            carpanlar[anahtar] = spla.splu(A[f_][:, f_].tocsc())
        F_m = F(float(t_adim[m]))
        rhs = (C / h_t - (1.0 - theta) * K) @ T_n + theta * F_m + (1.0 - theta) * F_n
        T_m = np.zeros(n)
        if len(c):
            T_m[c] = T_sabit(float(t_adim[m]))
        if len(f_):
            T_m[f_] = carpanlar[anahtar].solve(rhs[f_] - A[f_][:, c] @ T_m[c])
        if not np.all(np.isfinite(T_m)):
            raise ModelError(f"Geçici ısıl çözüm sonlu değil (t={t_adim[m]})")
        R = np.zeros(n)
        if len(c):
            R[c] = (A @ T_m - rhs)[c]
        akis = theta * (F_m - K @ T_m) + (1.0 - theta) * (F_n - K @ T_n) + R
        E[m] = E[m - 1] + h_t * float(bir @ akis)
        TT[m] = T_m
        T_n, F_n = T_m, F_m

    node_ids = np.array([nd.id for nd in model.nodes])
    tam = TransientResult(t=t_adim, T=TT, node_ids=node_ids, E_in=E)
    if kaydet is None:
        return tam
    istek = sorted({0.0, *(float(x) for x in kaydet)})
    for x in istek:
        if not np.isfinite(x) or x < 0.0 or x > t_end * (1.0 + _ZAMAN_TOL):
            raise ModelError(f"kaydet: {x} zamanı [0, t_end={t_end}] dışında")
    istek_t = np.array(istek)
    return TransientResult(
        t=istek_t,
        T=np.array([tam.at(x) for x in istek_t]),
        node_ids=node_ids,
        E_in=np.interp(istek_t, t_adim, E),
    )
