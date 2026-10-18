"""
SPEC 64 §2, §4, §5 — iş emri saklama ve durum makinesi.

    alindi → baglandi → hazir → gonderildi;  her durumdan → iptal (kayıt silinmez)

Saklama: yerel_parcalar/mes/is-emirleri.json (kanonik JSON, atomik yazım: geçici dosya + os.replace).
Bozuk dosya MesBozuk verir ve dosya sessizce sıfırlanmaz. Her durum değişikliği tekdüze artan bir
`degisiklik` numarası alır.

Bağlı iş (tezgah.depo adı) değişince `hazir` iş emri `baglandi`'ya döner (tazele): bayat çıktı verilmez.
`gonderildi` geçişi SPEC 63 gönderim kaydından gelir (esitle): kayıttaki program özeti iş emrinin dondurulmuş
program özetiyle eşleşirse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tezgah.mes.sema import IsEmri, IsEmriDurumu

DURUMLAR = ("alindi", "baglandi", "hazir", "gonderildi", "iptal")

# Çalışma klasörüne göre (Tezgah kullanıcı klasöründe çalışır; testler monkeypatch.chdir(tmp_path) ile).
DEPO_YOLU = Path("yerel_parcalar/mes/is-emirleri.json")
AYAR_YOLU = Path("yerel_parcalar/mes/ayar.json")  # {"izinli_kokenler": [str]} (CORS, §6)
GONDERIM_KAYDI = Path("yerel_parcalar/gonderim-kaydi.jsonl")  # SPEC 63 §5


class MesHatasi(Exception):
    """MES uçlarının kendi hataları (çekirdek hatası değil; uçlarda 404 / 409 / 503'e çevrilir)."""


class MesYok(MesHatasi):
    """Bilinmeyen mes_id (404)."""


class MesCakisma(MesHatasi):
    """Durum çakışması: aynı revizyon farklı gövde, yanlış durumda istenen çıktı ya da geçiş (409)."""


class MesBozuk(MesHatasi):
    """Depo dosyası okunamıyor (503); dosyaya dokunulmaz."""


@dataclass
class MesDepo:
    """Bellekteki depo; her değiştiren işlem dosyaya atomik yazar.

    kayitlar : mes_id → o mes_id'nin revizyonları (eskiden yeniye); sonuncusu güncel kayıttır
    sayac    : son verilen degisiklik numarası
    dondurulan: mes_id → `hazir` anında dondurulan çıktılar {"program": metin, "foy": html, "takimlar": [...],
                "sure": {...} | None} (dosyada saklanır; program uçları bunu verir)
    """

    yol: Path
    kayitlar: dict[str, list[IsEmriDurumu]] = field(default_factory=dict)
    sayac: int = 0
    dondurulan: dict[str, dict] = field(default_factory=dict)


def yukle(yol: Path = DEPO_YOLU) -> MesDepo:
    """Depo dosyasını okur; yoksa boş depo (dosya ilk yazımda oluşur). Bozuksa MesBozuk."""
    raise NotImplementedError


def kaydet(d: MesDepo) -> None:
    """Kanonik JSON, atomik yazım (yarıda hata → eski dosya sağlam)."""
    raise NotImplementedError


def koy(d: MesDepo, e: IsEmri) -> IsEmriDurumu:
    """Oluşturur ya da yeni revizyon (eskisi iptal, yenisi alindi).

    Aynı (mes_id, revizyon) aynı gövde → eş-etkili; farklı gövde ya da eski revizyon → MesCakisma.
    """
    raise NotImplementedError


def al(d: MesDepo, mes_id: str) -> IsEmriDurumu:
    """Güncel kayıt; bilinmeyen → MesYok."""
    raise NotImplementedError


def bagla(d: MesDepo, mes_id: str, is_adi: str) -> IsEmriDurumu:
    """alindi / baglandi → baglandi; is_adi tezgah.depo'da olmalı (yoksa KeyError → 422)."""
    raise NotImplementedError


def hazirla(d: MesDepo, mes_id: str) -> IsEmriDurumu:
    """baglandi → hazir: programı üretir (MES yorum satırıyla, Karar 4), SPEC 63 denetle (varsa) ile denetler,
    program / föy / takım listesi / süreyi dondurur. CamError → 422."""
    raise NotImplementedError


def iptal(d: MesDepo, mes_id: str, gerekce: str) -> IsEmriDurumu:
    """Her durumdan iptal; gerekçe boş → ValueError (uçta pydantic 422). Kayıt silinmez."""
    raise NotImplementedError


def tazele(d: MesDepo, mes_id: str) -> IsEmriDurumu:
    """Bağlı işin bugünkü programı dondurulanla aynı değilse hazir → baglandi (çıktılar geçersiz)."""
    raise NotImplementedError


def esitle(d: MesDepo, kayit_dosyasi: Path = GONDERIM_KAYDI) -> list[IsEmriDurumu]:
    """SPEC 63 kaydında programı eşleşen hazir iş emirlerini gonderildi yapar; değişenleri döndürür."""
    raise NotImplementedError


def degisenler(d: MesDepo, sonra: int) -> list[IsEmriDurumu]:
    """degisiklik > sonra olan güncel kayıtlar, degisiklik artan sırada."""
    raise NotImplementedError


def program_metni(d: MesDepo, mes_id: str) -> str:
    """Dondurulmuş program; durum hazir / gonderildi değilse MesCakisma."""
    raise NotImplementedError


def izinli_kokenler(yol: Path = AYAR_YOLU) -> list[str]:
    """CORS izinli kökenleri; dosya yoksa boş liste."""
    raise NotImplementedError
