"""
SPEC 65b — Tezgah'ta gerçekçi malzeme görünümü (PBR): ön ayar tablosu ve çözümleme. Saf Python.

Görünüm verisi fiziksel ölçüm değil, görsel ön ayardır; B2 malzeme kaydına girmez. Yerleşik tablo
`tezgah/gorunum.json`'dadır; kullanıcı tablosu anahtar bazında onu ezer. Anahtarlar:
    "grup:<GRUPLAR üyesi>", "id:<Malzeme.id>", "bitim:<BITIMLER üyesi>"

Çözümleme sırası (ilk bulunan kazanır, bitim en son uygulanır):
    1. yüz bitimi  2. bileşen geçersiz kılma  3. malzeme id ön ayarı  4. malzeme grubu ön ayarı
    5. varsayılan gri
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.model import ModelError

if TYPE_CHECKING:
    from malzeme.model import Malzeme

__all__ = ["BITIMLER", "Gorunum", "ModelError", "bitim_uygula", "coz", "montaj_gorunumu", "on_ayarlar"]

BITIMLER = ("ham", "frezelenmis", "taslanmis", "parlatilmis", "eloksal", "boyali", "kumlanmis")

YERLESIK = Path(__file__).with_name("gorunum.json")


@dataclass(frozen=True)
class Gorunum:
    """three.js MeshPhysicalMaterial parametreleri (metal/pürüzlülük iş akışı)."""

    renk: str  # "#rrggbb"
    metalness: float  # [0, 1]
    roughness: float  # [0, 1]
    clearcoat: float = 0.0  # [0, 1]
    anisotropy: float = 0.0  # [0, 1]

    def __post_init__(self) -> None:
        """Renk 7 karakterli onaltılık, sayılar sonlu ve [0, 1] içinde; değilse ModelError."""
        raise NotImplementedError("SPEC 65b: Gorunum doğrulaması")

    def to_dict(self) -> dict:
        """{"renk", "metalness", "roughness", "clearcoat", "anisotropy"}; JSON'a doğrudan uygun."""
        raise NotImplementedError("SPEC 65b: Gorunum.to_dict")


def on_ayarlar(yol: Path | None = None) -> Mapping[str, Gorunum]:
    """Yerleşik tablo; yol verilirse o JSON yerleşiği anahtar bazında ezer (eksik anahtarlar yerleşikten).

    Bozuk dosya, bilinmeyen anahtar biçimi veya aralık dışı değer → ModelError.
    """
    raise NotImplementedError("SPEC 65b: on_ayarlar")


def bitim_uygula(temel: Gorunum, bitim: str) -> Gorunum:
    """Bitimi temel görünüme uygular (belirlenimci). Bilinmeyen bitim → ModelError.

    ham: roughness 0.6; frezelenmis 0.35 + anizotropi 0.3; taslanmis 0.2 + anizotropi 0.6; parlatilmis 0.05;
    eloksal: metalness 0.6, clearcoat 1, renk eloksal rengi; boyali: metalness 0, clearcoat 0.5;
    kumlanmis 0.8.
    """
    raise NotImplementedError("SPEC 65b: bitim_uygula")


def coz(
    malzeme: Malzeme | None,
    bitim: str | None = None,
    gecersiz: Gorunum | None = None,
    *,
    tablo: Mapping[str, Gorunum] | None = None,
) -> Gorunum:
    """Çözümleme sırasıyla görünüm. tablo yoksa on_ayarlar(). Bilinmeyen bitim → ModelError."""
    raise NotImplementedError("SPEC 65b: coz")


def montaj_gorunumu(montaj: dict, tablo: Mapping[str, Gorunum] | None = None) -> dict:
    """GET /api/gorunum gövdesi: {bileşen adı: {"gorunum": {...}, "yuzler": {FaceRef: {...}}}}.

    montaj: proje montaj sözlüğü; bileşenlerde "material" ve isteğe bağlı
    "gorunum": {"bitim": {FaceRef: bitim}}.
    Malzeme id'si kayıtta yoksa ModelError.
    """
    raise NotImplementedError("SPEC 65b: montaj_gorunumu")
