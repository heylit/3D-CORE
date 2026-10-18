"""SPEC 51 testlerinin ortak yardımcıları: uydurma kinematikler, 5 eksen test profilleri, yollar, toleranslar.

Testler yalnız SPEC 51 metninden, iskelet imzalarından (`post5`, `swivel_angles`, `read_program5`),
`cam/model.py` arayüzünden ve main'deki SPEC 41 / 42 işlevlerinden (`from_xyz`, `from_zxz`, `linearize`,
`joint_path`, `inverse_time`) yazıldı; `cam/post/multiaxis.py` ve `read_multiaxis.py` gövdeleri okunmadı.

Varsayımlar (SPEC'te açık değil, koordinatöre bildirildi):
- Açılar da profilin `decimals` ondalığıyla yazılır; vektör bileşenleri en az o kadar ondalıkla.
- Okuyucunun döndürdüğü yolda kesme hareketleri (G1/G2/G3) özgün yolun kesme hareketleriyle aynı sırada;
  post'un eklediği G0 yaklaşma / geri çekilme hareketleri karşılaştırmaya girmez.
"""

from __future__ import annotations

import math
import re

import numpy as np

from cam.model import (
    Frame,
    Kinematics,
    MachineProfile,
    Move,
    MoveType,
    MultiAxisPost,
    PathMeta,
    RotaryAxis,
    ToolLibrary,
    Toolpath,
)
from tests.cam.post_ortak import kurulum, takim

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
KESME = (G1, G2, G3)

DILLER = ("sinumerik", "heidenhain", "fanuc")
TCP_VARSAYILAN = {"sinumerik": "traori", "heidenhain": "tcpm", "fanuc": "g43.4"}
TCP_VEKTOR = {"sinumerik": "traori", "heidenhain": "m128", "fanuc": "g43.5"}  # LN … TX TY TZ M128 ile
SWIVEL = {"sinumerik": "cycle800", "heidenhain": "plane_spatial", "fanuc": "g68.2"}

L_TAKIM = 100.0  # mm, ölçü boyu: tutucu 60 + taşma 40 (post_ortak.takim)
TAKIM = takim(1, L=L_TAKIM)
TAKIMLAR = ToolLibrary([TAKIM])
KURULUM = kurulum((0.0, 0.0, 0.0))
RPM = 8000.0

D = 3  # profil ondalığı
TOL_P = 0.5 * 10.0**-D * math.sqrt(3.0) + 1e-9  # konum (SPEC 04 kuralı)
TOL_ACI = 0.5 * 10.0**-D  # derece, tek açının yuvarlama hatası


# ---------------------------------------------------------------- kinematikler (uydurma)


def ac_masa() -> Kinematics:
    """AC masa-masa: A x ekseni etrafında (taban), C masa üstünde z etrafında."""
    return Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (0.0, 15.0, -60.0), -120.0, 120.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (4.0, -2.0, 0.0)),
        )
    )


def bc_masa_45() -> Kinematics:
    """BC masa-masa, DMU tipi: B ekseni YZ düzleminde 45° eğik (nütasyon), C masa üstünde."""
    s = math.sqrt(0.5)
    return Kinematics(
        rotary=(
            RotaryAxis("B", "masa", (0.0, -s, s), (0.0, 0.0, -100.0), 0.0, 180.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),
        )
    )


def bc_kafa_masa() -> Kinematics:
    """BC kafa-masa: B kafada y etrafında, C masada z etrafında."""
    return Kinematics(
        rotary=(
            RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), (0.0, 0.0, 150.0), -110.0, 110.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),
        ),
        gauge=(0.0, 0.0, 150.0),
    )


def a_masa() -> Kinematics:
    """A masalı 4 eksen (42 K7): A x ekseni etrafında, pivot orijinde."""
    return Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)),))


KINEMATIKLER = {"ac_masa": ac_masa, "bc_masa_45": bc_masa_45, "bc_kafa_masa": bc_kafa_masa}


# ---------------------------------------------------------------- profiller


def makine(
    dil: str,
    kin: Kinematics | None,
    tcp: str | None = None,
    swivel: str | None = None,
    vector: bool = False,
    multiaxis: bool = True,
    **kw,
) -> MachineProfile:
    """Kursu sınırsız, geniş devir / ilerleme sınırlı 5 eksen test profili."""
    ma = None
    if multiaxis:
        ma = MultiAxisPost(
            tcp=TCP_VARSAYILAN[dil] if tcp is None else tcp,
            swivel=SWIVEL[dil] if swivel is None else swivel,
            vector=vector,
        )
    d = dict(
        name="TEST 5X",
        controller=dil,
        rpm_min=0.0,
        rpm_max=30_000.0,
        feed_max=20_000.0,
        program_no_range=(1, 9999),
        decimals=D,
        kinematics=kin,
        multiaxis=ma,
        presets={"G54": 1} if dil == "heidenhain" else None,
    )
    d.update(kw)
    m = MachineProfile(**d)
    m.validate()
    return m


# ---------------------------------------------------------------- yollar


def meta(axis_mode: str) -> PathMeta:
    return PathMeta(strategy="ince", axis_mode=axis_mode)


def yon(tilt: float, az: float) -> np.ndarray:
    """+z'den `tilt` derece eğik, x'ten `az` derece dönük birim eksen."""
    t, a = math.radians(tilt), math.radians(az)
    return np.array([math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t)])


def yarim_kure(seed: int = 51, n: int = 24, R: float = 30.0, axis_mode: str | None = "5") -> Toolpath:
    """42 tipi yarım küre yolu: uç küre yüzeyinde, eksen dış normal (küre uçlu takım).

    Eğim 25° → 55°, azimut −60° → 60° düzgün değişir, sabit tohumlu küçük sapmalarla; kutuptan uzak
    (tekillik yok), ardışık açı değişimi küçük.
    """
    rng = np.random.default_rng(seed)
    c = np.array([0.0, 0.0, -R])
    tilts = np.linspace(25.0, 55.0, n) + rng.uniform(-2.0, 2.0, n)
    azs = np.linspace(-60.0, 60.0, n) + rng.uniform(-3.0, 3.0, n)
    A = [yon(t, a) for t, a in zip(tilts, azs, strict=True)]
    P = [c + R * a for a in A]
    moves = [Move(G1, tuple(p), feed=600.0, axis=tuple(a)) for p, a in zip(P, A, strict=True)]
    return Toolpath(
        name="KURE",
        tool=TAKIM,
        start=tuple(P[0] + 10.0 * A[0]),
        moves=moves,
        rpm=RPM,
        meta=None if axis_mode is None else meta(axis_mode),
    )


def egik_cep(frame: Frame, axis_mode: str | None = "3+2") -> Toolpath:
    """Eğik yüzde cep: yerel XY'de doğrular ve yaylar (G2, G3), yerel z = −2, sonda G0 geri çekilme."""
    z = -2.0
    moves = [
        Move(G1, (0.0, 0.0, z), feed=200.0),
        Move(G1, (15.0, 0.0, z), feed=500.0),
        Move(G3, (15.0, 10.0, z), feed=500.0, center=(15.0, 5.0)),
        Move(G1, (0.0, 10.0, z), feed=500.0),
        Move(G2, (-4.0, 6.0, z), feed=500.0, center=(0.0, 6.0)),
        Move(G1, (-4.0, 0.0, z), feed=500.0),
        Move(G0, (-4.0, 0.0, 10.0)),
    ]
    return Toolpath(
        name="CEP",
        tool=TAKIM,
        start=(0.0, 0.0, 10.0),
        moves=moves,
        rpm=RPM,
        frame=frame,
        meta=None if axis_mode is None else meta(axis_mode),
    )


def duz_yol(axis_mode: str | None = "3") -> Toolpath:
    """Eksensiz, çerçevesiz 3 eksen yol."""
    moves = [
        Move(G1, (0.0, 0.0, -1.0), feed=200.0),
        Move(G1, (20.0, 0.0, -1.0), feed=500.0),
        Move(G1, (20.0, 10.0, -1.0), feed=500.0),
        Move(G0, (20.0, 10.0, 10.0)),
    ]
    return Toolpath(
        name="DUZ",
        tool=TAKIM,
        start=(0.0, 0.0, 10.0),
        moves=moves,
        rpm=RPM,
        meta=None if axis_mode is None else meta(axis_mode),
    )


def yay_yolu(r: float = 50.0, delta: float = 30.0, x0: float = 20.0) -> Toolpath:
    """42 K7 analitik durumu: A eksenine r uzak iki uç, radyal eksen; yaklaşma + Δ dönme."""

    def p(phi):
        f = math.radians(phi)
        return np.array([x0, r * math.sin(f), r * math.cos(f)])

    def a(phi):
        f = math.radians(phi)
        return np.array([0.0, math.sin(f), math.cos(f)])

    moves = [
        Move(G1, tuple(p(0.0)), feed=500.0, axis=tuple(a(0.0))),
        Move(G1, tuple(p(delta)), feed=500.0, axis=tuple(a(delta))),
    ]
    return Toolpath(
        name="YAY", tool=TAKIM, start=tuple(p(0.0) + 10.0 * a(0.0)), moves=moves, rpm=RPM, meta=meta("5")
    )


# ---------------------------------------------------------------- karşılaştırma


def kesmeler(tp: Toolpath) -> list[Move]:
    return [m for m in tp.moves if m.type in KESME]


def eksen(m: Move) -> np.ndarray:
    return np.array((0.0, 0.0, 1.0) if m.axis is None else m.axis, dtype=float)


def aci(u, v) -> float:
    """İki yön arası açı [derece]."""
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    return math.degrees(math.atan2(np.linalg.norm(np.cross(u, v)), float(u @ v)))


def tek_yol(tps: list[Toolpath]) -> Toolpath:
    assert len(tps) == 1, f"tek yol beklenirdi ({len(tps)})"
    return tps[0]


# ---------------------------------------------------------------- metin işlemleri

_YORUM = re.compile(r"\([^)]*\)|;.*$")


def sozcukler(satir: str) -> str:
    """Satırın yorumsuz, büyük harf metni."""
    return _YORUM.sub("", satir).upper()


def var_mi(metin: str, desen: str) -> bool:
    """Yorumlar dışında `desen` (regex) geçiyor mu."""
    return any(re.search(desen, sozcukler(s)) for s in metin.splitlines())


def satir_ekle(metin: str, i: int, satir: str) -> tuple[str, int]:
    """`i` indeksli satırın önüne `satir` ekler; eklenen satırın 1 tabanlı numarasını döndürür."""
    satirlar = metin.splitlines()
    satirlar.insert(i, satir)
    return "\n".join(satirlar) + "\n", i + 1


def ilk_satir(metin: str, desen: str) -> int:
    """Yorumlar dışında `desen` geçen ilk satırın 0 tabanlı indeksi."""
    for i, s in enumerate(metin.splitlines()):
        if re.search(desen, sozcukler(s)):
            return i
    raise AssertionError(f"programda {desen!r} yok")
