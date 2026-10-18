"""
SPEC 64 §2–§3 — MES API'sinin pydantic modelleri; /api/openapi.json'daki bileşen şemaları buradan çıkar.

Alan adları ASCII Türkçe snake_case (MES tarafında TypeScript'e olduğu gibi geçer). v1 içinde yalnız ekleme
yapılır (yeni isteğe bağlı alan); silme, ad ya da tür değişikliği v2'dir.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# mes_id: yol parametresi ve programdaki ASCII yorum satırı ("MES <mes_id> REV <revizyon>") için güvenli küme.
MES_ID_DESENI = r"^[A-Za-z0-9_.-]{1,40}$"

Durum = Literal["alindi", "baglandi", "hazir", "gonderildi", "iptal"]


class IsEmri(BaseModel):
    """MES'in verdiği iş emri (§2). Bilinmeyen alan → 422."""

    model_config = ConfigDict(extra="forbid")

    mes_id: str = Field(pattern=MES_ID_DESENI)
    revizyon: int = Field(ge=1)
    parca_no: str
    parca_rev: str
    adet: int = Field(ge=1)
    malzeme_id: str | None = None
    tezgah: str | None = None  # MachineProfile.name
    termin: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")  # "YYYY-AA-GG"
    notlar: str = ""
    proje: str | None = None  # .3dc yolu (Tezgah'ın gördüğü yerel yol)

    @field_validator("termin")
    @classmethod
    def _gercek_tarih(cls, v: str | None) -> str | None:
        if v is not None:
            dt.date.fromisoformat(v)  # 2026-02-30 gibi geçersiz tarih → ValueError → 422
        return v


class Ciktilar(BaseModel):
    """`hazir` anında dondurulan çıktıların sha256 özetleri."""

    program_ozeti: str
    foy_ozeti: str


class IsEmriDurumu(BaseModel):
    is_emri: IsEmri
    durum: Durum
    is_adi: str | None = None  # bağlı Tezgah işi (depo adı)
    ciktilar: Ciktilar | None = None
    degisiklik: int  # tekdüze artan değişiklik sırası (§4)
    uyarilar: list[str] = []


class IptalIstek(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gerekce: str = Field(min_length=1)


class Saglik(BaseModel):
    api: Literal["v1"] = "v1"
    tezgah_surum: str
    sema_ozeti: str  # docs/mes-openapi-v1.json'ın sha256'sı


class Takim(BaseModel):
    """SPEC 38 ToolRow'dan bir satır."""

    t_no: int
    ad: str
    tur: str
    D: float  # mm
    boy: float  # mm
    tutucu: str
    sure_s: float  # s


class Sure(BaseModel):
    """SPEC 58 §1 parça başı süre (n = adet)."""

    t_isleme_s: float
    t_yukle_s: float
    t_hazirlik_s: float
    t_parca_s: float


class Kalem(BaseModel):
    """SPEC 58 Kalem."""

    ad: str  # "tezgah" | "hazirlik" | "iscilik" | "malzeme" | "takim" | "dis_islem"
    aciklama: str
    tutar_eur: float


class Maliyet(BaseModel):
    """SPEC 58 Maliyet (n = adet)."""

    n: int
    t_parca_s: float
    kalemler: list[Kalem]
    ara_toplam_eur: float
    fiyat_eur: float  # parça başı, genel gider ve kâr dahil
    uyarilar: list[str]


class GonderimProfil(BaseModel):
    model_config = ConfigDict(extra="allow")

    ad: str
    ozet: str


class GonderimProgram(BaseModel):
    model_config = ConfigDict(extra="allow")

    ad: str
    ozet: str  # program metninin sha256'sı; iş emrinin ciktilar.program_ozeti ile eşleşir
    lehce: str
    program_no: int | None = None


class GonderimKaydi(BaseModel):
    """SPEC 63 §5 gönderim kaydı + mes_id + sira (63'ün kaydı büyüyebilir: ek alanlara izin verilir)."""

    model_config = ConfigDict(extra="allow")

    sira: int  # gönderim kaydı dosyasındaki satır sırası (1'den); ?sonra= bununla süzülür
    mes_id: str | None  # program özeti bir iş emrinin dondurulmuş programıyla eşleşiyorsa o iş emri
    zaman: str
    operator: str
    profil: GonderimProfil
    program: GonderimProgram
    hedef: str
    sonuc: str  # "yazildi" | "ayni" | "ezildi"


ONEK = "/api/mes/v1/"


def _basvurular(x, bulunan: set[str]) -> None:
    if isinstance(x, dict):
        ref = x.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            bulunan.add(ref.rsplit("/", 1)[1])
        for v in x.values():
            _basvurular(v, bulunan)
    elif isinstance(x, list):
        for v in x:
            _basvurular(v, bulunan)


def alt_sema(openapi: dict) -> dict:
    """OpenAPI belgesinden /api/mes/v1/ yolları ve onların (dolaylı da) başvurduğu bileşen şemaları (§1).

    docs/mes-openapi-v1.json bu fonksiyonun çıktısıdır (kanonik JSON: sort_keys, indent 2, sonda satır sonu).
    """
    yollar = {k: v for k, v in openapi.get("paths", {}).items() if k.startswith(ONEK)}
    semalar = openapi.get("components", {}).get("schemas", {})
    gerekli: set[str] = set()
    _basvurular(yollar, gerekli)
    bekleyen = list(gerekli)
    while bekleyen:
        ad = bekleyen.pop()
        yeni: set[str] = set()
        _basvurular(semalar.get(ad, {}), yeni)
        for y in yeni - gerekli:
            gerekli.add(y)
            bekleyen.append(y)
    return {
        "paths": yollar,
        "components": {"schemas": {k: semalar[k] for k in sorted(gerekli) if k in semalar}},
    }
