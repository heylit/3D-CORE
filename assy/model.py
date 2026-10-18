"""
3D-CORE montaj veri modeli.

Montaj katmanının (montaj ağacı, kısıt çözücü, girişim) ortak dili. Saf Python + numpy; OCCT gerektirmez.

Konum / yönelim: 4x4 homojen dönüşüm  T = [[R, t], [0, 1]],  R ortonormal ve det(R) = +1.
    nokta:  p' = R p + t        yön:  d' = R d
Kaynak: Craig, Introduction to Robotics, Bölüm 2.

Birimler: mm, açı girdisi derece.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np


class AssyError(ValueError):
    """Montaj modelinde tutarsızlık (bilinmeyen bileşen, rijit olmayan dönüşüm...)."""


def transform(R: np.ndarray | None = None, t=None) -> np.ndarray:
    """T = [[R, t], [0, 1]]. R yoksa birim, t yoksa sıfır."""
    T = np.eye(4)
    if R is not None:
        T[:3, :3] = np.asarray(R, dtype=float)
    if t is not None:
        T[:3, 3] = np.asarray(t, dtype=float)
    return T


def _rot(axis: int, deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    # 90°'nin katlarında cos/sin'i tam değere yuvarla (1e-17 kalıntısı olmasın)
    c, s = (round(c) if abs(c - round(c)) < 1e-15 else c), (round(s) if abs(s - round(s)) < 1e-15 else s)
    i, j = [(1, 2), (2, 0), (0, 1)][axis]
    R = np.eye(3)
    R[i, i], R[i, j], R[j, i], R[j, j] = c, -s, s, c
    return R


def rot_x(deg: float) -> np.ndarray:
    return _rot(0, deg)


def rot_y(deg: float) -> np.ndarray:
    return _rot(1, deg)


def rot_z(deg: float) -> np.ndarray:
    return _rot(2, deg)


def is_rigid(T: np.ndarray, tol: float = 1e-9) -> bool:
    """R^T R = I, det R = +1 ve son satır [0, 0, 0, 1] ise True."""
    T = np.asarray(T, dtype=float)
    if T.shape != (4, 4):
        return False
    R = T[:3, :3]
    return (
        np.allclose(R.T @ R, np.eye(3), atol=tol)
        and abs(np.linalg.det(R) - 1.0) <= tol
        and np.allclose(T[3], [0, 0, 0, 1], atol=tol)
    )


class RefKind(StrEnum):
    PLANE = "duzlem"
    AXIS = "eksen"
    POINT = "nokta"


class MateKind(StrEnum):
    COINCIDENT = "cakisik"
    CONCENTRIC = "es_eksen"
    DISTANCE = "mesafe"
    ANGLE = "aci"


@dataclass
class Ref:
    """Bileşenin yerel koordinatında geometrik referans. PLANE: direction = normal; AXIS: eksen yönü."""

    component: str
    kind: RefKind
    origin: tuple[float, float, float]
    direction: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        self.kind = RefKind(self.kind)
        self.origin = tuple(float(v) for v in self.origin)
        d = np.asarray(self.direction, dtype=float)
        n = float(np.linalg.norm(d))
        if n < 1e-12:
            raise AssyError(f"Referans ({self.component}): yön vektörü sıfır olamaz")
        self.direction = tuple(float(v) for v in d / n)


@dataclass
class Component:
    name: str
    part: str                     # parça referansı (dosya yolu veya kimlik)
    T: np.ndarray = field(default_factory=lambda: np.eye(4))
    fixed: bool = False

    def __post_init__(self) -> None:
        self.T = np.asarray(self.T, dtype=float)
        if not is_rigid(self.T):
            raise AssyError(f"Bileşen '{self.name}': T rijit bir dönüşüm değil")


@dataclass
class Mate:
    kind: MateKind
    a: Ref
    b: Ref
    value: float = 0.0            # DISTANCE: mm, ANGLE: derece

    def __post_init__(self) -> None:
        self.kind = MateKind(self.kind)
        if self.kind is MateKind.DISTANCE and self.value < 0:
            raise AssyError(f"Mesafe kısıtı negatif olamaz ({self.value})")
        if self.kind is MateKind.ANGLE and not 0 <= self.value <= 180:
            raise AssyError(f"Açı kısıtı 0–180 derece olmalı ({self.value})")


@dataclass
class Assembly:
    name: str
    components: list[Component] = field(default_factory=list)
    mates: list[Mate] = field(default_factory=list)

    def component(self, name: str) -> Component:
        for c in self.components:
            if c.name == name:
                return c
        raise AssyError(f"Bilinmeyen bileşen: {name}")

    def validate(self) -> None:
        names = [c.name for c in self.components]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            raise AssyError(f"Yinelenen bileşen adı: {sorted(dup)}")
        for i, m in enumerate(self.mates):
            for ref in (m.a, m.b):
                if ref.component not in names:
                    raise AssyError(f"Kısıt {i}: bilinmeyen bileşen '{ref.component}'")
            if m.a.component == m.b.component:
                raise AssyError(f"Kısıt {i}: iki ucu aynı bileşende ('{m.a.component}')")

    def world(self, ref: Ref) -> tuple[np.ndarray, np.ndarray]:
        """Referansın dünya koordinatında origin'i (p' = R p + t) ve birim yönü (d' = R d)."""
        T = self.component(ref.component).T
        R, t = T[:3, :3], T[:3, 3]
        return R @ np.array(ref.origin) + t, R @ np.array(ref.direction)

    def to_dict(self) -> dict:
        def ref(r: Ref) -> dict:
            return {"component": r.component, "kind": r.kind.value,
                    "origin": list(r.origin), "direction": list(r.direction)}

        return {
            "name": self.name,
            "components": [
                {"name": c.name, "part": c.part, "T": c.T.tolist(), "fixed": c.fixed}
                for c in self.components
            ],
            "mates": [
                {"kind": m.kind.value, "a": ref(m.a), "b": ref(m.b), "value": m.value}
                for m in self.mates
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Assembly:
        def ref(r: dict) -> Ref:
            return Ref(component=r["component"], kind=r["kind"],
                       origin=tuple(r["origin"]), direction=tuple(r["direction"]))

        return cls(
            name=d["name"],
            components=[
                Component(name=c["name"], part=c["part"], T=np.array(c["T"]), fixed=c.get("fixed", False))
                for c in d.get("components", [])
            ],
            mates=[
                Mate(kind=m["kind"], a=ref(m["a"]), b=ref(m["b"]), value=m.get("value", 0.0))
                for m in d.get("mates", [])
            ],
        )
