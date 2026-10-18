"""
SPEC 25 — Torna köprüsü: SPEC 20 yolları + SPEC 21 G-code + SPEC 22 simülasyonu →
`Is` (tur "torna") ve ikili diziler.

Saf fonksiyonlar, web bağımlılığı yok. Birimler mm, mm/dev, m/dk, dev/dk, s.
Modelde x yarıçaptır (SPEC 20); G-code'da X çaptır (SPEC 21). `Is` sözlüğü SPEC 24 biçimindedir, ek alanlar:
    "tur": "torna"
    "kurulum": {"stok": CylinderStock.to_dict(), "wcs", "malzeme", "aynalar": [CylinderStock.to_dict()]}
    "islemler[].takim": {"T", "ad", "r" (burun yarıçapı), "uc" (uç numarası), "q": [q_z, q_x], "tur"}
    "gcode[]": {"metin", "islem", "dro": {"X": çap, "Z"} | None}   (hareket satırında satırın uç noktası)
    "sure": {"toplam", "islem", "kumulatif_url", "n_max": G50 sınırı | None}
Hareketler `(x, 0, z)`, yay merkezi `(x, z)` (cam.model kuralı).

Hata: geçersiz iş tanımı `CamError` fırlatır; sessiz düzeltme yok (altın kural 5).
"""

from __future__ import annotations

import math
import struct
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from cam.gcode import FANUC_TORNA, read_lathe, spindle_rpm, write_lathe
from cam.lathe import tip_offset
from cam.model import ARCS, CamError, CylinderStock, Move, MoveType, Setup, Toolpath
from tezgah import SEMA

if TYPE_CHECKING:
    from geometry.part import Part

KONUM_EPS = 5e-4  # mm: canlı bağ ve DRO toleransı (K2, K3)
KALAN_ORAN = (
    1e-3  # kalan malzeme uyarısı: kalan hacim > KALAN_ORAN · parça hacmi (burun köşe payı bunun altında)
)
PARCA_AG_TOL = 0.01  # mm: hedef parça ağı kiriş sapması (SPEC 22 `part_rmap`)
_G = {MoveType.RAPID: 0, MoveType.LINEAR: 1, MoveType.ARC_CW: 2, MoveType.ARC_CCW: 3}


@dataclass
class TornaIslem:
    """Torna işindeki bir işlem: SPEC 20 yolu + arayüzde gösterilen kimlik ve parametreler.

    anahtar     : işlem türü ("alin", "kaba", "ince", "kanal", "dis", "boy")
    op          : SPEC 20 `Toolpath` (plane ZX, feed_mode PER_REV)
    parametreler: arayüzde değiştirilebilen sayılar (ör. {"a_p": 2.0, "f": 0.25, "Vc": 200.0})
    """

    anahtar: str
    ad: str
    op: Toolpath
    parametreler: dict[str, float] = field(default_factory=dict)


@dataclass
class TornaIsi:
    """Bir torna işi.

    kurulum    : `CylinderStock` ya da ayna / punta bağlama elemanlı `Setup` (SPEC 22)
    spindle    : "M3" | "M4" (SPEC 21 yazıcısı)
    tool_change: (x, z) takım değiştirme noktası, yarıçap (SPEC 21)
    parca      : hedef CAD parçası (sapma, çakma, kalan malzeme için); None → bu kontroller yapılmaz
    hucre      : SPEC 22 radyal ızgara hücresi Δz [mm]
    """

    ad: str
    kurulum: CylinderStock | Setup
    malzeme: str
    islemler: list[TornaIslem]
    spindle: str = "M3"
    tool_change: tuple[float, float] = (100.0, 100.0)
    parca: Part | None = None
    hucre: float = 0.5


# ---------------------------------------------------------------- yardımcılar


def _yollar(tanim: TornaIsi) -> list[Toolpath]:
    if not tanim.islemler:
        raise CamError(f"Torna işi '{tanim.ad}': işlem yok")
    yollar = []
    for isl in tanim.islemler:
        isl.op.validate()
        yollar.append(isl.op)
    return yollar


def _stok(tanim: TornaIsi) -> CylinderStock:
    st = tanim.kurulum.stock if isinstance(tanim.kurulum, Setup) else tanim.kurulum
    if not isinstance(st, CylinderStock):
        raise CamError(f"Torna işi '{tanim.ad}': ham malzeme silindir olmalı ({type(st).__name__})")
    return st


def _aynalar(tanim: TornaIsi) -> list[CylinderStock]:
    return list(tanim.kurulum.fixtures) if isinstance(tanim.kurulum, Setup) else []


def _wcs(tanim: TornaIsi) -> str:
    return tanim.kurulum.wcs.code if isinstance(tanim.kurulum, Setup) else "G54"


def _hareket(m: Move, a, islem: int) -> dict:
    h = {"g": _G[m.type], "a": [float(v) for v in a], "b": [float(v) for v in m.end]}
    if m.type in ARCS:
        h["c"] = [float(v) for v in m.center]
    h["F"] = None if m.feed is None else float(m.feed)
    h["satir"] = -1
    h["islem"] = islem
    return h


def _hareketler(tanim: TornaIsi) -> list[dict]:
    out = []
    for i, tp in enumerate(_yollar(tanim)):
        a = tp.start
        for m in tp.moves:
            out.append(_hareket(m, a, i))
            a = m.end
    return out


# ---------------------------------------------------------------- G-code ve satır ↔ hareket

_PROGRAM: dict[
    int, tuple
] = {}  # id(tanim) → (satırlar, satır → işlem, satır → aralık); tanim silinince temizlenir


def _program(tanim: TornaIsi) -> tuple[list[str], list[int | None], list[list[int] | None]]:
    """(satırlar, satır → işlem, satır → hareket aralığı).

    Program SPEC 21 yazıcısıyla yazılır. Satır ↔ hareket eşlemesi SPEC 21 okuyucusuyla kurulur: programın ilk
    i satırı okunduğunda eklenen hareketler i. satırındır. Köprünün hareketleri okunan hareketlerin sıralı
    bir alt dizisidir (okuyucuda işlem başı yaklaşmaları ve geri çekmeler de var);
    her hareket satırı tek hareket üretir
    (SPEC 21 çevrim yazmaz). Yazıcının yazmadığı sıfır boylu G0 bir önceki satırın aralığına katılır.
    Eşleşmeyen hareket kalırsa CamError (sessiz eşleme yok).
    """
    anahtar = id(tanim)
    if anahtar in _PROGRAM:
        return _PROGRAM[anahtar]
    ops = _yollar(tanim)
    satirlar = write_lathe(ops, tanim.spindle, tanim.tool_change).splitlines()
    H = _hareketler(tanim)
    tools = {op.tool.id: op.tool for op in ops}
    n_onceki = 0
    satir_hareket: list[list[int] | None] = [None] * len(satirlar)
    h = 0
    son_satir: int | None = None
    for i in range(len(satirlar)):
        okunan = [m for tp in read_lathe("\n".join(satirlar[: i + 1]) + "\n", tools) for m in tp.moves]
        yeni, n_onceki = okunan[n_onceki:], len(okunan)
        if not yeni:
            continue
        while son_satir is not None and h < len(H) and _sifir_g0(H, h):
            satir_hareket[son_satir][1] = h  # yazılmayan sıfır boylu G0
            h += 1
        if len(yeni) == 1 and h < len(H) and _ayni(yeni[0], H[h]):
            satir_hareket[i] = [h, h]
            son_satir = i
            h += 1
    while son_satir is not None and h < len(H) and _sifir_g0(H, h):
        satir_hareket[son_satir][1] = h
        h += 1
    if h != len(H):
        raise CamError(
            f"G-code satırları hareketlerle eşleşmedi ({h} / {len(H)} hareket; ilk eşleşmeyen {h})"
        )
    satir_islem = _satir_islem(satirlar, satir_hareket, H)
    _PROGRAM[anahtar] = (satirlar, satir_islem, satir_hareket)
    weakref.finalize(tanim, _PROGRAM.pop, anahtar, None)
    return _PROGRAM[anahtar]


def _ayni(m: Move, h: dict) -> bool:
    """Okunan hareket köprünün hareketi mi: aynı tür ve uç nokta koordinat başına ≤ KONUM_EPS."""
    return _G.get(m.type) == h["g"] and float(np.max(np.abs(np.array(m.end) - np.array(h["b"])))) <= KONUM_EPS


def _sifir_g0(H: list[dict], h: int) -> bool:
    return H[h]["g"] == 0 and float(np.max(np.abs(np.array(H[h]["b"]) - np.array(H[h]["a"])))) <= KONUM_EPS


def _satir_islem(satirlar: list[str], satir_hareket: list, H: list[dict]) -> list[int | None]:
    """Satırın işlemi: işlemin ilk hareket satırından önceki yaklaşma satırları da o işlemindir; program başı
    (lehçe başlığı) ve son hareketten sonraki satırlar None."""
    out: list[int | None] = [None] * len(satirlar)
    sonraki: int | None = None
    for i in range(len(satirlar) - 1, len(FANUC_TORNA.header) - 1, -1):
        ar = satir_hareket[i]
        if ar is not None:
            sonraki = H[ar[0]]["islem"]
        out[i] = sonraki
    return out


def hareketler(tanim: TornaIsi) -> list[dict]:
    """İşlemlerin hareketleri art arda, SPEC 24 `hareketler` biçiminde (K1)."""
    H = _hareketler(tanim)
    _, _, satir_hareket = _program(tanim)
    for s, ar in enumerate(satir_hareket):
        if ar is not None:
            for k in range(ar[0], ar[1] + 1):
                H[k]["satir"] = s
    return H


def gcode_satirlari(tanim: TornaIsi) -> tuple[list[dict], list[list[int] | None]]:
    """SPEC 21 yazıcısının satırları (`dro` dahil) ve satır → hareket aralığı (K2, K3).

    `dro` hareket satırında satırın son hareketinin ucu: {"X": 2x (çap), "Z": z}; diğer satırlarda None.
    """
    satirlar, satir_islem, satir_hareket = _program(tanim)
    H = _hareketler(tanim)
    G = []
    for metin, islem, ar in zip(satirlar, satir_islem, satir_hareket, strict=True):
        dro = None if ar is None else {"X": 2.0 * H[ar[1]]["b"][0], "Z": H[ar[1]]["b"][2]}
        G.append({"metin": metin, "islem": islem, "dro": dro})
    return G, [None if ar is None else list(ar) for ar in satir_hareket]


# ---------------------------------------------------------------- simülasyon (SPEC 22)

_SIM: dict[int, object] = {}  # id(tanim) → LatheSimResult; tanim silinince temizlenir


def _sim22():
    """SPEC 22 torna simülasyonu modülü. Henüz main'de yoksa NotImplementedError (sessiz geçiş yok)."""
    import cam.sim as sim

    if not all(hasattr(sim, ad) for ad in ("RadialMap", "part_rmap", "simulate_lathe")):
        raise NotImplementedError("SPEC 22 (cam.sim torna simülasyonu) henüz yok")
    return sim


def _izgara(tanim: TornaIsi):
    return _sim22().RadialMap.from_stock(_stok(tanim), tanim.hucre, _aynalar(tanim))


def _simule(tanim: TornaIsi):
    """SPEC 22 `simulate_lathe` sonucu (iş başına bir kez).

    Hedef parça varsa parça haritasıyla (çakma, kalan).
    """
    anahtar = id(tanim)
    if anahtar not in _SIM:
        sim = _sim22()
        part = None if tanim.parca is None else sim.part_rmap(tanim.parca, _izgara(tanim), PARCA_AG_TOL)
        _SIM[anahtar] = sim.simulate_lathe(_yollar(tanim), tanim.kurulum, cell=tanim.hucre, part=part)
        weakref.finalize(tanim, _SIM.pop, anahtar, None)
    return _SIM[anahtar]


def _nokta_hareket(tanim: TornaIsi, sim) -> np.ndarray:
    """Nokta → hareket (bağlantı adımında ve nokta 0'da −1); adımlar hareketlerle sırayla eşleşir."""
    n_h = sum(len(tp.moves) for tp in _yollar(tanim))
    out = np.full(len(sim.steps) + 1, -1, dtype=np.int32)
    h = 0
    for st in sim.steps:
        if not st.link:
            out[st.k] = h
            h += 1
    if h != n_h:
        raise CamError(f"Simülasyon adımları ({h}) hareketlerle ({n_h}) eşleşmiyor")
    return out


def _devir_denetle(tanim: TornaIsi) -> None:
    for tp in _yollar(tanim):
        if tp.css is not None and not (math.isfinite(tp.rpm) and tp.rpm > 0):
            raise CamError(
                f"İşlem '{tp.name}': G96 (Vc = {tp.css}) altında G50 devir sınırı yok (rpm = {tp.rpm})"
            )


def devir(tanim: TornaIsi) -> np.ndarray:
    """Her noktada iş mili devri n_k [dev/dk], float64 (n,) (K4).

    G96'da min(1000·Vc/(π·2x), n_max), G97'de rpm.
    """
    _devir_denetle(tanim)
    sim = _simule(tanim)
    ops = _yollar(tanim)
    P = sim.points()
    op_k = [0] + [st.op for st in sim.steps]
    n = np.empty(len(P))
    for k, (p, j) in enumerate(zip(P, op_k, strict=True)):
        tp = ops[j]
        n[k] = tp.rpm if tp.css is None else spindle_rpm(tp.css, float(p[0]), tp.rpm)
    return n


# ---------------------------------------------------------------- kontroller (K7)

CARPMALAR = (
    ("cakma", "Çakma", "Takım hedef parçanın altına iniyor"),
    ("hizli_carpma", "Hızlı harekette çarpma", "G0 hareketi ham malzemeden geçiyor"),
    ("ayna_carpma", "Ayna / punta çarpması", "Takım bağlama elemanına giriyor"),
)


def _kontrol(kimlik: str, baslik: str, durum: str, deger, birim: str, aciklama: str, spec: str) -> dict:
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "deger": deger,
        "birim": birim,
        "durum": durum,
        "aciklama": aciklama,
        "spec": spec,
    }


def _kontroller(tanim: TornaIsi, sim) -> list[dict]:
    out = []
    for tur, baslik, ihlal in CARPMALAR:
        c = [x for x in sim.collisions if x.kind == tur]
        if tur == "cakma" and tanim.parca is None:
            out.append(
                _kontrol(tur, baslik, "uyari", None, "mm", "Hedef parça yok; çakma denetlenmedi", "SPEC 22")
            )
        elif c:
            en = max(c, key=lambda x: x.depth)
            aciklama = f"{ihlal}: {len(c)} kayıt, en derin {en.depth:.3f} mm (nokta {en.k}, işlem {en.op})"
            out.append(_kontrol(tur, baslik, "hata", float(en.depth), "mm", aciklama, "SPEC 22"))
        else:
            out.append(_kontrol(tur, baslik, "tamam", 0.0, "mm", "İhlal yok", "SPEC 22"))
    out.append(_kalan(tanim, sim))
    out.append(_geri_okuma(tanim))
    out.append(_devir_siniri(tanim, sim))
    return out


def _kalan(tanim: TornaIsi, sim) -> dict:
    k = ("kalan_malzeme", "Kalan malzeme")
    if tanim.parca is None:
        return _kontrol(*k, "uyari", None, "mm³", "Hedef parça yok; kalan malzeme denetlenmedi", "SPEC 22")
    V = float(sim.rest_volume())
    sinir = KALAN_ORAN * tanim.parca.volume
    durum = "tamam" if V <= sinir else "uyari"
    return _kontrol(
        *k, durum, V, "mm³", f"Kalan {V:.2f} mm³ (eşik {sinir:.1f} mm³ = parça hacminin ‰1)", "SPEC 22"
    )


def _geri_okuma(tanim: TornaIsi) -> dict:
    """SPEC 21: yazılan program okununca her hareket uç noktası okunan yolda sırayla
    bulunuyor mu (≤ KONUM_EPS).
    """
    k = ("geri_okuma", "G-code geri okuma")
    satirlar, _, _ = _program(tanim)
    tools = {op.tool.id: op.tool for op in _yollar(tanim)}
    try:
        okunan = read_lathe("\n".join(satirlar) + "\n", tools, tanim.spindle)
    except CamError as e:
        return _kontrol(*k, "hata", None, "mm", f"Okunamadı: {e}", "SPEC 21")
    P = np.array([m.end for tp in okunan for m in tp.moves])
    j, en = 0, 0.0
    for h in _hareketler(tanim):
        b = np.array(h["b"])
        while j < len(P) and np.abs(P[j] - b).max() > KONUM_EPS:
            j += 1
        if j == len(P):
            return _kontrol(
                *k, "hata", None, "mm", f"Hareket uç noktası okunan yolda yok: {h['b']}", "SPEC 21"
            )
        en = max(en, float(np.abs(P[j] - b).max()))
        j += 1
    return _kontrol(*k, "tamam", en, "mm", f"Her uç nokta okunan yolda, en büyük fark {en:.1e} mm", "SPEC 21")


def _devir_siniri(tanim: TornaIsi, sim) -> dict:
    """G96 işlemlerinde G50 sınırında geçen süre (bilgi); sınırsız G96 zaten CamError."""
    n = devir(tanim)
    ops = _yollar(tanim)
    T = sim.cumulative_time()
    t = 0.0
    for st in sim.steps:
        tp = ops[st.op]
        if tp.css is not None and n[st.k] >= tp.rpm * (1 - 1e-12) and n[st.k - 1] >= tp.rpm * (1 - 1e-12):
            t += float(T[st.k] - T[st.k - 1])
    aciklama = f"En yüksek devir {n.max():.0f} dev/dk; G50 sınırında {t:.2f} s"
    return _kontrol(
        "devir_siniri", "Devir sınırı (G50)", "tamam", float(n.max()), "dev/dk", aciklama, "SPEC 21"
    )


def kontroller(tanim: TornaIsi) -> list[dict]:
    """SPEC 21/22 kontrolleri (K7).

    cakma, kalan_malzeme, hizli_carpma, ayna_carpma, geri_okuma, devir_siniri.
    """
    return _kontroller(tanim, _simule(tanim))


# ---------------------------------------------------------------- Is


def _takim(tp: Toolpath) -> dict:
    t = tp.tool
    q = tip_offset(t.tip, t.nose_r)
    return {
        "T": t.id,
        "ad": t.name,
        "r": float(t.nose_r),
        "uc": t.tip,
        "q": [float(v) for v in q],
        "tur": t.kind.value,
    }


def is_json(tanim: TornaIsi) -> dict:
    """İşin tamamı: `Is` sözlüğü, `tur = "torna"` (modül belgesi). `json.dumps` ile yazılabilir (K1).

    `islemler[i]` ayrıca `plane`, `feed_mode` (enum değeri), `css`, `rpm` alanlarını
    (`Toolpath` adlarıyla) taşır;
    `takim.q` = q_T (z, x) [mm] (burun merkezinden hayali uca, SPEC 20).
    """
    _devir_denetle(tanim)
    stok = _stok(tanim)
    H = hareketler(tanim)
    G, satir_hareket = gcode_satirlari(tanim)
    sim = _simule(tanim)
    T = sim.cumulative_time()
    op_k = np.array([st.op for st in sim.steps])
    islemler = []
    for i, (isl, tp) in enumerate(zip(tanim.islemler, _yollar(tanim), strict=True)):
        ks = np.flatnonzero(op_k == i) + 1
        k0, k1 = (int(ks[0]) - 1, int(ks[-1])) if len(ks) else (0, 0)
        islemler.append(
            {
                "i": i,
                "anahtar": isl.anahtar,
                "ad": isl.ad,
                "takim": _takim(tp),
                "t0": float(T[k0]),
                "t1": float(T[k1]),
                "k0": k0,
                "k1": k1,
                "parametreler": {k: float(v) for k, v in isl.parametreler.items()},
                "plane": tp.plane.value,
                "feed_mode": tp.feed_mode.value,
                "css": None if tp.css is None else float(tp.css),
                "rpm": float(tp.rpm),
            }
        )
    g96 = [tp.rpm for tp in _yollar(tanim) if tp.css is not None]
    return {
        "sema": SEMA,
        "tur": "torna",
        "ad": tanim.ad,
        "kurulum": {
            "stok": stok.to_dict(),
            "wcs": _wcs(tanim),
            "malzeme": tanim.malzeme,
            "aynalar": [f.to_dict() for f in _aynalar(tanim)],
        },
        "islemler": islemler,
        "hareketler": H,
        "gcode": G,
        "satir_hareket": satir_hareket,
        "sure": {
            "toplam": float(sim.total_time),
            "islem": [float(t) for t in sim.op_times],
            "kumulatif_url": f"/api/ekran/torna/is/{tanim.ad}/noktalar",
            "n_max": float(max(g96)) if g96 else None,
        },
        "kontroller": _kontroller(tanim, sim),
    }


# ---------------------------------------------------------------- ikili diziler


def _blok(a: np.ndarray) -> bytes:
    """Dizinin little-endian baytları, 8'in katına sıfırla tamamlanmış."""
    b = a.astype(a.dtype.newbyteorder("<"), copy=False).tobytes()
    return b + bytes(-len(b) % 8)


def _oku(veri: bytes, ofs: int, dtype: str, n: int) -> tuple[np.ndarray, int]:
    dt = np.dtype(dtype).newbyteorder("<")
    if ofs + dt.itemsize * n > len(veri):
        raise CamError(f"İkili dizi kısa ({len(veri)} bayt)")
    a = np.frombuffer(veri, dtype=dt, count=n, offset=ofs)
    boy = dt.itemsize * n
    return a.astype(dt.newbyteorder("="), copy=True), ofs + boy + (-boy % 8)


NOKTA_BLOKLARI = (("konum", "f4", 3), ("zaman", "f8", 1), ("satir", "i4", 1), ("islem", "i2", 1),
                  ("hizli", "u1", 1), ("yuk", "f4", 1), ("hareket", "i4", 1), ("devir", "f4", 1))  # fmt: skip


def noktalar_ikili(tanim: TornaIsi) -> bytes:
    """SPEC 24 nokta dizisi biçimi + son blok `devir: float32[n]` [dev/dk] (K4, K5).

    Konum (x, 0, z): hayali uç.
    """
    sim = _simule(tanim)
    H = hareketler(tanim)
    P = sim.points()
    hk = _nokta_hareket(tanim, sim)
    satir = np.array([H[h]["satir"] if h >= 0 else -1 for h in hk], dtype=np.int32)
    islem = np.array([0] + [st.op for st in sim.steps], dtype=np.int16)
    hizli = np.array([0] + [st.type is MoveType.RAPID for st in sim.steps], dtype=np.uint8)
    mrr = np.array([0.0] + [st.mrr for st in sim.steps])
    yuk = mrr / mrr.max() if mrr.max() > 0 else mrr
    return b"".join(
        [
            struct.pack("<II", SEMA, len(P)),
            _blok(np.asarray(P, dtype=np.float32).ravel()),
            _blok(np.asarray(sim.cumulative_time(), dtype=np.float64)),
            _blok(satir),
            _blok(islem),
            _blok(hizli),
            _blok(yuk.astype(np.float32)),
            _blok(hk),
            _blok(devir(tanim).astype(np.float32)),
        ]
    )


def noktalar_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`noktalar_ikili` çıktısı → SPEC 24 alanları + "devir"."""
    sema, n = struct.unpack_from("<II", veri, 0)
    if sema != SEMA:
        raise CamError(f"Nokta dizisi sürümü {sema}, beklenen {SEMA}")
    out, ofs = {}, 8
    for ad, dt, m in NOKTA_BLOKLARI:
        out[ad], ofs = _oku(veri, ofs, dt, n * m)
    if ofs != len(veri):
        raise CamError(f"Nokta dizisi boyu tutmuyor ({len(veri)} bayt, beklenen {ofs})")
    out["konum"] = out["konum"].reshape(n, 3)
    return out


def _dis_ic(iv: np.ndarray) -> tuple[float, float]:
    """Aralık listesinden (dış, iç) yarıçap: SPEC 22 `outer()` / `inner()` tanımı (aralık yoksa 0)."""
    if len(iv) == 0:
        return 0.0, 0.0
    return float(np.max(iv[:, 1])), float(np.min(iv[:, 0]))


def sim_ikili(tanim: TornaIsi) -> bytes:
    """Torna kesit olay listesi, little-endian ikili (K6).

    Biçim (bloklar 8 baytın katına sıfırla tamamlanır):
        başlık : uint32 sema, uint32 nz, uint32 m (olay sayısı), uint32 0
        ızgara : float64[4]   z0, dz, r_dis0 (= D/2), r_ic0 (= d/2)
        ofset  : uint32[nz+1] hücre i'nin olayları [ofset[i], ofset[i+1])
        k      : int32[m]     olayın nokta indeksi (hücre içinde artan)
        r_dis  : float32[m]   olaydan sonraki dış yarıçap (SPEC 22 `outer()`)
        r_ic   : float32[m]   olaydan sonraki iç yarıçap (SPEC 22 `inner()`)
        islem  : int16[m]
        hedef  : float32[nz]  hedef parçanın hücre merkezlerindeki dış yarıçapı (parça yoksa NaN)
    k anındaki kesit: her hücrede k'si ≤ k olan son olay; yoksa (r_dis0, r_ic0).
    Izgara SPEC 22'nin ızgarasıdır (hücre Δz = `hucre`). Başlangıç kesiti (D/2, d/2)'den farklı hücrelerde
    (ham malzeme dışı) k = 0 olayı yazılır.
    """
    sim = _simule(tanim)
    stok = _stok(tanim)
    g0 = _izgara(tanim)
    g = sim.rmap
    r0, ri0 = stok.D / 2, stok.d / 2
    islem_k = np.array([0] + [st.op for st in sim.steps], dtype=np.int16)
    hucre: list[list[tuple[int, float, float, int]]] = [[] for _ in range(g.nz)]
    for i in range(g.nz):
        d0, c0 = _dis_ic(np.asarray(g0.intervals(i), dtype=float).reshape(-1, 2))
        if (d0, c0) != (r0, ri0):
            hucre[i].append((0, d0, c0, 0))
    for e in range(len(sim.event_k)):
        i, k = int(sim.event_cell[e]), int(sim.event_k[e])
        dis, ic = _dis_ic(sim.event_iv[sim.event_iv_off[e] : sim.event_iv_off[e + 1]])
        if hucre[i] and hucre[i][-1][0] == k:
            hucre[i].pop()
        hucre[i].append((k, dis, ic, int(islem_k[k])))
    olaylar = [o for h in hucre for o in h]
    ofset = np.zeros(g.nz + 1, dtype=np.uint32)
    ofset[1:] = np.cumsum([len(h) for h in hucre])
    hedef = np.full(g.nz, np.nan, dtype=np.float32)
    if sim.part is not None:
        hedef = np.asarray(sim.part.outer(), dtype=np.float32)
    elif tanim.parca is not None:
        hedef = np.asarray(_sim22().part_rmap(tanim.parca, g0, PARCA_AG_TOL).outer(), dtype=np.float32)
    return b"".join(
        [
            struct.pack("<IIII", SEMA, g.nz, len(olaylar), 0),
            struct.pack("<4d", g.z0, g.dz, r0, ri0),
            _blok(ofset),
            _blok(np.array([o[0] for o in olaylar], dtype=np.int32)),
            _blok(np.array([o[1] for o in olaylar], dtype=np.float32)),
            _blok(np.array([o[2] for o in olaylar], dtype=np.float32)),
            _blok(np.array([o[3] for o in olaylar], dtype=np.int16)),
            _blok(hedef),
        ]
    )


def _sim_coz(veri: bytes) -> dict:
    sema, nz, m, sifir = struct.unpack_from("<IIII", veri, 0)
    if sema != SEMA or sifir != 0:
        raise CamError(f"Torna sim dizisi sürümü {sema}, beklenen {SEMA}")
    z0, dz, r0, ri0 = struct.unpack_from("<4d", veri, 16)
    out = {"nz": nz, "m": m, "z0": z0, "dz": dz, "r0": r0, "ri0": ri0}
    ofs = 48
    for ad, dt, n in (("ofset", "u4", nz + 1), ("k", "i4", m), ("r_dis", "f4", m), ("r_ic", "f4", m),
                      ("islem", "i2", m), ("hedef", "f4", nz)):  # fmt: skip
        out[ad], ofs = _oku(veri, ofs, dt, n)
    if ofs != len(veri):
        raise CamError(f"Torna sim dizisi boyu tutmuyor ({len(veri)} bayt, beklenen {ofs})")
    return out


def sim_kesit(veri: bytes, k: int) -> tuple[np.ndarray, np.ndarray]:
    """`sim_ikili` çıktısından k anındaki (r_dis, r_ic), float32 (nz,) (K6)."""
    S = _sim_coz(veri)
    dis = np.full(S["nz"], S["r0"], dtype=np.float32)
    ic = np.full(S["nz"], S["ri0"], dtype=np.float32)
    of, K = S["ofset"], S["k"]
    for i in range(S["nz"]):
        a, b = int(of[i]), int(of[i + 1])
        j = a + int(np.searchsorted(K[a:b], k, side="right")) - 1  # k'si ≤ k olan son olay
        if j >= a:
            dis[i], ic[i] = S["r_dis"][j], S["r_ic"][j]
    return dis, ic
