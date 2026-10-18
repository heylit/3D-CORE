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

import hashlib
import importlib.util
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from core.model import ModelError
from tezgah.mes.sema import Ciktilar, IsEmri, IsEmriDurumu, Takim

DURUMLAR = ("alindi", "baglandi", "hazir", "gonderildi", "iptal")
SEMA = 1  # depo dosyası biçimi

# Çalışma klasörüne göre (Tezgah kullanıcı klasöründe çalışır; testler monkeypatch.chdir(tmp_path) ile).
DEPO_YOLU = Path("yerel_parcalar/mes/is-emirleri.json")
AYAR_YOLU = Path("yerel_parcalar/mes/ayar.json")  # {"izinli_kokenler": [str]} (CORS, §6)
GONDERIM_KAYDI = Path("yerel_parcalar/gonderim-kaydi.jsonl")  # SPEC 63 §5

# Uçlar ve depo işlemleri aynı dosyayı oku-değiştir-yaz ile kullanır; tek süreçte sırayla.
kilit = threading.RLock()


class MesHatasi(Exception):
    """MES uçlarının kendi hataları (çekirdek hatası değil; uçlarda 404 / 409 / 503'e çevrilir)."""


class MesYok(MesHatasi):
    """Bilinmeyen mes_id (404)."""


class MesCakisma(MesHatasi):
    """Durum çakışması: aynı revizyon farklı gövde, yanlış durumda istenen çıktı ya da geçiş (409)."""


class MesBozuk(MesHatasi):
    """Depo dosyası okunamıyor (503); dosyaya dokunulmaz."""


class MesYokBagimlilik(MesHatasi):
    """Uç, henüz main'de olmayan bir SPEC'e dayanıyor (503)."""


@dataclass
class MesDepo:
    """Bellekteki depo; her değiştiren işlem dosyaya atomik yazar.

    kayitlar : mes_id → o mes_id'nin revizyonları (eskiden yeniye); sonuncusu güncel kayıttır
    sayac    : son verilen degisiklik numarası
    dondurulan: mes_id → `hazir` anında dondurulan çıktılar {"program": metin, "foy": html, "takimlar": [...]}
    """

    yol: Path
    kayitlar: dict[str, list[IsEmriDurumu]] = field(default_factory=dict)
    sayac: int = 0
    dondurulan: dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------- saklama


def _ozet(metin: str) -> str:
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def yukle(yol: Path = DEPO_YOLU) -> MesDepo:
    """Depo dosyasını okur; yoksa boş depo (dosya ilk yazımda oluşur). Bozuksa MesBozuk."""
    yol = Path(yol)
    if not yol.exists():
        return MesDepo(yol)
    try:
        j = json.loads(yol.read_text(encoding="utf-8"))
        if not isinstance(j, dict) or j.get("sema") != SEMA:
            raise ValueError(f"sema {SEMA} bekleniyordu")
        kayitlar = {k: [IsEmriDurumu.model_validate(r) for r in v] for k, v in j["kayitlar"].items()}
        d = MesDepo(yol, kayitlar, int(j["sayac"]), dict(j["dondurulan"]))
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise MesBozuk(f"MES iş emri dosyası okunamıyor: {yol} ({e}); dosya değiştirilmedi") from None
    return d


def kaydet(d: MesDepo) -> None:
    """Kanonik JSON, atomik yazım (geçici dosya + os.replace; yarıda hata → eski dosya sağlam)."""
    j = {
        "sema": SEMA,
        "sayac": d.sayac,
        "kayitlar": {k: [r.model_dump(mode="json") for r in v] for k, v in d.kayitlar.items()},
        "dondurulan": d.dondurulan,
    }
    metin = json.dumps(j, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    d.yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = d.yol.with_name(d.yol.name + ".gecici")
    try:
        with open(gecici, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, d.yol)
    finally:
        if gecici.exists():
            gecici.unlink()


# ---------------------------------------------------------------- durum makinesi


def al(d: MesDepo, mes_id: str) -> IsEmriDurumu:
    """Güncel kayıt; bilinmeyen → MesYok."""
    if mes_id not in d.kayitlar:
        raise MesYok(f"Bilinmeyen iş emri: {mes_id!r}")
    return d.kayitlar[mes_id][-1]


def _degistir(d: MesDepo, mes_id: str, **alanlar) -> IsEmriDurumu:
    """Güncel kaydı alanlarla değiştirir, yeni degisiklik numarası verir ve dosyaya yazar."""
    d.sayac += 1
    yeni = al(d, mes_id).model_copy(update={**alanlar, "degisiklik": d.sayac})
    d.kayitlar[mes_id][-1] = yeni
    kaydet(d)
    return yeni


def koy(d: MesDepo, e: IsEmri) -> IsEmriDurumu:
    """Oluşturur ya da yeni revizyon (eskisi iptal, yenisi alindi).

    Aynı (mes_id, revizyon) aynı gövde → eş-etkili; farklı gövde ya da eski revizyon → MesCakisma.
    """
    gecmis = d.kayitlar.get(e.mes_id, [])
    if gecmis:
        son = gecmis[-1]
        if e.revizyon == son.is_emri.revizyon:
            if e != son.is_emri:
                raise MesCakisma(f"İş emri {e.mes_id} rev {e.revizyon} farklı içerikle zaten var")
            return son
        if e.revizyon < son.is_emri.revizyon:
            raise MesCakisma(f"İş emri {e.mes_id}: rev {e.revizyon} eski (güncel rev {son.is_emri.revizyon})")
    d.sayac += 1
    if gecmis:
        uyari = f"rev {e.revizyon} geldi; bu revizyon iptal"
        gecmis[-1] = gecmis[-1].model_copy(
            update={"durum": "iptal", "degisiklik": d.sayac, "uyarilar": [*gecmis[-1].uyarilar, uyari]}
        )
        d.dondurulan.pop(e.mes_id, None)
    yeni = IsEmriDurumu(is_emri=e, durum="alindi", degisiklik=d.sayac)
    d.kayitlar[e.mes_id] = [*gecmis, yeni]
    kaydet(d)
    return yeni


def bagla(d: MesDepo, mes_id: str, is_adi: str) -> IsEmriDurumu:
    """alindi / baglandi / hazir → baglandi (çıktılar düşer); is_adi depoda olmalı, yoksa KeyError."""
    from tezgah import depo as is_deposu

    k = al(d, mes_id)
    if k.durum not in ("alindi", "baglandi", "hazir"):
        raise MesCakisma(f"İş emri {mes_id} '{k.durum}' durumunda; iş bağlanamaz")
    if not is_deposu.var_mi(is_adi):
        raise KeyError(f"Bilinmeyen iş: {is_adi!r}")
    if k.durum == "baglandi" and k.is_adi == is_adi:
        return k
    d.dondurulan.pop(mes_id, None)
    return _degistir(d, mes_id, durum="baglandi", is_adi=is_adi, ciktilar=None)


def _profil(e: IsEmri):
    from cam.model import CamError
    from cam.post import builtin_machines

    if e.tezgah is None:
        raise CamError(f"İş emri {e.mes_id}: tezgah alanı boş; program için tezgâh profili gerekli")
    profiller = builtin_machines()
    if e.tezgah not in profiller:
        raise CamError(f"İş emri {e.mes_id}: bilinmeyen tezgâh profili {e.tezgah!r} ({sorted(profiller)})")
    return profiller[e.tezgah]


def _mes_satiri(metin: str, m, e: IsEmri) -> str:
    """POST yorum satırının hemen ardına aynı sözdizimiyle "MES <mes_id> REV <revizyon>" (Karar 4)."""
    post_yorumu = f"POST {m.name} {m.controller.upper()}"
    satirlar = metin.split("\n")
    i = next((k for k, s in enumerate(satirlar) if post_yorumu in s), None)
    if i is None:
        raise ModelError(f"Program metninde '{post_yorumu}' yorumu yok; MES satırı eklenemedi")
    satirlar.insert(i + 1, satirlar[i].replace(post_yorumu, f"MES {e.mes_id} REV {e.revizyon}"))
    if m.controller == "heidenhain":  # Klartext satır numaraları 0'dan ardışık
        satirlar = [re.sub(r"^\d+", str(n), s) if s else s for n, s in enumerate(satirlar)]
    return "\n".join(satirlar)


def _ciktilar(e: IsEmri, is_adi: str) -> dict:
    """Bağlı işten program (MES satırıyla), föy HTML'i ve takım listesi (dondurulacak hâl)."""
    from atolye.html import render_html
    from atolye.is_foyu import build_job_sheet
    from cam.model import ToolLibrary
    from cam.post import dialect_for, post
    from tezgah import depo as is_deposu

    tanim = is_deposu.al(is_adi)
    m = _profil(e)
    ops = [i.op for i in tanim.islemler]
    metin = _mes_satiri(post(ops, m, setup=tanim.kurulum, safe_z=tanim.safe_z, program_no=1), m, e)
    takimlar, gorulen = [], set()
    for op in ops:
        if op.tool.id not in gorulen:
            gorulen.add(op.tool.id)
            takimlar.append(op.tool)
    foy = build_job_sheet(
        f"{e.parca_no} rev {e.parca_rev}",
        [tanim.kurulum],
        [ops],
        ToolLibrary(tools=takimlar),
        tanim.malzeme,
        dialect=dialect_for(m),
        program_no=1,
        names=[[i.ad for i in tanim.islemler]],
    )
    satirlar = [
        Takim(
            t_no=r.T,
            ad=r.name,
            tur=r.kind,
            D=r.D,
            boy=r.stickout if r.stickout is not None else r.flute_length,
            tutucu=r.holder or "",
            sure_s=r.time,
        ).model_dump(mode="json")
        for s in foy.setups
        for r in s.tools
    ]
    uyarilar = []
    if importlib.util.find_spec("atolye.dnc") is not None:  # SPEC 63 Ö1–Ö5
        from atolye import dnc
        from cam.model import Toolpath
        from tezgah import kopru

        yollar = [op for op in ops if isinstance(op, Toolpath)]
        uyarilar = list(dnc.denetle(metin, m, yollar, kopru.kontroller(tanim)))
    return {"program": metin, "foy": render_html(foy), "takimlar": satirlar, "uyarilar": uyarilar}


def hazirla(d: MesDepo, mes_id: str) -> IsEmriDurumu:
    """baglandi → hazir: programı üretir (MES yorum satırıyla, Karar 4), SPEC 63 denetle (varsa) ile denetler,
    program / föy / takım listesini dondurur. CamError → 422."""
    k = al(d, mes_id)
    if k.durum not in ("baglandi", "hazir"):
        raise MesCakisma(f"İş emri {mes_id} '{k.durum}' durumunda; hazırlanamaz (önce iş bağlanmalı)")
    c = _ciktilar(k.is_emri, k.is_adi)
    ciktilar = Ciktilar(program_ozeti=_ozet(c["program"]), foy_ozeti=_ozet(c["foy"]))
    if k.durum == "hazir" and k.ciktilar == ciktilar:
        return k
    d.dondurulan[mes_id] = {key: c[key] for key in ("program", "foy", "takimlar")}
    return _degistir(d, mes_id, durum="hazir", ciktilar=ciktilar, uyarilar=c["uyarilar"])


def iptal(d: MesDepo, mes_id: str, gerekce: str) -> IsEmriDurumu:
    """Her durumdan iptal; gerekçe boş → ModelError (422). Kayıt silinmez."""
    if not gerekce.strip():
        raise ModelError("İptal gerekçesi boş olamaz")
    k = al(d, mes_id)
    if k.durum == "iptal":
        return k
    return _degistir(d, mes_id, durum="iptal", uyarilar=[*k.uyarilar, f"iptal: {gerekce}"])


def tazele(d: MesDepo, mes_id: str) -> IsEmriDurumu:
    """Bağlı işin bugünkü programı dondurulanla aynı değilse hazir → baglandi (çıktılar geçersiz)."""
    from tezgah import depo as is_deposu

    k = al(d, mes_id)
    if k.durum != "hazir":
        return k
    if not is_deposu.var_mi(k.is_adi):
        neden = f"bağlı iş {k.is_adi!r} artık yok"
    else:
        try:
            c = _ciktilar(k.is_emri, k.is_adi)
        except Exception as e:  # noqa: BLE001  iş artık post edilemiyor: çıktılar bayat, nedeni uyarıda
            neden = f"bağlı iş artık programlanamıyor ({e})"
        else:
            if _ozet(c["program"]) == k.ciktilar.program_ozeti and _ozet(c["foy"]) == k.ciktilar.foy_ozeti:
                return k
            neden = f"bağlı iş {k.is_adi!r} değişti"
    d.dondurulan.pop(mes_id, None)
    uyari = f"{neden}; çıktılar geçersiz, yeniden hazırlanmalı"
    return _degistir(d, mes_id, durum="baglandi", ciktilar=None, uyarilar=[*k.uyarilar, uyari])


def gonderim_kayitlari(kayit_dosyasi: Path = GONDERIM_KAYDI) -> list[dict]:
    """SPEC 63 §5 gönderim kaydı satırları (dosya yoksa boş); bozuk satır → MesBozuk."""
    yol = Path(kayit_dosyasi)
    if not yol.exists():
        return []
    sonuc = []
    try:
        for n, satir in enumerate(yol.read_text(encoding="utf-8").splitlines(), start=1):
            if satir.strip():
                r = json.loads(satir)
                if not isinstance(r, dict):
                    raise ValueError(f"satır {n} nesne değil")
                sonuc.append(r)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise MesBozuk(f"Gönderim kaydı okunamıyor: {yol} ({e})") from None
    return sonuc


def _program_ozeti(r: dict) -> str | None:
    p = r.get("program")
    return p.get("ozet") if isinstance(p, dict) else None


def esitle(d: MesDepo, kayit_dosyasi: Path = GONDERIM_KAYDI) -> list[IsEmriDurumu]:
    """SPEC 63 kaydında programı eşleşen hazir iş emirlerini gonderildi yapar; değişenleri döndürür."""
    gonderilen = {_program_ozeti(r) for r in gonderim_kayitlari(kayit_dosyasi)}
    degisen = []
    for mes_id in list(d.kayitlar):
        k = al(d, mes_id)
        if k.durum == "hazir" and k.ciktilar.program_ozeti in gonderilen:
            degisen.append(_degistir(d, mes_id, durum="gonderildi"))
    return degisen


def mes_id_bul(d: MesDepo, program_ozeti: str | None) -> str | None:
    """Dondurulmuş program özeti bu olan iş emri (gönderim kaydını iş emrine bağlamak için)."""
    for mes_id, gecmis in d.kayitlar.items():
        for k in gecmis:
            if k.ciktilar is not None and k.ciktilar.program_ozeti == program_ozeti:
                return mes_id
    return None


def degisenler(d: MesDepo, sonra: int) -> list[IsEmriDurumu]:
    """degisiklik > sonra olan güncel kayıtlar, degisiklik artan sırada."""
    return sorted(
        (v[-1] for v in d.kayitlar.values() if v[-1].degisiklik > sonra), key=lambda k: k.degisiklik
    )


def _dondurulan(d: MesDepo, mes_id: str) -> dict:
    k = al(d, mes_id)
    if k.durum not in ("hazir", "gonderildi") or mes_id not in d.dondurulan:
        raise MesCakisma(
            f"İş emri {mes_id} '{k.durum}' durumunda; çıktı yalnız hazir / gonderildi iş emrinde var"
        )
    return d.dondurulan[mes_id]


def program_metni(d: MesDepo, mes_id: str) -> str:
    """Dondurulmuş program; durum hazir / gonderildi değilse MesCakisma."""
    return _dondurulan(d, mes_id)["program"]


def foy_html(d: MesDepo, mes_id: str) -> str:
    return _dondurulan(d, mes_id)["foy"]


def takim_listesi(d: MesDepo, mes_id: str) -> list[Takim]:
    return [Takim.model_validate(t) for t in _dondurulan(d, mes_id)["takimlar"]]


def izinli_kokenler(yol: Path = AYAR_YOLU) -> list[str]:
    """CORS izinli kökenleri; dosya yoksa boş liste, bozuksa MesBozuk."""
    yol = Path(yol)
    if not yol.exists():
        return []
    try:
        j = json.loads(yol.read_text(encoding="utf-8"))
        L = j.get("izinli_kokenler", [])
        if not (isinstance(L, list) and all(isinstance(k, str) for k in L)):
            raise ValueError("izinli_kokenler metin listesi olmalı")
    except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
        raise MesBozuk(f"MES ayar dosyası okunamıyor: {yol} ({e})") from None
    return L
