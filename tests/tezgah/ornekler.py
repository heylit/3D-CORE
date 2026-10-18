"""SPEC 24 testleri için elle kurulmuş, uydurma freze işleri (gizlilik kuralı: gerçek parça yok).

Sayılar elle seçilmiştir; hiçbiri `tezgah` kodundan türetilmez.
"""

from __future__ import annotations

import numpy as np

from cam.gcode import GRBL, Dialect, DrillOp
from cam.model import Move, MoveType, Setup, Stock, Tool, Toolpath, Wcs
from tezgah.kopru import Islem, IsTanimi

M = MoveType

# Stok: 60 × 40 × 20 mm, üst yüz z = 20.
STOK = (0.0, 0.0, 0.0, 60.0, 40.0, 20.0)


def kurulum() -> Setup:
    return Setup(name="ust", wcs=Wcs("G54"), stock=Stock(*STOK))


def parmak(D: float = 10.0, flute_length: float = 30.0) -> Tool:
    return Tool(id=1, name=f"parmak {D:g}", kind="duz", D=D, flute_length=flute_length)


def matkap() -> Tool:
    return Tool(id=2, name="matkap 6", kind="matkap", D=6.0, flute_length=40.0)


def kanal_yolu(z: float = 18.0) -> Toolpath:
    """Düz takımla U biçimli kanal: dalma, doğru, G3 yarım daire, doğru, geri çekme."""
    return Toolpath(
        name="kanal",
        tool=parmak(),
        start=(10.0, 20.0, 25.0),
        moves=[
            Move(M.RAPID, (10.0, 20.0, 21.0)),
            Move(M.LINEAR, (10.0, 20.0, z), 300.0),
            Move(M.LINEAR, (50.0, 20.0, z), 800.0),
            Move(M.ARC_CCW, (50.0, 30.0, z), 800.0, (50.0, 25.0)),
            Move(M.LINEAR, (10.0, 30.0, z), 800.0),
            Move(M.RAPID, (10.0, 30.0, 25.0)),
        ],
        rpm=10_000.0,
    )


def delik_op() -> DrillOp:
    """İki delik, G83 gagalama (q = 4), dip z = 10."""
    return DrillOp(
        name="delik",
        tool=matkap(),
        rpm=3000.0,
        start=(55.0, 5.0, 25.0),
        holes=[(55.0, 5.0), (55.0, 35.0)],
        z=10.0,
        r=21.0,
        feed=150.0,
        kind="G83",
        q=4.0,
    )


def kucuk_is(dialect: Dialect = GRBL, parca_ag=None, kanal_z: float = 18.0) -> IsTanimi:
    """Kanal (Toolpath, yay dahil) + G83 delikler (DrillOp): iki işlem, iki takım."""
    return IsTanimi(
        ad="kucuk",
        kurulum=kurulum(),
        malzeme="aluminyum",
        islemler=[
            Islem("kanal", "U kanal", kanal_yolu(kanal_z), {"D": 10.0, "F": 800.0}),
            Islem("delik", "Delikler", delik_op(), {"D": 6.0, "q": 4.0, "F": 150.0}),
        ],
        dialect=dialect,
        parca_ag=parca_ag,
    )


def tek_g1_is(L: float = 100.0, F: float = 600.0) -> IsTanimi:
    """Stokun üstünde (kesmeyen) tek G1: süre analitik t = 60·L/F."""
    tp = Toolpath(
        name="tek",
        tool=parmak(),
        start=(0.0, 0.0, 30.0),
        moves=[Move(M.LINEAR, (L, 0.0, 30.0), F)],
        rpm=8000.0,
    )
    return IsTanimi(
        ad="tek-g1", kurulum=kurulum(), malzeme="aluminyum", islemler=[Islem("kontur", "Tek G1", tp)]
    )


def hizli_carpma_is() -> IsTanimi:
    """G0 ile stokun içinden (z = 10, stok üstü 20) X boyunca geçen yol."""
    tp = Toolpath(
        name="hizli",
        tool=parmak(),
        start=(-10.0, 20.0, 25.0),
        moves=[
            Move(M.RAPID, (-10.0, 20.0, 10.0)),
            Move(M.RAPID, (70.0, 20.0, 10.0)),
            Move(M.RAPID, (70.0, 20.0, 25.0)),
        ],
        rpm=8000.0,
    )
    return IsTanimi(
        ad="hizli-carpma", kurulum=kurulum(), malzeme="aluminyum", islemler=[Islem("kontur", "Hızlı", tp)]
    )


def kutu_ag(
    x0: float, x1: float, y0: float, y1: float, z0: float, z1: float
) -> tuple[np.ndarray, np.ndarray]:
    """Eksenlere hizalı kutunun 12 üçgenlik ağı (dışa bakan normaller)."""
    V = np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=float,
    )  # fmt: skip
    T = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # alt
            [4, 5, 6], [4, 6, 7],  # üst
            [0, 1, 5], [0, 5, 4],  # y0
            [2, 3, 7], [2, 7, 6],  # y1
            [1, 2, 6], [1, 6, 5],  # x1
            [3, 0, 4], [3, 4, 7],  # x0
        ],
        dtype=np.int64,
    )  # fmt: skip
    return V, T


def cakma_is() -> IsTanimi:
    """Parça üst yüzü z = 15; tek işlem z = 14.8'e (parçanın 0.2 mm altına) iner → çakma."""
    tp = Toolpath(
        name="cakan",
        tool=parmak(),
        start=(10.0, 20.0, 25.0),
        moves=[
            Move(M.RAPID, (10.0, 20.0, 21.0)),
            Move(M.LINEAR, (10.0, 20.0, 14.8), 300.0),
            Move(M.LINEAR, (50.0, 20.0, 14.8), 800.0),
            Move(M.RAPID, (50.0, 20.0, 25.0)),
        ],
        rpm=10_000.0,
    )
    return IsTanimi(
        ad="cakma",
        kurulum=kurulum(),
        malzeme="aluminyum",
        islemler=[Islem("kontur", "Çakan", tp)],
        parca_ag=kutu_ag(0.0, 60.0, 0.0, 40.0, 0.0, 15.0),
    )


def cakmayan_is() -> IsTanimi:
    """`cakma_is` ile aynı parça (üst yüz z = 15) ama yol z = 15.5'te kalır → çakma yok."""
    tanim = cakma_is()
    tp = tanim.islemler[0].op
    tp.moves[1] = Move(M.LINEAR, (10.0, 20.0, 15.5), 300.0)
    tp.moves[2] = Move(M.LINEAR, (50.0, 20.0, 15.5), 800.0)
    tanim.ad = "cakmayan"
    return tanim


def ops(tanim: IsTanimi) -> list:
    return [i.op for i in tanim.islemler]


def takimlar(tanim: IsTanimi) -> dict[int, Tool]:
    return {i.op.tool.id: i.op.tool for i in tanim.islemler}
