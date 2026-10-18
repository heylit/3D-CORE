"""
3D-CORE eskiz (kroki) veri modeli — SPEC 17.

Bir düzlem üzerindeki 2D eskizin ortak dili: noktalar, çizgiler, daireler, yaylar ve kısıtlar; çözücünün
çıkardığı bölgeler (SegLine / SegArc döngüleri). Saf Python + numpy; OCCT gerektirmez.

Düzlem: dünya noktası  P = origin + u·xdir + v·ydir,  ydir = normal × xdir.
Yay: merkez c, başlangıç s, bitiş e; s'den e'ye saat yönünün tersine (CCW). Yarıçap r = |s − c|.

Birimler: mm, açı girdisi derece.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

SEMA = 1
TOL = 1e-9  # mm; düzlem ortonormallik ve düzlemde olma toleransı


class SketchError(ValueError):
    """Eskizde tutarsızlık (bilinmeyen kimlik, yanlış referans, çelişen kısıt...).

    constraints: hatayla ilgili kısıtların sıraları (çelişki kümesi); yoksa boş.
    """

    def __init__(self, message: str, constraints: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.constraints = tuple(constraints)


def _vec(v, n: int, ad: str) -> np.ndarray:
    a = np.array(v, dtype=float).reshape(-1)
    if a.shape != (n,) or not np.all(np.isfinite(a)):
        raise SketchError(f"{ad}: sonlu ({n},) vektör bekleniyor ({v})")
    a.flags.writeable = False
    return a


def _sonlu(x: float, ad: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise SketchError(f"{ad}: sonlu sayı bekleniyor ({x!r})")
    return float(x)


@dataclass(frozen=True)
class Plane:
    """Eskiz düzlemi. normal ve xdir birim ve birbirine dik (TOL)."""

    origin: np.ndarray
    normal: np.ndarray
    xdir: np.ndarray

    def __post_init__(self) -> None:
        o, n, x = _vec(self.origin, 3, "origin"), _vec(self.normal, 3, "normal"), _vec(self.xdir, 3, "xdir")
        if abs(np.linalg.norm(n) - 1.0) > TOL or abs(np.linalg.norm(x) - 1.0) > TOL:
            raise SketchError(
                f"Düzlem: normal ve xdir birim olmalı (|n|={np.linalg.norm(n)}, |x|={np.linalg.norm(x)})"
            )
        if abs(float(n @ x)) > TOL:
            raise SketchError(f"Düzlem: normal · xdir = 0 olmalı ({float(n @ x)})")
        object.__setattr__(self, "origin", o)
        object.__setattr__(self, "normal", n)
        object.__setattr__(self, "xdir", x)

    @property
    def ydir(self) -> np.ndarray:
        return np.cross(self.normal, self.xdir)

    def to_world(self, uv) -> np.ndarray:
        """(u, v) → dünya noktası (3,)."""
        u, v = _vec(uv, 2, "uv")
        return self.origin + u * self.xdir + v * self.ydir

    def to_local(self, p) -> np.ndarray:
        """Dünya noktası → (u, v). Düzlemden uzaklık > TOL → SketchError."""
        d = _vec(p, 3, "p") - self.origin
        h = float(d @ self.normal)
        if abs(h) > TOL:
            raise SketchError(f"Nokta düzlemde değil (uzaklık {h} mm)")
        return np.array([d @ self.xdir, d @ self.ydir])

    @classmethod
    def XY(cls) -> Plane:
        return cls((0, 0, 0), (0, 0, 1), (1, 0, 0))

    @classmethod
    def XZ(cls) -> Plane:
        return cls((0, 0, 0), (0, -1, 0), (1, 0, 0))

    @classmethod
    def YZ(cls) -> Plane:
        return cls((0, 0, 0), (1, 0, 0), (0, 1, 0))

    def to_dict(self) -> dict:
        return {"origin": self.origin.tolist(), "normal": self.normal.tolist(), "xdir": self.xdir.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> Plane:
        return cls(d["origin"], d["normal"], d["xdir"])


# --- Öğeler -------------------------------------------------------------------------------------------


@dataclass
class Point:
    """Eskiz noktası. x, y: başlangıç (ya da çözülmüş) konum, mm. fixed=True → bilinmeyen değil."""

    x: float
    y: float
    fixed: bool = False


@dataclass
class Line:
    """Nokta kimlikleri p0 → p1."""

    p0: str
    p1: str
    construction: bool = False


@dataclass
class Circle:
    """Merkez nokta kimliği ve yarıçap r > 0 (bilinmeyen)."""

    center: str
    r: float
    construction: bool = False


@dataclass
class Arc:
    """Merkez, başlangıç, bitiş nokta kimlikleri; başlangıçtan bitişe CCW."""

    center: str
    start: str
    end: str
    construction: bool = False


Entity = Line | Circle | Arc


class ConstraintType(StrEnum):
    COINCIDENT = "coincident"
    POINT_ON_LINE = "point_on_line"
    POINT_ON_CIRCLE = "point_on_circle"
    MIDPOINT = "midpoint"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    ANGLE = "angle"
    EQUAL = "equal"
    LENGTH = "length"
    DISTANCE = "distance"
    HDISTANCE = "hdistance"
    VDISTANCE = "vdistance"
    RADIUS = "radius"
    DIAMETER = "diameter"
    TANGENT = "tangent"
    SYMMETRIC = "symmetric"


CT = ConstraintType

# Referans türleri: P nokta, L çizgi, C daire ya da yay.
# Değer kuralı: None → değer yok; "any" → sonlu sayı; "pos" → > 0; "angle" → (−180, 180].
SIGNATURES: dict[ConstraintType, dict[tuple[str, ...], str | None]] = {
    CT.COINCIDENT: {("P", "P"): None},
    CT.POINT_ON_LINE: {("P", "L"): None},
    CT.POINT_ON_CIRCLE: {("P", "C"): None},
    CT.MIDPOINT: {("P", "L"): None},
    CT.HORIZONTAL: {("L",): None, ("P", "P"): None},
    CT.VERTICAL: {("L",): None, ("P", "P"): None},
    CT.PARALLEL: {("L", "L"): None},
    CT.PERPENDICULAR: {("L", "L"): None},
    CT.ANGLE: {("L", "L"): "angle"},
    CT.EQUAL: {("L", "L"): None, ("C", "C"): None},
    CT.LENGTH: {("L",): "pos"},
    CT.DISTANCE: {("P", "P"): "pos", ("P", "L"): "any"},
    CT.HDISTANCE: {("P", "P"): "any"},
    CT.VDISTANCE: {("P", "P"): "any"},
    CT.RADIUS: {("C",): "pos"},
    CT.DIAMETER: {("C",): "pos"},
    CT.TANGENT: {("L", "C"): None, ("C", "C"): None},
    CT.SYMMETRIC: {("P", "P", "L"): None},
}


@dataclass
class Constraint:
    """Kısıt. refs: nokta / öğe kimlikleri (SIGNATURES sırasıyla). value: mm ya da derece.

    side: TANGENT dalı σ ∈ {−1, +1}; 0 → çözücü ilk konumdan seçer. internal: yalnızca daire/yay–daire/yay
    TANGENT'inde iç teğet (False → dış teğet).
    """

    type: ConstraintType
    refs: tuple[str, ...]
    value: float | None = None
    side: int = 0
    internal: bool = False

    def __post_init__(self) -> None:
        self.type = ConstraintType(self.type)
        self.refs = tuple(self.refs)


# --- Eskiz --------------------------------------------------------------------------------------------


@dataclass
class Sketch:
    """Düzlem + noktalar + öğeler + kısıtlar. Kimlikler noktalar ve öğeler arasında tekildir."""

    plane: Plane = field(default_factory=Plane.XY)
    points: dict[str, Point] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)
    constraints: list[Constraint] = field(default_factory=list)

    def kind(self, ident: str) -> str:
        """Kimliğin referans türü: "P", "L" ya da "C". Bilinmeyen → SketchError."""
        if ident in self.points:
            return "P"
        e = self.entities.get(ident)
        if isinstance(e, Line):
            return "L"
        if isinstance(e, (Circle, Arc)):
            return "C"
        raise SketchError(f"Bilinmeyen kimlik: {ident!r}")

    def validate(self) -> None:
        """Kimlikler, öğe tanımları ve kısıt imzaları tutarlı değilse SketchError."""
        if not isinstance(self.plane, Plane):
            raise SketchError("plane bir Plane olmalı")
        ortak = set(self.points) & set(self.entities)
        if ortak:
            raise SketchError(f"Kimlik hem nokta hem öğe: {sorted(ortak)}")
        for k, p in self.points.items():
            _sonlu(p.x, f"nokta {k}.x")
            _sonlu(p.y, f"nokta {k}.y")
        for k, e in self.entities.items():
            self._oge(k, e)
        for i, c in enumerate(self.constraints):
            self._kisit(i, c)

    def _nokta(self, ident: str, sahip: str) -> None:
        if ident not in self.points:
            raise SketchError(f"{sahip}: bilinmeyen nokta {ident!r}")

    def _oge(self, k: str, e: Entity) -> None:
        if isinstance(e, Line):
            ids = (e.p0, e.p1)
        elif isinstance(e, Circle):
            ids = (e.center,)
            if _sonlu(e.r, f"daire {k}.r") <= 0:
                raise SketchError(f"Daire {k}: r > 0 olmalı ({e.r})")
        elif isinstance(e, Arc):
            ids = (e.center, e.start, e.end)
        else:
            raise SketchError(f"Öğe {k}: bilinmeyen tür {type(e).__name__}")
        for p in ids:
            self._nokta(p, f"öğe {k}")
        if len(set(ids)) != len(ids):
            raise SketchError(f"Öğe {k}: nokta kimlikleri farklı olmalı ({ids})")

    def _kisit(self, i: int, c: Constraint) -> None:
        try:
            imza = tuple(self.kind(r) for r in c.refs)
        except SketchError as err:
            raise SketchError(f"Kısıt {i} ({c.type}): {err}", (i,)) from None
        kurallar = SIGNATURES[c.type]
        if imza not in kurallar:
            raise SketchError(f"Kısıt {i} ({c.type}): desteklenmeyen referans çifti {imza}", (i,))
        if len(set(c.refs)) != len(c.refs):
            raise SketchError(f"Kısıt {i} ({c.type}): aynı referans iki kez", (i,))
        kural = kurallar[imza]
        if kural is None:
            if c.value is not None:
                raise SketchError(f"Kısıt {i} ({c.type}): değer almaz ({c.value})", (i,))
        else:
            if c.value is None:
                raise SketchError(f"Kısıt {i} ({c.type}): değer gerekli", (i,))
            v = _sonlu(c.value, f"kısıt {i} değeri")
            if kural == "pos" and v <= 0:
                hint = " (COINCIDENT kullanın)" if c.type == CT.DISTANCE else ""
                raise SketchError(f"Kısıt {i} ({c.type}): değer > 0 olmalı ({v}){hint}", (i,))
            if kural == "angle" and not -180.0 < v <= 180.0:
                raise SketchError(f"Kısıt {i} ({c.type}): açı (−180, 180] aralığında olmalı ({v})", (i,))
        if c.side not in (-1, 0, 1):
            raise SketchError(f"Kısıt {i}: side −1, 0 ya da 1 olmalı ({c.side})", (i,))
        if c.internal and not (c.type == CT.TANGENT and imza == ("C", "C")):
            raise SketchError(f"Kısıt {i}: internal yalnızca daire–daire TANGENT'inde", (i,))

    # --- JSON köprüsü (SPEC 26) ---

    def to_dict(self) -> dict:
        def oge(e: Entity) -> dict:
            if isinstance(e, Line):
                d = {"tur": "line", "p0": e.p0, "p1": e.p1}
            elif isinstance(e, Circle):
                d = {"tur": "circle", "center": e.center, "r": e.r}
            else:
                d = {"tur": "arc", "center": e.center, "start": e.start, "end": e.end}
            d["construction"] = e.construction
            return d

        return {
            "sema": SEMA,
            "plane": self.plane.to_dict(),
            "points": {k: {"x": p.x, "y": p.y, "fixed": p.fixed} for k, p in self.points.items()},
            "entities": {k: oge(e) for k, e in self.entities.items()},
            "constraints": [
                {
                    "type": str(c.type),
                    "refs": list(c.refs),
                    "value": c.value,
                    "side": c.side,
                    "internal": c.internal,
                }
                for c in self.constraints
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Sketch:
        if d.get("sema") != SEMA:
            raise SketchError(f"Desteklenmeyen eskiz şeması: {d.get('sema')!r}")

        def oge(k: str, e: dict) -> Entity:
            tur, c = e["tur"], bool(e.get("construction", False))
            if tur == "line":
                return Line(e["p0"], e["p1"], c)
            if tur == "circle":
                return Circle(e["center"], e["r"], c)
            if tur == "arc":
                return Arc(e["center"], e["start"], e["end"], c)
            raise SketchError(f"Öğe {k}: bilinmeyen tür {tur!r}")

        s = cls(
            plane=Plane.from_dict(d["plane"]),
            points={k: Point(p["x"], p["y"], bool(p.get("fixed", False))) for k, p in d["points"].items()},
            entities={k: oge(k, e) for k, e in d["entities"].items()},
            constraints=[
                Constraint(
                    c["type"], tuple(c["refs"]), c.get("value"), c.get("side", 0), c.get("internal", False)
                )
                for c in d["constraints"]
            ],
        )
        s.validate()
        return s


# --- Çözücü çıktısı: bölgeler -------------------------------------------------------------------------


@dataclass(frozen=True)
class SegLine:
    """Bölge sınırında doğru parçası (uv, mm)."""

    p0: np.ndarray
    p1: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "p0", _vec(self.p0, 2, "p0"))
        object.__setattr__(self, "p1", _vec(self.p1, 2, "p1"))


@dataclass(frozen=True)
class SegArc:
    """Bölge sınırında yay (uv, mm). ccw: start'tan end'e dönüş yönü. start = end → tam daire."""

    center: np.ndarray
    r: float
    start: np.ndarray
    end: np.ndarray
    ccw: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "center", _vec(self.center, 2, "center"))
        object.__setattr__(self, "start", _vec(self.start, 2, "start"))
        object.__setattr__(self, "end", _vec(self.end, 2, "end"))
        if _sonlu(self.r, "r") <= 0:
            raise SketchError(f"SegArc: r > 0 olmalı ({self.r})")


Seg = SegLine | SegArc


@dataclass(frozen=True)
class SketchRegion:
    """Tek bağlantılı bölge: dış döngü CCW, delikler CW (malzeme her halkanın solunda)."""

    outer: tuple[Seg, ...]
    holes: tuple[tuple[Seg, ...], ...] = ()
