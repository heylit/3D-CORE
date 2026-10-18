"""
SPEC 63 — DNC (dosya yoluyla): denetlenmiş programı kontrolör kurallarına uygun adla, satır sonuyla ve
atomik olarak hedef klasöre yazar; var olan dosyayı sessizce ezmez; her gönderimi kayda
(`gonderim-kaydi.jsonl`) ekler.

Ağ, seri hat ve alt süreç yoktur (karar 3): yalnız yerel dosya yazımı.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from cam.model import CamError, MachineProfile, Tool, Toolpath
from cam.post import UYARI, read_program

KURAL_DOSYASI = Path(__file__).with_name("dnc_kurallari.json")
YEDEK = ".3dcore-yedek"
ZAMAN_DESENI = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
UYARI_SATIRI = 12  # Ö5: UYARI yorumu programın ilk bu kadar satırında aranır


@dataclass(frozen=True)
class DosyaKurali:
    """Bir kontrolörün dosya kuralı (`atolye/dnc_kurallari.json` satırı)."""

    kontrolor: str
    ad_deseni: str  # regex, tam eşleşme
    uzanti: str
    satir_sonu: str  # "\n" | "\r\n"
    satir_uzunlugu: int
    sinirlayici: str | None  # "%" ya da None


@dataclass(frozen=True)
class Gonderim:
    """Bir gönderimin sonucu."""

    yol: Path
    sonuc: str  # "yazildi" | "ayni" | "ezildi"
    kayit: dict  # §5 satırı


@cache
def _tablo() -> dict[str, DosyaKurali]:
    d = json.loads(KURAL_DOSYASI.read_text(encoding="utf-8"))
    return {
        r["kontrolor"]: DosyaKurali(
            kontrolor=r["kontrolor"],
            ad_deseni=r["ad_deseni"],
            uzanti=r["uzanti"],
            satir_sonu=r["satir_sonu"],
            satir_uzunlugu=r["satir_uzunlugu"],
            sinirlayici=r["sinirlayici"],
        )
        for r in d["kurallar"]
    }


def dosya_kurali(m: MachineProfile) -> DosyaKurali:
    """Profilin kontrolörüne ait dosya kuralı; tabloda yoksa CamError."""
    k = _tablo().get(m.controller)
    if k is None:
        raise CamError(f"DNC: '{m.controller}' kontrolörü için dosya kuralı yok ({KURAL_DOSYASI.name})")
    return k


def _o_hane(k: DosyaKurali) -> int | None:
    """'O' + n hane kuralında n; başka kuralda None."""
    e = re.fullmatch(r"O\[0-9\]\{(\d+)\}", k.ad_deseni)
    return int(e.group(1)) if e else None


def _ad(m: MachineProfile, program_no: int, ad: str | None) -> str:
    """Uzantısız dosya adı (kural denetimli)."""
    k = dosya_kurali(m)
    n = _o_hane(k)
    if n is not None:
        beklenen = f"O{program_no:0{n}d}"
        if ad is not None and ad != beklenen:
            raise CamError(
                f"DNC: {k.kontrolor} dosya adı program numarasıyla aynı olmalı ({beklenen}, verilen {ad!r})"
            )
        ad = beklenen
    elif ad is None:
        # ad verilmezse: Sinumerik'te ilk iki karakter harf olmalı → PRG_<no>; diğerlerinde numara
        ad = f"PRG_{program_no}" if k.kontrolor == "sinumerik" else str(program_no)
    if not isinstance(ad, str) or not re.fullmatch(k.ad_deseni, ad, flags=re.ASCII):
        raise CamError(f"DNC: {ad!r} {k.kontrolor} dosya adı kuralına uymuyor ({k.ad_deseni})")
    return ad


def dosya_adi(m: MachineProfile, program_no: int, ad: str | None = None) -> str:
    """Kontrolör kuralına uyan dosya adı (uzantı dahil); uymayan ad CamError."""
    return _ad(m, program_no, ad) + dosya_kurali(m).uzanti


def _karakterler(satirlar: list[str], k: DosyaKurali) -> None:
    """Ö4: yalnız yazdırılabilir ASCII (ve sekme), satır uzunluğu sınırın altında."""
    for i, s in enumerate(satirlar, 1):
        for c in s:
            if not (c == "\t" or 32 <= ord(c) < 127):
                raise CamError(
                    f"Ö4: satır {i}: ASCII dışı karakter {c!r} (U+{ord(c):04X}); program ASCII olmalı"
                )
        if len(s) > k.satir_uzunlugu:
            raise CamError(f"Ö4: satır {i}: uzunluk {len(s)} > {k.satir_uzunlugu} ({k.kontrolor} sınırı)")


def _uyari_var(satirlar: list[str]) -> bool:
    """Ö5: doğrulanmamış profil uyarısı programın başında yorum olarak var mı?"""
    return any(UYARI in s for s in satirlar[:UYARI_SATIRI])


def _uclar(yollar: Sequence[Toolpath]) -> list[tuple]:
    """Hareketler: (tip, uç, merkez | None)."""
    return [
        (mv.type, tuple(mv.end), None if mv.center is None else tuple(mv.center))
        for tp in yollar
        for mv in tp.moves
    ]


def _yakin(a: tuple, b: tuple, tol: float) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def _okunan_satir(metin: str, m: MachineProfile, tools: dict[int, Tool], i: int) -> int:
    """Okunan i. hareketi (0 tabanlı) üreten satır (1 tabanlı): öneklerin okunmasıyla ikili arama.

    Önek, programın son satırıyla kapatılır (Heidenhain `END PGM` ister); okunamayan önek "henüz yok"
    sayılır."""
    satirlar = metin.split("\n")
    son = next((s for s in reversed(satirlar) if s.strip()), "")

    def sayi(n: int) -> int:
        try:
            return sum(len(t.moves) for t in read_program("\n".join([*satirlar[:n], son]) + "\n", m, tools))
        except CamError:
            return 0

    lo, hi = 1, len(satirlar)
    while lo < hi:
        orta = (lo + hi) // 2
        if sayi(orta) > i:
            hi = orta
        else:
            lo = orta + 1
    return lo


def _gidis_donus(metin: str, m: MachineProfile, yollar: Sequence[Toolpath]) -> None:
    """Ö2: okunan yol üretilen yolun her hareketini sırayla içeriyor (uç ≤ 0.5·10⁻ᵈ mm, merkez ≤ 1e-2 mm)."""
    tools = {tp.tool.id: tp.tool for tp in yollar}
    try:
        okunan = read_program(metin, m, tools)
    except CamError as e:
        raise CamError(f"Ö2 gidiş-dönüş: program okunamadı: {e}") from e
    tol = 0.5 * 10.0 ** (-m.decimals) + 1e-9
    P = _uclar(okunan)
    j = 0
    for tip, uc, merkez in _uclar(yollar):
        bas = j
        while j < len(P) and not (
            P[j][0] == tip
            and _yakin(P[j][1], uc, tol)
            and (merkez is None or P[j][2] is None or _yakin(P[j][2], merkez, 1e-2))
        ):
            j += 1
        if j == len(P):
            # suçlu: son eşleşmeden sonra beklenen uca en yakın okunan hareket
            aday = range(bas, len(P)) or range(len(P))
            i = min(aday, key=lambda q: math.dist(P[q][1], uc)) if P else 0
            n = _okunan_satir(metin, m, tools, i)
            yaz = metin.split("\n")[n - 1] if P else ""
            raise CamError(
                f"Ö2 gidiş-dönüş: satır {n} ({yaz.strip()!r}) üretilen yolla aynı değil; beklenen uç "
                f"{tuple(round(v, 6) for v in uc)}"
            )
        j += 1


def denetle(
    metin: str, m: MachineProfile, yollar: Sequence[Toolpath], kontroller: Sequence[dict]
) -> list[str]:
    """Ö1–Ö5 ön koşulları: hata varsa CamError, yoksa uyarı listesi.

    Ö3 (program numarası) `gonder`'de denetlenir; burada numara yoktur."""
    k = dosya_kurali(m)
    uyarilar = []
    for c in kontroller:
        durum = c.get("durum")
        metin_c = f"{c.get('baslik', c.get('kimlik', '?'))}: {c.get('aciklama', '')}"
        if durum == "hata":
            raise CamError(f"Ö1 denetim hatası: {metin_c}")
        if durum == "uyari":
            uyarilar.append(metin_c)
    satirlar = metin.split("\n")
    _karakterler(satirlar, k)
    if not m.verified:
        if not _uyari_var(satirlar):
            raise CamError(f"Ö5: profil '{m.name}' doğrulanmamış ama programın başında '{UYARI}' yorumu yok")
        uyarilar.append(f"Doğrulanmamış profil '{m.name}': ilk parçada kuru çalıştırın")
    _gidis_donus(metin, m, yollar)
    return uyarilar


def _bicimle(metin: str, m: MachineProfile, k: DosyaKurali, ad: str) -> bytes:
    """Kontrolör biçimi: Heidenhain PGM adı = dosya adı, '%' sınırlayıcı ve O numarası, satır sonu."""
    satirlar = metin.split("\n")
    if satirlar and satirlar[-1] == "":
        satirlar.pop()
    if k.kontrolor == "heidenhain":
        for desen in (r"BEGIN PGM \S+ MM", r"END PGM \S+ MM"):
            yer = [i for i, s in enumerate(satirlar) if re.search(desen, s)]
            if len(yer) != 1:
                raise CamError(
                    f"DNC: Heidenhain programında tek '{desen.split()[0]} PGM' satırı olmalı ({len(yer)})"
                )
            yeni = desen.split()[0] + f" PGM {ad} MM"
            satirlar[yer[0]] = re.sub(desen, yeni, satirlar[yer[0]])
    if k.sinirlayici is not None:
        if not satirlar or satirlar[0] != k.sinirlayici:
            satirlar.insert(0, k.sinirlayici)
        if satirlar[-1] != k.sinirlayici:
            satirlar.append(k.sinirlayici)
    if _o_hane(k) is not None:
        yer = [i for i, s in enumerate(satirlar) if re.fullmatch(r"O\d+\s*(\(.*\))?", s)]
        if not yer or int(re.match(r"O(\d+)", satirlar[yer[0]]).group(1)) != int(ad[1:]):
            raise CamError(f"DNC: programın O numarası dosya adıyla ({ad}) aynı değil")
        satirlar[yer[0]] = re.sub(r"O\d+", ad, satirlar[yer[0]], count=1)
    return (k.satir_sonu.join(satirlar) + k.satir_sonu).encode("ascii")


def _ozet(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _kanonik(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def profil_ozeti(m: MachineProfile) -> str:
    """SPEC 48 ile aynı hesap: `MachineProfile.to_dict()` kanonik JSON'unun sha256'sı."""
    return _ozet(_kanonik(m.to_dict()).encode("utf-8"))


def _yaz(yol: Path, b: bytes) -> None:
    """Atomik yazım: `.<ad>.yaziliyor` → fsync → os.replace; hata olursa geçici dosya silinir."""
    gecici = yol.with_name(f".{yol.name}.yaziliyor")
    try:
        with open(gecici, "wb") as f:
            f.write(b)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except OSError as e:
        gecici.unlink(missing_ok=True)
        raise CamError(f"DNC: {yol} yazılamadı ({e}); hedefte yarım dosya bırakılmadı") from e


def _kaydet(kayit_dosyasi: Path, kayit: dict) -> None:
    kayit_dosyasi.parent.mkdir(parents=True, exist_ok=True)
    with open(kayit_dosyasi, "a", encoding="utf-8", newline="\n") as f:
        f.write(_kanonik(kayit) + "\n")


def gonder(
    metin: str,
    m: MachineProfile,
    yollar: Sequence[Toolpath],
    kontroller: Sequence[dict],
    hedef: str | Path,
    operator: str,
    zaman: str,
    program_no: int,
    ad: str | None = None,
    ezme: bool = False,
    gerekce: str = "",
    is_foyu: Path | None = None,
    kayit_dosyasi: str | Path = "yerel_parcalar/gonderim-kaydi.jsonl",
) -> Gonderim:
    """Denetle, kurala göre biçimle, ezme korumasıyla atomik yaz ve kayda ekle.

    Hata olursa (CamError) hedef klasör ve kayıt dosyası değişmez."""
    if not isinstance(zaman, str) or not re.fullmatch(ZAMAN_DESENI, zaman):
        raise CamError(f"DNC: zaman 'YYYY-AA-GGTSS:DD:SSZ' olmalı ({zaman!r})")
    if not isinstance(operator, str) or not operator.strip():
        raise CamError("DNC: operatör boş olamaz")
    hedef = Path(hedef)
    if not hedef.is_dir():
        raise CamError(f"DNC: hedef klasör yok: {hedef}")
    lo, hi = m.program_no_range
    if not lo <= program_no <= hi:
        raise CamError(f"Ö3: program numarası {program_no} tezgâh aralığı [{lo}, {hi}] dışında")
    k = dosya_kurali(m)
    ad0 = _ad(m, program_no, ad)
    uyarilar = denetle(metin, m, yollar, kontroller)
    b = _bicimle(metin, m, k, ad0)
    foy = None
    if is_foyu is not None:
        is_foyu = Path(is_foyu)
        if not is_foyu.is_file():
            raise CamError(f"DNC: iş föyü yok: {is_foyu}")
        foy = {"yol": str(is_foyu), "ozet": _ozet(is_foyu.read_bytes())}

    yol = hedef / (ad0 + k.uzanti)
    sonuc = "yazildi"
    if yol.exists():
        eski = yol.read_bytes()
        if eski == b:
            sonuc = "ayni"
        elif not ezme:
            raise CamError(f"{yol} var ve farklı (sha256 {_ozet(eski)}). Üzerine yazmak için onay gerekir.")
        elif not gerekce.strip():
            raise CamError(f"{yol} üzerine yazmak için gerekçe gerekir (ezme=True, gerekce boş)")
        else:
            yedek = hedef / YEDEK
            yedek.mkdir(exist_ok=True)
            shutil.copy2(yol, yedek / f"{yol.name}.{_ozet(eski)[:12]}")
            sonuc = "ezildi"
    elif ezme and not gerekce.strip():
        raise CamError("DNC: ezme=True yalnız boş olmayan gerekçeyle kabul edilir")
    if sonuc != "ayni":
        _yaz(yol, b)

    kayit = {
        "sema": 1,
        "zaman": zaman,
        "operator": operator,
        "profil": {"ad": m.name, "ozet": profil_ozeti(m)},
        "program": {"ad": yol.name, "ozet": _ozet(b), "lehce": m.controller, "program_no": program_no},
        "hedef": str(hedef),
        "sonuc": sonuc,
        "gerekce": gerekce,
        "dogrulanmis": bool(m.verified),
        "denetim": {"sim": "temiz", "gidis_donus": "ayni", "uyarilar": uyarilar},
        "is_foyu": foy,
    }
    _kaydet(Path(kayit_dosyasi), kayit)
    return Gonderim(yol=yol, sonuc=sonuc, kayit=kayit)


def kayitlari_oku(kayit_dosyasi: str | Path) -> list[dict]:
    """Gönderim kaydının satırları (yazım sırasıyla); dosya yoksa boş liste, bozuk satır CamError."""
    p = Path(kayit_dosyasi)
    if not p.exists():
        return []
    out = []
    for i, s in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not s.strip():
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError as e:
            raise CamError(f"Gönderim kaydı {p} satır {i} okunamadı: {e}") from e
    return out
