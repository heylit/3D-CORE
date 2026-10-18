"""
Hacim kuvvetleri ve ısıl yük: düğüm Load listeleri (SPEC 67b).

Saf hesap: numpy + core (K18). İşlevler modeli DEĞİŞTİRMEZ; döndürülen listeyi `add_loads` modele ekler.
Teori: specs/67-fem-genisletme.md (Hacim kuvvetleri, Isıl yük).

Biçim kuralları (SPEC metninin bıraktığı yerlerde bu modülün kararları):
- Döndürülen her liste düğüm id ve dof sırasıyla ("ux", "uy", "uz") dizilir; her (düğüm, dof) en çok bir
  kez geçer, değeri tam sıfır olan bileşen yazılmaz.
- Eleman tipleri: "tet4" ve "tet10" (67a). Başka tip, `model.dim != 3` ya da boş model → ModelError.
- Yoğunluk `Material.rho` (t/mm³); yerçekimi ve merkezkaçta bir elemanın malzemesinde `rho <= 0` →
  ModelError.
- `T`: düğüm id → °C eşlemi ya da SPEC 56 `ThermalResult` (`node_ids`, `T` dizileri; ördek tipleme,
  core.isil import edilmez). Modelin bir köşe düğümü için sıcaklık yoksa ModelError. tet10'da T
  köşelerden doğrusal alınır (SPEC): kenar düğümünün sıcaklığı iki ucunun ortalamasıdır, verilen kenar
  değeri kullanılmaz.
- `alpha`: tek sayı ya da malzeme adı → 1/K eşlemi; eşlemde olmayan malzeme ya da sonlu olmayan değer →
  ModelError.
- `thermal_strain_stress` sonucu eleman sırasıdır, Voigt sırası core.post ile aynı (xx, yy, zz, xy, xz,
  yz); tet10'da Gauss noktası ortalaması (SPEC 13 eleman gerilmesi sözleşmesi).
- `add_loads`: modeldeki mevcut Load'larla birlikte aynı (düğüm, dof) toplanır ve tek Load kalır; ilk
  geçtiği sıradaki yerinde durur. Bilinmeyen düğüm ya da dof → ModelError.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence

import numpy as np

from core.elements import tet4, tet10
from core.model import Element, Load, Model, ModelError

DOFLAR = ("ux", "uy", "uz")
KATI_TIPLER = ("tet4", "tet10")

# Hidrostatik birim gerinme [1, 1, 1, 0, 0, 0] (Voigt)
BIRIM_GENLESME = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])

# tet4 hacim kuvveti: 4 noktalı Gauss kuralı (2. derece; N_a · doğrusal b tam)
GAUSS_L, GAUSS_W = tet10.GAUSS_L, tet10.GAUSS_W

# tet10 hacim kuvveti: 15 noktalı Keast kuralında N (15, 10) ve ∂N/∂ξ (15, 10, 3)
KEAST_N = np.array([tet10.N(L) for L in tet10.KEAST_L])
KEAST_DN = np.array([tet10._dN_dL(L) @ tet10._DL_DXI for L in tet10.KEAST_L])


def _kati_model(model: Model) -> None:
    """Model 3B ve yalnız tet4 / tet10 elemanlıdır; değilse ModelError."""
    if model.dim != 3:
        raise ModelError(f"Hacim / ısıl yük 3B katı model ister (dim={model.dim})")
    if not model.elements:
        raise ModelError("Hacim / ısıl yük: modelde eleman yok")
    for e in model.elements:
        if e.type not in KATI_TIPLER:
            raise ModelError(f"Eleman {e.id}: hacim / ısıl yük yalnız tet4 ve tet10 için ('{e.type}')")


def vector3(v, ad: str) -> np.ndarray:
    try:
        x = np.asarray(v, dtype=float).ravel()
    except (TypeError, ValueError):
        raise ModelError(f"{ad} üç sayı olmalı ({v!r})") from None
    if x.shape != (3,) or not np.all(np.isfinite(x)):
        raise ModelError(f"{ad} üç sonlu sayı olmalı ({v!r})")
    return x


def _rho(model: Model, e: Element) -> float:
    rho = model.material(e.material).rho
    if not rho > 0.0:
        raise ModelError(f"Eleman {e.id}: malzeme '{e.material}' için ρ > 0 olmalı (ρ={rho})")
    return float(rho)


def _yuk_listesi(toplam: dict[int, np.ndarray]) -> list[Load]:
    """Düğüm id ve dof sırasıyla Load listesi; tam sıfır bileşen yazılmaz."""
    return [
        Load(nid, dof, float(v))
        for nid in sorted(toplam)
        for dof, v in zip(DOFLAR, toplam[nid], strict=True)
        if v != 0.0
    ]


def _ekle(toplam: dict[int, np.ndarray], dugumler: Sequence[int], f: np.ndarray) -> None:
    for nid, fa in zip(dugumler, f, strict=True):
        toplam[nid] = toplam.get(nid, np.zeros(3)) + fa


def _hacim_kuvveti(model: Model, b: Callable[[Element, np.ndarray], np.ndarray]) -> list[Load]:
    """f_a = ∫ N_a b dV; b(e, x) noktalardaki (q, 3) kuvvet yoğunluğu [N/mm³], x (q, 3).

    tet4: N_a = L_a, det J = 6V, 4 noktalı Gauss. tet10: izoparametrik N, 15 noktalı Keast (eğri elemanda
    da Σ_a f_a = ∫ b dV tam: b doğrusal, det J 3. derece).
    """
    _kati_model(model)
    toplam: dict[int, np.ndarray] = {}
    for e in model.elements:
        X = np.array([model.node(nid).xyz for nid in e.nodes])
        if e.type == "tet4":
            V = tet4.volume(e, model)
            Nq = GAUSS_L  # (4, 4): satır nokta, sütun N_a
            wdet = GAUSS_W * 6.0 * V
        else:
            Nq = KEAST_N
            detJ = np.linalg.det(np.einsum("ni,qnj->qij", X, KEAST_DN))  # J = Xᵀ ∂N/∂ξ, (15,)
            if not np.all(detJ > 1e-12 * float(np.abs(X - X.mean(axis=0)).max()) ** 3):
                for L in tet10.KEAST_L:
                    tet10._nokta(e, X, L)  # det J ≤ 0 → tet10'un ModelError'ı
            wdet = tet10.KEAST_W * detJ
        bq = b(e, Nq @ X)  # (q, 3)
        _ekle(toplam, e.nodes, Nq.T @ (wdet[:, None] * bq))
    return _yuk_listesi(toplam)


def gravity_loads(model: Model, g: Sequence[float]) -> list[Load]:
    """b = ρ g (N/mm³) için tutarlı düğüm kuvvetleri; g mm/s² (Dünya |g| = 9810, çağıran verir).

    tet4'te her düğüme ρ g V/4; düz tet10'da köşelere −ρ g V/20, kenarlara ρ g V/5.
    """
    g = vector3(g, "Yerçekimi ivmesi g")
    return _hacim_kuvveti(model, lambda e, x: np.broadcast_to(_rho(model, e) * g, x.shape))


def centrifugal_loads(
    model: Model, omega: float, point: Sequence[float], axis: Sequence[float]
) -> list[Load]:
    """b = ρ ω² r⊥ için tutarlı düğüm kuvvetleri; ω rad/s, eksen `point` + birim olmayabilen `axis`.

    r⊥ = (x − p0) − ((x − p0)·â) â. `axis` sıfır vektör ya da sonlu olmayan girdi → ModelError.
    """
    try:
        omega = float(omega)
    except (TypeError, ValueError):
        raise ModelError(f"Açısal hız ω bir sayı olmalı ({omega!r})") from None
    if not math.isfinite(omega):
        raise ModelError(f"Açısal hız ω sonlu olmalı (ω={omega})")
    p0 = vector3(point, "Eksen noktası")
    a = vector3(axis, "Eksen yönü")
    boy = float(np.linalg.norm(a))
    if not boy > 0.0:
        raise ModelError("Eksen yönü sıfır vektör olamaz")
    a = a / boy

    def b(e: Element, x: np.ndarray) -> np.ndarray:
        d = x - p0
        return _rho(model, e) * omega**2 * (d - np.outer(d @ a, a))

    return _hacim_kuvveti(model, b)


def temperature_lookup(model: Model, T) -> Callable[[int], float]:
    """Düğüm id → sıcaklık [°C]; T eşlem ya da ThermalResult (node_ids, T). Eksik düğüm → ModelError."""
    if hasattr(T, "node_ids") and hasattr(T, "T"):
        ids = np.asarray(T.node_ids).ravel()
        degerler = np.asarray(T.T, dtype=float).ravel()
        if ids.shape != degerler.shape:
            raise ModelError(f"ThermalResult: node_ids {ids.shape} ve T {degerler.shape} aynı boyda olmalı")
        T = {int(i): float(v) for i, v in zip(ids, degerler, strict=True)}
    elif not isinstance(T, Mapping):
        raise ModelError(f"Sıcaklık alanı düğüm eşlemi ya da ThermalResult olmalı ({type(T).__name__})")

    def sicaklik(nid: int) -> float:
        if nid not in T:
            raise ModelError(f"Düğüm {nid} için sıcaklık yok")
        try:
            v = float(T[nid])
        except (TypeError, ValueError):
            raise ModelError(f"Düğüm {nid}: sıcaklık bir sayı olmalı ({T[nid]!r})") from None
        if not math.isfinite(v):
            raise ModelError(f"Düğüm {nid}: sıcaklık sonlu olmalı ({v})")
        return v

    return sicaklik


def alpha_of(alpha, malzeme: str) -> float:
    """Isıl genleşme katsayısı [1/K]: tek sayı ya da malzeme adı → değer eşlemi."""
    if isinstance(alpha, Mapping):
        if malzeme not in alpha:
            raise ModelError(f"alpha eşleminde '{malzeme}' malzemesi yok")
        alpha = alpha[malzeme]
    try:
        a = float(alpha)
    except (TypeError, ValueError):
        raise ModelError(f"alpha bir sayı olmalı ({alpha!r})") from None
    if not math.isfinite(a):
        raise ModelError(f"alpha sonlu olmalı ({a})")
    return a


def _isil_noktalar(
    model: Model, e: Element, sicaklik: Callable[[int], float], T_ref: float, alpha
) -> tuple[list[np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    """Elemanın integrasyon noktaları: (B listesi, w · det J (q,), ε0 (q, 6), D (6, 6)).

    tet4: tek nokta, T dört köşenin ortalaması. tet10: 4 Gauss noktası, T köşelerden doğrusal.
    """
    mat = model.material(e.material)
    Dm = tet4.D(mat)
    a = alpha_of(alpha, e.material)
    dT = np.array([sicaklik(nid) for nid in e.nodes[:4]]) - T_ref
    if e.type == "tet4":
        V = tet4.volume(e, model)
        return [tet4.B(e, model)], np.array([V]), a * dT.mean() * BIRIM_GENLESME[None, :], Dm
    X = np.array([model.node(nid).xyz for nid in e.nodes])
    Bs, wdet = [], []
    for L, w in zip(GAUSS_L, GAUSS_W, strict=True):
        dN_dx, detJ = tet10._nokta(e, X, L)
        Bs.append(tet10._B(dN_dx))
        wdet.append(w * detJ)
    eps0 = a * (GAUSS_L @ dT)[:, None] * BIRIM_GENLESME[None, :]
    return Bs, np.array(wdet), eps0, Dm


def thermal_loads(model: Model, T, T_ref: float, alpha: float | Mapping[str, float]) -> list[Load]:
    """f_e = ∫ Bᵀ D ε0 dV, ε0 = α (T − T_ref) [1, 1, 1, 0, 0, 0]ᵀ."""
    _kati_model(model)
    sicaklik = temperature_lookup(model, T)
    T_ref = float(T_ref)
    toplam: dict[int, np.ndarray] = {}
    for e in model.elements:
        Bs, wdet, eps0, Dm = _isil_noktalar(model, e, sicaklik, T_ref, alpha)
        f = sum(w * Bm.T @ (Dm @ ep) for Bm, w, ep in zip(Bs, wdet, eps0, strict=True))
        _ekle(toplam, e.nodes, np.asarray(f).reshape(-1, 3))
    return _yuk_listesi(toplam)


def thermal_strain_stress(model: Model, u: np.ndarray, T, T_ref: float, alpha) -> np.ndarray:
    """(m, 6) eleman gerilmesi σ = D (B u − ε0) [MPa]; `u` modelin DOF düzeninde."""
    _kati_model(model)
    u = np.asarray(u, dtype=float)
    if u.shape != (model.n_dof,):
        raise ModelError(f"u boyu modelin DOF sayısı olmalı ({u.shape} ≠ ({model.n_dof},))")
    sicaklik = temperature_lookup(model, T)
    T_ref = float(T_ref)
    sonuc = np.zeros((len(model.elements), 6))
    for k, e in enumerate(model.elements):
        Bs, _, eps0, Dm = _isil_noktalar(model, e, sicaklik, T_ref, alpha)
        d = u[[model.dof_index(nid, dof) for nid in e.nodes for dof in DOFLAR]]
        sonuc[k] = np.mean([Dm @ (Bm @ d - ep) for Bm, ep in zip(Bs, eps0, strict=True)], axis=0)
    return sonuc


def add_loads(model: Model, loads: Iterable[Load]) -> None:
    """Load'ları modele ekler; aynı (düğüm, dof) toplanır, tek Load kalır."""
    yeni = list(loads)
    for ld in yeni:
        if not isinstance(ld, Load):
            raise ModelError(f"add_loads yalnız Load kabul eder ({type(ld).__name__})")
        model.dof_index(ld.node, ld.dof)  # bilinmeyen düğüm / dof → ModelError (model değişmeden)
    toplam: dict[tuple[int, str], float] = {}
    for ld in [*model.loads, *yeni]:
        anahtar = (ld.node, ld.dof)
        toplam[anahtar] = toplam.get(anahtar, 0.0) + ld.value
    model.loads[:] = [Load(nid, dof, v) for (nid, dof), v in toplam.items()]
