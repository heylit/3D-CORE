"""
SPEC 44 — Tezgâh gövde modeli: halkalar, ilkel gövdeler (kutu, kapsül), halka dönüşümleri.

Halkalar: "taban" (sabit), doğrusal eksenler "X", "Y", "Z", döner eksenler (kinematikteki adlarıyla,
ör. "A", "C"), "is_mili", "is_parcasi". Zincirler (çarpımlar-üstel, her eksen sıfır konumunda tanımlı):
- masa: taban → (masadaki doğrusallar, X, Y, Z sırasıyla) → t1 → t2 → is_parcasi
- kafa: taban → (kafadaki doğrusallar, X, Y, Z sırasıyla) → h1 → h2 → is_mili
Halka dönüşümü x ↦ R·x + t (gövde sıfır konumundaki makine koordinatından şimdiki konumuna):
kafa halkası Trans(Σ kafa doğrusalları) ∘ Rot(h1) ∘ …, masa halkası Trans(−Σ masa doğrusalları) ∘ Rot(t1) ∘ …
(masa doğrusalı +X hareketini masayı −X yönünde götürerek verir; uç–iş parçası ilişkisi SPEC 41 ile aynı).

Otomatik gövdeler (kullanıcı gövdesi bu adları kullanamaz):
- "is_parcasi" halkasında: "ham_malzeme" (Setup.stock), "fikstur_0", "fikstur_1", … (Setup.fixtures);
  WCS'den makineye `Wcs.origin` ile, kutu olarak (silindir ham malzeme sınır kutusuyla).
- "is_mili" halkasında (uç sıfır konumunda tip₀ = g − L·s, s iş mili yönü, uçtan iş miline):
  "takim" kapsül r = D/2, p = tip₀ + r·s, q = tip₀ + max(r, L_f − r)·s;
  "sap" kapsül r = shank/2, tip₀ + L_f·s → tip₀ + H_üst·s;
  "tutucu_0", "tutucu_1", … her SPEC 05 `body_steps` tutucu basamağı j için kapsül r = ρ_j,
  tip₀ + H_j·s → tip₀ + H_{j+1}·s (son basamakta H_üst). H_üst = tutucu varsa stickout + tutucu ölçü boyu
  (= L, ölçü hattı), yoksa L; sapın üstü tutucu varsa stickout.

JSON (`to_dict`):
    {"profile": MachineProfile.to_dict(), "linear_carrier": {"X": "masa"|"kafa", "Y": …, "Z": …},
     "bodies": [{"name", "link", "shape": {"type": "kutu", "center", "half", "R"}
                                         | {"type": "kapsul", "p", "q", "r"}}],
     "ignore": [[a, b], …]}
Birimler: mm, derece.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cam.model import MachineProfile, Setup, Tool

LINKS_FIXED = ("taban", "X", "Y", "Z", "is_mili", "is_parcasi")


@dataclass
class Box:
    """Yönlendirilmiş kutu: merkez, yarı boylar (> 0), R ortonormal (sütunlar kutunun yerel eksenleri)."""

    center: tuple[float, float, float]
    half: tuple[float, float, float]
    R: tuple[tuple[float, float, float], ...] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 44: Box doğrulaması")


@dataclass
class Capsule:
    """Kapsül: p–q doğru parçası etrafında r (> 0) yarıçaplı küre süpürmesi; p = q küre."""

    p: tuple[float, float, float]
    q: tuple[float, float, float]
    r: float

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 44: Capsule doğrulaması")


@dataclass
class Body:
    """Bir halkaya bağlı gövde; şekil sıfır konumunda makine koordinatında."""

    name: str
    link: str
    shape: Box | Capsule


@dataclass
class MachineModel:
    """Tezgâh: profil (doğrusal sınırlar, kinematik), doğrusal eksen taşıyıcıları, gövdeler, hariç çiftler."""

    profile: MachineProfile
    linear_carrier: dict[str, str]
    bodies: list[Body]
    ignore: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 44: MachineModel doğrulaması")

    def to_dict(self) -> dict:
        raise NotImplementedError("SPEC 44: MachineModel.to_dict")

    @classmethod
    def from_dict(cls, d: dict) -> MachineModel:
        raise NotImplementedError("SPEC 44: MachineModel.from_dict")


def poses(model: MachineModel, q, setup: Setup, tool: Tool) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Eklem değerleri q = (X, Y, Z, θ…) → her halkanın dönüşümü {ad: (R (3, 3), t (3,))}."""
    raise NotImplementedError("SPEC 44: poses")
