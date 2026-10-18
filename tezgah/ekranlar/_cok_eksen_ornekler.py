"""
SPEC 47b — Çok eksen ekranının örnek işleri (uydurma geometri; gizlilik kuralı).

Tezgâh: `examples/tezgah_ac_besik.json` (SPEC 44, uydurma AC beşik). `ac_besik_dar` aynı tezgâhın `A` sınırı
bilerek dar seçilmiş varyantıdır; `examples/`'ta değil, burada `DAR_PROFIL` ile kurulur.

Örnekler (SPEC 47 "Ekran 2 / Örnek işler"):
- `egik_yuz_3arti2`: 80×60×40 blok, bir kenarı boyunca 30° eğik yüz, eğik yüzde 30×20×3 cep; çerçeve
  `from_normal(o, n, x_hint)`, SPEC 03 cebi yerel çerçevede, `to_world` ile WCS'ye; Ø6 düz freze. Varsayılan
  profil `ac_besik`.
- `kubbe_5eksen`: 60×60 taban, R40 küre kapağı (tepe z = 20); SPEC 06 `Raster` + SPEC 42 `finish5`,
  `Orientation("normal", lead=0, tilt=10)`, Ø6 küresel uç, `linearize(tol_p=1e-3, tol_a=0.05)`. Varsayılan
  profil `ac_besik_dar` (tarayıcıda en az bir `eksen_siniri` olayı görünsün diye); `profil="ac_besik"` ile
  olaysız kurulur.
- `kubbe_carpisma`: `kubbe_5eksen` + takım tutucusunun geçtiği yerde fikstür kutusu; varsayılan profil
  `ac_besik`.

İşin `model`'i `MachineModel` alt sınıfıdır (`IsTezgahi`): SPEC 44 `check`'in kendi eklediği otomatik gövdeler
(ham malzeme, fikstür, takım, sap, tutucu) `otomatik` listesinde de durur; ekran onları listeler ve çizer;
çekirdek bu listeyi okumaz. Pahalı yollar (finish5, linearize) girdiye göre önbelleklidir ve örnekler arasında
paylaşılır; yollar değiştirilmez.

Bu modül `EKRAN` vermez (`_` önekli: A3 import etmez); ekran kaydı yalnız `cok_eksen.py`'nin `EKRAN`'ını
kullanır. SPEC 41–44 modülleri fonksiyonların içinde import edilir: onlar yokken bu modülün importu
başarılıdır.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from cam.model import Setup, Stock, Tool, ToolHolder, Wcs

if TYPE_CHECKING:
    from cam.dropcutter import TriMesh
    from cam.model import Frame, Kinematics, Toolpath
    from cam.multiaxis.machine import MachineModel
    from cam.multiaxis.toolpath5 import Orientation

ORNEKLER: tuple[str, ...] = ("egik_yuz_3arti2", "kubbe_5eksen", "kubbe_carpisma")
PROFILLER: tuple[str, ...] = ("ac_besik", "ac_besik_dar")
# Örnek → (tür, varsayılan profil); `ornek(ad)` ile kurulan işin `tur` ve `profil` alanları.
VARSAYILAN: dict[str, tuple[str, str]] = {
    "egik_yuz_3arti2": ("3arti2", "ac_besik"),
    "kubbe_5eksen": ("5eksen", "ac_besik_dar"),
    "kubbe_carpisma": ("5eksen", "ac_besik"),
}

# Varsayılan girdiler (SPEC 47): POST /parametre anahtarları bu adlardır.
LEAD = 0.0  # derece
TILT = 10.0  # derece
TOL_P = 1e-3  # mm
TOL_A = 0.05  # derece
CLEARANCE = 0.0  # mm, SPEC 44 check() güvenlik payı
PARAMETRELER: tuple[str, ...] = ("lead", "tilt", "tol_p", "tol_a", "L", "clearance")


@dataclass
class CokEksenIsi:
    """Çok eksen ekranında oynatılan bir iş: çekirdeğin (41–44) girdileri ve ürettiği yollar.

    ad      : örnek adı (`ORNEKLER`'den)
    tur     : "3arti2" | "5eksen"
    profil  : "ac_besik" | "ac_besik_dar"
    model   : SPEC 44 `MachineModel` (gövdeler ve `profile.kinematics`)
    setup   : SPEC 14 `Setup` (stok, WCS)
    tool    : işlemlerin takımı
    L       : takım boyu (pivot – uç) [mm]
    ops     : WCS'de, her `Move.axis` dolu yollar (3+2: `to_world` çıktısı; 5 eksen: `linearize` çıktısı)
    ham     : çekirdeğin ilk yolu (5 eksen: `finish5` çıktısı, `linearize` öncesi; 3+2: `frame`'li yerel
              SPEC 03 yolu, `to_machine` girdisi)
    cerceveler : işlem başına 3+2 çerçevesi (`Frame`) ya da None
    yonelimler : işlem başına SPEC 42 `Orientation` ya da None
    part    : parça ağı (çakma hesabı için) ya da None
    lead, tilt, tol_p, tol_a, clearance : kullanıcının değiştirebildiği girdiler (`PARAMETRELER`)
    """

    ad: str
    tur: str
    profil: str
    model: MachineModel
    setup: Setup
    tool: Tool
    L: float
    ops: list[Toolpath]
    ham: list[Toolpath]
    cerceveler: list[Frame | None] = field(default_factory=list)
    yonelimler: list[Orientation | None] = field(default_factory=list)
    part: TriMesh | None = None
    lead: float = LEAD
    tilt: float = TILT
    tol_p: float = TOL_P
    tol_a: float = TOL_A
    clearance: float = CLEARANCE

    @property
    def stock(self) -> Stock:
        return self.setup.stock


# ---------------------------------------------------------------- tezgâh

KOK = Path(__file__).resolve().parents[2]
TEZGAH_JSON = KOK / "examples" / "tezgah_ac_besik.json"
DAR_A = (-40.0, 40.0)  # derece: `ac_besik_dar` profilinde A sınırı (kubbe eteğinde aşılır)

# Ortak uydurma tutucu: ağızdan ölçü hattına 60 mm, iki basamaklı.
TUTUCU = ToolHolder(
    name="HSK-uydurma", gauge_length=60.0, profile=((0.0, 10.0), (25.0, 10.0), (25.0, 20.0), (60.0, 20.0))
)
TASMA = 40.0  # mm, tutucu ağzından takım ucuna
WCS = Wcs("G54", (0.0, 0.0, -350.0))  # iş sıfırı C tablası üst yüzünde, A pivotunun üstünde


@functools.cache
def _tezgah_cls():
    from cam.multiaxis.machine import MachineModel

    @dataclass
    class IsTezgahi(MachineModel):
        """İşin tezgâhı: `MachineModel` + SPEC 44 `check`'in kendisinin eklediği otomatik gövdeler
        (ham malzeme, fikstürler, takım, sap, tutucu; `setup_bodies` + `tool_bodies`). `otomatik` yalnız
        görüntü içindir (gövde listesi, pozlar, ağlar); çekirdek fonksiyonlar onu okumaz."""

        otomatik: list = field(default_factory=list)

    return IsTezgahi


def tezgah_modeli(profil: str = "ac_besik") -> MachineModel:
    """`examples/tezgah_ac_besik.json`'dan `MachineModel`; `ac_besik_dar` → aynı model, `A` sınırı dar.

    Bilinmeyen profil → CamError.
    """
    from cam.model import CamError
    from cam.multiaxis.machine import MachineModel

    if profil not in PROFILLER:
        raise CamError(f"Çok eksen: bilinmeyen tezgâh profili {profil!r} ({', '.join(PROFILLER)})")
    model = MachineModel.from_dict(json.loads(TEZGAH_JSON.read_text(encoding="utf-8")))
    if profil == "ac_besik_dar":
        kin = model.profile.kinematics
        rotary = tuple(
            dataclasses.replace(a, min=DAR_A[0], max=DAR_A[1]) if a.name == "A" else a for a in kin.rotary
        )
        prof = dataclasses.replace(
            model.profile,
            name=model.profile.name + " (dar A)",
            kinematics=dataclasses.replace(kin, rotary=rotary),
        )
        model = MachineModel(prof, dict(model.linear_carrier), list(model.bodies), list(model.ignore))
    return model


def _is_tezgahi(model: MachineModel, setup: Setup, tool: Tool, L: float) -> MachineModel:
    from cam.multiaxis.machine import setup_bodies, tool_bodies

    otomatik = setup_bodies(setup) + tool_bodies(model.kinematics, tool, L)
    return _tezgah_cls()(
        model.profile, dict(model.linear_carrier), list(model.bodies), list(model.ignore), otomatik
    )


# ---------------------------------------------------------------- girdiler


def _girdi(ad: str, girdi: dict[str, float]) -> dict[str, float]:
    """Varsayılanlarla birleşmiş, denetlenmiş girdiler. Bilinmeyen anahtar / geçersiz değer → CamError."""
    from cam.model import CamError

    fazla = sorted(set(girdi) - set(PARAMETRELER))
    if fazla:
        raise CamError(f"Çok eksen '{ad}': bilinmeyen parametre {fazla} ({', '.join(PARAMETRELER)})")
    g = {"lead": LEAD, "tilt": TILT, "tol_p": TOL_P, "tol_a": TOL_A, "L": TUTUCU.gauge_length + TASMA}
    g["clearance"] = CLEARANCE
    for k, v in girdi.items():
        try:
            v = float(v)
        except (TypeError, ValueError) as e:
            raise CamError(f"Çok eksen '{ad}': {k} sayı olmalı ({v!r})") from e
        if not math.isfinite(v):
            raise CamError(f"Çok eksen '{ad}': {k} sonlu olmalı ({v})")
        g[k] = v
    for k in ("tol_p", "tol_a", "L"):
        if g[k] <= 0:
            raise CamError(f"Çok eksen '{ad}': {k} pozitif olmalı ({g[k]})")
    if g["clearance"] < 0:
        raise CamError(f"Çok eksen '{ad}': clearance negatif olamaz ({g['clearance']})")
    return g


def _takim(kind: str, tid: int) -> Tool:
    from cam.model import ToolKind

    return Tool(
        id=tid,
        name=f"{'K' if kind == 'ball' else 'D'}6",
        kind=ToolKind.BALL if kind == "ball" else ToolKind.FLAT,
        D=6.0,
        flute_length=20.0,
        corner_r=3.0 if kind == "ball" else 0.0,
        flutes=2,
        stickout=TASMA,
        holder=TUTUCU,
    )


def ornek(ad: str, profil: str | None = None, **girdi: float) -> CokEksenIsi:
    """Örnek işi kurar. `profil` None → örneğin varsayılan profili (modül belgesi).

    `girdi`: `PARAMETRELER` anahtarlarından değerler (verilmeyen varsayılan). Bilinmeyen örnek → KeyError;
    bilinmeyen profil, bilinmeyen girdi anahtarı ya da geçersiz değer (`tol_p ≤ 0`, `L ≤ 0` …) → CamError.
    Her çağrı yeni nesne kurar; önceki işler değişmez.
    """
    kur = {"egik_yuz_3arti2": egik_yuz_3arti2, "kubbe_5eksen": kubbe_5eksen, "kubbe_carpisma": kubbe_carpisma}
    if ad not in kur:
        raise KeyError(ad)
    return kur[ad](**girdi) if profil is None else kur[ad](profil, **girdi)


# ---------------------------------------------------------------- 3+2: eğik yüz


@functools.cache
def _egik_yollari():
    """(takım, çerçeve, ham yerel yollar, WCS yolları); bir kez kurulur, örnekler arasında paylaşılır."""
    from cam.model import CamError
    from cam.multiaxis.indexed import from_normal, to_world
    from cam.ops2d import Cut, face, pocket
    from cam.profile import Line, Profile, Region

    s, c = math.sin(math.radians(30.0)), math.cos(math.radians(30.0))
    fr = from_normal((0.0, 20.0, 40.0 - 10.0 * math.tan(math.radians(30.0))), (0.0, s, c), (1.0, 0.0, 0.0))
    tool = _takim("flat", 2)
    ortak = dict(feed=1200.0, plunge_feed=300.0, rpm=9000.0, z_safe=15.0, stepover=4.0)
    pah = face(
        Stock(-40.0, -12.0, 0.0, 40.0, 12.0, 10.0), tool, Cut(z_top=10.0, z_bottom=0.0, a_p=3.5, **ortak)
    )
    kose = [(-15.0, -10.0), (15.0, -10.0), (15.0, 10.0), (-15.0, 10.0)]
    bolge = Region(Profile([Line(kose[i], kose[(i + 1) % 4]) for i in range(4)]))
    cep = pocket(bolge, tool, Cut(z_top=0.0, z_bottom=-3.0, a_p=1.5, **ortak))
    ham = [dataclasses.replace(pah, name="pah", frame=fr), dataclasses.replace(cep, name="cep", frame=fr)]
    for tp in ham:
        if any(m.center is not None for m in tp.moves):
            raise CamError(f"egik_yuz_3arti2: '{tp.name}' yolunda yay var (nokta dizisi ham yolla eşleşmez)")
    return tool, fr, ham, [to_world(tp) for tp in ham]


def egik_yuz_3arti2(profil: str = "ac_besik", **girdi: float) -> CokEksenIsi:
    """`egik_yuz_3arti2` örneği (modül belgesi).

    Blok x ∈ [−40, 40], y ∈ [−30, 30], z ∈ [0, 40]; pah düzlemi y = 10, z = 40 kenarından +y'ye 30° iner
    (normal (0, sin 30°, cos 30°)). İki işlem aynı çerçevede: "pah" (SPEC 03 yüz alma, pah kamasını kaldırır)
    ve "cep" (30×20, 3 mm derin, SPEC 03 cep). Yollar yaysız (nokta dizisi `ham` ile `ops` aynı sayıda).
    """
    g = _girdi("egik_yuz_3arti2", girdi)
    model = tezgah_modeli(profil)
    tool, fr, ham, ops = _egik_yollari()
    setup = Setup(name="egik_yuz", wcs=WCS, stock=Stock(-40.0, -30.0, 0.0, 40.0, 30.0, 40.0))
    return CokEksenIsi(
        ad="egik_yuz_3arti2",
        tur="3arti2",
        profil=profil,
        model=_is_tezgahi(model, setup, tool, g["L"]),
        setup=setup,
        tool=tool,
        L=g["L"],
        ops=list(ops),
        ham=list(ham),
        cerceveler=[fr, fr],
        yonelimler=[None, None],
        part=None,
        lead=g["lead"],
        tilt=g["tilt"],
        tol_p=g["tol_p"],
        tol_a=g["tol_a"],
        clearance=g["clearance"],
    )


# ---------------------------------------------------------------- 5 eksen: kubbe

KUBBE_R = 40.0  # mm, küre yarıçapı (merkez z = −20, tepe z = 20)
KUBBE_ADIM = 2.0  # mm, yükseklik alanı ağının ızgara adımı
KUBBE_TABAN = -10.0  # mm, parça ağının alt yüzü
MAX_DANGLE = 5.0  # derece: finish5 süreklilik eşiğinin taban değeri (SPEC 42 varsayılanı)


def max_dangle(lead: float, tilt: float) -> float:
    """finish5 süreklilik eşiği: zikzak dönüşünde ilerleme yönü tersine döner, lead/tilt eğimi de onunla
    yön değiştirir; eksen bu noktada en çok 2(|lead| + |tilt|) döner ve bölmeyle düzelmez."""
    return MAX_DANGLE + 2.0 * (abs(lead) + abs(tilt))


def _kubbe_z(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, np.sqrt(np.maximum(KUBBE_R**2 - x**2 - y**2, 0.0)) - 20.0)


def kubbe_agi() -> TriMesh:
    """60×60 taban üstünde R40 küre kapağı, kapalı ağ (üst yükseklik alanı + yanlar + alt yüz)."""
    from cam.dropcutter import TriMesh

    n = int(round(60.0 / KUBBE_ADIM))
    u = np.linspace(-30.0, 30.0, n + 1)
    X, Y = np.meshgrid(u, u, indexing="ij")
    V = [np.column_stack([X.ravel(), Y.ravel(), _kubbe_z(X, Y).ravel()])]
    idx = np.arange((n + 1) ** 2).reshape(n + 1, n + 1)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()
    T = [np.column_stack([a, b, c]), np.column_stack([a, c, d])]
    # Kenar halkası (saat yönünün tersi, yukarıdan) ve alt kopyası.
    halka = np.concatenate([idx[:, 0], idx[-1, 1:], idx[-2::-1, -1], idx[0, -2:0:-1]])
    m = len(halka)
    alt0 = (n + 1) ** 2
    ust = V[0][halka]
    V.append(np.column_stack([ust[:, :2], np.full(m, KUBBE_TABAN)]))
    j = np.arange(m)
    k = (j + 1) % m
    T.append(np.column_stack([halka[j], alt0 + j, alt0 + k]))
    T.append(np.column_stack([halka[j], alt0 + k, halka[k]]))
    merkez = alt0 + m
    V.append(np.array([[0.0, 0.0, KUBBE_TABAN]]))
    T.append(np.column_stack([alt0 + k, alt0 + j, np.full(m, merkez)]))
    return TriMesh(V=np.vstack(V), T=np.vstack(T))


def serbest(kin: Kinematics) -> Kinematics:
    """Döner eksen sınırları kaldırılmış kinematik (SPEC 44 `check` kuralı: sınır içinde çözüm yoksa
    sınırsız çözüm)."""
    from cam.model import Kinematics, RotaryAxis

    rotary = tuple(RotaryAxis(a.name, a.carrier, a.u, a.pivot) for a in kin.rotary)
    return Kinematics(rotary=rotary, spindle=kin.spindle, gauge=kin.gauge)


KUBBE_X = 20.0  # mm, raster sıraları x ∈ [−20, 20]
KUBBE_S = 4.0  # mm, sıra aralığı


def kubbe_y(lead: float, tilt: float) -> float:
    """Raster y yarı genişliği Y ∈ [20, 23] (sıralar y = −Y + 4k, X'e paralel, zikzak).

    AC masada takım ekseni düşey (A = 0) iken C tanımsızdır (tekillik); oradan geçen sıra C'yi çok hızlı
    döndürür, doğrusallaştırma çok kısa hareketler üretir ve G93 değeri sınırı aşar. Eksen
    a = R_f(tilt)·(n cos lead + f sin lead), ilerleme f = ±x iken sürüş noktası (küre merkezi, ofset küre
    yarıçapı R + r) yaklaşık (x, y) = ∓(R + r)(sin lead, −sin tilt) iken düşeydir; Y, o yöndeki sıraların
    bu noktaya en küçük uzaklığını en büyük yapacak biçimde seçilir (eşitlikte küçük Y).
    """
    lam, tau = math.radians(lead), math.radians(tilt)
    Rc = KUBBE_R + 3.0  # küresel uç yarıçapı 3 (Ø6)
    tekil = {+1: (-Rc * math.sin(lam), Rc * math.sin(tau))}
    tekil[-1] = (-tekil[+1][0], -tekil[+1][1])
    en_iyi, en_iyi_d = 20.0, -1.0
    for Y in np.arange(20.0, 23.0 + 1e-9, 0.25):
        d = math.inf
        for k in range(int(math.floor(2 * Y / KUBBE_S + 1e-9)) + 1):
            x_s, y_s = tekil[+1 if k % 2 == 0 else -1]
            if abs(x_s) <= KUBBE_X + KUBBE_S:
                d = min(d, abs(-Y + KUBBE_S * k - y_s))
        if d > en_iyi_d + 1e-9:
            en_iyi, en_iyi_d = float(Y), d
    return en_iyi


@functools.lru_cache(maxsize=16)
def _kubbe_yollari(lead: float, tilt: float, tol_p: float, tol_a: float, L: float):
    """(parça ağı, takım, yönelim, finish5 yolu, linearize yolu); girdiye göre önbellekli.

    Yollar örnekler arasında paylaşılır ve değiştirilmez. `linearize` sınırsız kinematikle çalışır:
    dar profilde sınır dışı noktalar yine kurulur, ihlali SPEC 44 `check` `eksen_siniri` olarak yazar.
    """
    from cam.multiaxis.linearize import linearize
    from cam.multiaxis.toolpath5 import Orientation, finish5
    from cam.ops3d import Raster

    tool = _takim("ball", 1)
    part = kubbe_agi()
    Y = kubbe_y(lead, tilt)
    raster = Raster(
        xmin=-KUBBE_X, xmax=KUBBE_X, ymin=-Y, ymax=Y, stepover=KUBBE_S, ds=2.0, tol=0.01, ds_min=0.5,
        feed=1000.0, plunge_feed=300.0, rpm=12000.0, z_safe=40.0,
    )  # fmt: skip
    yon = Orientation("normal", lead=lead, tilt=tilt)
    kaba = finish5(part, tool, raster, yon, max_dangle=max_dangle(lead, tilt))
    kin = serbest(tezgah_modeli("ac_besik").kinematics)
    op = linearize(kaba, kin, WCS, L, tol_p=tol_p, tol_a=tol_a)
    return part, tool, yon, kaba, op


def _kubbe(ad: str, profil: str, fikstur: bool, girdi: dict[str, float]) -> CokEksenIsi:
    g = _girdi(ad, girdi)
    model = tezgah_modeli(profil)
    part, tool, yon, kaba, op = _kubbe_yollari(g["lead"], g["tilt"], g["tol_p"], g["tol_a"], g["L"])
    fiks = [Stock(38.0, -8.0, 0.0, 50.0, 8.0, 45.0)] if fikstur else []
    setup = Setup(name=ad, wcs=WCS, stock=Stock(-30.0, -30.0, KUBBE_TABAN, 30.0, 30.0, 21.0), fixtures=fiks)
    return CokEksenIsi(
        ad=ad,
        tur="5eksen",
        profil=profil,
        model=_is_tezgahi(model, setup, tool, g["L"]),
        setup=setup,
        tool=tool,
        L=g["L"],
        ops=[op],
        ham=[kaba],
        cerceveler=[None],
        yonelimler=[yon],
        part=part,
        lead=g["lead"],
        tilt=g["tilt"],
        tol_p=g["tol_p"],
        tol_a=g["tol_a"],
        clearance=g["clearance"],
    )


def kubbe_5eksen(profil: str = "ac_besik_dar", **girdi: float) -> CokEksenIsi:
    """`kubbe_5eksen` örneği (modül belgesi)."""
    return _kubbe("kubbe_5eksen", profil, False, girdi)


def kubbe_carpisma(profil: str = "ac_besik", **girdi: float) -> CokEksenIsi:
    """`kubbe_carpisma` örneği (modül belgesi): `kubbe_5eksen` + fikstür kutusu (`Setup.fixtures`, SPEC 44
    otomatik gövdesi `fikstur_0`) kubbenin +x eteğinde, eğilen sap ve tutucunun geçtiği yerde."""
    return _kubbe("kubbe_carpisma", profil, True, girdi)
