"""
Emniyet katsayısı ve parça dayanımı köprüsü (SPEC 67b).

`emniyet` saf hesaptır (core); `parca_dayanimi` Part → mesh_part → yükler → çözüm → emniyet zinciridir
(gmsh + OCCT). Teori: specs/67-fem-genisletme.md (Emniyet katsayısı).

Biçim kuralları (SPEC metninin bıraktığı yerlerde bu modülün kararları):
- `Dayanim.n`: `model.nodes` sırasıyla düğüm başına `Rp0.2 / σ_vM`; σ_vM düğüm gerilmesidir
  (`core.post.nodal_stress_tensors` + `von_mises`). σ_vM = 0 ise n = +inf (tanım gereği, sessiz hata
  değil); bütün düğümlerde σ_vM = 0 ise `n_min = inf`, `dugum` en küçük id'li düğüm. Eşitlikte en küçük
  düğüm id'si seçilir.
- `Rp02`: tek sayı ya da malzeme adı → MPa eşlemi; düğüm, komşu elemanlarının malzemelerinden en küçük
  Rp0.2'yi alır. Eşlemde olmayan malzeme ya da `Rp02 <= 0` → ModelError.
- `T` verilirse (core.yukler ile aynı biçim) ısıl gerinme düşülür: düğüm gerilmesinden D·ε0 çıkarılır
  (ε0 düğüm sıcaklığıyla; D komşu elemanların malzemelerinin hacim ağırlıklı ortalaması). `alpha` yoksa
  ModelError.
- `parca_dayanimi`'nin `malzeme`'si B2 `Malzeme` kaydıdır (ördek tipleme: `fem_malzemesi()`,
  `iste(alan)`, `grup`; malzeme paketi import edilmez). `gevrek = (malzeme.grup == "dokme_demir")`.
- `kuvvet`: (FaceRef, (Fx, Fy, Fz)) yüze verilen toplam kuvvettir; yüz alanına bölünüp düzgün çekme
  olarak dağıtılır (`mesh.add_traction`). `basinc`: (FaceRef, p) `mesh.add_pressure` ile (içe doğru).
- `sabit`: yüzlerdeki bütün düğümlerin üç DOF'u tutulur (`mesh.fix`).
- `g`: (gx, gy, gz) mm/s²; `omega` rad/s ile `eksen = (nokta, yön)` birlikte verilir (biri eksik →
  ModelError).
- `T` verilirse `alpha = malzeme.iste("alpha")`, ısıl yük `T_ref`'e göre eklenir.
- Hatalar (ModelError): `sabit` boş ve hiçbir hacim / ısıl yük yok; bulunamayan ref; malzemede Rp02 yok;
  g ya da omega verilmiş ama rho yok (ya da 0); T verilmiş ama alpha yok.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

import mesh
from core import elements, post, yukler
from core.model import Model, ModelError
from core.solver import solve
from mesh.yuz_esleme import PartMesh

KENARLAR_TET10 = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))  # C3D10 kenar düğümleri 5..10
BIRIM_GENLESME = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])


@dataclass(frozen=True)
class Dayanim:
    n: np.ndarray  # (n_dugum,) emniyet katsayısı, inf olabilir
    n_min: float
    dugum: int  # n_min'in düğümü
    konum: np.ndarray  # (3,)
    sigma_vM_maks: float
    gevrek: bool


def _pozitif(deger, ad: str) -> float:
    try:
        x = float(deger)
    except (TypeError, ValueError):
        raise ModelError(f"{ad} bir sayı olmalı ({deger!r})") from None
    if not (math.isfinite(x) and x > 0.0):
        raise ModelError(f"{ad} pozitif ve sonlu olmalı ({ad}={deger})")
    return x


def _malzeme_degeri(deger, malzeme: str, ad: str) -> float:
    """Tek sayı ya da malzeme adı → değer eşleminden `malzeme`'nin değeri; eksik → ModelError."""
    if isinstance(deger, Mapping):
        if malzeme not in deger:
            raise ModelError(f"{ad} eşleminde '{malzeme}' malzemesi yok")
        deger = deger[malzeme]
    return float(deger)


def _isil_duzeltme(model: Model, T, T_ref: float, alpha) -> dict[int, np.ndarray]:
    """Düğüm başına D·ε0 (6,): komşu elemanlarda V_e D_e α_e ΔT(düğüm) hacim ağırlıklı ortalaması.

    ΔT düğüm sıcaklığıdır; tet10 kenar düğümünde iki köşenin ortalaması (core.yukler ile aynı doğrusal T).
    """
    sicaklik = yukler.temperature_lookup(model, T)
    toplam: dict[int, np.ndarray] = {}
    hacim: dict[int, float] = {}
    for e in model.elements:
        eleman = elements.get(e.type)
        V = eleman.volume(e, model)
        a = yukler.alpha_of(alpha, e.material)
        Dm = eleman.D(model.material(e.material))
        kose = [sicaklik(nid) - T_ref for nid in e.nodes[:4]]
        dT = kose + [(kose[i] + kose[j]) / 2 for i, j in KENARLAR_TET10[: len(e.nodes) - 4]]
        for nid, dt in zip(e.nodes, dT, strict=True):
            toplam[nid] = toplam.get(nid, 0.0) + V * a * dt * (Dm @ BIRIM_GENLESME)
            hacim[nid] = hacim.get(nid, 0.0) + V
    return {nid: toplam[nid] / hacim[nid] for nid in toplam}


def emniyet(
    model: Model,
    u: np.ndarray,
    Rp02: float | Mapping[str, float],
    *,
    gevrek: bool = False,
    T=None,
    T_ref: float = 0.0,
    alpha=None,
) -> Dayanim:
    """Düğüm başına emniyet katsayısı n = Rp0.2 / σ_vM; T verilirse ısıl gerinme düşülür.

    σ_vM = 0 olan düğümde n = +inf (tanım gereği).
    """
    if T is not None and alpha is None:
        raise ModelError("Isıl gerinme düşmek için alpha gerekli (T verildi, alpha yok)")
    u = np.asarray(u, dtype=float)
    if u.shape != (model.n_dof,):
        raise ModelError(f"u boyu modelin DOF sayısı olmalı ({u.shape} ≠ ({model.n_dof},))")

    # Düğüm Rp0.2: komşu elemanların malzemelerinden en küçüğü
    Rp_dugum: dict[int, float] = {}
    for e in model.elements:
        rp = _pozitif(_malzeme_degeri(Rp02, e.material, "Rp02"), f"Rp02 ('{e.material}')")
        for nid in e.nodes:
            Rp_dugum[nid] = min(Rp_dugum.get(nid, math.inf), rp)

    sigma = post.nodal_stress_tensors(model, u)
    if T is not None:
        for nid, d in _isil_duzeltme(model, T, float(T_ref), alpha).items():
            sigma[nid] = sigma[nid] - d
    S = np.array([sigma.get(n.id, np.zeros(6)) for n in model.nodes]).reshape(-1, 6)
    vm = np.atleast_1d(post.von_mises(S)) if len(S) else np.zeros(0)
    Rp = np.array([Rp_dugum.get(n.id, math.inf) for n in model.nodes])
    with np.errstate(divide="ignore"):
        n = np.where(vm > 0.0, Rp / np.where(vm > 0.0, vm, 1.0), math.inf)

    ids = np.array([nd.id for nd in model.nodes])
    if len(ids) == 0:
        raise ModelError("Emniyet katsayısı: modelde düğüm yok")
    n_min = float(n.min())
    i = int(np.flatnonzero(n == n_min)[np.argmin(ids[n == n_min])])
    return Dayanim(
        n=n,
        n_min=n_min,
        dugum=int(ids[i]),
        konum=np.array(model.nodes[i].xyz, dtype=float),
        sigma_vM_maks=float(vm.max()),
        gevrek=bool(gevrek),
    )


def _iste(malzeme, alan: str) -> float:
    """B2 `Malzeme.iste(alan)`; malzeme paketinin hatası core ModelError'a çevrilir."""
    try:
        return float(malzeme.iste(alan))
    except ModelError:
        raise
    except (ValueError, KeyError, LookupError, TypeError, AttributeError) as hata:
        raise ModelError(f"Malzeme '{getattr(malzeme, 'id', malzeme)}': {alan} alınamadı ({hata})") from None


def _yuz_alani(model: Model, tris: np.ndarray) -> float:
    """Yüzün ∫ dA'sı, add_traction'ın kendi kuralıyla (t = (1, 0, 0) yükünün toplamı; model değişmez)."""
    once = len(model.loads)
    try:
        mesh.add_traction(model, tris, (1.0, 0.0, 0.0))
        return float(sum(ld.value for ld in model.loads[once:] if ld.dof == "ux"))
    finally:
        del model.loads[once:]


def parca_dayanimi(
    part,
    h: float,
    malzeme,
    *,
    order: int = 2,
    sabit: Sequence = (),
    basinc: Sequence[tuple] = (),
    kuvvet: Sequence[tuple] = (),
    g=None,
    omega=None,
    eksen=None,
    T=None,
    T_ref: float = 0.0,
) -> tuple[PartMesh, np.ndarray, Dayanim]:
    """Parçayı ağlar, FaceRef yüzlerine mesnet ve yük koyar, çözer; (ağ, u, Dayanim) döndürür."""
    from geometry.part import GeometryError

    sabit, basinc, kuvvet = list(sabit), list(basinc), list(kuvvet)
    if not sabit and g is None and omega is None and T is None:
        raise ModelError("parca_dayanimi: sabit yüz yok ve hacim / ısıl yük yok")
    if (omega is None) != (eksen is None):
        raise ModelError("parca_dayanimi: omega ve eksen birlikte verilmeli")
    for ref in [*sabit, *(r for r, _ in basinc), *(r for r, _ in kuvvet)]:
        try:
            part.find(ref)
        except GeometryError as hata:
            raise ModelError(str(hata)) from None
    Rp02 = _iste(malzeme, "Rp02")
    if g is not None or omega is not None:
        _pozitif(_iste(malzeme, "rho"), "rho")
    alpha = _iste(malzeme, "alpha") if T is not None else None
    try:
        mat = malzeme.fem_malzemesi()
    except ModelError:
        raise
    except (ValueError, KeyError, LookupError, TypeError) as hata:
        raise ModelError(f"Malzeme FEM kaydına çevrilemedi ({hata})") from None

    pm = mesh.mesh_part(part, h, mat, order=order)
    m = pm.model
    for ref in sabit:
        mesh.fix(m, pm.nodes(part, ref))
    for ref, p in basinc:
        mesh.add_pressure(m, pm.triangles(part, ref), p)
    for ref, F in kuvvet:
        tris = pm.triangles(part, ref)
        F = yukler.vector3(F, f"'{ref}' kuvveti")
        mesh.add_traction(m, tris, F / _yuz_alani(m, tris))
    hacim = []
    if g is not None:
        hacim += yukler.gravity_loads(m, g)
    if omega is not None:
        p0, a = eksen
        hacim += yukler.centrifugal_loads(m, omega, p0, a)
    if T is not None:
        hacim += yukler.thermal_loads(m, T, T_ref, alpha)
    yukler.add_loads(m, hacim)

    u = solve(m).u
    gevrek = getattr(malzeme, "grup", None) == "dokme_demir"
    return pm, u, emniyet(m, u, Rp02, gevrek=gevrek, T=T, T_ref=T_ref, alpha=alpha)
