"""
SPEC 24 — Köprü: `cam/model.py` nesneleri → `Is` JSON sözlüğü ve ikili diziler.

Saf fonksiyonlar, yan etkisiz, web bağımlılığı yok (FastAPI'siz test edilir). Birimler mm, mm/dk, s.
Her JSON yanıtında `"sema": SEMA` alanı vardır.

Is sözlüğü:
    {
      "sema": 1,
      "ad": str,
      "kurulum": {"stok": {"x0", "x1", "y0", "y1", "z0", "z1"}, "wcs": "G54", "malzeme": str},
      "islemler": [{"i", "anahtar", "ad", "takim": {"T", "ad", "R", "tur"}, "t0", "t1", "k0", "k1",
                    "parametreler": {anahtar: sayı}}],
      "hareketler": [{"g": 0|1|2|3, "a": [x,y,z], "b": [x,y,z], "c": [x,y] (yalnız yayda),
                      "F": sayı | None (G0'da None), "satir": int, "islem": int}],
      "gcode": [{"metin": str, "islem": int | None}],
      "satir_hareket": [[ilk, son] | None],     # gcode satırı → hareket indeks aralığı (kapalı)
      "sure": {"toplam": s, "islem": [s, ...], "kumulatif_url": "/api/is/{ad}/noktalar"},
      "kontroller": [Kontrol],
    }
    Kontrol = {"kimlik", "baslik", "deger", "birim", "durum": "tamam"|"uyari"|"hata", "aciklama", "spec"}

- `hareketler`: işlemlerin hareketleri, işlem sırasıyla art arda. `a` hareketin başı (bir önceki
  hareketin `b`'si; işlemin ilk hareketinde işlemin `start`'ı), `b` = `Move.end`, `c` = `Move.center`,
  `F` = `Move.feed`. Delik işlemi (`DrillOp`) kanonik açılımıyla (`DrillOp.to_toolpath(dialect)`) yer alır.
  Sayılar `float`'tır; JSON'a yazılıp okununca birebir aynı kalır (K1).
- `gcode`: `cam.gcode.write` çıktısı satır satır; `islem` satırın ait olduğu işlem (baş/son satırlarda None).
- `satir_hareket[i]`: i. G-code satırının ürettiği hareketlerin indeks aralığı `[ilk, son]` (dahil); hareket
  üretmeyen satırda None. Hareket satırında `hareketler[son]["b"]`, SPEC 04 okuyucusunun aynı satır için
  verdiği uç noktadan koordinat başına ≤ 5·10⁻⁴ mm uzaktadır; delik çevrimi satırı kanonik açılımın son
  hareketine eşlenir (K2). Hareketler okuyucudan değil yoldan gelir; eşleme bu yüzden bir tolerans içindedir.
- `sure`, `islemler[].t0/t1`, `kontroller`: SPEC 05 (`cam.sim`) çıktısı (K3, K5). Kümülatif süre JSON'da
  değil, `kumulatif_url`'deki ikili nokta dizisindedir.
- `islemler[].k0/k1`: işlemin nokta indeks aralığı (`noktalar_ikili` içindeki k).

Hata: geçersiz iş tanımı `CamError` / `ModelError` fırlatır; sessiz düzeltme yok (altın kural 5).
"""

from __future__ import annotations

import struct
import weakref
from dataclasses import dataclass, field

import numpy as np

from cam.gcode import GRBL, Dialect, DrillOp, read, snap, write
from cam.model import ARCS, CamError, Move, MoveType, Setup, Stock, Toolpath
from tezgah import SEMA

KONUM_EPS = 5e-4  # mm: canlı bağ toleransı (K2)
GOUGE_TOL = 1e-3  # mm: SPEC 05 çakma eşiği
_G = {MoveType.RAPID: 0, MoveType.LINEAR: 1, MoveType.ARC_CW: 2, MoveType.ARC_CCW: 3}


@dataclass
class Islem:
    """İş içindeki bir işlem: çekirdeğin ürettiği op + arayüzde gösterilen kimlik ve parametreler.

    anahtar     : işlem türü ("yuzey", "kontur", "cep", "delik", ...)
    ad          : görünen ad
    op          : `Toolpath` veya `DrillOp` (çekirdek çıktısı)
    parametreler: arayüzde değiştirilebilen sayılar (ör. {"D": 10.0, "ap": 1.0, "F": 800.0})
    """

    anahtar: str
    ad: str
    op: Toolpath | DrillOp
    parametreler: dict[str, float] = field(default_factory=dict)


@dataclass
class IsTanimi:
    """Bir freze işi: kurulum, malzeme, işlemler; isteğe bağlı hedef parça ağı (çakma denetimi için).

    parca_ag: hedef CAD parçasının üçgen ağı (V (n, 3), T (m, 3)), iş koordinatında; None → çakma denetlenmez.
    safe_z  : `cam.gcode.write` güvenli Z'si; None → yazıcının varsayılanı.
    """

    ad: str
    kurulum: Setup
    malzeme: str
    islemler: list[Islem]
    dialect: Dialect = GRBL
    safe_z: float | None = None
    parca_ag: tuple[np.ndarray, np.ndarray] | None = None


# ---------------------------------------------------------------- yardımcılar


def _yollar(tanim: IsTanimi) -> list[Toolpath]:
    """Her işlemin doğrulanmış yolu; delik işlemi kanonik açılımıyla (`DrillOp.to_toolpath`)."""
    if not tanim.islemler:
        raise CamError(f"İş '{tanim.ad}': işlem yok")
    yollar = []
    for isl in tanim.islemler:
        op = isl.op
        op.validate()
        tp = op.to_toolpath(tanim.dialect) if isinstance(op, DrillOp) else op
        tp.validate()
        yollar.append(tp)
    return yollar


def _stok(tanim: IsTanimi) -> Stock:
    st = tanim.kurulum.stock
    if not isinstance(st, Stock):
        raise CamError(
            f"İş '{tanim.ad}': Tezgah freze akışı yalnız kutu stok kabul eder ({type(st).__name__})"
        )
    return st


def _safe_z(tanim: IsTanimi) -> float:
    """Yazıcıya verilen güvenli Z: tanımdaki ya da (yazıcının varsayılanı) op başlarının en yükseği.

    Ön ek programlarının (`gcode_satirlari`) hepsi aynı güvenli Z ile yazılsın diye açıkça hesaplanır.
    """
    if tanim.safe_z is not None:
        return float(tanim.safe_z)
    return max(isl.op.start[2] for isl in tanim.islemler)


def _hareket(m: Move, a, islem: int) -> dict:
    h = {"g": _G[m.type], "a": [float(v) for v in a], "b": [float(v) for v in m.end]}
    if m.type in ARCS:
        h["c"] = [float(v) for v in m.center]
    h["F"] = None if m.feed is None else float(m.feed)
    h["satir"] = -1
    h["islem"] = islem
    return h


# ---------------------------------------------------------------- hareketler, G-code, canlı bağ


def _hareketler(tanim: IsTanimi) -> list[dict]:
    out = []
    for i, tp in enumerate(_yollar(tanim)):
        a = tp.start
        for m in tp.moves:
            out.append(_hareket(m, a, i))
            a = m.end
    return out


def _satirlar(tanim: IsTanimi) -> tuple[list[str], list[int | None], list[list[int] | None]]:
    """(satırlar, satır → işlem, satır → hareket aralığı).

    Yazıcı her `Move`'u tam bir satıra yazar (SPEC 04); işlem başı ve geri çekme satırları hareket değildir.
    İşlem j'nin satırları, ilk j işlemin programı (aynı güvenli Z ile) ile ilk j−1 işleminkinin farkından
    bulunur: ön ek programı tam programın ön ekidir (son geri çekme satırı bir sonraki işlemin ilk
    satırıyla aynıdır).
    Çevrimli dilde delik işleminin her delik satırı o deliğin kanonik açılımına eşlenir.
    """
    ops = [isl.op for isl in tanim.islemler]
    z = _safe_z(tanim)
    d = tanim.dialect
    tam = write(ops, d, safe_z=z).splitlines()
    n_son = len(d.footer)
    on = [len(d.header)]  # on[j]: ilk j işlemin programının (son satırları hariç) uzunluğu
    geri = [0]  # geri[j]: o programın sonundaki geri çekme satırı sayısı (0 / 1)
    for j in range(1, len(ops) + 1):
        satir = write(ops[:j], d, safe_z=z).splitlines()[:-n_son]
        if satir != tam[: len(satir)]:
            raise CamError("G-code ön eki tam programla uyuşmuyor; satır eşlemesi kurulamadı")
        on.append(len(satir))
        geri.append(_geri_cekme(tanim.islemler[j - 1].op, d, z))
    satir_islem: list[int | None] = [None] * len(tam)
    satir_hareket: list[list[int] | None] = [None] * len(tam)
    h0 = 0  # işlemin ilk hareketinin genel indeksi
    for j, isl in enumerate(tanim.islemler):
        a, b = on[j] - geri[j], on[j + 1] - geri[j + 1]  # işlemin satırları [a, b)
        for s in range(a, b):
            satir_islem[s] = j
        op = isl.op
        if isinstance(op, DrillOp):
            tp = op.to_toolpath(d)
            n = len(tp.moves)
            if d.canned_cycles:
                # satırlar: ... delik_1 .. delik_m, G80; delik k → açılımının hareketleri
                sinir = [0] + [len(_tek(op, k).to_toolpath(d).moves) for k in range(1, len(op.holes) + 1)]
                ilk = b - 1 - len(op.holes)
                for k in range(len(op.holes)):
                    satir_hareket[ilk + k] = [h0 + sinir[k], h0 + sinir[k + 1] - 1]
                h0 += n
                continue
        else:
            n = len(op.moves)
        for k in range(n):
            satir_hareket[b - n + k] = [h0 + k, h0 + k]
        h0 += n
    return tam, satir_islem, satir_hareket


def _tek(op: DrillOp, k: int) -> DrillOp:
    """İlk k deliği olan kopya (kanonik açılımın delik sınırlarını bulmak için)."""
    return DrillOp(
        name=op.name,
        tool=op.tool,
        rpm=op.rpm,
        start=op.start,
        holes=op.holes[:k],
        z=op.z,
        r=op.r,
        feed=op.feed,
        kind=op.kind,
        q=op.q,
        retract=op.retract,
    )


def _geri_cekme(op: Toolpath | DrillOp, d: Dialect, z: float) -> int:
    """İşlemden sonra yazıcının `G0 Z<güvenli>` satırı yazıp yazmadığı (yuvarlanmış metne göre)."""
    if isinstance(op, DrillOp) and d.canned_cycles:
        son = op.z_ret
    else:
        tp = op.to_toolpath(d) if isinstance(op, DrillOp) else op
        son = tp.moves[-1].end[2] if tp.moves else tp.start[2]
    return int(snap(son, d.decimals) < snap(z, d.decimals))


def hareketler(tanim: IsTanimi) -> list[dict]:
    """`Is["hareketler"]` listesi (yukarıdaki biçim). Her op önce doğrulanır (CamError)."""
    hs = _hareketler(tanim)
    _, _, satir_hareket = _satirlar(tanim)
    for s, ar in enumerate(satir_hareket):
        if ar is not None:
            for k in range(ar[0], ar[1] + 1):
                hs[k]["satir"] = s
    return hs


def gcode_satirlari(tanim: IsTanimi) -> tuple[list[dict], list[list[int] | None]]:
    """(`Is["gcode"]`, `Is["satir_hareket"]`). G-code `cam.gcode.write` ile yazılır."""
    _yollar(tanim)
    tam, satir_islem, satir_hareket = _satirlar(tanim)
    gcode = [{"metin": m, "islem": i} for m, i in zip(tam, satir_islem, strict=True)]
    return gcode, satir_hareket


# ---------------------------------------------------------------- simülasyon (SPEC 05)

_SIM: dict[tuple[int, float], object] = {}  # (id(tanim), hücre) → SimResult; tanim silinince temizlenir


def _simule(tanim: IsTanimi, hucre: float = 1.0):
    """SPEC 05 `simulate` sonucu (iş ve hücre başına bir kez hesaplanır)."""
    anahtar = (id(tanim), float(hucre))
    if anahtar not in _SIM:
        from cam.sim import ZMap, mesh_zmap, simulate

        stok = _stok(tanim)
        part_z = None
        if tanim.parca_ag is not None:
            V, T = tanim.parca_ag
            part_z = mesh_zmap(np.asarray(V, float), np.asarray(T), ZMap.from_stock(stok, hucre))
        ops = [isl.op for isl in tanim.islemler]
        _SIM[anahtar] = simulate(ops, stok, cell=hucre, part_z=part_z, dialect=tanim.dialect)
        weakref.finalize(tanim, _SIM.pop, anahtar, None)
    return _SIM[anahtar]


def _nokta_hareket(tanim: IsTanimi, sim) -> np.ndarray:
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


KONTROLLER = (
    ("cakma", "Çakma", "cakma", "Takım hedef parçanın altına iniyor"),
    ("hizli_carpma", "Hızlı harekette çarpma", "hizli_carpma", "G0 hareketi malzemeden geçiyor"),
    ("sap", "Sap çarpması", "sap_carpma", "Takım gövdesi kesici boyun üstündeki malzemeye değiyor"),
    ("tutucu", "Tutucu çarpması", "tutucu_carpma", "Takım tutucusu malzemeye değiyor"),
)


def _kontroller(tanim: IsTanimi, sim) -> list[dict]:
    out = []
    for kimlik, baslik, tur, ihlal in KONTROLLER:
        c = [x for x in sim.collisions if x.kind == tur]
        if kimlik == "cakma" and tanim.parca_ag is None:
            durum, aciklama, deger = "uyari", "Hedef parça ağı yok; çakma denetlenmedi", None
        elif c:
            en = max(c, key=lambda x: x.depth)
            durum, deger = "hata", float(en.depth)
            aciklama = f"{ihlal}: {len(c)} adım, en derin {en.depth:.3f} mm (nokta {en.k}, işlem {en.op})"
        else:
            durum, deger, aciklama = "tamam", 0.0, "İhlal yok"
        out.append(
            {
                "kimlik": kimlik,
                "baslik": baslik,
                "deger": deger,
                "birim": "mm",
                "durum": durum,
                "aciklama": aciklama,
                "spec": "SPEC 05",
            }
        )
    out.append(_geri_okuma(tanim))
    return out


def _geri_okuma(tanim: IsTanimi) -> dict:
    """SPEC 04: yazılan G-code okunduğunda her hareket uç noktası, okunan yolda sırayla bulunuyor mu?

    Okuyucunun yolunda işlem başı / geri çekme hareketleri de vardır; köprünün hareketleri onun sıralı bir alt
    dizisi olmalı (koordinat başına ≤ KONUM_EPS).
    """
    gcode, _ = gcode_satirlari(tanim)
    tools = {isl.op.tool.id: isl.op.tool for isl in tanim.islemler}
    k = {"kimlik": "gcode_geri_okuma", "baslik": "G-code geri okuma", "birim": "mm", "spec": "SPEC 04"}
    try:
        okunan = read("\n".join(g["metin"] for g in gcode) + "\n", tools, tanim.dialect)
    except CamError as e:
        return {**k, "deger": None, "durum": "hata", "aciklama": f"Okunamadı: {e}"}
    P = np.array([m.end for tp in okunan for m in tp.moves])
    j, en = 0, 0.0
    for h in _hareketler(tanim):
        b = np.array(h["b"])
        while j < len(P) and np.abs(P[j] - b).max() > KONUM_EPS:
            j += 1
        if j == len(P):
            return {
                **k,
                "deger": None,
                "durum": "hata",
                "aciklama": f"Hareket uç noktası okunan yolda yok: {h['b']}",
            }
        en = max(en, float(np.abs(P[j] - b).max()))
        j += 1
    return {
        **k,
        "deger": en,
        "durum": "tamam",
        "aciklama": f"Her uç nokta okunan yolda, en büyük fark {en:.1e} mm",
    }


def kontroller(tanim: IsTanimi) -> list[dict]:
    """`Is["kontroller"]`: SPEC 04/05 fonksiyonlarından gelen kontroller (K5).

    Kimlikler: "cakma" (yol CAD parçasının altına iniyor), "hizli_carpma" (G0 malzemeden geçiyor),
    "sap" (kesici boy aşımı), "tutucu" (tutucu çarpışması), "gcode_geri_okuma" (yazılan G-code okununca
    yolla aynı). Temiz işte hepsi "tamam"; ihlalde "hata".
    """
    return _kontroller(tanim, _simule(tanim))


def is_json(tanim: IsTanimi) -> dict:
    """İşin tamamı: `Is` sözlüğü (modül belgesindeki biçim). `json.dumps` ile doğrudan yazılabilir."""
    stok = _stok(tanim)
    hs = hareketler(tanim)
    gcode, satir_hareket = gcode_satirlari(tanim)
    sim = _simule(tanim)
    T = sim.cumulative_time()
    op_k = np.array([st.op for st in sim.steps])
    islemler = []
    for i, isl in enumerate(tanim.islemler):
        ks = np.flatnonzero(op_k == i) + 1  # bu işlemin adımlarının bitiş noktaları
        k0, k1 = (int(ks[0]) - 1, int(ks[-1])) if len(ks) else (0, 0)
        tool = isl.op.tool
        islemler.append(
            {
                "i": i,
                "anahtar": isl.anahtar,
                "ad": isl.ad,
                "takim": {"T": tool.id, "ad": tool.name, "R": tool.D / 2, "tur": tool.kind.value},
                "t0": float(T[k0]),
                "t1": float(T[k1]),
                "k0": k0,
                "k1": k1,
                "parametreler": {k: float(v) for k, v in isl.parametreler.items()},
            }
        )
    return {
        "sema": SEMA,
        "ad": tanim.ad,
        "kurulum": {
            "stok": {
                "x0": stok.xmin,
                "x1": stok.xmax,
                "y0": stok.ymin,
                "y1": stok.ymax,
                "z0": stok.zmin,
                "z1": stok.zmax,
            },
            "wcs": tanim.kurulum.wcs.code,
            "malzeme": tanim.malzeme,
        },
        "islemler": islemler,
        "hareketler": hs,
        "gcode": gcode,
        "satir_hareket": satir_hareket,
        "sure": {
            "toplam": float(sim.total_time),
            "islem": [float(t) for t in sim.op_times],
            "kumulatif_url": f"/api/is/{tanim.ad}/noktalar",
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
    a = np.frombuffer(veri, dtype=dt, count=n, offset=ofs)
    boy = dt.itemsize * n
    return a.astype(dt.newbyteorder("="), copy=True), ofs + boy + (-boy % 8)


NOKTA_BLOKLARI = (("konum", "f4", 3), ("zaman", "f8", 1), ("satir", "i4", 1), ("islem", "i2", 1),
                  ("hizli", "u1", 1), ("yuk", "f4", 1), ("hareket", "i4", 1))  # fmt: skip


def noktalar_ikili(tanim: IsTanimi) -> bytes:
    """Nokta dizisi, little-endian ikili. k = SPEC 05 simülasyonundaki adım (nokta) indeksi.

    Biçim (her blok 8 baytın katına sıfırla tamamlanır, böylece tarayıcıda typed array olarak okunur):
        başlık : uint32 sema, uint32 n
        konum  : float32[n·3]   (x, y, z) takım uç noktası
        zaman  : float64[n]     kümülatif süre [s], azalmayan, zaman[0] = 0
        satir  : int32[n]       noktayı üreten G-code satırı (gcode indeksi; yoksa −1)
        islem  : int16[n]       işlem indeksi
        hizli  : uint8[n]       1 = noktaya G0 ile gelinir
        yuk    : float32[n]     normalize takım yükü 0..1 (adımın talaş kaldırma hızı / en büyüğü)
        hareket: int32[n]       noktaya getiren `Is["hareketler"]` indeksi (bağlantıda ve nokta 0'da −1);
                                ön yüz yayları bununla çizer
    """
    sim = _simule(tanim)
    hs = hareketler(tanim)
    P = sim.points()
    n = len(P)
    hk = _nokta_hareket(tanim, sim)
    satir = np.array([hs[h]["satir"] if h >= 0 else -1 for h in hk], dtype=np.int32)
    islem = np.array([0] + [st.op for st in sim.steps], dtype=np.int16)
    hizli = np.array([0] + [st.type is MoveType.RAPID for st in sim.steps], dtype=np.uint8)
    mrr = np.array([0.0] + [st.mrr for st in sim.steps])
    yuk = mrr / mrr.max() if mrr.max() > 0 else mrr
    return b"".join(
        [
            struct.pack("<II", SEMA, n),
            _blok(P.astype(np.float32).ravel()),
            _blok(np.asarray(sim.cumulative_time(), dtype=np.float64)),
            _blok(satir),
            _blok(islem),
            _blok(hizli),
            _blok(yuk.astype(np.float32)),
            _blok(hk),
        ]
    )


def noktalar_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`noktalar_ikili` çıktısı → {"konum" (n, 3), "zaman", "satir", "islem", "hizli", "yuk", "hareket"}."""
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


def sim_ikili(tanim: IsTanimi, hucre: float = 1.0) -> bytes:
    """SPEC 05 z-haritası olay listesi, little-endian ikili (K6).

    Biçim (bloklar 8 baytın katına sıfırla tamamlanır):
        başlık : uint32 sema, uint32 nx, uint32 ny, uint32 m (olay sayısı)
        ızgara : float64[6]     x0, y0, dx, dy, z_ust (başlangıç yüzeyi), z_alt
        ofset  : uint32[nx·ny+1] hücre c'nin olayları [ofset[c], ofset[c+1]); hücre c = j·nx + i
        k      : int32[m]       olayın nokta indeksi (hücre içinde artan)
        z      : float32[m]     olaydan sonraki yüzey yüksekliği
        islem  : int16[m]
    k anındaki yüzey: her hücrede k'si ≤ k olan son olayın z'si; yoksa z_ust.
    """
    sim = _simule(tanim, hucre)
    g = sim.zmap
    k = np.asarray(sim.event_k, dtype=np.int32)
    op = np.array([0] + [st.op for st in sim.steps], dtype=np.int16)[k]
    return b"".join(
        [
            struct.pack("<IIII", SEMA, g.nx, g.ny, len(k)),
            _blok(np.array([g.x0, g.y0, g.dx, g.dy, g.zmax, g.zmin], dtype=np.float64)),
            _blok(np.asarray(sim.offsets, dtype=np.uint32)),
            _blok(k),
            _blok(np.asarray(sim.event_z, dtype=np.float32)),
            _blok(op),
        ]
    )


def sim_yuzey(veri: bytes, k: int) -> np.ndarray:
    """`sim_ikili` çıktısından k anındaki yüzey, float32 (ny, nx)."""
    sema, nx, ny, m = struct.unpack_from("<IIII", veri, 0)
    if sema != SEMA:
        raise CamError(f"Sim dizisi sürümü {sema}, beklenen {SEMA}")
    izgara, ofs = _oku(veri, 16, "f8", 6)
    ofset, ofs = _oku(veri, ofs, "u4", nx * ny + 1)
    ek, ofs = _oku(veri, ofs, "i4", m)
    ez, ofs = _oku(veri, ofs, "f4", m)
    z = np.full(nx * ny, np.float32(izgara[4]), dtype=np.float32)
    # her hücrede k'si ≤ k olan son olay: hücre içi k artan olduğundan searchsorted
    for c in np.flatnonzero(np.diff(ofset)):
        a, b = int(ofset[c]), int(ofset[c + 1])
        j = a + int(np.searchsorted(ek[a:b], k, side="right")) - 1
        if j >= a:
            z[c] = ez[j]
    return z.reshape(ny, nx)
