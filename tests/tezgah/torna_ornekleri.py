"""SPEC 25 testleri için elle kurulmuş, uydurma torna işleri (gizlilik kuralı: gerçek parça yok).

Sayılar elle seçilmiştir; hiçbiri `tezgah` kodundan türetilmez. Hareketler `cam.model` kuralıyla (x, 0, z),
x yarıçap; yay merkezi (x, z). Hızlı hareketler eksen eksen (SPEC 21: çapraz G0 yazılmaz).
"""

from __future__ import annotations

from cam.model import CylinderStock, FeedMode, LatheTool, Move, MoveType, Plane, Setup, Toolpath, Wcs
from tezgah.torna import TornaIsi, TornaIslem

M = MoveType

# Ham Ø50 × 60, z ∈ [0, 60]; ön yüz z = 60.
D, ZMIN, ZMAX = 50.0, 0.0, 60.0


def stok(d: float = 0.0) -> CylinderStock:
    return CylinderStock(D=D, zmin=ZMIN, zmax=ZMAX, d=d)


def dis_takim(id: int = 1, nose_r: float = 0.8) -> LatheTool:
    """CNMG benzeri dış tornalama ucu, T3, κr 95°, εr 80°, kenar 8 mm."""
    return LatheTool(
        id=id, name=f"CNMG r{nose_r:g}", kind="tornalama", nose_r=nose_r, tip=3, kappa_r=95.0, eps_r=80.0,
        edge_len=8.0,
    )  # fmt: skip


def _yol(name, tool, start, moves, rpm, css=None) -> Toolpath:
    return Toolpath(
        name=name,
        tool=tool,
        start=start,
        moves=moves,
        rpm=rpm,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=css,
    )


def alin_yolu(css: float | None = 200.0, n_max: float = 3000.0, z: float = 59.0, f: float = 0.2) -> Toolpath:
    """Alın tornalama: x = 27'den eksene (x = 0) kadar, z sabit;
    G96 (css) ya da G97 (css None → n_max devir)."""
    return _yol(
        "alin",
        dis_takim(),
        (27.0, 0.0, 62.0),
        [
            Move(M.RAPID, (27.0, 0.0, z)),
            Move(M.LINEAR, (0.0, 0.0, z), f),
            Move(M.RAPID, (0.0, 0.0, 62.0)),
            Move(M.RAPID, (27.0, 0.0, 62.0)),
        ],
        rpm=n_max,
        css=css,
    )


def boy_yolu(rpm: float = 1500.0, x: float = 23.0, z_son: float = 30.0) -> Toolpath:
    """Boyuna paso + omuzda çeyrek yay (G2), sabit devir (G97).

    Yay: (x − 2, 42) → (x, 40), merkez (x, z) = (x, 42), r = 2; ZX'te (u, v) = (z, x), süpürme π/2 saat yönü.
    """
    return _yol(
        "boy",
        dis_takim(),
        (30.0, 0.0, 62.0),
        [
            Move(M.RAPID, (x - 2, 0.0, 62.0)),
            Move(M.RAPID, (x - 2, 0.0, 61.0)),
            Move(M.LINEAR, (x - 2, 0.0, 42.0), 0.25),
            Move(M.ARC_CW, (x, 0.0, 40.0), 0.25, (x, 42.0)),
            Move(M.LINEAR, (x, 0.0, z_son), 0.25),
            Move(M.LINEAR, (26.0, 0.0, z_son), 0.25),
            Move(M.RAPID, (26.0, 0.0, 62.0)),
            Move(M.RAPID, (30.0, 0.0, 62.0)),
        ],
        rpm=rpm,
    )


def kucuk_torna(parca=None, kurulum=None) -> TornaIsi:
    """İki işlem, aynı takım: G96 alın + G97 boy (yay dahil)."""
    return TornaIsi(
        ad="kucuk_torna",
        kurulum=kurulum if kurulum is not None else stok(),
        malzeme="C45",
        islemler=[
            TornaIslem("alin", "Alın", alin_yolu(), {"Vc": 200.0, "f": 0.2, "n_max": 3000.0}),
            TornaIslem("boy", "Boy", boy_yolu(), {"f": 0.25, "a_p": 2.0}),
        ],
        parca=parca,
        hucre=0.5,
    )


def tek_alin(x1: float, x0: float, Vc: float, f: float, n_max: float, z: float = 59.0) -> TornaIsi:
    """Yalnız tek G1 alın hareketi (x1 → x0, z sabit), G96: kapalı form süre denetimi (K5)."""
    tp = _yol(
        "alin",
        dis_takim(),
        (x1, 0.0, z),
        [Move(M.LINEAR, (x0, 0.0, z), f)],
        rpm=n_max,
        css=Vc,
    )
    return TornaIsi(ad="tek_alin", kurulum=stok(), malzeme="C45", islemler=[TornaIslem("alin", "Alın", tp)])


def g96_sinirsiz() -> TornaIsi:
    """G96 ama G50 sınırı (rpm) verilmemiş (0): K4'te CamError beklenir."""
    tp = alin_yolu()
    tp.rpm = 0.0
    return TornaIsi(
        ad="g96_sinirsiz", kurulum=stok(), malzeme="C45", islemler=[TornaIslem("alin", "Alın", tp)]
    )


# ---------------------------------------------------------------- K7: hatalı işler


def cakan_is(parca) -> TornaIsi:
    """Hedef parça Ø40 (r = 20) iken x = 18'e inen boy pasosu: profilin altına iner (çakma)."""
    tp = boy_yolu(x=18.0, z_son=35.0)
    return TornaIsi(
        ad="cakan", kurulum=stok(), malzeme="C45", islemler=[TornaIslem("boy", "Boy", tp)], parca=parca
    )


def temiz_is(parca) -> TornaIsi:
    """Aynı parça, x ≥ 21 kalan boy pasosu (çakma yok)."""
    return TornaIsi(
        ad="temiz",
        kurulum=stok(),
        malzeme="C45",
        islemler=[TornaIslem("boy", "Boy", boy_yolu())],
        parca=parca,
    )


def hizli_carpan_is() -> TornaIsi:
    """x = 10'da z = 65 → 40 G0: Ø50 ham malzemenin içinden hızlı geçer."""
    tp = _yol(
        "hizli",
        dis_takim(),
        (30.0, 0.0, 65.0),
        [
            Move(M.RAPID, (10.0, 0.0, 65.0)),
            Move(M.RAPID, (10.0, 0.0, 40.0)),
            Move(M.RAPID, (10.0, 0.0, 65.0)),
            Move(M.RAPID, (30.0, 0.0, 65.0)),
        ],
        rpm=1000.0,
    )
    return TornaIsi(ad="hizli", kurulum=stok(), malzeme="C45", islemler=[TornaIslem("hizli", "Hızlı", tp)])


def ayna_kurulumu() -> Setup:
    """Ham Ø50 z ∈ [−20, 60]; ayna çeneleri halkası d = 50 (tutulan çap), D = 90, z ∈ [−20, 0]."""
    return Setup(
        name="ayna",
        wcs=Wcs("G54"),
        stock=CylinderStock(D=D, zmin=-20.0, zmax=ZMAX),
        fixtures=[CylinderStock(D=90.0, zmin=-20.0, zmax=0.0, d=50.0)],
    )


def ayna_carpan_is() -> TornaIsi:
    """x = 24'te z = −10'a kadar boy pasosu: takım çene bölgesine (z < 0, r ≥ 25) girer."""
    tp = boy_yolu(x=24.0, z_son=-10.0)
    return TornaIsi(
        ad="ayna", kurulum=ayna_kurulumu(), malzeme="C45", islemler=[TornaIslem("boy", "Boy", tp)]
    )


def ayna_guvenli_is() -> TornaIsi:
    """Aynı kurulum, z_son = 30: çeneden uzak."""
    return TornaIsi(
        ad="ayna_guvenli",
        kurulum=ayna_kurulumu(),
        malzeme="C45",
        islemler=[TornaIslem("boy", "Boy", boy_yolu())],
    )
