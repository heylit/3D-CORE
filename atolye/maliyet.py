"""
SPEC 58 — Süre, maliyet ve teklif: parça başı maliyet dökümü.

Süre iş föyünden (SPEC 38 `JobSheet`) okunur, yeniden hesaplanmaz; SPEC 72 zaman profili verilirse bağlama
süresi `CycleTime.total`'dan gelir (Ek 1). Ücretler gizli veridir: `yerel_parcalar/atolye-ucretleri.json`
(repoya girmez; örnek: examples/58_atolye_ucretleri_ornek.json).

Süre s, ücret €/saat (çarpımda / 3600), kütle t, fiyat €/kg (· 1000). Kodda başka birim dönüşümü yok.
Bağımlılık (K11): yalnız stdlib, cam.model, malzeme.model, malzeme.kutuphane, atolye.is_foyu.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atolye.is_foyu import JobSheet
from cam.model import CylinderStock, MachineProfile, Stock
from malzeme.model import Malzeme, ModelError

if TYPE_CHECKING:  # SPEC 72 / 59 main'de değilken de içe aktarılabilsin diye yalnız tip
    TimeProfile = Any
    ToolWear = Any
    Operation = Any  # SPEC 72 cycle_time'ın kabul ettiği işlem (Toolpath | DrillOp)

VARSAYILAN_YOL = "yerel_parcalar/atolye-ucretleri.json"
ORNEK_YOL = "examples/58_atolye_ucretleri_ornek.json"
KALEM_ADLARI = ("tezgah", "hazirlik", "iscilik", "malzeme", "takim", "dis_islem")

__all__ = [
    "KALEM_ADLARI",
    "Kalem",
    "Maliyet",
    "ModelError",
    "Ucretler",
    "ham_hacim",
    "kademeler",
    "maliyet",
    "ucretleri_oku",
]


@dataclass(frozen=True)
class Ucretler:
    """Atölye ücret dosyasının alanları (şema 1). Adlar JSON anahtarlarıyla aynıdır.

    aciklama: örnek dosyanın ilk alanı ("UYDURMA ÖRNEK ..."); hesapta kullanılmaz.
    fire_orani: §2 malzeme kalemindeki f_fire, [0, 1); dosyada yoksa 0.
    Kurucu denetlemez (sınır dışı değer replace ile kurulabilsin); from_dict ve maliyet() denetler.
    """

    sema: int = 1
    aciklama: str = ""
    para_birimi: str = "EUR"
    iscilik_saat: float = 0.0  # U_i €/saat
    operator_orani: float = 1.0  # k_op, (0, 1]
    genel_gider: float = 0.0  # g, [0, 5]
    kar_payi: float = 0.0  # k, [0, 5]
    fire_orani: float = 0.0  # f_fire, [0, 1)
    tezgah_saat: Mapping[str, float] = field(default_factory=dict)  # MachineProfile.name → U_m €/saat
    varsayilan_sureler: Mapping[str, float] = field(default_factory=dict)  # yukle_s, hazirlik_s
    malzeme_fiyati: Mapping[str, float] = field(default_factory=dict)  # Malzeme.id → €/kg
    takim: Mapping[str, Mapping[str, float | None]] = field(default_factory=dict)  # kenar_eur, kenar_omru_dk
    kesim_payi: Mapping[str, float] = field(default_factory=dict)  # prizma_mm, testere_mm, alin_mm

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Ucretler:
        """Şema 1 sözlüğü → Ucretler; bilinmeyen alan, yanlış şema, negatif ücret → ModelError."""
        if not isinstance(d, Mapping):
            raise ModelError("Atölye ücretleri: JSON nesnesi bekleniyor")
        _anahtarlar("Atölye ücretleri", d, set(cls.__dataclass_fields__))
        if d.get("sema", 1) != 1 or isinstance(d.get("sema", 1), bool):
            raise ModelError(f"Atölye ücretleri: desteklenmeyen şema {d.get('sema')!r} (yalnız 1)")
        for ad in ("aciklama", "para_birimi"):
            if ad in d and not isinstance(d[ad], str):
                raise ModelError(f"Atölye ücretleri: '{ad}' metin olmalı ({d[ad]!r})")
        sayilar = {ad: _sayi(f"Atölye ücretleri: '{ad}'", d[ad]) for ad in _ORANLAR if ad in d}
        tezgah = _sayi_sozlugu("tezgah_saat", d.get("tezgah_saat", {}), None)
        sureler = _sayi_sozlugu(
            "varsayilan_sureler", d.get("varsayilan_sureler", {}), {"yukle_s", "hazirlik_s"}
        )
        fiyat = _sayi_sozlugu("malzeme_fiyati", d.get("malzeme_fiyati", {}), None)
        pay = _sayi_sozlugu("kesim_payi", d.get("kesim_payi", {}), {"prizma_mm", "testere_mm", "alin_mm"})
        takim_ham = d.get("takim", {})
        if not isinstance(takim_ham, Mapping):
            raise ModelError("Atölye ücretleri: 'takim' nesne olmalı")
        takim: dict[str, dict[str, float | None]] = {}
        for ad, t in takim_ham.items():
            yer = f"Atölye ücretleri: takim['{ad}']"
            if not isinstance(t, Mapping):
                raise ModelError(f"{yer} nesne olmalı")
            _anahtarlar(yer, t, {"kenar_eur", "kenar_omru_dk"})
            omur = t.get("kenar_omru_dk")
            takim[str(ad)] = {
                "kenar_eur": _sayi(f"{yer}.kenar_eur", t["kenar_eur"]) if "kenar_eur" in t else None,
                "kenar_omru_dk": None if omur is None else _sayi(f"{yer}.kenar_omru_dk", omur),
            }
        u = cls(
            sema=1,
            aciklama=d.get("aciklama", ""),
            para_birimi=d.get("para_birimi", "EUR"),
            tezgah_saat=tezgah,
            varsayilan_sureler=sureler,
            malzeme_fiyati=fiyat,
            takim=takim,
            kesim_payi=pay,
            **sayilar,
        )
        _ucret_denetle(u)
        return u

    def to_dict(self) -> dict[str, Any]:
        return {
            "aciklama": self.aciklama,
            "sema": self.sema,
            "para_birimi": self.para_birimi,
            "iscilik_saat": self.iscilik_saat,
            "operator_orani": self.operator_orani,
            "genel_gider": self.genel_gider,
            "kar_payi": self.kar_payi,
            "fire_orani": self.fire_orani,
            "tezgah_saat": dict(self.tezgah_saat),
            "varsayilan_sureler": dict(self.varsayilan_sureler),
            "malzeme_fiyati": dict(self.malzeme_fiyati),
            "takim": {ad: dict(t) for ad, t in self.takim.items()},
            "kesim_payi": dict(self.kesim_payi),
        }


_ORANLAR = ("iscilik_saat", "operator_orani", "genel_gider", "kar_payi", "fire_orani")


def _anahtarlar(yer: str, d: Mapping, izinli: set[str]) -> None:
    bilinmeyen = sorted(set(d) - izinli)
    if bilinmeyen:
        raise ModelError(f"{yer}: bilinmeyen alan {bilinmeyen}")


def _sayi(yer: str, v: Any) -> float:
    """Sonlu, negatif olmayan sayı; değilse ModelError (bool sayı sayılmaz)."""
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise ModelError(f"{yer}: sonlu sayı olmalı ({v!r})")
    if v < 0:
        raise ModelError(f"{yer}: negatif olamaz ({v!r})")
    return float(v)


def _sayi_sozlugu(ad: str, d: Any, izinli: set[str] | None) -> dict[str, float]:
    if not isinstance(d, Mapping):
        raise ModelError(f"Atölye ücretleri: '{ad}' nesne olmalı")
    if izinli is not None:
        _anahtarlar(f"Atölye ücretleri: '{ad}'", d, izinli)
    return {str(k): _sayi(f"Atölye ücretleri: {ad}['{k}']", v) for k, v in d.items()}


def _ucret_denetle(u: Ucretler) -> None:
    """Oran sınırları (K7): g, k ∈ [0, 5], k_op ∈ (0, 1], f_fire ∈ [0, 1), U_i ≥ 0."""
    _sayi("Atölye ücretleri: 'iscilik_saat'", u.iscilik_saat)
    for ad, deger in (("genel_gider", u.genel_gider), ("kar_payi", u.kar_payi)):
        if not (_sonlu(deger) and 0.0 <= deger <= 5.0):
            raise ModelError(f"Atölye ücretleri: '{ad}' [0, 5] aralığında olmalı ({deger!r})")
    if not (_sonlu(u.operator_orani) and 0.0 < u.operator_orani <= 1.0):
        k_op = u.operator_orani
        raise ModelError(f"Atölye ücretleri: 'operator_orani' (0, 1] aralığında olmalı ({k_op!r})")
    if not (_sonlu(u.fire_orani) and 0.0 <= u.fire_orani < 1.0):
        raise ModelError(f"Atölye ücretleri: 'fire_orani' [0, 1) aralığında olmalı ({u.fire_orani!r})")


def _sonlu(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, int | float) and math.isfinite(v)


def ucretleri_oku(yol: str | Path = VARSAYILAN_YOL) -> Ucretler:
    """Ücret dosyasını okur. Dosya yoksa ModelError:
    "Atölye ücret dosyası yok: <yol>. Örnek: examples/58_atolye_ucretleri_ornek.json"."""
    yol = Path(yol)
    if not yol.is_file():
        raise ModelError(f"Atölye ücret dosyası yok: {yol}. Örnek: {ORNEK_YOL}")
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ModelError(f"Atölye ücret dosyası okunamadı: {yol} ({e})") from e
    return Ucretler.from_dict(veri)


@dataclass(frozen=True)
class Kalem:
    ad: str  # KALEM_ADLARI'ndan biri
    aciklama: str  # formül + girdiler, okunur metin
    tutar_eur: float  # parça başı


@dataclass(frozen=True)
class Maliyet:
    n: int
    t_parca_s: float
    kalemler: tuple[Kalem, ...]
    ara_toplam_eur: float  # M = Σ kalem
    fiyat_eur: float  # parça başı, M · (1 + g) · (1 + k)
    uyarilar: tuple[str, ...]


def _s(x: float) -> str:
    """Açıklamadaki sayı: tam gidiş-dönüş gösterimi (repr)."""
    return repr(float(x))


def _pay(u: Ucretler, ad: str) -> float:
    return float(u.kesim_payi.get(ad, 0.0))


def ham_hacim(stok: Stock | CylinderStock, u: Ucretler) -> float:
    """Ham malzeme hacmi [mm³] (§3): prizma (Lx+2p)(Ly+2p)(Lz+2p); çubuk π(D/2)²(L + p_testere + p_alin)."""
    if isinstance(stok, Stock):
        p = _pay(u, "prizma_mm")
        Lx, Ly, Lz = (float(v) for v in stok.size)
        return (Lx + 2 * p) * (Ly + 2 * p) * (Lz + 2 * p)
    if isinstance(stok, CylinderStock):
        L = stok.length + _pay(u, "testere_mm") + _pay(u, "alin_mm")
        return math.pi * (stok.D / 2) ** 2 * L
    raise ModelError(f"Ham malzeme türü desteklenmiyor: {type(stok).__name__} (Stock, CylinderStock)")


def _adet(n: Any) -> int:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ModelError(f"Adet tam sayı olmalı (n={n!r})")
    if n < 1:
        raise ModelError(f"Adet en az 1 olmalı (n={n})")
    return n


def _bagalama_sureleri(
    job: JobSheet, u: Ucretler, sureler: Sequence[tuple[float, float]] | None
) -> list[tuple[float, float]]:
    """Bağlama başına (t_yukle, t_hazirlik) [s]."""
    B = len(job.setups)
    if sureler is None:
        eksik = [ad for ad in ("yukle_s", "hazirlik_s") if ad not in u.varsayilan_sureler]
        if eksik:
            raise ModelError(f"Varsayılan süre yok: {VARSAYILAN_YOL} → varsayilan_sureler.{eksik[0]}")
        sureler = [(u.varsayilan_sureler["yukle_s"], u.varsayilan_sureler["hazirlik_s"])] * B
    sureler = list(sureler)
    if len(sureler) != B:
        raise ModelError(f"sureler bağlama sayısı kadar olmalı ({len(sureler)} ≠ {B})")
    return [
        (_sayi(f"Bağlama {i + 1} yükleme süresi", y), _sayi(f"Bağlama {i + 1} hazırlık süresi", h))
        for i, (y, h) in enumerate(sureler)
    ]


def _tezgah_ucreti(u: Ucretler, prof: MachineProfile) -> float:
    if prof.name not in u.tezgah_saat:
        raise ModelError(f"Tezgâh '{prof.name}' için saat ücreti yok: {VARSAYILAN_YOL} → tezgah_saat")
    return float(u.tezgah_saat[prof.name])


def _malzeme_fiyati(malzeme: Malzeme, u: Ucretler) -> tuple[float, str]:
    """€/kg ve kaynağı: yerel malzeme_fiyati önce, sonra Malzeme.fiyat (SPEC 66 D7: yerleşikte boş)."""
    if malzeme.id in u.malzeme_fiyati:
        return float(u.malzeme_fiyati[malzeme.id]), "yerel dosya"
    if malzeme.fiyat is not None:
        return float(malzeme.fiyat), "malzeme kaydı"
    raise ModelError(
        f"Malzeme {malzeme.id} ({malzeme.name}) için fiyat yok: {VARSAYILAN_YOL} → malzeme_fiyati"
    )


def _takim_kalemi(job: JobSheet, u: Ucretler, asinma: Sequence[ToolWear] | None) -> Kalem:
    """Takım payı: aşınma listesinde olan takım c_kenar · D (SPEC 59, Ek 2), olmayan t_kesme / T_omur (§4)."""
    D_harita: dict[int, float] = {}
    for w in asinma or ():
        D_harita[int(w.tool_id)] = D_harita.get(int(w.tool_id), 0.0) + _sayi("ToolWear.D", w.D)
    satirlar: dict[tuple[int, str], float] = {}  # (T, ad) → toplam kesme süresi [s]
    for b in job.setups:
        for r in b.tools:
            satirlar[(r.T, r.name)] = satirlar.get((r.T, r.name), 0.0) + float(r.time)
    tutar, parcalar = 0.0, []
    for (T, ad), t_s in satirlar.items():
        if T not in D_harita and t_s <= 0.0:
            continue
        veri = u.takim.get(ad)
        if veri is None or veri.get("kenar_eur") is None:
            raise ModelError(f"Takım '{ad}' için kenar fiyatı yok: {VARSAYILAN_YOL} → takim.{ad}.kenar_eur")
        c = float(veri["kenar_eur"])
        if T in D_harita:
            D = D_harita[T]
            tutar += c * D
            parcalar.append(f"T{T} '{ad}': takım: SPEC 59 Miner D; c_kenar · D = {_s(c)} € · {_s(D)}")
            continue
        omur = veri.get("kenar_omru_dk")
        if omur is None or omur <= 0:
            raise ModelError(f"Takım '{ad}' için ömür yok: {VARSAYILAN_YOL} → takim.{ad}.kenar_omru_dk")
        t_dk = t_s / 60.0
        tutar += c * t_dk / float(omur)
        parcalar.append(
            f"T{T} '{ad}': takım: kenar ömrü (yerel dosya); c_kenar · t_kesme / T_omur = "
            f"{_s(c)} € · {_s(t_dk)} dk / {_s(omur)} dk"
        )
    aciklama = "Σ_takım c_kenar · t_kesme / T_omur; " + ("; ".join(parcalar) if parcalar else "kesme yok")
    return Kalem("takim", aciklama, tutar)


def _cevrim_suresi(
    tezgah: str, prof: TimeProfile, ops: Sequence[Sequence[Operation]] | None, i: int, t_yukle: float
) -> float:
    """Ek 1: SPEC 72 cycle_time(ops_b, prof_b, setup_time=t_yukle).total (k kalibrasyonu dahil)."""
    if ops is None:
        raise ModelError(f"Tezgâh '{tezgah}' için SPEC 72 zaman profili verildi ama ops (işlemler) yok")
    try:
        from cam.sim.cevrim import cycle_time  # K11: izinli; 72 main'de değilse yok
    except ImportError as e:
        raise ModelError(f"Tezgâh '{tezgah}': zaman profili verildi ama SPEC 72 (cam.sim.cevrim) yok") from e
    return _sayi(f"Bağlama {i + 1} çevrim süresi", cycle_time(list(ops[i]), prof, setup_time=t_yukle).total)


def maliyet(
    job: JobSheet,
    profiller: Sequence[MachineProfile],
    stok: Stock | CylinderStock,
    malzeme: Malzeme,
    u: Ucretler,
    n: int,
    sureler: Sequence[tuple[float, float]] | None = None,
    dis_islem: Sequence[tuple[str, float]] = (),
    zaman_profilleri: Mapping[str, TimeProfile] | None = None,
    asinma: Sequence[ToolWear] | None = None,
    *,
    ops: Sequence[Sequence[Operation]] | None = None,
) -> Maliyet:
    """n adetlik partide parça başı maliyet (§1, §2; Ek 1–3).

    profiller: bağlama başına tezgâh (len = len(job.setups)). sureler: bağlama başına (yukle_s, hazirlik_s);
    None → u.varsayilan_sureler. dis_islem: (ad, € / parça). zaman_profilleri: tezgâh adı → SPEC 72 profili.
    asinma: SPEC 59 ToolWear listesi (takım payı c_kenar · D). ops: bağlama başına işlem listesi; bağlamanın
    tezgâhının profili de varsa t_isleme + t_yukle = cycle_time(ops_b, prof_b, setup_time=t_yukle).total.
    """
    n = _adet(n)
    _ucret_denetle(u)
    profiller = list(profiller)
    B = len(job.setups)
    if B == 0:
        raise ModelError("İş föyünde bağlama yok")
    if len(profiller) != B:
        raise ModelError(f"profiller bağlama sayısı kadar olmalı ({len(profiller)} ≠ {B})")
    yh = _bagalama_sureleri(job, u, sureler)
    if ops is not None and len(ops) != B:
        raise ModelError(f"ops bağlama sayısı kadar olmalı ({len(ops)} ≠ {B})")
    U_i, k_op = float(u.iscilik_saat), float(u.operator_orani)

    uyarilar: list[str] = []
    t_seri = t_haz = 0.0  # Σ (t_isleme + t_yukle), Σ t_hazirlik
    tezgah = hazirlik = iscilik = 0.0
    tz_metin, hz_metin, kaynaklar = [], [], set()
    for i, (b, prof, (t_yukle, t_hazirlik)) in enumerate(zip(job.setups, profiller, yh, strict=True)):
        U_m = _tezgah_ucreti(u, prof)
        if zaman_profilleri is not None and prof.name in zaman_profilleri:
            t = _cevrim_suresi(prof.name, zaman_profilleri[prof.name], ops, i, t_yukle)
            t_isleme = t - t_yukle
            kaynaklar.add("SPEC 72 CycleTime")
        else:
            uyarilar.append(f"Süre SPEC 05 modelinden (72 zaman profili yok: {prof.name})")
            t_isleme = float(b.time)
            t = t_isleme + t_yukle
            kaynaklar.add("SPEC 05 (iş föyü)")
        t_seri += t
        t_haz += t_hazirlik
        tezgah += t * U_m / 3600.0
        hazirlik += t_hazirlik * (U_m + U_i) / 3600.0 / n
        iscilik += t * U_i * k_op / 3600.0
        tz_metin.append(
            f"b{b.index} {prof.name}: ({_s(t_isleme)} s + {_s(t_yukle)} s) · {_s(U_m)} €/saat / 3600"
        )
        hz_metin.append(
            f"b{b.index} {prof.name}: {_s(t_hazirlik)} s · ({_s(U_m)} + {_s(U_i)}) €/saat / 3600 / {n}"
        )

    rho = malzeme.rho
    if rho is None:
        raise ModelError(f"Malzeme {malzeme.id} ({malzeme.name}) için yoğunluk (rho) yok")
    V = ham_hacim(stok, u)
    m_ham = float(rho) * V  # t
    fiyat_kg, kaynak = _malzeme_fiyati(malzeme, u)
    f = float(u.fire_orani)
    malz = fiyat_kg * 1000.0 * m_ham * (1.0 + f)

    dis_tutar, dis_metin = 0.0, []
    for ad, c in dis_islem:
        c = _sayi(f"Dış işlem '{ad}'", c)
        dis_tutar += c
        dis_metin.append(f"{ad}: {_s(c)} €")

    kalemler = (
        Kalem(
            "tezgah",
            f"süre: {' + '.join(sorted(kaynaklar))}; Σ_b (t_isleme + t_yukle) · U_m / 3600; "
            + "; ".join(tz_metin),
            tezgah,
        ),
        Kalem("hazirlik", "Σ_b t_hazirlik · (U_m + U_i) / 3600 / n; " + "; ".join(hz_metin), hazirlik),
        Kalem(
            "iscilik",
            f"Σ_b (t_isleme + t_yukle) · U_i · k_op / 3600 = "
            f"{_s(t_seri)} s · {_s(U_i)} €/saat · {_s(k_op)} / 3600",
            iscilik,
        ),
        Kalem(
            "malzeme",
            f"fiyat · 1000 · ρ · V_ham · (1 + f_fire) = {_s(fiyat_kg)} €/kg ({kaynak}) · 1000"
            f" · {_s(float(rho))} t/mm³ · {_s(V)} mm³ · (1 + {_s(f)});"
            f" m_ham = {_s(m_ham)} t ({malzeme.id} {malzeme.name})",
            malz,
        ),
        _takim_kalemi(job, u, asinma),
        Kalem("dis_islem", "Σ c_dis; " + ("; ".join(dis_metin) if dis_metin else "yok"), dis_tutar),
    )
    M = sum(k.tutar_eur for k in kalemler)
    fiyat = M * (1.0 + float(u.genel_gider)) * (1.0 + float(u.kar_payi))
    return Maliyet(
        n=n,
        t_parca_s=t_seri + t_haz / n,
        kalemler=kalemler,
        ara_toplam_eur=M,
        fiyat_eur=fiyat,
        uyarilar=tuple(uyarilar),
    )


def kademeler(
    job: JobSheet,
    profiller: Sequence[MachineProfile],
    stok: Stock | CylinderStock,
    malzeme: Malzeme,
    u: Ucretler,
    adetler: Sequence[int] = (1, 10, 50, 200),
    sureler: Sequence[tuple[float, float]] | None = None,
    dis_islem: Sequence[tuple[str, float]] = (),
    zaman_profilleri: Mapping[str, TimeProfile] | None = None,
    asinma: Sequence[ToolWear] | None = None,
    *,
    ops: Sequence[Sequence[Operation]] | None = None,
) -> list[Maliyet]:
    """Her adet için maliyet(...) baştan hesaplanır (§5); satırlar birbirinden türetilmez."""
    adetler = list(adetler)
    if not adetler:
        raise ModelError("Kademe listesi boş")
    return [
        maliyet(job, profiller, stok, malzeme, u, n, sureler, dis_islem, zaman_profilleri, asinma, ops=ops)
        for n in adetler
    ]
