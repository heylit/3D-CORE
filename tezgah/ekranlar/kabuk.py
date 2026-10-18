"""
SPEC 37 — Kabuk ekranı: proje dosyası, ekranlar arası tek geri al / yinele, yayılım ve etki.

Kabuk hesap yapmaz: hangi bölümün kimden etkilendiğini (Ekran.bolum / Ekran.bagimli) bilir, yeniden hesabı
sırayla sahibi ekrana (`ice_aktar`) yaptırır ve önce / sonra `ozet()`'lerini karşılaştırır.

Uçlar `/api/proje/...` altındadır (A3 §URL kararı: kabuğun kendi uçları); `kur(app)` ile bağlanır, ayrıca
ekranların durum değiştiren isteklerini yakalayan ara katmanı kurar.

    Etki = [{bolum, ekran, once: Ozet, sonra: Ozet, fark: {anahtar: sonra − once}}]

Ekran listesi: `app.state.ekranlar` (A3 `uygulama(ekranlar=...)` verdiyse), yoksa `ekranlar()` keşfi.
"""

from __future__ import annotations

import heapq
import tempfile
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

import fileio.proje as pj
import tezgah.ornekler_37 as ornekler_37
from assy.model import AssyError
from cam.model import CamError
from core.model import ModelError
from fileio.proje import Onbellek, Proje, ProjeError, kanonik, ozet
from geometry.part import GeometryError
from sketch.model import SketchError
from tezgah.ekranlar import Ekran, ekranlar

AD = "kabuk"
BOLUM = "kabuk"
ONEK = "/api/proje"
ETIKET_BASLIGI = "X-Tezgah-Etiket"
ONBELLEK_SINIRI = 256 * 1024 * 1024  # bellekteki önbellek, bayt
VARSAYILAN_KLASOR = Path.home() / "3D-CORE projeleri"

# Kullanıcıya 422 olarak dönen çekirdek hataları (A3 hata işleyicisiyle aynı küme).
CEKIRDEK_HATALARI = (ProjeError, CamError, ModelError, AssyError, GeometryError, SketchError, KeyError)

Etki = list[dict]


# ---------------------------------------------------------------- bağımlılık grafiği


def _sahipler(ekranlar: Sequence[Ekran]) -> dict[str, Ekran]:
    """bölüm → sahibi ekran (bölümsüz ekranlar ve kabuğun kendisi hariç)."""
    return {e.bolum: e for e in ekranlar if e.bolum is not None and e.ad != AD}


def sira(ekranlar: Sequence[Ekran]) -> list[str]:
    """Bölümlerin topolojik sırası; eşitlikte ad. Döngü / bilinmeyen bölüme bağımlılık → ProjeError."""
    sahip = _sahipler(ekranlar)
    for b, e in sahip.items():
        for g in e.bagimli:
            if g not in sahip:
                raise ProjeError(f"bölüm {b!r} bilinmeyen bölüme bağımlı: {g!r}")
    giris = {b: len(set(e.bagimli)) for b, e in sahip.items()}
    cocuklar: dict[str, list[str]] = {b: [] for b in sahip}
    for b, e in sahip.items():
        for g in set(e.bagimli):
            cocuklar[g].append(b)
    hazir = [b for b, n in giris.items() if n == 0]
    heapq.heapify(hazir)
    sonuc: list[str] = []
    while hazir:
        b = heapq.heappop(hazir)
        sonuc.append(b)
        for c in cocuklar[b]:
            giris[c] -= 1
            if giris[c] == 0:
                heapq.heappush(hazir, c)
    if len(sonuc) != len(sahip):
        dongu = sorted(b for b in sahip if b not in sonuc)
        raise ProjeError(f"bölümler arasında bağımlılık döngüsü: {', '.join(dongu)}")
    return sonuc


def kapanis(ekranlar: Sequence[Ekran], degisen: set[str]) -> list[str]:
    """`degisen`'in aşağı akış kapanışı (değişenler hariç), topolojik sırayla."""
    sahip = _sahipler(ekranlar)
    etkilenen = set(degisen)
    sonuc: list[str] = []
    for b in sira(ekranlar):
        if b in degisen:
            continue
        if any(g in etkilenen for g in sahip[b].bagimli):
            etkilenen.add(b)
            sonuc.append(b)
    return sonuc


def girdi_ozeti(ekran: Ekran, bolumler: Mapping[str, dict]) -> str:
    """ozet({b: bolumler[b] for b in (ekran.bolum,) + ekran.bagimli})."""
    return ozet({b: bolumler[b] for b in (ekran.bolum, *ekran.bagimli)})


def _fark(once: dict, sonra: dict) -> dict:
    """İki tarafta da sayı (bool değil) olan anahtarlar için sonra − once."""

    def sayi(x) -> bool:
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    return {k: sonra[k] - once[k] for k in once if k in sonra and sayi(once[k]) and sayi(sonra[k])}


# ---------------------------------------------------------------- JSON Pointer yaması


def _isaretci(isaretci) -> list[str]:
    if not isinstance(isaretci, str) or not isaretci.startswith("/"):
        raise ProjeError(f"geçersiz JSON Pointer: {isaretci!r} ('/' ile başlamalı)")
    return [p.replace("~1", "/").replace("~0", "~") for p in isaretci[1:].split("/")]


def _yamala(bolumler: dict[str, dict], yamalar: list[dict]) -> set[str]:
    """Yamaları `bolumler`'e (kopya) uygular; dokunulan bölümleri döndürür. Geçersiz yol → ProjeError."""
    if not isinstance(yamalar, list) or not yamalar:
        raise ProjeError("yama listesi boş")
    dokunulan: set[str] = set()
    for y in yamalar:
        if not isinstance(y, dict) or not {"bolum", "isaretci", "deger"} <= set(y):
            raise ProjeError(f"geçersiz yama: {y!r} ({{bolum, isaretci, deger}} gerekli)")
        b = y["bolum"]
        if b not in bolumler:
            raise ProjeError(f"bilinmeyen bölüm: {b!r}")
        parcalar = _isaretci(y["isaretci"])
        kap = bolumler[b]
        for i, p in enumerate(parcalar):
            son = i == len(parcalar) - 1
            if isinstance(kap, dict):
                if son:
                    kap[p] = y["deger"]
                elif p in kap:
                    kap = kap[p]
                else:
                    raise ProjeError(f"{b}{y['isaretci']}: yol yok ({p!r})")
            elif isinstance(kap, list) and p.isdigit() and int(p) < len(kap):
                if son:
                    kap[int(p)] = y["deger"]
                else:
                    kap = kap[int(p)]
            else:
                raise ProjeError(f"{b}{y['isaretci']}: yol yok ({p!r})")
        kanonik(bolumler[b])  # nan / inf / JSON dışı değer → ProjeError
        dokunulan.add(b)
    return dokunulan


# ---------------------------------------------------------------- kabuk durumu


class Kabuk:
    """Tek kullanıcılı proje durumu: güncel Proje, dosya yolu, kirli bayrağı, son Etki."""

    def __init__(
        self,
        ekranlar: Sequence[Ekran],
        kurtarma: object | None = None,  # fileio.kurtarma.KurtarmaAyari (SPEC 54 Karar 9)
        klasor: Path | None = None,
    ) -> None:
        self._kurtarma = kurtarma  # None → otomatik kayıt kapalı (SPEC 54 §5)
        self._klasor = klasor
        self.kurtarma_uyarilari: list[str] = []
        self._ekranlar = [e for e in ekranlar if e.ad != AD]
        self._sahip = _sahipler(self._ekranlar)
        self._sira = sira(self._ekranlar)
        self._kilit = threading.RLock()
        self._depo: OrderedDict[str, dict[str, bytes]] = OrderedDict()  # girdi_ozeti → {anahtar: veri}
        self._yol: str | None = None
        self._kirli = False
        self.son_etki: Etki | None = None
        self.son_hata_bolumu: str | None = None
        bolumler = dict(pj.bos_proje("adsız").bolumler)
        for b in self._sira:
            bolumler[b] = self._belge(b)
        self._proje = Proje("adsız", bolumler)
        self._son_ozet = {b: self._ozet(b) for b in self._sira}
        for b in self._sira:
            self._onbellek_topla(b, bolumler)
        global _SON
        _SON = self

    # ----------------------------------------------------- yardımcılar

    def _belge(self, b: str) -> dict:
        belge = self._sahip[b].disa_aktar()
        pj._bolum_denetle(b, belge)
        return pj._kopya(belge)

    def _ozet(self, b: str) -> dict:
        e = self._sahip[b]
        return dict(e.ozet()) if e.ozet is not None else {}

    def _onbellek_ver(self, b: str, bolumler: Mapping[str, dict]) -> dict[str, bytes]:
        g = girdi_ozeti(self._sahip[b], bolumler)
        if g in self._depo:
            self._depo.move_to_end(g)
            return dict(self._depo[g])
        return {}

    def _onbellek_topla(self, b: str, bolumler: Mapping[str, dict]) -> None:
        e = self._sahip[b]
        kayitlar = dict(e.onbellek()) if e.onbellek is not None else {}
        if not kayitlar:
            return
        for anahtar in kayitlar:
            pj._anahtar_denetle(anahtar)
        g = girdi_ozeti(e, bolumler)
        self._depo[g] = {**self._depo.get(g, {}), **{a: bytes(v) for a, v in kayitlar.items()}}
        self._depo.move_to_end(g)
        boyut = sum(len(v) for d in self._depo.values() for v in d.values())
        while boyut > ONBELLEK_SINIRI and len(self._depo) > 1:
            _, eski = self._depo.popitem(last=False)
            boyut -= sum(len(v) for v in eski.values())

    def _ice_aktar(self, b: str, bolumler: Mapping[str, dict]) -> None:
        self._sahip[b].ice_aktar(pj._kopya(bolumler[b]), self._onbellek_ver(b, bolumler))
        self._onbellek_topla(b, bolumler)

    def _yay(self, eski: dict, yeni: dict, degisen: set[str], kendisi: bool) -> Etki:
        """`degisen` bölümlerden aşağı akışa yayar; hata → bütün geri çevirme ve hatanın kendisi.

        kendisi=True: değişenlerin sahipleri de `ice_aktar` alır (kabuktan gelen değişiklik);
        False: sahipler durumu zaten kurmuştur (yakalama), yalnız aşağı akış dolaşılır.
        """
        degisen = {b for b in degisen if b in self._sahip}
        alt = set(kapanis(self._ekranlar, degisen))
        sirali = [b for b in self._sira if b in degisen or b in alt]
        once = {b: (self._son_ozet[b] if (b in degisen and not kendisi) else self._ozet(b)) for b in sirali}
        uygulanan = [] if kendisi else [b for b in sirali if b in degisen]
        self.son_hata_bolumu = None
        for b in sirali:
            if b in degisen and not kendisi:
                continue
            try:
                self._ice_aktar(b, yeni)
            except Exception:
                self.son_hata_bolumu = b
                self._geri_cevir(uygulanan, eski)
                raise
            uygulanan.append(b)
        if not kendisi:
            for b in degisen:
                self._onbellek_topla(b, yeni)
        etki = []
        for b in sirali:
            sonra = self._ozet(b)
            etki.append(
                {
                    "bolum": b,
                    "ekran": self._sahip[b].ad,
                    "once": once[b],
                    "sonra": sonra,
                    "fark": _fark(once[b], sonra),
                }
            )
            self._son_ozet[b] = sonra
        return etki

    def _geri_cevir(self, uygulanan: list[str], eski: Mapping[str, dict]) -> None:
        """Uygulanmış bölümleri topolojik sırayla eski belgelerine döndürür."""
        for b in [x for x in self._sira if x in uygulanan]:
            self._ice_aktar(b, eski)
            self._son_ozet[b] = self._ozet(b)

    def _ekran_adi(self, bolumler: set[str]) -> str:
        for b in self._sira:
            if b in bolumler:
                return self._sahip[b].ad
        return AD

    # ----------------------------------------------------- durum

    @property
    def proje(self) -> Proje:
        """Güncel proje; önbellek yalnız güncel girdi özetlerine ait kayıtları taşır."""
        with self._kilit:
            onbellek: dict[str, Onbellek] = {}
            for b in self._sira:
                g = girdi_ozeti(self._sahip[b], self._proje.bolumler)
                for anahtar, veri in self._depo.get(g, {}).items():
                    onbellek[anahtar] = Onbellek(g, veri)
            return replace(self._proje, onbellek=onbellek)

    @property
    def kirli(self) -> bool:
        return self._kirli

    def durum(self) -> dict:
        """GET /api/proje yanıtı."""
        with self._kilit:
            p, g = self._proje, self._proje.gecmis
            return {
                "sema": pj.SEMA,
                "ad": p.ad,
                "yol": self._yol,
                "kirli": self._kirli,
                "geri_al": g.kayitlar[g.konum - 1]["etiket"] if g.konum > 0 else None,
                "yinele": g.kayitlar[g.konum]["etiket"] if g.konum < len(g.kayitlar) else None,
                "bolumler": sorted(p.bolumler),
                "uyarilar": list(p.uyarilar),
                "son_etki": self.son_etki,
            }

    def gecmis(self) -> dict:
        """GET /api/proje/gecmis yanıtı (belgeler gönderilmez)."""
        with self._kilit:
            g = self._proje.gecmis
            kayitlar = [
                {"etiket": k["etiket"], "ekran": k["ekran"], "bolumler": sorted(k["bolumler"])}
                for k in g.kayitlar
            ]
            return {"konum": g.konum, "kayitlar": kayitlar}

    # ----------------------------------------------------- değişiklik

    def degistir(self, yamalar: list[dict], etiket: str, onizle: bool = False) -> Etki:
        """JSON Pointer yamalarını uygular, yayar, Etki döndürür; hata → bütün geri çevirme."""
        with self._kilit:
            eski = dict(self._proje.bolumler)
            yeni = {b: pj._kopya(v) for b, v in eski.items()}
            dokunulan = _yamala(yeni, yamalar)
            for b in dokunulan:
                pj._bolum_denetle(b, yeni[b])
            degisen = {b for b in dokunulan if kanonik(yeni[b]) != kanonik(eski[b])}
            if not degisen:
                return []
            etki = self._yay(eski, yeni, degisen, kendisi=True)
            if onizle:
                self._geri_cevir([b for b in self._sira if b in {x["bolum"] for x in etki}], eski)
                return etki
            ekran = self._ekran_adi({yamalar[0]["bolum"]})
            self._proje = pj.uygula(self._proje, etiket, ekran, {b: yeni[b] for b in degisen})
            self._kirli, self.son_etki = True, etki
            return etki

    def yakala(self, etiket: str, ekran: str | None = None) -> Etki | None:
        """Bir ekranın kendi ucundan sonra: disa_aktar farklarını kaydeder ve aşağı akışa yayar."""
        with self._kilit:
            eski = dict(self._proje.bolumler)
            yeni = dict(eski)
            for b in self._sira:
                yeni[b] = self._belge(b)
            degisen = {b for b in self._sira if kanonik(yeni[b]) != kanonik(eski[b])}
            if not degisen:
                return None
            etki = self._yay(eski, yeni, degisen, kendisi=False)
            ekran = ekran or self._ekran_adi(degisen)
            self._proje = pj.uygula(self._proje, etiket, ekran, {b: yeni[b] for b in degisen})
            self._kirli, self.son_etki = True, etki
            return etki

    def _gecis(self, hedef: Proje) -> Etki:
        eski = dict(self._proje.bolumler)
        yeni = dict(hedef.bolumler)
        degisen = {b for b in self._sira if kanonik(eski[b]) != kanonik(yeni[b])}
        etki = self._yay(eski, yeni, degisen, kendisi=True)
        self._proje = hedef
        self._kirli, self.son_etki = True, etki
        return etki

    def geri_al(self) -> Etki:
        with self._kilit:
            return self._gecis(pj.geri_al(self._proje))

    def yinele(self) -> Etki:
        with self._kilit:
            return self._gecis(pj.yinele(self._proje))

    # ----------------------------------------------------- dosya

    def _yukle(self, p: Proje, yol: str | None) -> None:
        """Projeyi bütün ekranlara `sira` ile yükler; hata → hiçbir ekran değişmez."""
        eski = dict(self._proje.bolumler)
        yeni = dict(p.bolumler)
        for b in self._sira:
            yeni.setdefault(b, eski[b])
        for anahtar, o in p.onbellek.items():
            self._depo.setdefault(o.girdi_ozeti, {})[anahtar] = o.veri
        uyarilar = list(p.uyarilar)
        for b in sorted(yeni):
            if b not in self._sahip and b != BOLUM:
                metin = f"bölüm {b!r}: hiçbir ekran sahiplenmiyor; olduğu gibi korunur"
                uyarilar.append(pj._uyari("proje_bilinmeyen_bolum", metin))
        self._yay(eski, yeni, set(self._sira), kendisi=True)
        self._proje = Proje(p.ad, yeni, {}, p.gecmis, tuple(uyarilar))
        self._yol, self._kirli, self.son_etki = yol, False, None

    def yeni(self, ad: str) -> None:
        with self._kilit:
            if not isinstance(ad, str) or not ad.strip():
                raise ProjeError("proje adı boş")
            for e in self._ekranlar:
                if e.sifirla is not None:
                    e.sifirla()
            bolumler = dict(pj.bos_proje(ad).bolumler)
            for b in self._sira:
                bolumler[b] = self._belge(b)
            self._proje = Proje(ad, bolumler)
            self._son_ozet = {b: self._ozet(b) for b in self._sira}
            self._yol, self._kirli, self.son_etki = None, False, None

    def ac(self, yol: str | Path) -> None:
        with self._kilit:
            self._yukle(pj.ac(yol), str(yol))

    def ac_bayt(self, veri: bytes) -> None:
        with tempfile.TemporaryDirectory() as d:
            gecici = Path(d) / f"yuklenen{pj.UZANTI}"
            gecici.write_bytes(veri)
            p = pj.ac(gecici)
        with self._kilit:
            self._yukle(p, None)

    def ornek(self, ad: str) -> None:
        if ad not in ornekler_37.ORNEK_PROJELER:
            raise KeyError(f"bilinmeyen örnek proje: {ad!r}")
        p = ornekler_37.ornek_proje(ad)
        with self._kilit:
            self._yukle(p, None)

    def kaydet(self, yol: str | Path | None = None) -> Path:
        with self._kilit:
            hedef = yol if yol is not None else self._yol
            if hedef is None:
                raise ProjeError("kaydedilecek yol yok: önce bir dosya yolu verin")
            p = Path(hedef).expanduser()
            if p.suffix != pj.UZANTI:
                raise ProjeError(f"proje dosyası {pj.UZANTI} uzantılı olmalı: {p.name}")
            if not p.is_absolute():
                VARSAYILAN_KLASOR.mkdir(parents=True, exist_ok=True)
                p = VARSAYILAN_KLASOR / p
            pj.kaydet(self.proje, p)
            self._yol = str(hedef) if Path(str(hedef)).is_absolute() else str(p)
            self._kirli = False
            return p

    def bayt(self) -> bytes:
        """GET /api/proje/indir: güncel projenin .3dc baytları."""
        return pj.proje_baytlari(self.proje)

    # ----------------------------------------------------- SPEC 54 §5 otomatik kayıt

    def kurtarma_adimi(self, simdi: float | None = None) -> bool:
        """Zamanı geldiyse kurtarma yazımını arka planda başlatır; başladıysa True."""
        raise NotImplementedError("SPEC 54: Kabuk.kurtarma_adimi")

    def kurtarma_bekle(self, zaman_asimi: float = 10.0) -> bool:
        """Süren kurtarma yazımının bitmesini bekler; bittiyse True."""
        raise NotImplementedError("SPEC 54: Kabuk.kurtarma_bekle")

    def zamanlayici_baslat(self, aralik: float = 1.0) -> None:
        raise NotImplementedError("SPEC 54: Kabuk.zamanlayici_baslat")

    def zamanlayici_durdur(self) -> None:
        raise NotImplementedError("SPEC 54: Kabuk.zamanlayici_durdur")

    def kurtarma_durumu(self) -> dict:
        """GET /api/proje/kurtarma: {"bulunan", "adsizlar", "uyarilar"}."""
        raise NotImplementedError("SPEC 54: Kabuk.kurtarma_durumu")

    def kurtarma_sec(self, secim: str, yol: str | None = None) -> str | None:
        """ "kurtar" | "yoksay" | "ikisi"; "ikisi" kopyanın yolunu döndürür."""
        raise NotImplementedError("SPEC 54: Kabuk.kurtarma_sec")


# ---------------------------------------------------------------- FastAPI bağlantısı

_SON: Kabuk | None = None  # en son kurulan kabuk (kabuğun kendi bölümü için)


def _kabuk_al(app: FastAPI) -> Kabuk:
    k = getattr(app.state, "kabuk", None)
    if k is None:
        liste = getattr(app.state, "ekranlar", None)
        k = Kabuk(liste if liste is not None else ekranlar())
        app.state.kabuk = k
    return k


def _hata(e: Exception, k: Kabuk) -> JSONResponse:
    govde = {"detail": str(e.args[0]) if isinstance(e, KeyError) and e.args else str(e)}
    if k.son_hata_bolumu is not None:
        govde["bolum"] = k.son_hata_bolumu
    return JSONResponse(govde, status_code=422)


def _router(app: FastAPI) -> APIRouter:
    r = APIRouter(prefix=ONEK)

    def calis(f, *a):
        k = _kabuk_al(app)
        k.son_hata_bolumu = None
        try:
            return f(k, *a)
        except CEKIRDEK_HATALARI as e:
            return _hata(e, k)

    def yanit(k: Kabuk, etki: Etki) -> dict:
        return {"etki": etki, "proje": k.durum()}

    @r.get("")
    def durum() -> dict:
        return _kabuk_al(app).durum()

    @r.get("/gecmis")
    def gecmis() -> dict:
        return _kabuk_al(app).gecmis()

    @r.post("/yeni")
    def yeni(govde: dict) -> dict:
        return calis(lambda k: (k.yeni(govde.get("ad", "adsız")), k.durum())[1])

    @r.post("/ac")
    def ac(govde: dict) -> dict:
        if not isinstance(govde.get("yol"), str):
            raise HTTPException(422, "yol gerekli")
        return calis(lambda k: (k.ac(govde["yol"]), k.durum())[1])

    @r.post("/kaydet")
    def kaydet(govde: dict) -> dict:
        return calis(lambda k: (k.kaydet(govde.get("yol")), k.durum())[1])

    @r.get("/indir")
    def indir() -> Response:
        k = _kabuk_al(app)
        ad = "".join(c if (c.isascii() and c.isalnum()) or c in "-_" else "_" for c in k.proje.ad) or "proje"
        return Response(
            k.bayt(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{ad}{pj.UZANTI}"'},
        )

    @r.post("/yukle")
    async def yukle(istek: Request) -> dict:
        veri = await istek.body()
        return calis(lambda k: (k.ac_bayt(veri), k.durum())[1])

    @r.post("/degistir")
    def degistir(govde: dict) -> dict:
        etiket = govde.get("etiket") or "değişiklik"
        return calis(lambda k: yanit(k, k.degistir(govde.get("yamalar"), etiket, bool(govde.get("onizle")))))

    @r.post("/geri-al")
    def geri_al() -> dict:
        k = _kabuk_al(app)
        if k.durum()["geri_al"] is None:
            raise HTTPException(409, "geri alınacak değişiklik yok")
        return calis(lambda k: yanit(k, k.geri_al()))

    @r.post("/yinele")
    def yinele() -> dict:
        k = _kabuk_al(app)
        if k.durum()["yinele"] is None:
            raise HTTPException(409, "yinelenecek değişiklik yok")
        return calis(lambda k: yanit(k, k.yinele()))

    @r.get("/kurtarma")
    def kurtarma() -> dict:
        return _kabuk_al(app).kurtarma_durumu()

    @r.post("/kurtarma")
    def kurtarma_sec(govde: dict) -> dict:
        def sec(k: Kabuk) -> dict:
            kopya = k.kurtarma_sec(govde.get("secim"), govde.get("yol"))
            return {"proje": k.durum(), "kopya": kopya}

        return calis(sec)

    @r.get("/ornekler")
    def ornekler() -> dict:
        return {"ornekler": list(ornekler_37.ORNEK_PROJELER)}

    @r.post("/ornek/{ad}")
    def ornek(ad: str) -> dict:
        if ad not in ornekler_37.ORNEK_PROJELER:
            raise HTTPException(404, f"bilinmeyen örnek proje: {ad!r}")
        return calis(lambda k: (k.ornek(ad), k.durum())[1])

    return r


def _yakalanir(istek: Request) -> bool:
    yol = istek.url.path
    return (
        istek.method not in ("GET", "HEAD", "OPTIONS")
        and yol.startswith("/api/")
        and not (yol == ONEK or yol.startswith(ONEK + "/"))
    )


def kur(app: FastAPI) -> None:
    """`/api/proje` router'ını ve yakalama ara katmanını uygulamaya bağlar (A3 Ekran.kur)."""
    app.include_router(_router(app))

    @app.middleware("http")
    async def yakala(istek: Request, sonraki):
        if not _yakalanir(istek):
            return await sonraki(istek)
        _kabuk_al(app)  # kabuk ekranın değişikliğinden önce kurulsun (başlangıç durumu)
        yanit = await sonraki(istek)
        if not 200 <= yanit.status_code < 300:
            return yanit
        yol = istek.url.path
        etiket = istek.headers.get(ETIKET_BASLIGI) or f"{istek.method} {yol}"
        ekran = None
        if yol.startswith("/api/ekran/"):
            ekran = yol.removeprefix("/api/ekran/").split("/", 1)[0] or None
        k = _kabuk_al(app)
        k.son_hata_bolumu = None
        try:
            k.yakala(etiket, ekran)
        except CEKIRDEK_HATALARI as e:
            return _hata(e, k)
        return yanit


# ---------------------------------------------------------------- A3 kaydı


def _disa_aktar() -> dict:
    if _SON is not None:
        return pj._kopya(_SON._proje.bolumler[BOLUM])
    return dict(pj.bos_proje("adsız").bolumler[BOLUM])


def _ice_aktar(belge: dict, onbellek: Mapping[str, bytes]) -> None:
    pj._bolum_denetle(BOLUM, belge)
    if _SON is not None:
        bolumler = {**_SON._proje.bolumler, BOLUM: pj._kopya(belge)}
        _SON._proje = replace(_SON._proje, bolumler=bolumler)


EKRAN = Ekran(
    ad=AD,
    baslik="Proje",
    sira=0,
    bolum=BOLUM,
    disa_aktar=_disa_aktar,
    ice_aktar=_ice_aktar,
    kur=kur,
)
