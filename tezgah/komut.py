"""
SPEC 62 — komut paleti: normalleştirme, belirlenimci dilbilgisi, öneri (yapay zekâ yok).

Tanınmayan ya da iki anlamlı komut tahmin edilmez: KomutError (öneri ve okumalarla). FastAPI'siz test edilir.

Çıktı adımı (Cozum.adim) SPEC 26 adım sözlüğünün yerleşimsiz çekirdeğidir; sayılar float, adet int:
    delik : {tur: "delik", cesit: "duz", d, derinlik}            derinlik None = boydan boya
            + {tolerans: "H7", d_hedef}                          tolerans verilirse (tezgah.tolerans)
            cesit "dis"   : + {thread: "M8" | "M8x1"}, d = kılavuz matkabı d_n − P (M8 → 6.8, M8x1 → 7.0)
            cesit "havsa" : + {csk_d, csk_angle}                 "havşa 12x90"; açı yoksa 90
            cesit "lamba" : + {cbore_d, cbore_depth}             "lamba Ø15 derin 9"
    cep   : {tur: "cep", w, l, r, derinlik}                      "cep 40x20 derin 5" → r = 0.0
    pah   : {tur: "pah", d, aci}                                 açı yoksa 45.0
    fillet: {tur: "fillet", r}
    kanal : {tur: "kanal", genislik, derinlik}
    ortak nitelikler: {adet: int, aralik: float} (dizi), {yuz: ad}; verilmeyen nitelik sözlükte yoktur.

Yerleşim (hangi yüz, hangi nokta) `yerlestir` ile ayrı yapılır: cozumle yerleşimsiz adımı verir (K1),
yerlestir seçili yüz / noktayla SPEC 26 model adımlarını üretir (K3); seçim yoksa "Önce bir yüz seçin".

Delik toleransı küçük harfle yazılsa da delik alanıdır ("h7" → "H7"): delik mil toleransı alamaz.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from geometry.holes import THREADS_COARSE


class KomutError(ValueError):
    """Çözülemeyen komut. oneriler: en yakın anahtar sözcükler; okumalar: iki anlamlılıkta olası okumalar."""

    def __init__(self, mesaj: str, oneriler: tuple[str, ...] = (), okumalar: tuple[str, ...] = ()):
        super().__init__(mesaj)
        self.oneriler = tuple(oneriler)
        self.okumalar = tuple(okumalar)


@dataclass(frozen=True)
class Cozum:
    """adim: yerleşimsiz SPEC 26 adım çekirdeği (modül açıklaması); aciklama: insan okunur geri bildirim."""

    adim: dict = field(default_factory=dict)
    aciklama: str = ""


# Kaba diş kılavuz matkabı [mm], ISO 2306 (6H) ticari matkap; ince diş: d_n − P
KILAVUZ = {
    "M3": 2.5,
    "M4": 3.3,
    "M5": 4.2,
    "M6": 5.0,
    "M8": 6.8,
    "M10": 8.5,
    "M12": 10.2,
    "M14": 12.0,
    "M16": 14.0,
    "M20": 17.5,
    "M24": 21.0,
}

ANAHTAR = (
    "delik",
    "dis",
    "cep",
    "pah",
    "fillet",
    "radyüs",
    "kanal",
    "derin",
    "boydan",
    "boya",
    "havşa",
    "lamba",
    "adet",
    "aralık",
    "yüz",
    "r",
)
DELIK_ORNEK = "Örnek: 'Ø10 delik, 20 derin' ya da 'Ø10 delik, boydan boya'"
_SAYI = r"\d+(?:\.\d+)?"
_TOLERANS = re.compile(r"(js|[hgfkmnp])(\d{1,2})")


# --- normalleştirme ----------------------------------------------------------------------------


def normallestir(metin: str) -> str:
    """Türkçe kurallı küçük harf, Ø / çap, ondalık virgül, x, derin eşanlamlıları, tek boşluk (SPEC 62 §1)."""
    if not isinstance(metin, str):
        raise KomutError(f"Komut metin olmalı ({type(metin).__name__})")
    s = metin.replace("I", "ı").replace("İ", "i").lower()
    s = s.replace("ø", "Ø").replace("⌀", "Ø")
    s = re.sub(r"\bçap\b", "Ø", s)
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)  # ondalık virgül; virgül + boşluk ayraçtır
    s = re.sub(rf"({_SAYI})\s*[×*x]\s*(?=\d)", r"\1x", s)
    s = re.sub(r"\bderinlik\b", "derin", s)
    s = re.sub(r"\bd\s*=\s*", "derin ", s)
    s = re.sub(r"Ø\s+(?=\d)", "Ø", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    return re.sub(r"\s+", " ", s).strip(" ,")


# --- sözcükler ---------------------------------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    onceki = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        simdi = [i]
        for j, cb in enumerate(b, 1):
            simdi.append(min(onceki[j] + 1, simdi[j - 1] + 1, onceki[j - 1] + (ca != cb)))
        onceki = simdi
    return onceki[-1]


def _oneri(sozcuk: str) -> tuple[str, ...]:
    uz = sorted((_levenshtein(sozcuk, k), k) for k in ANAHTAR if len(k) > 1)
    return tuple(k for d, k in uz if d <= 2)


def _sayi(t: str | None) -> float | None:
    return float(t) if t is not None and re.fullmatch(_SAYI, t) else None


def _pozitif(ad: str, v: float) -> float:
    if not (math.isfinite(v) and v > 0):
        raise KomutError(f"{ad} pozitif olmalı ({v:g})")
    return v


# --- çözümleyici -------------------------------------------------------------------------------


class _Okuyucu:
    """Normalleştirilmiş metni sözcük dizisi olarak sırayla okur; virgüller yalnız ayraçtır."""

    def __init__(self, metin: str):
        self.t = [w for w in re.split(r"[ ,]+", metin) if w]
        self.i = 0
        self.eylem: str | None = None
        self.adim: dict = {}
        self.nitelik: dict[str, object] = {}
        self.yazim: dict[str, str] = {}

    def bak(self, k: int = 0) -> str | None:
        return self.t[self.i + k] if self.i + k < len(self.t) else None

    def al(self) -> str:
        w = self.t[self.i]
        self.i += 1
        return w

    def sayi_al(self, ad: str) -> float:
        v = _sayi(self.bak())
        if v is None:
            raise KomutError(f"'{ad}' sonrasında sayı bekleniyordu ({self.bak() or 'metin bitti'})")
        self.i += 1
        return v

    def eylem_koy(self, eylem: str, adim: dict) -> None:
        if self.eylem is not None:
            raise KomutError(
                f"Komutta iki eylem var: {self.eylem} ve {eylem}; her komut tek işlem",
                okumalar=(self.eylem, eylem),
            )
        self.eylem, self.adim = eylem, adim

    def nitelik_koy(self, ad: str, deger, yazim: str) -> None:
        if ad in self.nitelik:
            raise KomutError(
                f"'{ad}' iki kez verildi; hangisi geçerli belli değil",
                okumalar=(f"{ad} {self.yazim[ad]}", f"{ad} {yazim}"),
            )
        self.nitelik[ad], self.yazim[ad] = deger, yazim


def _oku(o: _Okuyucu) -> None:
    w = o.al()
    sonraki = o.bak()
    # Ø<sayı> [delik]
    if m := re.fullmatch(rf"Ø({_SAYI})", w):
        if sonraki == "delik":
            o.i += 1
        o.eylem_koy("delik", {"tur": "delik", "cesit": "duz", "d": float(m.group(1))})
        return
    if w == "delik":
        if o.eylem == "delik":  # "Ø10 H7 delik": eylem çaptan geldi, sözcük yalnız tekrar
            return
        if sonraki is not None and (m := re.fullmatch(rf"Ø({_SAYI})", sonraki)):
            o.i += 1
            o.eylem_koy("delik", {"tur": "delik", "cesit": "duz", "d": float(m.group(1))})
            return
        raise KomutError("Delik çapı eksik. " + DELIK_ORNEK)
    # m<sayı>[x<sayı>] [dis | delik]
    if m := re.fullmatch(rf"m(\d+)(?:x({_SAYI}))?", w):
        if sonraki in ("dis", "diş", "delik"):
            o.i += 1
        thread = f"M{m.group(1)}" + (f"x{m.group(2)}" if m.group(2) else "")
        o.eylem_koy("dis", {"tur": "delik", "cesit": "dis", "thread": thread, "d": _kilavuz(thread)})
        return
    if w == "cep":
        a, b = _carpim(o, "cep")
        o.eylem_koy("cep", {"tur": "cep", "w": a, "l": b})
        return
    if w == "pah":
        t = o.bak()
        if t is not None and (m := re.fullmatch(rf"({_SAYI})x({_SAYI})", t)):
            o.i += 1
            d, aci = float(m.group(1)), float(m.group(2))
        else:
            d, aci = o.sayi_al("pah"), 45.0
        o.eylem_koy("pah", {"tur": "pah", "d": d, "aci": aci})
        return
    if w in ("fillet", "radyüs", "radyus"):
        o.eylem_koy("fillet", {"tur": "fillet", "r": o.sayi_al(w)})
        return
    if w == "kanal":
        a, b = _carpim(o, "kanal")
        o.eylem_koy("kanal", {"tur": "kanal", "genislik": a, "derinlik": b})
        return
    # nitelikler
    if w == "r":
        r = o.sayi_al("r")
        o.nitelik_koy("r", r, f"r {r:g}")
        return
    if w == "derin":
        v = o.sayi_al("derin")
        o.nitelik_koy("derin", v, f"{v:g}")
        return
    if (v := _sayi(w)) is not None and sonraki == "derin":
        o.i += 1
        o.nitelik_koy("derin", v, f"{v:g}")
        return
    if w == "boydan" and sonraki == "boya":
        o.i += 1
        o.nitelik_koy("derin", None, "boydan boya")
        return
    if w in ("havşa", "havsa"):
        t = o.bak()
        if t is not None and (m := re.fullmatch(rf"({_SAYI})x({_SAYI})", t)):
            o.i += 1
            csk = (float(m.group(1)), float(m.group(2)))
        else:
            csk = (o.sayi_al("havşa"), 90.0)
        o.nitelik_koy("havsa", csk, f"{csk[0]:g}x{csk[1]:g}")
        return
    if w == "lamba":
        t = o.bak()
        m = re.fullmatch(rf"Ø({_SAYI})", t or "")
        if m is None or o.bak(1) != "derin" or _sayi(o.bak(2)) is None:
            raise KomutError("Lamba yazımı: 'lamba Ø15 derin 9'")
        o.i += 3
        lamba = (float(m.group(1)), float(o.t[o.i - 1]))
        o.nitelik_koy("lamba", lamba, f"Ø{lamba[0]:g} derin {lamba[1]:g}")
        return
    if w == "adet":
        v = o.sayi_al("adet")
        if v != int(v) or v < 1:
            raise KomutError(f"Adet pozitif tamsayı olmalı ({v:g})")
        o.nitelik_koy("adet", int(v), f"{int(v)}")
        return
    if w in ("aralık", "aralik"):
        v = o.sayi_al("aralık")
        o.nitelik_koy("aralik", v, f"{v:g}")
        return
    if w in ("yüz", "yuz"):
        if o.bak() is None:
            raise KomutError("'yüz' sonrasında yüz adı bekleniyordu")
        ad = o.al()
        o.nitelik_koy("yuz", ad, ad)
        return
    if m := _TOLERANS.fullmatch(w):
        o.nitelik_koy("tolerans", w, w)
        return
    if _sayi(w) is not None:
        raise KomutError(f"'{w}' sayısının ne olduğu belli değil (ör. '{w} derin')")
    raise KomutError(f"Tanınmayan sözcük: '{w}'", oneriler=_oneri(w))


def _carpim(o: _Okuyucu, ad: str) -> tuple[float, float]:
    t = o.bak()
    if t is None or (m := re.fullmatch(rf"({_SAYI})x({_SAYI})", t)) is None:
        raise KomutError(f"{ad} iki ölçü ister: '{ad} 40x20'")
    o.i += 1
    return float(m.group(1)), float(m.group(2))


def _kilavuz(thread: str) -> float:
    m = re.fullmatch(rf"M(\d+)(?:x({_SAYI}))?", thread)
    if m.group(2) is None:
        if thread not in KILAVUZ or thread not in THREADS_COARSE:
            raise KomutError(f"Kaba diş tabloda yok: {thread} (bilinenler: {', '.join(KILAVUZ)})")
        return KILAVUZ[thread]
    d_n, P = float(m.group(1)), float(m.group(2))
    if not 0 < P < d_n:
        raise KomutError(f"Hatve 0 < P < d olmalı ({thread})")
    return round(d_n - P, 6)


def _birlestir(o: _Okuyucu) -> dict:
    """Eylem + nitelikler → adım; zorunlu nitelikler, uyumsuz nitelikler ve ölçü denetimi."""
    n = dict(o.nitelik)
    if o.eylem is None:
        if "r" in n and len(n) == 1:
            r = n["r"]
            raise KomutError(
                f"'r {r:g}' iki anlamlı: fillet mi, cep köşe radyüsü mü? Açık yazın: 'fillet {r:g}' ya da "
                f"'cep 40x20 r {r:g} derin 5'",
                okumalar=(f"fillet {r:g}", f"cep köşesi r {r:g}"),
            )
        raise KomutError("Komutta işlem yok (delik, cep, pah, fillet, kanal, diş). " + DELIK_ORNEK)
    adim = dict(o.adim)
    e = o.eylem
    izinli = {
        "delik": {"derin", "tolerans", "havsa", "lamba", "adet", "aralik", "yuz"},
        "dis": {"derin", "adet", "aralik", "yuz"},
        "cep": {"derin", "r", "adet", "aralik", "yuz"},
        "pah": {"yuz"},
        "fillet": {"yuz"},
        "kanal": {"adet", "aralik", "yuz"},
    }[e]
    fazla = sorted(set(n) - izinli)
    if fazla:
        raise KomutError(f"{e} için geçersiz nitelik: {', '.join(fazla)}")
    if e in ("delik", "dis"):
        if "derin" not in n:
            raise KomutError(("Diş derinliği eksik. Örnek: 'M8 dis, derin 16'") if e == "dis" else
                             "Delik derinliği eksik. " + DELIK_ORNEK)  # fmt: skip
        adim["derinlik"] = n["derin"]
        if "havsa" in n and "lamba" in n:
            raise KomutError("Havşa ve lamba birlikte olamaz", okumalar=("havşa", "lamba"))
        if "havsa" in n:
            adim["cesit"], (adim["csk_d"], adim["csk_angle"]) = "havsa", n["havsa"]
        if "lamba" in n:
            adim["cesit"], (adim["cbore_d"], adim["cbore_depth"]) = "lamba", n["lamba"]
        if "tolerans" in n:
            from tezgah.tolerans import hedef_cap

            alan = _delik_alani(str(n["tolerans"]))
            adim["tolerans"], adim["d_hedef"] = alan, hedef_cap(alan, adim["d"])
    elif e == "cep":
        if "derin" not in n or n["derin"] is None:
            raise KomutError("Cep derinliği eksik. Örnek: 'cep 40x20 derin 5'")
        adim["r"], adim["derinlik"] = n.get("r", 0.0), n["derin"]
    for k in ("adet", "aralik", "yuz"):
        if k in n:
            adim[k] = n[k]
    for k in (
        "d",
        "w",
        "l",
        "derinlik",
        "aci",
        "r",
        "genislik",
        "csk_d",
        "csk_angle",
        "cbore_d",
        "cbore_depth",
    ):
        if k in adim and adim[k] is not None and not (k == "r" and e == "cep" and adim[k] == 0.0):
            _pozitif(k, adim[k])
    if e == "cep" and adim["r"] > min(adim["w"], adim["l"]) / 2:
        raise KomutError(f"Cep köşe radyüsü en fazla min(en, boy)/2 ({adim['r']:g})")
    if e == "pah" and not 0 < adim["aci"] < 90:
        raise KomutError(f"Pah açısı 0–90° arasında olmalı ({adim['aci']:g})")
    if "havsa" in n and not 0 < adim["csk_angle"] < 180:
        raise KomutError(f"Havşa açısı 0–180° arasında olmalı ({adim['csk_angle']:g})")
    if "havsa" in n and adim["csk_d"] <= adim["d"]:
        raise KomutError("Havşa çapı delik çapından büyük olmalı")
    if "lamba" in n and adim["cbore_d"] <= adim["d"]:
        raise KomutError("Lamba çapı delik çapından büyük olmalı")
    return adim


def _delik_alani(t: str) -> str:
    m = _TOLERANS.fullmatch(t)
    harf, derece = m.groups()
    if harf != "h":
        raise KomutError(f"Delik toleransı H alanı olmalı ({t.upper()}; mil alanları deliğe verilemez)")
    return f"H{derece}"


def _aciklama(adim: dict) -> str:
    t = adim["tur"]
    if t == "delik":
        derin = "boydan boya" if adim["derinlik"] is None else f"{adim['derinlik']:g} mm derin"
        if adim["cesit"] == "dis":
            bas = f"{adim['thread']} diş (matkap Ø{adim['d']:g})"
        else:
            tol = f" {adim['tolerans']}" if "tolerans" in adim else ""
            ek = {"havsa": " havşalı", "lamba": " lambalı"}.get(adim["cesit"], "")
            bas = f"Ø{adim['d']:g}{tol}{ek} delik"
        s = f"{bas}, {derin}"
        if "d_hedef" in adim:
            s += f"; hedef çap {adim['d_hedef']:.4f}".rstrip("0")
    elif t == "cep":
        s = f"{adim['w']:g} × {adim['l']:g} cep, köşe r {adim['r']:g}, {adim['derinlik']:g} mm derin"
    elif t == "pah":
        s = f"{adim['d']:g} × {adim['aci']:g}° pah"
    elif t == "fillet":
        s = f"r {adim['r']:g} fillet"
    else:
        s = f"{adim['genislik']:g} × {adim['derinlik']:g} kanal"
    if "adet" in adim:
        s += f", {adim['adet']} adet"
    if "aralik" in adim:
        s += f", aralık {adim['aralik']:g}"
    return s


def cozumle(metin: str, secim: dict | None = None) -> Cozum:
    """Komut → Cozum. Hata → KomutError. secim yalnız aciklama içindir; yerleşim yerlestir'dedir."""
    s = normallestir(metin)
    if not s:
        raise KomutError("Komut boş. " + DELIK_ORNEK)
    o = _Okuyucu(s)
    while o.bak() is not None:
        _oku(o)
    adim = _birlestir(o)
    return Cozum(adim=adim, aciklama=_aciklama(adim))


# --- yerleşim ----------------------------------------------------------------------------------


def yerlestir(adim: dict, secim: dict | None, model: dict) -> list[dict]:
    """Yerleşimsiz adım + seçim → modele eklenecek SPEC 26 adımları ([eskiz, delik]).

    secim = {"duzlem": SPEC 26 Duzlem sözlüğü, "nokta": [u, v]} (düzlem koordinatı, mm).
    secim None → KomutError("Önce bir yüz seçin"). İlk sürüm yalnız delik adımını yerleştirir; cep, pah,
    fillet ve kanal için SPEC 26'da adım olmadığından KomutError (ikinci aşama).
    """
    if secim is None or "duzlem" not in secim:
        raise KomutError("Önce bir yüz seçin")
    if adim.get("tur") != "delik":
        raise KomutError(f"{adim.get('tur')!r} komutu henüz modele uygulanamıyor (yalnız delik)")
    nokta = secim.get("nokta")
    if nokta is None or len(nokta) != 2 or not all(math.isfinite(float(v)) for v in nokta):
        raise KomutError("Önce delik merkezini seçin (yüz üstünde bir nokta)")
    from sketch.model import Plane

    kimlikler = {str(a.get("kimlik")) for a in model.get("adimlar", [])}
    i = 1
    while f"komut_{i}" in kimlikler or f"komut_{i}_eskiz" in kimlikler:
        i += 1
    adet = int(adim.get("adet", 1))
    aralik = float(adim.get("aralik", 0.0))
    if adet > 1 and aralik <= 0:
        raise KomutError("Birden fazla delik için 'aralık' gerekli (ör. 'adet 4, aralık 25')")
    u0, v0 = float(nokta[0]), float(nokta[1])
    noktalar = {f"p{j + 1}": {"x": u0 + j * aralik, "y": v0, "fixed": True} for j in range(adet)}
    eskiz = {
        "kimlik": f"komut_{i}_eskiz",
        "tur": "eskiz",
        "duzlem": dict(secim["duzlem"]),
        "eskiz": {
            "sema": 1,
            "plane": Plane.XY().to_dict(),  # kurulumda duzlem'den yeniden hesaplanır (SPEC 26)
            "points": noktalar,
            "entities": {},
            "constraints": [],
        },
        "olculer": {},
    }
    delik = {k: v for k, v in adim.items() if k not in ("adet", "aralik", "yuz")}
    delik.update(kimlik=f"komut_{i}", eskiz=eskiz["kimlik"], noktalar=list(noktalar))
    return [eskiz, delik]


def ornekler() -> list[tuple[str, dict]]:
    """Paletin yardım listesi: (komut, beklenen adım). K1 tablosuyla aynı kaynak."""
    return [(k, cozumle(k).adim) for k in ORNEK_KOMUTLAR]


ORNEK_KOMUTLAR = (
    "Ø10 delik, 20 derin",
    "ø10 delik, 20 derin, H7",
    "delik ⌀6,8 boydan boya",
    "M8 dis, derin 16",
    "M8x1 dis, derin 16",
    "Ø6.6 delik, boydan boya, havşa 12x90",
    "Ø9 delik, boydan boya, lamba Ø15 derin 9",
    "cep 40x20 derin 5",
    "cep 40 × 20, r 3, derin 5",
    "pah 1x45",
    "pah 2",
    "fillet 3",
    "kanal 8x4",
    "Ø10 delik, 20 derin, adet 4, aralık 25",
    "Ø10 DELİK, 20 DERİN",
)
