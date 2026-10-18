"""SPEC 46 — uçtan uca altın senaryo: ortak fikstürler ve halka koruması.

Senaryo (SPEC 46 Teori §1, uydurma geometri): kare flanş 80 × 80 × 12 (Ø20 merkez delik, köşelerde 4 × Ø6.6),
mil Ø20 × 60 (üst ucu 1 mm pah), malzeme "Al". Zincir yalnız `main`'deki genel işlevleri kullanır; yeni
uygulama kodu yoktur. Parça fikstürleri OCCT ister: onları kullanan testler `@pytest.mark.occt` taşır.
"""

from __future__ import annotations

import importlib
import math
from types import ModuleType

import numpy as np
import pytest

from assy.model import Mate, MateKind, Node, Ref, RefKind
from cam import cutting, lathe_ops, ops2d
from cam.gcode import DrillOp
from cam.model import (
    CuttingData,
    CylinderStock,
    LatheTool,
    LatheToolKind,
    Setup,
    Stock,
    Tool,
    ToolKind,
    ToolLibrary,
    Toolpath,
    Wcs,
)
from cam.profile import Line, Profile, Region

MALZEME = "Al"

# ------------------------------------------------------------------ senaryo ölçüleri (SPEC 46 §1)
A, B, H = 80.0, 80.0, 12.0  # flanş
MERKEZ = (40.0, 40.0)
D_MERKEZ = 20.0
D_KOSE = 6.6
KOSELER = [(12.0, 12.0), (68.0, 12.0), (12.0, 68.0), (68.0, 68.0)]
R_MIL, L_MIL, PAH = 10.0, 60.0, 1.0
STOK_UST = 15.0
CUBUK_D, CUBUK_ZMIN, CUBUK_ZMAX = 24.0, -5.0, 61.0
N_MAX = 6000.0  # torna G50 devir sınırı (uydurma)


def halka(spec: str, modul: str, *adlar: str) -> ModuleType:
    """Halkanın bağımlılığını ister; modül veya ad yoksa modül düzeyinde atlar (SPEC 46 §3).

    Yalnız "yok" durumunda atlanır: modül var ama işlev NotImplementedError fırlatıyorsa test koşar.
    """
    try:
        m = importlib.import_module(modul)
    except ModuleNotFoundError:
        pytest.skip(f"SPEC {spec} main'de değil ({modul} yok)", allow_module_level=True)
    eksik = [a for a in adlar if not hasattr(m, a)]
    if eksik:
        pytest.skip(f"SPEC {spec} main'de değil ({modul}.{', '.join(eksik)} yok)", allow_module_level=True)
    return m


# ------------------------------------------------------------------ beklenen analitik değerler


def V_flans() -> float:
    return A * B * H - math.pi * (D_MERKEZ / 2) ** 2 * H - 4 * math.pi * (D_KOSE / 2) ** 2 * H


def V_pah(r: float = R_MIL, c: float = PAH) -> float:
    """Dik kenarları c olan üçgen kesitin dönmesi (Pappus): alan c²/2, ağırlık merkezi yarıçapı r − c/3."""
    return math.pi * c**2 * (r - c / 3)


def V_mil() -> float:
    return math.pi * R_MIL**2 * L_MIL - V_pah()


# ------------------------------------------------------------------ parçalar (OCCT)


@pytest.fixture(scope="session")
def flans():
    from geometry.features import block, hole

    p = block(A, B, H, name="flans")
    p = hole(p, *MERKEZ, D_MERKEZ)
    for x, y in KOSELER:
        p = hole(p, x, y, D_KOSE)
    return p


@pytest.fixture(scope="session")
def mil():
    from geometry.features import chamfer_top, cylinder

    return chamfer_top(cylinder(R_MIL, L_MIL, name="mil"), PAH)


# ------------------------------------------------------------------ ham malzeme, bağlama, takımlar


@pytest.fixture(scope="session")
def flans_stok() -> Stock:
    return Stock(0.0, 0.0, 0.0, A, B, STOK_UST)


@pytest.fixture(scope="session")
def flans_setup(flans_stok) -> Setup:
    return Setup("flans", Wcs("G54"), flans_stok)


@pytest.fixture(scope="session")
def mil_stok() -> CylinderStock:
    return CylinderStock(D=CUBUK_D, zmin=CUBUK_ZMIN, zmax=CUBUK_ZMAX)


@pytest.fixture(scope="session")
def kutuphane() -> ToolLibrary:
    """Uydurma kesme verili takım kütüphanesi (SPEC 46 §1 tablo)."""
    al_freze = {MALZEME: CuttingData(Vc=300.0, fz=0.05, ap=4.0, ae=4.0)}
    al_matkap = {MALZEME: CuttingData(Vc=80.0, fz=0.08)}
    al_torna = {MALZEME: CuttingData(Vc=250.0, fn=0.15, ap=1.5)}
    return ToolLibrary(
        [
            Tool(1, "freze16", ToolKind.FLAT, D=16.0, flute_length=30.0, flutes=3, cutting=al_freze),
            Tool(2, "freze10", ToolKind.FLAT, D=10.0, flute_length=25.0, flutes=3, cutting=al_freze),
            Tool(3, "matkap6.6", ToolKind.DRILL, D=D_KOSE, flute_length=30.0, flutes=2, cutting=al_matkap),
            LatheTool(
                11,
                "dis_kalem",
                LatheToolKind.TURN,
                nose_r=0.4,
                tip=3,
                kappa_r=93.0,
                eps_r=55.0,
                cutting=al_torna,
            ),
        ]
    )


# ------------------------------------------------------------------ elle işlem listeleri (H3, H7)


def _cut(tool: Tool, z_top: float, z_bottom: float, z_safe: float) -> ops2d.Cut:
    sf = cutting.milling(tool, MALZEME)
    cd = tool.cutting[MALZEME]
    return ops2d.Cut(
        z_top=z_top,
        z_bottom=z_bottom,
        a_p=min(cd.ap, tool.flute_length),
        feed=sf.F,
        plunge_feed=0.3 * sf.F,
        rpm=sf.n,
        z_safe=z_safe,
        stepover=min(cd.ae, tool.D / 2),
    )


@pytest.fixture(scope="session")
def z_guvenli(flans_setup) -> float:
    from cam.setups import clearance_height

    return clearance_height(flans_setup)


@pytest.fixture(scope="session")
def freze_ops(kutuphane, flans_stok, z_guvenli) -> list[Toolpath | DrillOp]:
    """Flanş: alın (T1, z 15 → 12), merkez delik dairesel cep (T2, z 12 → 0), köşe delikleri (T3)."""
    T1, T2, T3 = (kutuphane.get(i) for i in (1, 2, 3))
    alin = ops2d.face(flans_stok, T1, _cut(T1, STOK_UST, H, z_guvenli))
    bolge = Region(Profile.circle(MERKEZ, D_MERKEZ / 2))
    cep = ops2d.pocket(bolge, T2, _cut(T2, H, 0.0, z_guvenli))
    sf = cutting.milling(T3, MALZEME)
    delik = DrillOp(
        "kose_delikleri",
        T3,
        rpm=sf.n,
        start=(*KOSELER[0], z_guvenli),
        holes=KOSELER,
        z=0.0,  # SPEC 14: ham malzeme altına inilmez (taşma 0)
        r=H + 1.0,
        feed=sf.F,
        kind="G81",
    )
    return [alin, cep, delik]


def mil_profili() -> Profile:
    """(z, x) düzleminde dış profil: pah (60, 9) → (59, 10), Ø20 silindir → (0, 10), alın x = 12'ye."""
    return Profile(
        [
            Line((L_MIL, R_MIL - PAH), (L_MIL - PAH, R_MIL)),
            Line((L_MIL - PAH, R_MIL), (0.0, R_MIL)),
            Line((0.0, R_MIL), (0.0, CUBUK_D / 2)),
        ],
        closed=False,
    )


@pytest.fixture(scope="session")
def torna_ops(kutuphane, mil_stok) -> list[Toolpath]:
    """Mil: alın (z 61 → 60), kaba (0.2 mm pay) ve finiş.

    SPEC 20: kaba / finiş profili ham malzemenin ön yüzünden başlar; alından sonraki çubuk `zmax = 60`'tır.
    """
    T = kutuphane.get(11)
    alin_sonrasi = CylinderStock(D=mil_stok.D, zmin=mil_stok.zmin, zmax=L_MIL)
    Vc, n_max = cutting.css(T, MALZEME, N_MAX)
    cd = T.cutting[MALZEME]
    kesme = lathe_ops.TurnCut(feed=cd.fn, rpm=n_max, css=Vc, a_p=cd.ap)
    return [
        lathe_ops.face(mil_stok, T, kesme, z_face=L_MIL),
        lathe_ops.rough(mil_profili(), alin_sonrasi, T, kesme, allowance=0.2),
        lathe_ops.finish(mil_profili(), alin_sonrasi, T, kesme),
    ]


# ------------------------------------------------------------------ montaj (H6)


def _T(t, aci_z: float = 0.0) -> np.ndarray:
    c, s = math.cos(aci_z), math.sin(aci_z)
    T = np.eye(4)
    T[:3, :3] = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    T[:3, 3] = t
    return T


def montaj_agaci(mil_T: np.ndarray | None = None) -> Node:
    """Kök altında flanş (orijinde) ve mil (verilen ya da keyfi başlangıç konumunda)."""
    if mil_T is None:
        mil_T = _T((55.0, 20.0, 7.0), aci_z=0.3)
    return Node(
        "montaj",
        children=[Node("flans", part="flans"), Node("mil", T=mil_T, part="mil")],
    )


def montaj_kisitlari() -> list[Mate]:
    """Eş eksen (flanş merkez delik ↔ mil ekseni) + çakışık alt düzlemler."""
    return [
        Mate(
            MateKind.CONCENTRIC,
            Ref("flans", RefKind.AXIS, (*MERKEZ, 0.0), (0.0, 0.0, 1.0)),
            Ref("mil", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ),
        Mate(
            MateKind.COINCIDENT,
            Ref("flans", RefKind.PLANE, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
            Ref("mil", RefKind.PLANE, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
            flip=True,
        ),
    ]
