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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core.model import Model
from mesh.yuz_esleme import PartMesh


@dataclass(frozen=True)
class Dayanim:
    n: np.ndarray  # (n_dugum,) emniyet katsayısı, inf olabilir
    n_min: float
    dugum: int  # n_min'in düğümü
    konum: np.ndarray  # (3,)
    sigma_vM_maks: float
    gevrek: bool


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
    """Düğüm başına emniyet katsayısı n = Rp0.2 / σ_vM; T verilirse ısıl gerinme düşülür."""
    raise NotImplementedError("SPEC 67b: emniyet")


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
    raise NotImplementedError("SPEC 67b: parca_dayanimi")
