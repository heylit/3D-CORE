"""
SPEC 29 §6 — Otomatik işlem planı (torna): SPEC 27 torna özelliklerinden SPEC 20 işlemlerine (alın, kaba,
finiş, kanal, iç işlem), takım ve kesme verisi SPEC 14'ten, G-code SPEC 21'den.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from cam import lathe_ops
from cam.cutting import SpindleFeed, css
from cam.gcode import write_lathe
from cam.lathe_ops import TurnCut
from cam.model import CamError, CylinderStock, LatheTool, LatheToolKind, Setup, ToolLibrary, Toolpath, Wcs
from cam.plan import PlannedOp, PlanNote, Unplanned, _ozet, check_common
from cam.profile import Line, Profile
from cam.turn_features import TurnFeatures, turn_features

KINDS = ("alin", "dis_kaba", "ic_kaba", "ic_finis", "dis_finis", "kanal")


@dataclass(frozen=True)
class TurnOptions:
    rpm_max: float  # zorunlu (G50)
    finish_allowance: float = 0.2
    clearance: float = 1.0
    strict: bool = False


@dataclass(frozen=True)
class TurnPlan:
    material: str
    outer: TurnFeatures
    inner: TurnFeatures | None
    setup: Setup
    ops: tuple[PlannedOp, ...]
    unplanned: tuple[Unplanned, ...]
    notes: tuple[PlanNote, ...]

    def summary(self) -> list[dict]:
        return [_ozet(o) for o in self.ops]

    def gcode(self, spindle: str, tool_change: tuple[float, float], program_no: int = 1) -> str:
        """SPEC 21 `write_lathe`."""
        return write_lathe([o.op for o in self.ops], spindle, tool_change, program_no=program_no)


def _check_options(o: TurnOptions) -> None:
    if not isinstance(o, TurnOptions):
        raise CamError(f"Torna planı: options TurnOptions olmalı ({type(o).__name__})")
    for ad, alt, kapali in (
        ("rpm_max", 0.0, False),
        ("finish_allowance", 0.0, True),
        ("clearance", 0.0, False),
    ):
        v = getattr(o, ad)
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or (v < alt if kapali else v <= alt)
        ):
            raise CamError(f"Torna planı: {ad} sonlu ve {'≥' if kapali else '>'} 0 olmalı ({v!r})")


def _extend(p: Profile, x: float) -> Profile:
    """Kaba profil: sonundan ham yüzeye (x) dik doğruyla uzatılır (zaten oradaysa aynen)."""
    e = p.end
    if abs(e[1] - x) < 1e-9:
        return p
    return Profile([*p.segments, Line(e, (e[0], x))], False)


class _Plan:
    """Torna planı kurulurken biriken durum (dışarı verilmez)."""

    def __init__(self, stock: CylinderStock, lib: ToolLibrary, material: str, o: TurnOptions):
        self.stock = stock
        self.lib = lib
        self.material = material
        self.o = o
        self.ops: list[tuple[str, str, Toolpath, LatheTool, SpindleFeed, float | None]] = []
        self.unplanned: list[Unplanned] = []

    def candidates(self, kind: LatheToolKind, desc: bool, need_ap: bool = False, width: float | None = None):
        """§6 aday sırası: tür, kesme verisi (kabada ap), nose_r (kanalda width), eşitlikte id artan."""
        tur = [t for t in self.lib.tools if isinstance(t, LatheTool) and t.kind is kind]
        out = []
        for t in tur:
            cd = t.cutting.get(self.material)
            if cd is None or (need_ap and cd.ap is None):
                continue
            if width is not None and t.width > width + 1e-9:
                continue
            out.append(t)
        if width is not None:
            return sorted(out, key=lambda t: (-t.width, t.id))
        return sorted(out, key=lambda t: (-t.nose_r if desc else t.nose_r, t.id))

    def cut(self, T: LatheTool) -> tuple[TurnCut, SpindleFeed, float | None]:
        Vc, n = css(T, self.material, self.o.rpm_max)
        cd = T.cutting[self.material]
        c = TurnCut(feed=cd.fn, rpm=n, css=Vc, a_p=cd.ap, clearance=self.o.clearance)
        return c, SpindleFeed(n=n, F=n * cd.fn, Vc=Vc, f=cd.fn), cd.ap

    def attempt(self, kind: str, feature: str, aday: list[LatheTool], build) -> bool:
        """Adayları sırayla dener; build(T, cut) → Toolpath. Hiçbiri olmazsa takim_yok (son hata)."""
        hata = f"'{self.material}' için kesme verisi olan uygun torna takımı yok"
        for T in aday:
            c, sf, a_p = self.cut(T)
            try:
                tp = build(T, c)
            except CamError as e:
                hata = str(e)
                continue
            self.ops.append((kind, feature, tp, T, sf, a_p))
            return True
        self.unplanned.append(Unplanned(feature, "takim_yok", hata))
        return False


def plan_turn(
    outer: Profile,
    stock: CylinderStock,
    lib: ToolLibrary,
    material: str,
    options: TurnOptions,
    inner: Profile | None = None,
    wcs: Wcs | None = None,
    fixtures: Sequence[CylinderStock] = (),
) -> TurnPlan:
    """SPEC 29 §6: alın → dış kaba → iç kaba → iç finiş → dış finiş → kanallar."""
    check_common(material, lib)
    if not isinstance(stock, CylinderStock):
        raise CamError(f"Torna planı CylinderStock ister ({type(stock).__name__})")
    _check_options(options)
    o = options
    tf = turn_features(outer, stock, "dis")
    P = _Plan(stock, lib, material, o)
    K = LatheToolKind

    tfi = None
    if inner is not None:
        if stock.d > 0:
            tfi = turn_features(inner, stock, "ic")
        else:
            P.unplanned.append(Unplanned("ic", "on_delik_yok", "İç profil var ama ham malzeme dolu (d = 0)"))

    # alın: özgün stokla; sonraki SPEC 20 çağrıları alnı alınmış stokla
    sf_stok = stock
    if tf.z_face is not None and tf.face_depth is not None:
        z_face = tf.z_face
        if P.attempt(
            "alin", "alin", P.candidates(K.TURN, True), lambda T, c: lathe_ops.face(stock, T, c, z_face)
        ):
            sf_stok = CylinderStock(D=stock.D, zmin=stock.zmin, zmax=z_face, d=stock.d)

    def kaba_finis(t: TurnFeatures, side: str, kind: LatheToolKind, x_ham: float) -> list:
        """Önce finiş denenir (payı belirler), sonra kaba; dönen sıra (kaba, finiş)."""
        adres = "dis" if side == "dis" else "ic"
        once = len(P.ops)
        fin_ok = P.attempt(
            f"{adres}_finis",
            adres,
            P.candidates(kind, False),
            lambda T, c: lathe_ops.finish(t.rough, sf_stok, T, c, side=side),
        )
        fin = P.ops[once:]
        del P.ops[once:]
        delta = o.finish_allowance if fin_ok else 0.0
        kaba_p = _extend(t.rough, x_ham)
        P.attempt(
            f"{adres}_kaba",
            adres,
            P.candidates(kind, True, need_ap=True),
            lambda T, c: lathe_ops.rough(kaba_p, sf_stok, T, c, allowance=delta, side=side),
        )
        kaba = P.ops[once:]
        del P.ops[once:]
        return kaba, fin

    dis_kaba, dis_fin = kaba_finis(tf, "dis", K.TURN, stock.D / 2)
    P.ops += dis_kaba
    if tfi is not None:
        ic_kaba, ic_fin = kaba_finis(tfi, "ic", K.BORE, stock.d / 2)
        P.ops += ic_kaba + ic_fin
    P.ops += dis_fin

    # kanallar ve genel girintiler (önce dış, sonra iç; ön→arka)
    kanallar = [(g, "dis") for g in tf.grooves] + ([(g, "ic") for g in tfi.grooves] if tfi else [])
    for i, (g, side) in enumerate(kanallar):
        P.attempt(
            "kanal",
            f"grooves[{i}]",
            P.candidates(K.GROOVE, True, width=g.z_right - g.z_left),
            lambda T, c, g=g, side=side: lathe_ops.groove(
                sf_stok, T, c, g.z_left, g.z_right, g.x_top, g.x_bottom, side=side
            ),
        )
    girintiler = list(tf.recesses) + (list(tfi.recesses) if tfi else [])
    for i, r in enumerate(girintiler):
        P.unplanned.append(
            Unplanned(
                f"recesses[{i}]", "genel_girinti", f"z ∈ [{r.z_left:g}, {r.z_right:g}]: profilli kanal yok"
            )
        )

    ops = []
    for k, (kind, adres, tp, T, sf, a_p) in enumerate(P.ops):
        ad = f"{k + 1:02d}-{kind}-T{T.id}"
        tp.name = ad
        ops.append(PlannedOp(ad, kind, 0, adres, T.id, tp, sf, a_p, None))
    unplanned = tuple(sorted(P.unplanned, key=lambda u: (u.feature, u.code)))
    if o.strict and unplanned:
        raise CamError("Torna planı eksik: " + "; ".join(f"{u.feature}: {u.code}" for u in unplanned))
    setup = Setup("torna-1", wcs if wcs is not None else Wcs("G54"), stock, list(fixtures))
    return TurnPlan(material, tf, tfi, setup, tuple(ops), unplanned, ())
