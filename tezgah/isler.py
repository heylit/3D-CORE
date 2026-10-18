"""
SPEC 24 — Örnek işler ve parametre → iş üretimi.

Örnek işler uydurma geometridir (gizlilik kuralı). İşlemler `cam` paketinin herkese açık
fonksiyonlarıyla (SPEC 03 `face`, `contour`, `pocket`; SPEC 04 `DrillOp`) üretilir.

"flans-plakasi": 120 × 80 × 20 mm alüminyum blok; işlemler sırasıyla
    0 "yuzey"  (alın frezeleme)     parametreler: D, ap, F, rpm
    1 "kontur" (dış kontur)          parametreler: D, ap, F, rpm
    2 "cep"    (orta cep)            parametreler: D, ap, F, rpm, stepover
    3 "delik"  (köşe delikleri G83)  parametreler: D, q, F, rpm
`D` takım çapı [mm], `ap` paso derinliği [mm], `F` ilerleme [mm/dk], `rpm` devir [dev/dk],
`stepover` yanal adım [mm], `q` gagalama derinliği [mm].
"""

from __future__ import annotations

import copy
import math

import numpy as np

from cam.gcode import FANUC, DrillOp
from cam.model import Setup, Stock, Tool, ToolKind, Wcs
from cam.ops2d import Cut, contour, face, pocket
from cam.profile import Profile, Region
from tezgah.kopru import Islem, IsTanimi

ORNEK_ISLER: tuple[str, ...] = ("flans-plakasi",)

# ---------------------------------------------------------------- flanş plakası (uydurma)
# İş sıfırı: stok sol alt köşesi, Z = 0 bitmiş üst yüz. Stok üstünde 0.5 mm alın payı.
STOK = Stock(0.0, 0.0, -19.5, 120.0, 80.0, 0.5)
Z_GUVENLI = 5.0
FLANS = (5.0, 5.0, 110.0, 70.0)  # x0, y0, a, b: dış kontur
Z_FLANS = -8.0  # flanş yüksekliği (kontur dibi)
CEP_M, CEP_R, Z_CEP = (60.0, 40.0), 20.0, -6.0  # orta yuvarlak cep
DELIKLER = ((15.0, 15.0), (105.0, 15.0), (105.0, 65.0), (15.0, 65.0))
Z_DELIK, R_DELIK = -10.0, 1.0

VARSAYILAN: dict[int, dict[str, float]] = {
    0: {"D": 20.0, "ap": 1.0, "F": 1200.0, "rpm": 9000.0},
    1: {"D": 10.0, "ap": 2.0, "F": 900.0, "rpm": 10000.0},
    2: {"D": 8.0, "ap": 1.5, "F": 800.0, "rpm": 11000.0, "stepover": 3.5},
    3: {"D": 6.6, "q": 3.0, "F": 250.0, "rpm": 4500.0},
}
ADLAR = (
    ("yuzey", "Alın frezeleme"),
    ("kontur", "Dış kontur"),
    ("cep", "Orta cep"),
    ("delik", "Delikler G83"),
)


def _takim(T: int, ad: str, D: float, tur: ToolKind = ToolKind.FLAT) -> Tool:
    return Tool(id=T, name=f"{ad} Ø{D:g}", kind=tur, D=D, flute_length=30.0, flutes=3)


def _kes(p: dict[str, float], z_top: float, z_bottom: float, stepover: float | None = None) -> Cut:
    return Cut(
        z_top=z_top,
        z_bottom=z_bottom,
        a_p=p["ap"],
        feed=p["F"],
        plunge_feed=p["F"] / 3,
        rpm=p["rpm"],
        z_safe=Z_GUVENLI,
        stepover=stepover,
    )


def _flans_islemleri(P: dict[int, dict[str, float]]) -> list[Islem]:
    p0, p1, p2, p3 = (P[i] for i in range(4))
    y = face(STOK, _takim(1, "Alın frezesi", p0["D"]), _kes(p0, STOK.zmax, 0.0, 0.7 * p0["D"]))
    k = contour(Profile.rectangle(*FLANS), _takim(2, "Parmak freze", p1["D"]), _kes(p1, 0.0, Z_FLANS), "dis")
    c = pocket(
        Region(Profile.circle(CEP_M, CEP_R)),
        _takim(3, "Parmak freze", p2["D"]),
        _kes(p2, 0.0, Z_CEP, p2["stepover"]),
    )
    d = DrillOp(
        name="delik",
        tool=_takim(4, "Matkap", p3["D"], ToolKind.DRILL),
        rpm=p3["rpm"],
        start=(*DELIKLER[0], Z_GUVENLI),
        holes=list(DELIKLER),
        z=Z_DELIK,
        r=R_DELIK,
        feed=p3["F"],
        kind="G83",
        q=p3["q"],
    )
    return [
        Islem(a, ad, op, dict(P[i])) for i, ((a, ad), op) in enumerate(zip(ADLAR, (y, k, c, d), strict=True))
    ]


def _flans_z(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Bitmiş flanş plakasının üst yüzeyi z(x, y): kontur dışı Z_FLANS, cep Z_CEP, delik dibi Z_DELIK."""
    x0, y0, a, b = FLANS
    z = np.where((X >= x0) & (X <= x0 + a) & (Y >= y0) & (Y <= y0 + b), 0.0, Z_FLANS)
    z = np.where(np.hypot(X - CEP_M[0], Y - CEP_M[1]) <= CEP_R, Z_CEP, z)
    for hx, hy in DELIKLER:
        z = np.where(np.hypot(X - hx, Y - hy) <= VARSAYILAN[3]["D"] / 2, Z_DELIK, z)
    return z


def hucre_agi(f, stok: Stock, hucre: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Yükseklik fonksiyonu f(X, Y) → hücre başına ayrı düz kare (2 üçgen) ağı.

    Izgara SPEC 05 z-haritasınınki (`nx = ⌈Lx/Δ⌉`, `dx = Lx/nx`); her kare z = f(hücre merkezi) yüksekliğinde.
    Merkez yalnız kendi karesinin içinde kaldığından ağın o ızgaradaki z-haritası f'nin merkezlerdeki
    değeridir (kenar enterpolasyonu yok, sınırda sahte çakma yok).
    """
    nx = math.ceil((stok.xmax - stok.xmin) / hucre - 1e-12)
    ny = math.ceil((stok.ymax - stok.ymin) / hucre - 1e-12)
    xs = np.linspace(stok.xmin, stok.xmax, nx + 1)
    ys = np.linspace(stok.ymin, stok.ymax, ny + 1)
    Xc, Yc = np.meshgrid((xs[:-1] + xs[1:]) / 2, (ys[:-1] + ys[1:]) / 2)
    Z = f(Xc, Yc).ravel()
    X0, Y0 = np.meshgrid(xs[:-1], ys[:-1])
    X1, Y1 = np.meshgrid(xs[1:], ys[1:])
    X0, Y0, X1, Y1 = X0.ravel(), Y0.ravel(), X1.ravel(), Y1.ravel()
    V = np.stack(
        [
            np.stack([X0, Y0, Z], 1),
            np.stack([X1, Y0, Z], 1),
            np.stack([X1, Y1, Z], 1),
            np.stack([X0, Y1, Z], 1),
        ],
        axis=1,
    ).reshape(-1, 3)
    b = 4 * np.arange(nx * ny)[:, None]
    T = np.concatenate([b + [0, 1, 2], b + [0, 2, 3]]).astype(np.int64)
    return V, T


def _flans(P: dict[int, dict[str, float]]) -> IsTanimi:
    return IsTanimi(
        ad="flans-plakasi",
        kurulum=Setup(name="Üst bağlama", wcs=Wcs("G54"), stock=STOK),
        malzeme="AlMg3",
        islemler=_flans_islemleri(P),
        dialect=FANUC,
        safe_z=Z_GUVENLI,
        parca_ag=hucre_agi(_flans_z, STOK),
    )


_KURUCULAR = {"flans-plakasi": (_flans, VARSAYILAN)}


def ornek_is(ad: str, parametreler: dict[int, dict[str, float]] | None = None) -> IsTanimi:
    """`ad` örnek işini kurar. `parametreler` {işlem indeksi: {anahtar: değer}} varsayılanları ezer.

    Bilinmeyen iş, işlem indeksi ya da anahtar → KeyError. Çekirdeğin reddettiği değer (ör. D ≤ 0,
    cep takımdan dar) çekirdeğin `CamError` / `ModelError`'ını olduğu gibi geçirir.
    """
    if ad not in _KURUCULAR:
        raise KeyError(f"Bilinmeyen örnek iş: {ad!r}")
    kurucu, varsayilan = _KURUCULAR[ad]
    P = copy.deepcopy(varsayilan)
    for i, d in (parametreler or {}).items():
        if i not in P:
            raise KeyError(f"'{ad}' işinde {i} numaralı işlem yok")
        for anahtar, deger in d.items():
            if anahtar not in P[i]:
                raise KeyError(f"'{ad}' işinin {i} numaralı işleminde '{anahtar}' parametresi yok")
            P[i][anahtar] = float(deger)
    tanim = kurucu(P)
    for isl in tanim.islemler:
        isl.op.validate()  # çekirdeğin reddettiği değer burada CamError
    return tanim


def parametre_uygula(tanim: IsTanimi, islem: int, anahtar: str, deger: float) -> IsTanimi:
    """`tanim`'ın parametrelerinde tek değeri değiştirip işi yeniden üretir; `tanim` değişmez."""
    if not 0 <= islem < len(tanim.islemler):
        raise KeyError(f"'{tanim.ad}' işinde {islem} numaralı işlem yok")
    P = {i: dict(isl.parametreler) for i, isl in enumerate(tanim.islemler)}
    if anahtar not in P[islem]:
        raise KeyError(f"'{tanim.ad}' işinin {islem} numaralı işleminde '{anahtar}' parametresi yok")
    P[islem][anahtar] = float(deger)
    return ornek_is(tanim.ad, P)
