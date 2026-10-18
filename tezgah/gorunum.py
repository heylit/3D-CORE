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

import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from core.model import ModelError
from malzeme.model import GRUPLAR

if TYPE_CHECKING:
    from malzeme.model import Malzeme

__all__ = ["BITIMLER", "Gorunum", "ModelError", "bitim_uygula", "coz", "montaj_gorunumu", "on_ayarlar"]

BITIMLER = ("ham", "frezelenmis", "taslanmis", "parlatilmis", "eloksal", "boyali", "kumlanmis")

YERLESIK = Path(__file__).with_name("gorunum.json")

_RENK = re.compile(r"#[0-9a-fA-F]{6}")
_ANAHTAR = re.compile(r"(grup|id|bitim):\S+")
# Malzemesi atanmamış ya da ön ayarı olmayan bileşenin görünümü.
# Tablodan gelmez: anahtarlar yalnız grup:/id:/bitim:.
_GRI = {"renk": "#a0a0a0", "metalness": 0.0, "roughness": 0.6}


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
        if not isinstance(self.renk, str) or not _RENK.fullmatch(self.renk):
            raise ModelError(f"Görünüm rengi '#rrggbb' olmalı ({self.renk!r})")
        for ad in ("metalness", "roughness", "clearcoat", "anisotropy"):
            v = getattr(self, ad)
            sayi = isinstance(v, int | float) and not isinstance(v, bool)
            if not (sayi and math.isfinite(v) and 0.0 <= v <= 1.0):
                raise ModelError(f"Görünüm {ad} [0, 1] içinde sonlu bir sayı olmalı ({v!r})")
            object.__setattr__(self, ad, float(v))

    def to_dict(self) -> dict:
        """{"renk", "metalness", "roughness", "clearcoat", "anisotropy"}; JSON'a doğrudan uygun."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping) -> Gorunum:
        """Sözlükten görünüm; eksik zorunlu / bilinmeyen alan → ModelError."""
        if not isinstance(d, Mapping):
            raise ModelError(f"Görünüm bir sözlük olmalı ({type(d).__name__})")
        try:
            return cls(**d)
        except TypeError as e:
            raise ModelError(f"Görünüm okunamadı: {e}") from e


def on_ayarlar(yol: Path | None = None) -> Mapping[str, Gorunum]:
    """Yerleşik tablo; yol verilirse o JSON yerleşiği anahtar bazında ezer (eksik anahtarlar yerleşikten).

    Bozuk dosya, bilinmeyen anahtar biçimi veya aralık dışı değer → ModelError.
    """
    tablo = _tablo_oku(YERLESIK)
    if yol is not None:
        tablo.update(_tablo_oku(Path(yol)))
    return MappingProxyType(tablo)


def _tablo_oku(yol: Path) -> dict[str, Gorunum]:
    """JSON ön ayar dosyası → {anahtar: Gorunum}. "_" ile başlayan anahtarlar açıklamadır, atlanır."""
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ModelError(f"Görünüm tablosu okunamadı: {yol} ({e})") from e
    if not isinstance(ham, dict):
        raise ModelError(f"Görünüm tablosu bir JSON nesnesi olmalı: {yol}")
    tablo: dict[str, Gorunum] = {}
    for anahtar, deger in ham.items():
        if anahtar.startswith("_"):
            continue
        if not _ANAHTAR.fullmatch(anahtar):
            raise ModelError(f"Görünüm tablosunda geçersiz anahtar {anahtar!r} (grup:/id:/bitim:)")
        if anahtar.startswith("grup:") and anahtar[5:] not in GRUPLAR:
            raise ModelError(f"Görünüm tablosunda bilinmeyen malzeme grubu {anahtar!r}")
        if anahtar.startswith("bitim:") and anahtar[6:] not in BITIMLER:
            raise ModelError(f"Görünüm tablosunda bilinmeyen bitim {anahtar!r}")
        tablo[anahtar] = Gorunum.from_dict(deger)
    return tablo


def bitim_uygula(temel: Gorunum, bitim: str, *, tablo: Mapping[str, Gorunum] | None = None) -> Gorunum:
    """Bitimi temel görünüme uygular (belirlenimci). Bilinmeyen bitim → ModelError.

    ham: roughness 0.6; frezelenmis 0.35 + anizotropi 0.3; taslanmis 0.2 + anizotropi 0.6; parlatilmis 0.05;
    eloksal: metalness 0.6, clearcoat 1, renk eloksal rengi; boyali: metalness 0, clearcoat 0.5;
    kumlanmis 0.8.
    Eloksal rengi tablonun "bitim:eloksal" kaydından gelir (tablo yoksa on_ayarlar()).
    """
    if bitim not in BITIMLER:
        raise ModelError(f"Bilinmeyen yüzey bitimi {bitim!r}; geçerli: {', '.join(BITIMLER)}")
    if bitim == "ham":
        return replace(temel, roughness=0.6, anisotropy=0.0)
    if bitim == "frezelenmis":
        return replace(temel, roughness=0.35, anisotropy=0.3)
    if bitim == "taslanmis":
        return replace(temel, roughness=0.2, anisotropy=0.6)
    if bitim == "parlatilmis":
        return replace(temel, roughness=0.05, anisotropy=0.0)
    if bitim == "kumlanmis":
        return replace(temel, roughness=0.8, anisotropy=0.0)
    if bitim == "boyali":
        return replace(temel, metalness=0.0, clearcoat=0.5, anisotropy=0.0)
    t = on_ayarlar() if tablo is None else tablo
    renk = t["bitim:eloksal"].renk if "bitim:eloksal" in t else temel.renk
    return replace(temel, renk=renk, metalness=0.6, clearcoat=1.0, anisotropy=0.0)


def coz(
    malzeme: Malzeme | None,
    bitim: str | None = None,
    gecersiz: Gorunum | None = None,
    *,
    tablo: Mapping[str, Gorunum] | None = None,
) -> Gorunum:
    """Çözümleme sırasıyla görünüm. tablo yoksa on_ayarlar(). Bilinmeyen bitim → ModelError."""
    if bitim is not None and bitim not in BITIMLER:
        raise ModelError(f"Bilinmeyen yüzey bitimi {bitim!r}; geçerli: {', '.join(BITIMLER)}")
    t = on_ayarlar() if tablo is None else tablo
    if gecersiz is not None:
        temel = gecersiz
    elif malzeme is not None and f"id:{malzeme.id}" in t:
        temel = t[f"id:{malzeme.id}"]
    elif malzeme is not None and f"grup:{malzeme.grup}" in t:
        temel = t[f"grup:{malzeme.grup}"]
    else:
        temel = Gorunum(**_GRI)
    if bitim is None:
        return temel
    # tabloda o bitimin kaydı yoksa yerleşik bitim (ör. eloksal rengi) geçerlidir
    return bitim_uygula(temel, bitim, tablo=t if f"bitim:{bitim}" in t else None)


class _IdMalzeme:
    """Kayıt (66) yokken yalnız id'si bilinen malzeme: id ön ayarı varsa o, yoksa grup bilinmez."""

    def __init__(self, id: str) -> None:  # noqa: A002 - Malzeme.id ile aynı ad
        self.id = id
        self.grup = None


def montaj_gorunumu(
    montaj: dict,
    tablo: Mapping[str, Gorunum] | None = None,
    *,
    malzemeler: Mapping[str, Malzeme] | None = None,
) -> dict:
    """GET /api/gorunum gövdesi: {bileşen adı: {"gorunum": {...}, "yuzler": {FaceRef: {...}}}}.

    montaj: proje montaj sözlüğü (assy.model.Assembly.to_dict biçimi); bileşenlerde "material" ve isteğe
    bağlı "gorunum": {"gecersiz": {Gorunum}, "bitim": {FaceRef: bitim}}.
    malzemeler: malzeme kaydı (id → Malzeme); verilmezse SPEC 66 kütüphanesi (malzeme.kutuphane).
    Kayıtta olmayan id için tabloda "id:<id>" ön ayarı yoksa ModelError (grup bilinmeden görünüm
    çözülemez; sessiz gri yok).
    """
    t = on_ayarlar() if tablo is None else tablo
    if not isinstance(montaj, Mapping) or not isinstance(montaj.get("components", []), list):
        raise ModelError("Montaj sözlüğünde 'components' listesi yok")
    sonuc: dict[str, dict] = {}
    for c in montaj.get("components", []):
        if not isinstance(c, Mapping) or not isinstance(c.get("name"), str):
            raise ModelError(f"Montaj bileşeni okunamadı: {c!r}")
        ad = c["name"]
        malzeme = _malzeme_bul(ad, c.get("material"), t, malzemeler)
        g = c.get("gorunum") or {}
        if not isinstance(g, Mapping) or set(g) - {"gecersiz", "bitim"}:
            raise ModelError(f"Bileşen {ad!r}: 'gorunum' yalnız 'gecersiz' ve 'bitim' alanlarını alır")
        gecersiz = Gorunum.from_dict(g["gecersiz"]) if g.get("gecersiz") is not None else None
        bitimler = g.get("bitim") or {}
        if not isinstance(bitimler, Mapping):
            raise ModelError(f"Bileşen {ad!r}: 'gorunum.bitim' FaceRef → bitim sözlüğü olmalı")
        sonuc[ad] = {
            "gorunum": coz(malzeme, None, gecersiz, tablo=t).to_dict(),
            "yuzler": {str(ref): coz(malzeme, b, gecersiz, tablo=t).to_dict() for ref, b in bitimler.items()},
        }
    return sonuc


def _malzeme_bul(ad: str, mid, tablo: Mapping[str, Gorunum], malzemeler: Mapping | None):
    """Bileşenin malzemesi: kayıttan, yoksa yalnız id ön ayarı varsa id'den; atanmamış → None."""
    if mid is None:
        return None
    m = _kayittan(mid, malzemeler)
    if m is not None:
        return m
    if f"id:{mid}" in tablo:
        return _IdMalzeme(mid)
    raise ModelError(f"Bileşen {ad!r}: malzeme {mid!r} kayıtta yok ve görünüm ön ayarı tanımsız")


def _kayittan(mid: str, malzemeler: Mapping | None):
    """Malzeme kaydından id; kayıt verilmediyse SPEC 66 kütüphanesi (henüz yoksa None)."""
    if malzemeler is not None:
        return malzemeler.get(mid)
    try:
        from malzeme.kutuphane import kutuphane
    except ImportError:
        return None
    try:
        return kutuphane().get(mid)
    except (KeyError, ModelError):
        return None
