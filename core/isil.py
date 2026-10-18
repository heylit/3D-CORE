"""
Kararlı hal ısı iletimi, tet4 ağı üzerinde (SPEC 56).

−∇·(k ∇T) = Q; sabit sıcaklık (Dirichlet), ısı akısı (Neumann), taşınım (Robin) ve hacimsel üretim.
Birimler: N – mm – s; güç mW, k mW/(mm·K), q mW/mm², h mW/(mm²·K), Q mW/mm³.
`model.bcs` ve `model.loads` okunmaz: ısıl koşullar bu dosyadaki kayıtlardır.

Teori: specs/56-isil-analiz.md (Incropera bölüm 3; Zienkiewicz–Taylor cilt 1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from core.elements import tet4
from core.model import Model, ModelError


@dataclass(frozen=True)
class Temperature:
    """Sabit sıcaklık: düğüm id, T [°C]."""

    node: int
    T: float


@dataclass(frozen=True)
class HeatFlux:
    """Γ_q: üçgenler (k, 3) düğüm id'leri, q [mW/mm²], parçaya giren pozitif."""

    tris: np.ndarray
    q: float


@dataclass(frozen=True)
class Convection:
    """Γ_h: üçgenler (k, 3), film katsayısı h [mW/(mm²·K)] > 0, ortam sıcaklığı T_inf [°C]."""

    tris: np.ndarray
    h: float
    T_inf: float


@dataclass(frozen=True)
class ThermalResult:
    node_ids: np.ndarray  # (n,) model.nodes sırası
    T: np.ndarray  # (n,) °C
    R: np.ndarray  # (n,) mW, tepki ısısı; sabit sıcaklıklı olmayan düğümde 0
    Q_gen: float  # mW, toplam üretim
    Q_flux: float  # mW, Γ_q'dan giren toplam
    Q_conv: float  # mW, Γ_h'den giren toplam (soğutmada negatif)

    def temperature(self, node_id: int) -> float:
        """Düğüm sıcaklığı [°C]. Bilinmeyen düğüm → ModelError."""
        i = np.flatnonzero(self.node_ids == node_id)
        if len(i) != 1:
            raise ModelError(f"Bilinmeyen düğüm: {node_id}")
        return float(self.T[i[0]])


# ---------- girdi denetimi ----------


def _sonlu(ad: str, x: float) -> float:
    x = float(x)
    if not np.isfinite(x):
        raise ModelError(f"{ad} sonlu bir sayı olmalı ({ad}={x})")
    return x


def _malzeme_degeri(model: Model, deger, ad: str) -> list[float]:
    """Eleman başına değer: tek sayı ya da Material.name → değer sözlüğü. Eksik ad → ModelError."""
    sonuc = []
    for e in model.elements:
        if isinstance(deger, Mapping):
            if e.material not in deger:
                raise ModelError(f"{ad}: '{e.material}' malzemesi için değer yok")
            sonuc.append(_sonlu(ad, deger[e.material]))
        else:
            sonuc.append(_sonlu(ad, deger))
    return sonuc


def _iletkenlikler(model: Model, k) -> list[float]:
    kler = _malzeme_degeri(model, k, "k")
    for kk in kler:
        if kk <= 0.0:
            raise ModelError(f"Isıl iletkenlik k > 0 olmalı (k={kk})")
    return kler


def _denetle(model: Model) -> None:
    """3B, en az bir eleman ve sadece tet4. Aksi halde ModelError."""
    model.validate()
    if model.dim != 3:
        raise ModelError(f"Isıl analiz sadece 3B modelde (dim={model.dim})")
    if not model.elements:
        raise ModelError("Isıl analiz: modelde eleman yok")
    for e in model.elements:
        if e.type != "tet4":
            raise ModelError(f"Eleman {e.id}: ısıl analiz sadece tet4 destekler ('{e.type}')")


def _ucgenler(model: Model, tris) -> tuple[np.ndarray, np.ndarray]:
    """(indeksler (k, 3), alanlar (k,)). Biçim hatası veya bilinmeyen düğüm → ModelError."""
    t = np.asarray(tris)
    if t.size == 0:
        return np.zeros((0, 3), dtype=int), np.zeros(0)
    if t.ndim != 2 or t.shape[1] != 3:
        raise ModelError(f"Üçgen dizisi (k, 3) olmalı (şekil {t.shape})")
    idx = np.array([[model.node_index(int(n)) for n in satir] for satir in t])
    X = np.array([n.xyz for n in model.nodes])[idx]  # (k, 3, 3)
    A = 0.5 * np.linalg.norm(np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]), axis=1)
    return idx, A


# ---------- birleştirme ----------


def _K_iletim(model: Model, kler: list[float]) -> sp.csr_matrix:
    n = len(model.nodes)
    satir, sutun, deger = [], [], []
    for e, kk in zip(model.elements, kler, strict=True):
        idx = [model.node_index(nid) for nid in e.nodes]
        k_e = tet4.kt(e, model, kk)
        satir += np.repeat(idx, 4).tolist()
        sutun += np.tile(idx, 4).tolist()
        deger += k_e.ravel().tolist()
    return sp.coo_matrix((deger, (satir, sutun)), shape=(n, n)).tocsr()


def conductivity_matrix(model: Model, k: float | Mapping[str, float]) -> sp.csr_matrix:
    """Global iletkenlik matrisi Σ ke (taşınım hariç), (n x n), model.nodes sırasında."""
    _denetle(model)
    return _K_iletim(model, _iletkenlikler(model, k))


# Taşınım iletkenliği Hh = h A / 12 · [[2 1 1] [1 2 1] [1 1 2]]
_HH = (np.ones((3, 3)) + np.eye(3)) / 12.0


def solve_thermal(
    model: Model,
    k: float | Mapping[str, float],
    *,
    temperatures: Sequence[Temperature] = (),
    fluxes: Sequence[HeatFlux] = (),
    convection: Sequence[Convection] = (),
    Q: float | Mapping[str, float] = 0.0,
) -> ThermalResult:
    """K T = F'yi çözer (specs/56-isil-analiz.md).

    K = Σ ke + Σ Hh, F = Σ fQ + Σ fq + Σ fh; sabit sıcaklıklı düğümler bölümlenir, R = K T − F.
    `model.bcs` ve `model.loads` OKUNMAZ: mekanik ve ısıl koşullar aynı modelde karışmaz.
    Hatalar (ModelError): dim ≠ 3, tet4 dışı eleman, k ≤ 0, h ≤ 0, sonlu olmayan değer, eksik malzeme adı,
    bilinmeyen düğüm, aynı düğüme iki farklı sıcaklık, hem sıcaklık hem taşınım yok, sonlu olmayan çözüm.
    """
    _denetle(model)
    kler = _iletkenlikler(model, k)
    Qler = _malzeme_degeri(model, Q, "Q")
    n = len(model.nodes)

    sabit: dict[int, float] = {}
    for t in temperatures:
        i = model.node_index(t.node)
        T = _sonlu(f"Düğüm {t.node} sıcaklığı", t.T)
        if i in sabit and sabit[i] != T:
            raise ModelError(f"Düğüm {t.node}: iki farklı sıcaklık ({sabit[i]} ve {T})")
        sabit[i] = T
    if not sabit and not convection:
        raise ModelError("Isıl analiz: sabit sıcaklık veya taşınım yok, sıcaklık belirsiz (tekil K)")

    K = _K_iletim(model, kler).tolil()
    F = np.zeros(n)

    # Hacimsel üretim: fQ = Q V / 4 · [1 1 1 1]
    Q_gen = 0.0
    for e, Qe in zip(model.elements, Qler, strict=True):
        if Qe == 0.0:
            continue
        V = tet4.volume(e, model)
        for nid in e.nodes:
            F[model.node_index(nid)] += Qe * V / 4.0
        Q_gen += Qe * V

    # Isı akısı: fq = q A / 3 · [1 1 1]
    Q_flux = 0.0
    for fl in fluxes:
        q = _sonlu("q", fl.q)
        idx, A = _ucgenler(model, fl.tris)
        np.add.at(F, idx, (q * A / 3.0)[:, None] * np.ones((1, 3)))
        Q_flux += q * A.sum()

    # Taşınım: Hh → K, fh = h T∞ A / 3 · [1 1 1]
    tasinim = []
    for cv in convection:
        h = _sonlu("h", cv.h)
        if h <= 0.0:
            raise ModelError(f"Film katsayısı h > 0 olmalı (h={h})")
        T_inf = _sonlu("T_inf", cv.T_inf)
        idx, A = _ucgenler(model, cv.tris)
        for tri, a in zip(idx, A, strict=True):
            for p in range(3):
                for r in range(3):
                    K[tri[p], tri[r]] += h * a * _HH[p, r]
        np.add.at(F, idx, (h * T_inf * A / 3.0)[:, None] * np.ones((1, 3)))
        tasinim.append((idx, A, h, T_inf))
    K = K.tocsr()

    # Bölümleme: tutulan (c) / serbest (f)
    T = np.zeros(n)
    c = np.array(sorted(sabit), dtype=int)
    T[c] = [sabit[i] for i in c]
    f = np.setdiff1d(np.arange(n), c)
    if len(f):
        Kff = K[f][:, f].tocsc()
        b = F[f] - K[f][:, c] @ T[c]
        T_f = spla.spsolve(Kff, b) if len(f) > 1 else b / Kff.toarray()[0, 0]
        T[f] = np.atleast_1d(T_f)
    if not np.all(np.isfinite(T)):
        raise ModelError("Isıl çözüm sonlu değil (tekil sistem: sınır koşulu olmayan bölge olabilir)")

    R = np.zeros(n)
    R[c] = (K @ T - F)[c]
    # Γ_h'den giren ısı: Σ h A (T∞ − T̄_üçgen)
    Q_conv = sum(float((h * A * (T_inf - T[idx].mean(axis=1))).sum()) for idx, A, h, T_inf in tasinim)
    return ThermalResult(
        node_ids=np.array([nd.id for nd in model.nodes]),
        T=T,
        R=R,
        Q_gen=float(Q_gen),
        Q_flux=float(Q_flux),
        Q_conv=float(Q_conv),
    )


# ---------- sonrası ----------


def heat_flux(model: Model, k: float | Mapping[str, float], result: ThermalResult) -> np.ndarray:
    """Eleman ısı akısı q_e = −k B T_e, (m, 3) mW/mm², eleman sırası."""
    _denetle(model)
    kler = _iletkenlikler(model, k)
    T = np.asarray(result.T, dtype=float)
    if T.shape != (len(model.nodes),):
        raise ModelError(f"Sıcaklık dizisi model düğüm sayısıyla uyuşmuyor ({T.shape})")
    q = np.zeros((len(model.elements), 3))
    for j, (e, kk) in enumerate(zip(model.elements, kler, strict=True)):
        _, G = tet4._hacim_ve_gradyan(e, model)
        T_e = T[[model.node_index(nid) for nid in e.nodes]]
        q[j] = -kk * G @ T_e
    return q


def nodal_heat_flux(model: Model, k: float | Mapping[str, float], result: ThermalResult) -> np.ndarray:
    """Düğüm ısı akısı, (n, 3) mW/mm², düğümü içeren elemanların hacim ağırlıklı ortalaması.

    Hiçbir elemana ait olmayan düğüm → ModelError.
    """
    q = heat_flux(model, k, result)
    n = len(model.nodes)
    toplam = np.zeros((n, 3))
    hacim = np.zeros(n)
    for e, q_e in zip(model.elements, q, strict=True):
        V = tet4.volume(e, model)
        for nid in e.nodes:
            i = model.node_index(nid)
            toplam[i] += V * q_e
            hacim[i] += V
    if np.any(hacim == 0.0):
        bos = [model.nodes[i].id for i in np.flatnonzero(hacim == 0.0)]
        raise ModelError(f"Hiçbir elemana ait olmayan düğüm(ler): {bos}")
    return toplam / hacim[:, None]
