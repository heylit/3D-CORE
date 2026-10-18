"""
SPEC 61 — Tasarım için imalat (DFM) denetimi.

Model değiştiği anda işlenemeyecek ya da zor işlenecek yerleri bulur: iç köşe, derin dar cep, delik,
erişilemeyen yüz, ince duvar, torna kanalı / iç çap / köşe. CAM yolu üretmez; geometriye, takım kütüphanesine
ve izin verilen takım yönlerine bakar. Her bulgu ölçülen değeri, sınırı ve öneriyi sayıyla söyler.

Kural dosyası (`atolye/dfm_kurallari.json`): `{grup: {anahtar: {"deger": float, "kaynak": str}}}`.
Yerel ezme dosyası aynı biçimde, değer yalın sayı: `{"ince_duvar": {"aluminyum": 0.5}}`.
`kurallari_oku` her yaprağı `{"deger", "kaynak", "yerel"}` olarak döndürür; ezilen yaprakta `yerel = True`.
Bulgunun sınırı ezilmiş bir kuraldan geliyorsa `Bulgu.kural` "grup.anahtar (yerel)" olur,
değilse "grup.anahtar".
Yerel dosyada bilinmeyen grup ya da anahtar → `CamError`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cam.model import ToolLibrary
    from geometry.part import Part

DERECELER = ("hata", "uyari", "bilgi")
TURLER = (
    "ic_kose",
    "derin_cep",
    "delik",
    "erisilemez",
    "ince_duvar",
    "torna_kanal",
    "torna_ic_cap",
    "torna_kose",
)
KURAL_DOSYASI = Path(__file__).with_name("dfm_kurallari.json")


@dataclass(frozen=True)
class Bulgu:
    """Tek DFM bulgusu: bir yüze ya da noktaya bağlı, sayılı mesaj ve öneri."""

    tur: str
    derece: str
    yuzler: tuple[int, ...]  # Part yüz indisleri (Tezgah vurgusu); boş olabilir
    nokta: tuple[float, float, float] | None
    olculen: float
    sinir: float
    mesaj: str  # Türkçe, sayılı
    oneri: str  # Türkçe, sayılı; yoksa ""
    kural: str  # kural dosyasındaki anahtar ("grup.anahtar", ezilmişse sonuna " (yerel)")


@dataclass(frozen=True)
class Rapor:
    """Denetim sonucu: bulgular derece (hata → bilgi), sonra tur, sonra ilk yüz indisine göre sıralı."""

    bulgular: tuple[Bulgu, ...]
    tamam: bool  # bütçe aşıldıysa False ("kısmi" uyarısıyla)
    sure_s: float


def kurallari_oku(yerel: str | Path | None = "yerel_parcalar/dfm-kurallari.json") -> dict:
    """Repodaki kural dosyası + (varsa) yerel ezme dosyası. Yerel dosya yoksa yalnız repodaki kurallar."""
    raise NotImplementedError("SPEC 61: kurallari_oku")


def denetle(
    part: Part,
    lib: ToolLibrary,
    yonler: Sequence[tuple[float, float, float]] = ((0, 0, 1),),
    malzeme_grubu: str | None = None,
    kurallar: dict | None = None,
    butce_s: float | None = 1.0,
) -> Rapor:
    """Parçayı DFM kurallarıyla denetler. malzeme_grubu None ise ince duvar için en sıkı sınır kullanılır."""
    raise NotImplementedError("SPEC 61: denetle")
