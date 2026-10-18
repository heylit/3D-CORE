"""SPEC 57 testleri için ortak uydurma tezgâh profilleri ve parça yardımcıları.

Profiller (uydurma; gerçek tezgâh verisi değil):
- `uc_eksen()`: 3 eksen, `kinematics = None` → R(c) = {−c}.
- `masa_masa(θ)`: DMU / DMF benzeri masa-masa; A devrilme ekseni ±θ, C sınırsız
  → R(c) = {d : ∠(d, −c) ≤ θ, d ≠ c}.
- `yatay_b()`: NHC benzeri yatay; B döner tabla tabla normaline (Y) paralel → R(c) = {d ⊥ c}.
"""

from __future__ import annotations

import numpy as np

from cam.model import Kinematics, MachineProfile, RotaryAxis

ANA = {
    "+X": (1.0, 0.0, 0.0),
    "-X": (-1.0, 0.0, 0.0),
    "+Y": (0.0, 1.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
    "+Z": (0.0, 0.0, 1.0),
    "-Z": (0.0, 0.0, -1.0),
}


def uc_eksen() -> MachineProfile:
    return MachineProfile(name="UC EKSEN", controller="sinumerik", rpm_max=12000, feed_max=10000)


def masa_masa(theta: float = 110.0) -> MachineProfile:
    kin = Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), min=-theta, max=theta),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),
        ),
        spindle=(0.0, 0.0, 1.0),
    )
    return MachineProfile(
        name="DMU BENZERI", controller="sinumerik", rpm_max=12000, feed_max=10000, kinematics=kin
    )


def yatay_b() -> MachineProfile:
    """Yatay işleme merkezi: iş mili yatay (Z), B döner tablası tabla normaline (Y) paralel."""
    kin = Kinematics(rotary=(RotaryAxis("B", "masa", (0.0, 1.0, 0.0)),), spindle=(0.0, 0.0, 1.0))
    return MachineProfile(
        name="NHC BENZERI", controller="sinumerik", rpm_max=12000, feed_max=10000, kinematics=kin
    )


# Dünya → görünüm dönmesi: yüz normali n görünümde +Z olur (rijit, det = +1).
GORUNUM = {
    "+Z": np.eye(3),
    "-Z": np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]]),
    "+X": np.array([[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]),
    "-X": np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]),
    "+Y": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]),
    "-Y": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]),
}


def yuzde(part, yuz: str, islem):
    """`islem`'i `yuz` üste bakan, sınır kutusu orijinden başlayan döndürülmüş parçada uygular.

    Sonuç dünya konumuna geri taşınır (geometry.features.pocket / hole yalnız üstten keser).
    """
    T = np.eye(4)
    T[:3, :3] = GORUNUM[yuz]
    q = part.moved(T)
    lo, _ = q.bbox
    S = np.eye(4)
    S[:3, 3] = -lo
    T = S @ T
    out = islem(part.moved(T))
    Ti = np.eye(4)
    Ti[:3, :3] = T[:3, :3].T
    Ti[:3, 3] = -T[:3, :3].T @ T[:3, 3]
    return out.moved(Ti)
