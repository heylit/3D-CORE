"""
SPEC 10 — Bağlama (fikstür) kütüphanesi ve montaj-CAM köprüsü.

Parametrik mengene, üç çeneli torna aynası ve pabuç; sıkma denetimi; temkinli bağlama üst yüzey haritası;
SPEC 05 simülasyon sonucuna ek fikstür çarpışması; montaj ağacından CAM kurulumuna ve geri dönüş.
Saf Python + numpy (OCCT yok); `assy` paketinden yalnız `assy.model.Node` kullanılır.
Birimler: mm, derece. Hatalar `cam.model.CamError`. Hiçbir fonksiyon girdisini değiştirmez.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from assy.model import Node
from cam.gcode import DrillOp
from cam.model import CylinderStock, Fixture, Frame, Setup, Stock, Toolpath
from cam.sim import SimResult
from geometry.part import Part

_BIRIM = Frame((0.0, 0.0, 0.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))

# ---------------------------------------------------------------- ilkel cisimler


@dataclass(frozen=True)
class Primitive:
    """Bağlama elemanının yerel çerçevesinde bir kutu ya da Z eksenli silindir."""

    shape: Stock | CylinderStock
    frame: Frame = field(default_factory=lambda: _BIRIM)

    def to_dict(self) -> dict:
        """{"shape": shape.to_dict(), "frame": frame.to_dict()}"""
        raise NotImplementedError("SPEC 10: Primitive.to_dict")

    @property
    def volume(self) -> float:
        raise NotImplementedError("SPEC 10: Primitive.volume")


# ---------------------------------------------------------------- kütüphane


@dataclass(frozen=True)
class Vise:
    """Mengene; yerel orijin açıklığın ortası, yatak üstünde; sıkma yönü yerel Y."""

    jaw_width: float
    jaw_thickness: float
    jaw_height: float
    opening: float
    bed_height: float = 40.0
    bed_extra: float = 60.0
    parallel: float = 0.0
    parallel_width: float = 6.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 10: Vise doğrulama")

    def primitives(self) -> list[Primitive]:
        """Sabit çene, hareketli çene, yatak, (p > 0 ise) iki paralel."""
        raise NotImplementedError("SPEC 10: Vise.primitives")

    def params(self) -> dict[str, float]:
        raise NotImplementedError("SPEC 10: Vise.params")

    @classmethod
    def from_params(cls, d: Mapping[str, float]) -> Vise:
        raise NotImplementedError("SPEC 10: Vise.from_params")


@dataclass(frozen=True)
class Chuck3:
    """Üç çeneli torna aynası; yerel orijin eksende ayna alnında, +Z stoğa doğru."""

    grip_d: float
    jaw_length: float
    body_d: float = 160.0
    body_length: float = 80.0
    jaw_height: float = 25.0
    jaw_width: float = 20.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 10: Chuck3 doğrulama")

    def primitives(self) -> list[Primitive]:
        """Gövde, çeneler 90°, 210°, 330°."""
        raise NotImplementedError("SPEC 10: Chuck3.primitives")

    def rings(self, frame: Frame) -> list[CylinderStock]:
        """[çene halkası (D = 2 r_o, d = grip_d), gövde]; frame.R = I olmalı."""
        raise NotImplementedError("SPEC 10: Chuck3.rings")

    def params(self) -> dict[str, float]:
        raise NotImplementedError("SPEC 10: Chuck3.params")

    @classmethod
    def from_params(cls, d: Mapping[str, float]) -> Chuck3:
        raise NotImplementedError("SPEC 10: Chuck3.from_params")


@dataclass(frozen=True)
class Clamp:
    """Pabuç (kol + topuk + cıvata); yerel orijin burnun alt kenarında, kol −X yönünde."""

    support_height: float
    arm_length: float = 80.0
    arm_width: float = 20.0
    arm_thickness: float = 12.0
    bolt_d: float = 12.0
    bolt_above: float = 15.0
    heel_width: float = 15.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 10: Clamp doğrulama")

    def primitives(self) -> list[Primitive]:
        """Kol, topuk, cıvata."""
        raise NotImplementedError("SPEC 10: Clamp.primitives")

    def params(self) -> dict[str, float]:
        raise NotImplementedError("SPEC 10: Clamp.params")

    @classmethod
    def from_params(cls, d: Mapping[str, float]) -> Clamp:
        raise NotImplementedError("SPEC 10: Clamp.from_params")


def vise_for(stock: Stock, grip: float, axis: str = "x", **olculer) -> tuple[Vise, Frame]:
    raise NotImplementedError("SPEC 10: vise_for")


def chuck_for(stock: CylinderStock, grip: float, **olculer) -> tuple[Chuck3, Frame]:
    raise NotImplementedError("SPEC 10: chuck_for")


def clamp_for(stock: Stock, side: str, at: float, overlap: float, **olculer) -> tuple[Clamp, Frame]:
    raise NotImplementedError("SPEC 10: clamp_for")


def make_fixture(name: str, item: Vise | Chuck3 | Clamp, frame: Frame) -> Fixture:
    raise NotImplementedError("SPEC 10: make_fixture")


def from_fixture(fx: Fixture) -> Vise | Chuck3 | Clamp:
    raise NotImplementedError("SPEC 10: from_fixture")


def primitives_wcs(fx: Fixture) -> list[Primitive]:
    raise NotImplementedError("SPEC 10: primitives_wcs")


def envelope(fx: Fixture, parts: Mapping[str, Part] | None = None) -> list[Stock]:
    raise NotImplementedError("SPEC 10: envelope")


def check_clamping(
    stock: Stock | CylinderStock,
    fixtures: Sequence[Fixture],
    parts: Mapping[str, Part] | None = None,
    tol_l: float = 1e-9,
    tol_v: float = 1e-6,
) -> None:
    raise NotImplementedError("SPEC 10: check_clamping")


def fixture_top(fixtures: Sequence[Fixture], parts: Mapping[str, Part] | None = None) -> float:
    raise NotImplementedError("SPEC 10: fixture_top")


# ---------------------------------------------------------------- üst yüzey haritası ve çarpışma


@dataclass
class FixtureMap:
    """Bir bağlamanın WCS XY sınır kutusundaki temkinli üst yüzey haritası; top (ny, nx), değmeyen -inf."""

    fixture: str
    x0: float
    y0: float
    dx: float
    dy: float
    nx: int
    ny: int
    top: np.ndarray

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError("SPEC 10: FixtureMap.centers")


def primitive_topmap(prims: Sequence[Primitive], grid: FixtureMap) -> np.ndarray:
    raise NotImplementedError("SPEC 10: primitive_topmap")


def mesh_topmap(V: np.ndarray, F: np.ndarray, frame: Frame, grid: FixtureMap) -> np.ndarray:
    raise NotImplementedError("SPEC 10: mesh_topmap")


def fixture_map(
    fx: Fixture,
    cell: float,
    parts: Mapping[str, Part] | None = None,
    mesh_tol: float = 0.01,
    max_cells: int = 4_000_000,
) -> FixtureMap:
    raise NotImplementedError("SPEC 10: fixture_map")


@dataclass(frozen=True)
class FixtureCollision:
    fixture: str
    k: int
    op: int
    part: str  # "kesici" | "sap" | "tutucu"
    at: tuple[float, float, float]
    depth: float


def fixture_collisions(
    ops: list[Toolpath | DrillOp],
    result: SimResult,
    maps: Sequence[FixtureMap],
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
) -> list[FixtureCollision]:
    raise NotImplementedError("SPEC 10: fixture_collisions")


@dataclass
class SetupSim:
    sim: SimResult
    fixture_collisions: list[FixtureCollision]
    maps: list[FixtureMap]


def simulate_setup(
    ops: list[Toolpath | DrillOp],
    stock: Stock,
    fixtures: Sequence[Fixture],
    parts: Mapping[str, Part] | None = None,
    cell: float = 1.0,
    fixture_cell: float | None = None,
    **sim_kwargs,
) -> SetupSim:
    raise NotImplementedError("SPEC 10: simulate_setup")


# ---------------------------------------------------------------- montaj köprüsü


@dataclass
class AssemblySetup:
    setup: Setup
    workpiece: str  # yaprak yolu
    part: str  # parça kimliği
    T_part: np.ndarray  # parçanın yerelinden WCS'ye, 4x4
    fixtures: list[Fixture] = field(default_factory=list)


def from_assembly(
    root: Node,
    parts: Mapping[str, Part],
    workpiece: str,
    wcs: str | Frame,
    fixtures: Sequence[str],
    name: str = "baglama",
    code: str = "G54",
    origin=(0.0, 0.0, 0.0),
    margin: float | tuple[float, float, float] = 0.0,
    kinds: Mapping[str, Fixture] | None = None,
) -> AssemblySetup:
    raise NotImplementedError("SPEC 10: from_assembly")


def to_assembly(job: AssemblySetup, name: str = "baglama") -> Node:
    raise NotImplementedError("SPEC 10: to_assembly")
