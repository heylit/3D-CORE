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
  core.isil import edilmez). Modelin bir köşe düğümü için sıcaklık yoksa ModelError. tet10 kenar
  düğümünün sıcaklığı verilmemişse iki ucunun ortalamasıdır; verilmişse o kullanılır.
- `alpha`: tek sayı ya da malzeme adı → 1/K eşlemi; eşlemde olmayan malzeme ya da sonlu olmayan değer →
  ModelError.
- `thermal_strain_stress` sonucu eleman sırasıdır, Voigt sırası core.post ile aynı (xx, yy, zz, xy, xz,
  yz); tet10'da Gauss noktası ortalaması (SPEC 13 eleman gerilmesi sözleşmesi).
- `add_loads`: modeldeki mevcut Load'larla birlikte aynı (düğüm, dof) toplanır ve tek Load kalır; ilk
  geçtiği sıradaki yerinde durur. Bilinmeyen düğüm ya da dof → ModelError.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from core.model import Load, Model


def gravity_loads(model: Model, g: Sequence[float]) -> list[Load]:
    """b = ρ g (N/mm³) için tutarlı düğüm kuvvetleri; g mm/s² (Dünya |g| = 9810, çağıran verir)."""
    raise NotImplementedError("SPEC 67b: gravity_loads")


def centrifugal_loads(
    model: Model, omega: float, point: Sequence[float], axis: Sequence[float]
) -> list[Load]:
    """b = ρ ω² r⊥ için tutarlı düğüm kuvvetleri; ω rad/s, eksen `point` + birim olmayabilen `axis`.

    `axis` sıfır vektör ya da sonlu olmayan girdi → ModelError.
    """
    raise NotImplementedError("SPEC 67b: centrifugal_loads")


def thermal_loads(model: Model, T, T_ref: float, alpha: float | Mapping[str, float]) -> list[Load]:
    """f_e = ∫ Bᵀ D ε0 dV, ε0 = α (T − T_ref) [1, 1, 1, 0, 0, 0]ᵀ."""
    raise NotImplementedError("SPEC 67b: thermal_loads")


def thermal_strain_stress(model: Model, u: np.ndarray, T, T_ref: float, alpha) -> np.ndarray:
    """(m, 6) eleman gerilmesi σ = D (B u − ε0); `u` modelin DOF düzeninde."""
    raise NotImplementedError("SPEC 67b: thermal_strain_stress")


def add_loads(model: Model, loads: Iterable[Load]) -> None:
    """Load'ları modele ekler; aynı (düğüm, dof) toplanır, tek Load kalır."""
    raise NotImplementedError("SPEC 67b: add_loads")
