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


class Distribution(StrEnum):
    """Tolerans dağılımı. T = yarı bant genişliği."""

    NORMAL = "normal"  # bant = ±sigma_level·σ
    UNIFORM = "duzgun"  # σ = T / √3
    TRIANGULAR = "ucgen"  # σ = T / √6


@dataclass(frozen=True)
class Tolerance:
    """Bir boyutun toleransı. lower / upper nominale göre sapmadır (mm veya derece), lower ≤ upper.

    Ör. Ø20 H7: Tolerance(20.0, 0.0, 0.021); 50 ± 0.1: Tolerance.symmetric(50.0, 0.1).
    __post_init__: distribution dizeden çevrilir; nominal, lower, upper, sigma_level sonlu; lower ≤ upper;
    sigma_level > 0; aksi AssyError.
    """

    nominal: float
    lower: float = 0.0
    upper: float = 0.0
    distribution: Distribution = Distribution.NORMAL
    sigma_level: float = 3.0  # yalnız NORMAL: bant = ±sigma_level·σ
    name: str = ""

    def __post_init__(self) -> None:
        raise NotImplementedError("A1a: Tolerance doğrulaması")

    @property
    def mean(self) -> float:
        """nominal + (lower + upper) / 2."""
        raise NotImplementedError("A1a: Tolerance.mean")

    @property
    def half_width(self) -> float:
        """T = (upper − lower) / 2."""
        raise NotImplementedError("A1a: Tolerance.half_width")

    @property
    def sigma(self) -> float:
        """NORMAL: T / sigma_level; UNIFORM: T / √3; TRIANGULAR: T / √6; T = 0 → 0."""
        raise NotImplementedError("A1a: Tolerance.sigma")

    def to_dict(self) -> dict:
        """distribution .value olarak."""
        raise NotImplementedError("A1a: Tolerance.to_dict")

    @classmethod
    def from_dict(cls, d: dict) -> Tolerance:
        raise NotImplementedError("A1a: Tolerance.from_dict")

    @classmethod
    def symmetric(
        cls,
        nominal: float,
        t: float,
        distribution: Distribution = Distribution.NORMAL,
        sigma_level: float = 3.0,
        name: str = "",
    ) -> Tolerance:
        """nominal ± t (lower = −t, upper = +t); t ≥ 0, aksi AssyError."""
        raise NotImplementedError("A1a: Tolerance.symmetric")


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
        if not (np.all(np.isfinite(self.origin)) and np.all(np.isfinite(d))):
            raise AssyError(f"Referans ({self.component}): origin ve yön sonlu olmalı")
        n = float(np.linalg.norm(d))
        if n < 1e-12:
            raise AssyError(f"Referans ({self.component}): yön vektörü sıfır olamaz")
        self.direction = tuple(float(v) for v in d / n)


@dataclass
class Component:
    name: str
    part: str  # parça referansı (dosya yolu veya kimlik)
    T: np.ndarray = field(default_factory=lambda: np.eye(4))
    fixed: bool = False

    def __post_init__(self) -> None:
        self.T = np.asarray(self.T, dtype=float)
        if not is_rigid(self.T):
            raise AssyError(f"Bileşen '{self.name}': T rijit bir dönüşüm değil")

    def __eq__(self, other: object) -> bool:
        # dataclass'ın ürettiği __eq__ numpy dizisinde ValueError verir; T'yi np.array_equal ile karşılaştır
        if not isinstance(other, Component):
            return NotImplemented
        return (self.name, self.part, self.fixed) == (other.name, other.part, other.fixed) and np.array_equal(
            self.T, other.T
        )


@dataclass
class Mate:
    """İki referans arasında kısıt.

    flip: yönlü referansın yönü ters alınır (b'nin; b NOKTA ise a'nın). Varsayılan (False) davranış:
        PLANE–PLANE normaller zıt (yüz yüze), flip → aynı yön;
        POINT–PLANE DISTANCE nokta normalin tarafında, flip → öbür tarafta;
        ANGLE θ yönler arasında, flip → 180° − θ.
    Yönün sonucu değiştirmediği kısıtlarda (eksen–eksen, nokta–nokta, nokta–eksen, nokta–düzlem
    çakışık) flip = True hatadır: etkisiz bayrak sessizce yutulmaz.
    """

    kind: MateKind
    a: Ref
    b: Ref
    value: float = 0.0  # DISTANCE: mm, ANGLE: derece
    flip: bool = False

    def __post_init__(self) -> None:
        self.kind = MateKind(self.kind)
        if not math.isfinite(self.value):
            raise AssyError(f"Kısıt değeri sonlu olmalı ({self.value})")
        if not isinstance(self.flip, bool):
            raise AssyError(f"flip bool olmalı ({self.flip!r})")
        if self.flip and not self._flip_etkili():
            raise AssyError(
                f"flip bu kısıtta etkisiz: {self.kind.name} {self.a.kind.name}–{self.b.kind.name}"
            )
        if self.kind is MateKind.DISTANCE and self.value < 0:
            raise AssyError(f"Mesafe kısıtı negatif olamaz ({self.value})")
        if self.kind is MateKind.ANGLE and not 0 <= self.value <= 180:
            raise AssyError(f"Açı kısıtı 0–180 derece olmalı ({self.value})")

    def _flip_etkili(self) -> bool:
        """Yön tersine çevrilince artığın değiştiği kısıtlar (bkz. sınıf açıklaması)."""
        cift = {self.a.kind, self.b.kind}
        if self.kind is MateKind.ANGLE:
            return True
        if cift == {RefKind.PLANE}:
            return self.kind in (MateKind.COINCIDENT, MateKind.DISTANCE)
        return cift == {RefKind.POINT, RefKind.PLANE} and self.kind is MateKind.DISTANCE


class JointKind(StrEnum):
    FIXED = "sabit"  # 0 SD
    REVOLUTE = "doner"  # 1 SD: eksen etrafında dönme
    PRISMATIC = "kayar"  # 1 SD: eksen boyunca öteleme
    CYLINDRICAL = "silindirik"  # 2 SD: dönme + öteleme
    SPHERICAL = "kuresel"  # 3 SD: nokta etrafında dönme


@dataclass
class Joint:
    """İki bileşen arası yönlü eklem: a ebeveyn, b çocuk; z_b = +z_a.

    a, b: SPHERICAL → NOKTA referansı; diğerleri → EKSEN referansı.
    zero_a / zero_b: yerel sıfır yönü; eksene dik bileşeni birimlenir. None → dünya taban vektörlerinden
    |z·e| en küçük olan (eşitlikte x, y, z sırası), x = birim(e − (e·z) z).
    limits: REVOLUTE (alt, üst) derece ⊂ [−180, 180]; PRISMATIC (alt, üst) mm;
    CYLINDRICAL ((θa, θü) | None, (sa, sü) | None); SPHERICAL / FIXED → None zorunlu.
    __post_init__ AssyError: boş name; referans türü uyumsuz; zero sonlu değil veya eksene paralel
    (|birim(zero) × z| < 1e-9); SPHERICAL / FIXED'de limits dolu; alt > üst, sonlu olmayan, REVOLUTE
    [−180, 180] dışı; CYLINDRICAL limits iki elemanlı değil.
    """

    name: str
    kind: JointKind
    a: Ref
    b: Ref
    zero_a: tuple[float, float, float] | None = None
    zero_b: tuple[float, float, float] | None = None
    limits: tuple | None = None

    def __post_init__(self) -> None:
        raise NotImplementedError("A1b: Joint doğrulaması")

    @property
    def dof(self) -> int:
        """Serbestlik derecesi: FIXED 0, REVOLUTE 1, PRISMATIC 1, CYLINDRICAL 2, SPHERICAL 3."""
        raise NotImplementedError("A1b: Joint.dof")

    def axis_frame(self, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """side 'a' / 'b' için bileşenin YEREL koordinatında (origin, z, x); z = ref yönü, x = sıfır yönü."""
        raise NotImplementedError("A1b: Joint.axis_frame")


@dataclass
class Assembly:
    name: str
    components: list[Component] = field(default_factory=list)
    mates: list[Mate] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)  # A1b: validate ve to_dict / from_dict ("joints") kodda

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
            return {
                "component": r.component,
                "kind": r.kind.value,
                "origin": list(r.origin),
                "direction": list(r.direction),
            }

        return {
            "name": self.name,
            "components": [
                {"name": c.name, "part": c.part, "T": c.T.tolist(), "fixed": c.fixed} for c in self.components
            ],
            "mates": [
                {"kind": m.kind.value, "a": ref(m.a), "b": ref(m.b), "value": m.value, "flip": m.flip}
                for m in self.mates
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Assembly:
        def ref(r: dict) -> Ref:
            return Ref(
                component=r["component"],
                kind=r["kind"],
                origin=tuple(r["origin"]),
                direction=tuple(r["direction"]),
            )

        return cls(
            name=d["name"],
            components=[
                Component(name=c["name"], part=c["part"], T=np.array(c["T"]), fixed=c.get("fixed", False))
                for c in d.get("components", [])
            ],
            mates=[
                Mate(
                    kind=m["kind"],
                    a=ref(m["a"]),
                    b=ref(m["b"]),
                    value=m.get("value", 0.0),
                    flip=m.get("flip", False),
                )
                for m in d.get("mates", [])
            ],
        )


@dataclass
class Node:
    """Montaj ağacında bir oluşum. Yaprak: part dolu, children boş. Alt montaj: part None, children dolu.

    T ebeveyne göre rijit dönüşümdür. Ağaç bütünlüğü (kardeş adları, boş alt montaj, tanım tutarlılığı)
    assy.tree.validate'tedir, çünkü ağaç adım adım kurulabilmeli.
    """

    name: str  # kardeşler arasında tekil, boş değil, '/' içermez
    T: np.ndarray = field(default_factory=lambda: np.eye(4))  # ebeveyne göre, rijit
    part: str | None = None  # yaprak: parça kimliği
    children: list[Node] = field(default_factory=list)
    ref: str | None = None  # alt montaj tanım adı; None → name

    def __post_init__(self) -> None:
        if not self.name or "/" in self.name:
            raise AssyError(f"Düğüm adı boş olamaz ve '/' içeremez ({self.name!r})")
        self.T = np.asarray(self.T, dtype=float)
        if not is_rigid(self.T):
            raise AssyError(f"Düğüm '{self.name}': T rijit bir dönüşüm değil")
        if self.part is not None and (self.children or self.ref is not None):
            raise AssyError(f"Düğüm '{self.name}': yaprakta (part dolu) çocuk veya ref olamaz")

    def __eq__(self, other: object) -> bool:
        # dataclass'ın ürettiği __eq__ numpy dizisinde ValueError verir; T'yi np.array_equal ile, çocukları
        # sırasıyla özyinelemeli karşılaştır
        if not isinstance(other, Node):
            return NotImplemented
        return (
            (self.name, self.part, self.ref) == (other.name, other.part, other.ref)
            and np.array_equal(self.T, other.T)
            and self.children == other.children
        )

    @property
    def definition(self) -> str:
        """Yaprak: parça kimliği; alt montaj: ref, yoksa name."""
        if self.part is not None:
            return self.part
        return self.ref if self.ref is not None else self.name

    def to_dict(self) -> dict:
        """Özyinelemeli sözlük; T 4x4 liste olarak."""
        return {
            "name": self.name,
            "T": self.T.tolist(),
            "part": self.part,
            "children": [c.to_dict() for c in self.children],
            "ref": self.ref,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Node:
        return cls(
            name=d["name"],
            T=np.array(d.get("T", np.eye(4))),
            part=d.get("part"),
            children=[cls.from_dict(c) for c in d.get("children", [])],
            ref=d.get("ref"),
        )
