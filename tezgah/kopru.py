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

from dataclasses import dataclass, field

import numpy as np

from cam.gcode import GRBL, Dialect, DrillOp
from cam.model import Setup, Toolpath

KONUM_EPS = 5e-4  # mm: canlı bağ toleransı (K2)


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


def hareketler(tanim: IsTanimi) -> list[dict]:
    """`Is["hareketler"]` listesi (yukarıdaki biçim). Her op önce doğrulanır (CamError)."""
    raise NotImplementedError("SPEC 24: uygulanmadı")


def gcode_satirlari(tanim: IsTanimi) -> tuple[list[dict], list[list[int] | None]]:
    """(`Is["gcode"]`, `Is["satir_hareket"]`). G-code `cam.gcode.write` ile yazılır."""
    raise NotImplementedError("SPEC 24: uygulanmadı")


def kontroller(tanim: IsTanimi) -> list[dict]:
    """`Is["kontroller"]`: SPEC 04/05 fonksiyonlarından gelen kontroller (K5).

    Kimlikler: "cakma" (yol CAD parçasının altına iniyor), "hizli_carpma" (G0 malzemeden geçiyor),
    "sap" (kesici boy aşımı), "tutucu" (tutucu çarpışması), "gcode_geri_okuma" (yazılan G-code okununca
    yolla aynı). Temiz işte hepsi "tamam"; ihlalde "hata".
    """
    raise NotImplementedError("SPEC 24: uygulanmadı")


def is_json(tanim: IsTanimi) -> dict:
    """İşin tamamı: `Is` sözlüğü (modül belgesindeki biçim). `json.dumps` ile doğrudan yazılabilir."""
    raise NotImplementedError("SPEC 24: uygulanmadı")


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
    """
    raise NotImplementedError("SPEC 24: uygulanmadı")


def noktalar_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`noktalar_ikili` çıktısı → {"konum" (n, 3), "zaman", "satir", "islem", "hizli", "yuk"} dizileri."""
    raise NotImplementedError("SPEC 24: uygulanmadı")


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
    raise NotImplementedError("SPEC 24: uygulanmadı")


def sim_yuzey(veri: bytes, k: int) -> np.ndarray:
    """`sim_ikili` çıktısından k anındaki yüzey, float32 (ny, nx)."""
    raise NotImplementedError("SPEC 24: uygulanmadı")
