"""
SPEC 38 — İş föyü veri tipleri ve kurulumu: WCS tarifi, takım tablosu ve boy ofsetleri, SPEC 05 süre modeli,
işe özel doğrulama maddeleri (docs/tezgah-dogrulama.md bölümleri).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from cam.gcode import GRBL, Dialect, DrillOp
from cam.library import check_tools
from cam.model import (
    CamError,
    FeedMode,
    LatheTool,
    Move,
    MoveType,
    Plane,
    Setup,
    Stock,
    ToolLibrary,
    Toolpath,
)
from cam.setups import check_setup
from cam.sim import Machine, move_time
from cam.tool_length import length_offsets
from geometry.drawing.dimensions import format_value
from geometry.drawing.types import Dimension, Sheet

if TYPE_CHECKING:
    from geometry.part import Part


@dataclass(frozen=True)
class ToolRow:
    T: int
    name: str
    kind: str  # ToolKind değeri
    D: float
    corner_r: float
    flute_length: float
    stickout: float | None
    holder: str | None
    L: float | None  # gauge_length
    offset: float | None  # Fanuc: L; GRBL: ΔL; bilinmiyorsa None
    need: float  # gerekli kesici boy (§3)
    rpm_max: int
    ops: tuple[str, ...]
    time: float  # s


@dataclass(frozen=True)
class OpRow:
    no: int  # bağlama içinde 1'den
    name: str
    T: int
    rpm: int
    F: float  # kesme hareketlerinin en büyük ilerlemesi (DrillOp: feed); kesme yoksa 0
    z_min: float  # kesme hareketlerinin en alçak Z'si (DrillOp: z)
    time: float  # s, §4
    t_end: float  # s, bağlama içinde birikimli


@dataclass(frozen=True)
class SetupSheet:
    index: int  # 1'den
    setup: Setup
    wcs: tuple[str, str, str]  # wcs_text(setup.stock)
    ref_id: int | None  # GRBL referans takımı; Fanuc'ta None
    tools: tuple[ToolRow, ...]
    ops: tuple[OpRow, ...]
    time: float
    tool_changes: int
    drawing: Sheet  # §5


@dataclass(frozen=True)
class InspectionItem:
    no: int  # 1'den
    text: str
    nominal: float
    tol: float  # ±t
    lower: float
    upper: float


@dataclass(frozen=True)
class CheckItem:
    section: int  # docs/tezgah-dogrulama.md bölümü (1..5)
    text: str


@dataclass(frozen=True)
class JobSheet:
    title: str
    material: str
    dialect: Dialect
    program_no: int
    setups: tuple[SetupSheet, ...]
    inspection: tuple[InspectionItem, ...]
    checks: tuple[CheckItem, ...]
    warnings: tuple[str, ...]
    total_time: float
    date: str | None = None


EPS = 1e-9  # mm, WCS tarifinde eşitlik


def _eksen(lo: float, hi: float, adlar: tuple[str, str, str], diger: str) -> str:
    if abs(lo) <= EPS:
        return adlar[0]
    if abs(hi) <= EPS:
        return adlar[1]
    if abs((lo + hi) / 2) <= EPS:
        return adlar[2]
    return diger


def wcs_text(stock: Stock) -> tuple[str, str, str]:
    """İş sıfırının ham malzemedeki yeri, eksen başına metin (§2)."""
    x = _eksen(
        stock.xmin,
        stock.xmax,
        ("sol kenar", "sağ kenar", "X ortası"),
        f"sol kenardan {format_value(-stock.xmin)} mm",
    )
    y = _eksen(
        stock.ymin,
        stock.ymax,
        ("ön kenar", "arka kenar", "Y ortası"),
        f"ön kenardan {format_value(-stock.ymin)} mm",
    )
    if stock.zmax > 0:
        z_diger = f"üst yüzden {format_value(stock.zmax)} mm aşağıda"
    else:
        z_diger = f"üst yüzden {format_value(-stock.zmax)} mm yukarıda"
    z = _eksen(stock.zmin, stock.zmax, ("alt yüz", "üst yüz", "Z ortası"), z_diger)
    return x, y, z


def sayi(v: float, decimals: int) -> str:
    """Sabit basamaklı, ondalık virgüllü sayı; "-0,000" yazılmaz."""
    metin = f"{v:.{decimals}f}"
    if metin.startswith("-") and not metin.strip("-0."):
        metin = metin[1:]
    return metin.replace(".", ",")


# ---------------------------------------------------------------- girdi denetimi


def _pozitif_sonlu(ad: str, v) -> None:
    if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
        raise CamError(f"İş föyü: {ad} pozitif ve sonlu olmalı ({ad}={v})")


def _metin(ad: str, v) -> None:
    if not isinstance(v, str) or not v.strip():
        raise CamError(f"İş föyü: {ad} boş olmayan metin olmalı ({v!r})")


def _op_denetle(op) -> None:
    if isinstance(op, DrillOp):
        return
    if not isinstance(op, Toolpath):
        raise CamError(f"İş föyü: Toolpath veya DrillOp bekleniyor ({type(op).__name__})")
    if isinstance(op.tool, LatheTool):
        raise CamError(f"İş föyü: '{op.name}' torna takımı kullanıyor (torna föyü kapsam dışı)")
    if op.plane is not Plane.XY:
        raise CamError(f"İş föyü: '{op.name}' yalnız G17 (XY) yolları ({op.plane.value})")
    if op.feed_mode is not FeedMode.PER_MIN:
        raise CamError(f"İş föyü: '{op.name}' yalnız G94 (mm/dk) ilerleme")


def _denetle(title, setups, ops, material, n_max, scale, program_no, names, tol_class) -> None:
    from atolye.olcum import TABLO

    _metin("title", title)
    _metin("material", material)
    if not setups:
        raise CamError("İş föyü: en az bir bağlama gerekli")
    if len(ops) != len(setups):
        raise CamError(f"İş föyü: op listesi sayısı ({len(ops)}) bağlama sayısından ({len(setups)}) farklı")
    for s, liste in zip(setups, ops, strict=True):
        if not isinstance(s, Setup):
            raise CamError(f"İş föyü: Setup bekleniyor ({type(s).__name__})")
        if not isinstance(s.stock, Stock):
            raise CamError(f"İş föyü: '{s.name}' kutu ham malzeme ister (torna föyü kapsam dışı)")
        if not liste:
            raise CamError(f"İş föyü: '{s.name}' bağlamasında op yok")
        for op in liste:
            _op_denetle(op)
    if names is not None and (
        len(names) != len(ops) or any(len(n) != len(o) for n, o in zip(names, ops, strict=False))
    ):
        raise CamError("İş föyü: names şekli op listeleriyle uyuşmuyor")
    if n_max is not None:
        _pozitif_sonlu("n_max", n_max)
    _pozitif_sonlu("scale", scale)
    if not isinstance(program_no, int) or isinstance(program_no, bool) or program_no < 1:
        raise CamError(f"İş föyü: program_no ≥ 1 tam sayı olmalı ({program_no})")
    if tol_class not in TABLO:
        raise CamError(f"İş föyü: bilinmeyen tolerans sınıfı {tol_class!r} (f, m, c, v)")


# ---------------------------------------------------------------- süre (SPEC 05 op_times kuralı)


def _yollar(ops, dialect: Dialect) -> list[Toolpath]:
    return [op.to_toolpath(dialect) if isinstance(op, DrillOp) else op for op in ops]


def op_times(yollar: list[Toolpath], machine: Machine) -> list[float]:
    """SPEC 05 `simulate` ile aynı kural: bağlantı G0 ve takım değişimi sonraki op'a sayılır."""
    sureler = [0.0] * len(yollar)
    pos: np.ndarray | None = None
    onceki: int | None = None
    for i, tp in enumerate(yollar):
        if onceki is not None and tp.tool.id != onceki:
            sureler[i] += machine.tool_change
        onceki = tp.tool.id
        bas = np.array(tp.start, dtype=float)
        if pos is not None and not np.array_equal(pos, bas):
            sureler[i] += move_time(pos, bas, Move(MoveType.RAPID, tp.start), Plane.XY, machine)
        pos = bas
        for m in tp.moves:
            sureler[i] += move_time(pos, m.end, m, Plane.XY, machine)
            pos = np.array(m.end, dtype=float)
    return sureler


def _degisim(ids: list[int]) -> int:
    """İlk takım + ardışık farklı takım geçişleri."""
    return (1 if ids else 0) + sum(1 for a, b in zip(ids, ids[1:], strict=False) if a != b)


# ---------------------------------------------------------------- bağlama


def _ilerleme(op) -> float:
    if isinstance(op, DrillOp):
        return float(op.feed)
    F = [m.feed for m in op.moves if m.type is not MoveType.RAPID and m.feed is not None]
    return float(max(F)) if F else 0.0


def _baglama(
    index: int,
    setup: Setup,
    ops: list,
    adlar: list[str],
    lib: ToolLibrary,
    dialect: Dialect,
    machine: Machine,
    ref_id: int | None,
    part,
    scale: float,
    uyarilar: list[str],
) -> SetupSheet:
    from atolye.baglama import setup_drawing
    from atolye.olcum import kesme_z_min

    check_tools(lib, ops)
    check_setup(setup, ops)
    z_ust = setup.stock.zmax
    sureler = op_times(_yollar(ops, dialect), machine)
    satirlar: list[OpRow] = []
    t = 0.0
    for no, (op, ad, sure) in enumerate(zip(ops, adlar, sureler, strict=True), start=1):
        t += sure
        z = kesme_z_min(op)
        satirlar.append(
            OpRow(no, ad, op.tool.id, int(round(op.rpm)), _ilerleme(op), z_ust if z is None else z, sure, t)
        )

    ids: list[int] = []
    for op in ops:
        if op.tool.id not in ids:
            ids.append(op.tool.id)
    if ref_id is not None and ref_id not in ids:
        raise CamError(f"İş föyü: referans takım T{ref_id} '{setup.name}' bağlamasında yok ({ids})")
    L = {n: lib.get(n).gauge_length for n in ids}
    eksik = [n for n in sorted(ids) if L[n] is None]
    ofset: dict[int, float | None] = dict.fromkeys(ids)
    ref = None
    if dialect.tool_length_comp:
        if not eksik:
            ofset = {n: float(L[n]) for n in ids}
    else:
        ref = ids[0] if ref_id is None else ref_id
        if not eksik:
            ofset = length_offsets(lib, ids, ref)
    for n in eksik:
        u = f"T{n} ölçü boyu bilinmiyor: tezgâhta ölçülecek"
        if u not in uyarilar:
            uyarilar.append(u)

    takimlar = []
    for n in ids:
        tool = lib.get(n)
        kendi = [r for r in satirlar if r.T == n]
        need = max(0.0, z_ust - min(r.z_min for r in kendi))
        takimlar.append(
            ToolRow(
                T=n,
                name=tool.name,
                kind=tool.kind.value,
                D=tool.D,
                corner_r=tool.corner_r,
                flute_length=tool.flute_length,
                stickout=tool.stickout,
                holder=None if tool.holder is None else tool.holder.name,
                L=None if L[n] is None else float(L[n]),
                offset=ofset[n],
                need=need,
                rpm_max=max(r.rpm for r in kendi),
                ops=tuple(r.name for r in kendi),
                time=sum(r.time for r in kendi),
            )
        )
    return SetupSheet(
        index=index,
        setup=setup,
        wcs=wcs_text(setup.stock),
        ref_id=ref,
        tools=tuple(takimlar),
        ops=tuple(satirlar),
        time=t,
        tool_changes=_degisim([op.tool.id for op in ops]),
        drawing=setup_drawing(setup, part=part, scale=scale),
    )


# ---------------------------------------------------------------- doğrulama maddeleri (§7)


def _maddeler(
    setups: list[SetupSheet], dialect: Dialect, n_max: float | None, rpm_max: int, k: int
) -> list[CheckItem]:
    d = dialect.decimals
    out: list[CheckItem] = []
    if n_max is not None:
        out.append(CheckItem(1, f"En yüksek devir S{rpm_max} ≤ tezgâh sınırı {format_value(n_max)}"))
    for s in setups:
        w = s.setup.wcs
        ox, oy, oz = (sayi(v, d) for v in w.origin)
        out.append(CheckItem(2, f"{w.code} kaydına X{ox} Y{oy} Z{oz} girildi"))
        out.append(CheckItem(2, f"Sıfır: X0 {s.wcs[0]}, Y0 {s.wcs[1]}, Z0 {s.wcs[2]}"))
        for t in s.tools:
            if t.offset is None:
                metin = f"T{t.T}: ölçü boyu tezgâhta ölçülecek"
            elif dialect.tool_length_comp:
                metin = f"T{t.T}: H{t.T} = {sayi(t.offset, d)}"
            else:
                metin = f"T{t.T}: G43.1 Z{sayi(t.offset, d)} (referans T{s.ref_id})"
            out.append(CheckItem(3, metin))
        stok = s.setup.stock
        z_tepe = max([stok.zmax, *(f.zmax for f in s.setup.fixtures)])
        h = max(50, math.ceil(z_tepe - stok.zmin) + 10)
        out.append(CheckItem(4, f"Kuru çalıştırma: {w.code} Z'si +{h} mm kaydırıldı"))
    if k:
        out.append(CheckItem(5, f"İlk parça ölçüm listesindeki {k} kalem ölçüldü ve kaydedildi"))
    return out


def build_job_sheet(
    title: str,
    setups: Sequence[Setup],
    ops: Sequence[Sequence[Toolpath | DrillOp]],
    lib: ToolLibrary,
    material: str,
    dialect: Dialect = GRBL,
    machine: Machine | None = None,
    n_max: float | None = None,
    ref_id: int | None = None,
    program_no: int = 1,
    names: Sequence[Sequence[str]] | None = None,
    dims: Sequence[Dimension] = (),
    tol_class: str = "m",
    warnings: Sequence[str] = (),
    part: Part | None = None,
    scale: float = 1.0,
    date: str | None = None,
) -> JobSheet:
    """Bağlamalar ve op'lardan iş föyü (§1–7). Güvensiz programda CamError."""
    from atolye.olcum import inspection_items

    _denetle(title, setups, ops, material, n_max, scale, program_no, names, tol_class)
    if machine is None:
        machine = Machine()
    if not isinstance(machine, Machine):
        raise CamError(f"İş föyü: machine bir Machine olmalı ({type(machine).__name__})")
    rpm = max(op.rpm for liste in ops for op in liste)
    if n_max is not None and rpm > n_max:
        raise CamError(f"İş föyü: en yüksek devir S{rpm:g} tezgâh sınırını ({n_max:g}) aşıyor")
    uyarilar = [str(w) for w in warnings]
    sayfalar = []
    for i, (s, liste) in enumerate(zip(setups, ops, strict=True)):
        adlar = [op.name for op in liste] if names is None else [str(a) for a in names[i]]
        sayfalar.append(
            _baglama(i + 1, s, list(liste), adlar, lib, dialect, machine, ref_id, part, scale, uyarilar)
        )
    olcum = inspection_items(dims, setups, ops, tol_class)
    maddeler = _maddeler(sayfalar, dialect, n_max, int(round(rpm)), len(olcum))
    return JobSheet(
        title=title,
        material=material,
        dialect=dialect,
        program_no=program_no,
        setups=tuple(sayfalar),
        inspection=tuple(olcum),
        checks=tuple(maddeler),
        warnings=tuple(uyarilar),
        total_time=sum(s.time for s in sayfalar),
        date=date,
    )
