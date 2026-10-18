"""
SPEC 25 — Tek iplik: parametre bağları, yeniden hesaplama zinciri ve ikiye bölme önerisi.

Bir parametre değişince parça → torna işi (yol, G-code, sim, süre) → montaj (çözüm, girişim) birlikte
yeniden hesaplanır. Öneri: v(p) = girişim hacmi; p₀'da v > 0 iken p₀'a en yakın v = 0 sınırı
ikiye bölmeyle |Δp| ≤ eps içinde bulunur ve v = 0 tarafındaki uç önerilir. Bulunamazsa öneri yok
(sahte sayı yok, altın kural 5).

Saf Python, web bağımlılığı yok. Durum (`Depo`) tek kullanıcılık sunucu belleğindedir.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field

from cam.model import CamError

ONERI_EPS = 1e-3  # parametre birimi (mm)
ONERI_EN_FAZLA = 40  # en fazla v(p) değerlendirmesi


@dataclass(frozen=True)
class Bag:
    """Bir iş parametresinin hangi parçaları değiştirdiği. min ≤ deger ≤ max."""

    is_ad: str
    anahtar: str
    deger: float
    min: float
    max: float
    parcalar: tuple[str, ...]


@dataclass(frozen=True)
class Oneri:
    """İkiye bölme sonucu. deger None → öneri yok, `neden` açıklar."""

    deger: float | None
    hacim: float | None
    neden: str | None
    degerlendirme: int


class _Butce(Exception):
    """Değerlendirme hakkı bitti."""


def oneri(
    v: Callable[[float], float],
    p0: float,
    pmin: float,
    pmax: float,
    eps: float = ONERI_EPS,
    en_fazla: int = ONERI_EN_FAZLA,
) -> Oneri:
    """v(p0) > 0 iken [pmin, pmax] içinde p0'a en yakın v = 0 sınırını ikiye bölmeyle bulur (K16).

    v = 0 olan her uç için p0 ile o uç arasında ikiye bölünür (|Δp| ≤ eps); sınırlardan p0'a en yakını,
    v = 0 tarafındaki ucuyla önerilir. Hak (en_fazla) eps'e inmeden biterse öneri yok.
    """
    if not (pmin <= p0 <= pmax) or not eps > 0:
        raise CamError(f"Öneri: p0 aralıkta ve eps > 0 olmalı (p0={p0}, [{pmin}, {pmax}], eps={eps})")
    sayac = 0

    def deger(p: float) -> float:
        nonlocal sayac
        if sayac >= en_fazla:
            raise _Butce
        sayac += 1
        return float(v(p))

    def yok(neden: str) -> Oneri:
        return Oneri(None, None, neden, sayac)

    try:
        if deger(p0) <= 0.0:
            return yok("Bu değerde girişim yok; öneri gerekmiyor")
        uclar = [u for u in (pmin, pmax) if u != p0 and deger(u) <= 0.0]
        if not uclar:
            return yok(f"Aralığın iki ucunda da girişim var [{pmin}, {pmax}]; girişimi sıfırlayan değer yok")
        adaylar = []
        for u in sorted(uclar, key=lambda u: abs(u - p0)):
            a, b = p0, u  # v(a) > 0, v(b) = 0
            while abs(b - a) > eps:
                m = 0.5 * (a + b)
                if deger(m) > 0.0:
                    a = m
                else:
                    b = m
            adaylar.append(b)
    except _Butce:
        return yok(f"{en_fazla} değerlendirmede |Δp| ≤ {eps} sınırına inilemedi")
    p = min(adaylar, key=lambda b: abs(b - p0))
    return Oneri(p, 0.0, None, sayac)


def _varsayilan() -> dict[str, dict[str, float]]:
    from tezgah.ornekler_25 import VARSAYILAN

    return copy.deepcopy(VARSAYILAN)


@dataclass
class Depo:
    """Sunucu belleğindeki güncel parametreler: iş adı → {anahtar: değer}.

    `sifirla` örnek değerlerine döndürür. Hesaplanan `Is` / `Montaj` sözlükleri parametre değerleriyle
    önbelleğe alınır (aynı değerde yeniden hesap yok).
    """

    parametreler: dict[str, dict[str, float]] = field(default_factory=_varsayilan)
    # torna işi adı → işlem sırası → {anahtar: değer} (müfettiş; ornekler_25.ISLEM_VARSAYILAN üstüne)
    islem_parametreleri: dict[str, dict[int, dict[str, float]]] = field(default_factory=dict)
    _onbellek: dict = field(default_factory=dict, repr=False, compare=False)

    def sifirla(self) -> None:
        self.parametreler = _varsayilan()
        self.islem_parametreleri = {}

    def _anahtar(self, tur: str, ad: str) -> tuple:
        def dondur(d: dict) -> tuple:
            return tuple(sorted((k, dondur(v) if isinstance(v, dict) else v) for k, v in d.items()))

        return (tur, ad, dondur(self.parametreler), dondur(self.islem_parametreleri))

    def _bellek(self, tur: str, ad: str, hesap: Callable[[], object]):
        k = self._anahtar(tur, ad)
        if k not in self._onbellek:
            self._onbellek[k] = hesap()
        return self._onbellek[k]

    def torna_isi(self, ad: str):
        """Güncel parametrelerle `TornaIsi` (tezgah.ornekler_25, önbellekli). Bilinmeyen ad → KeyError."""
        from tezgah import ornekler_25 as o

        if ad not in o.TORNA_ISLERI:
            raise KeyError(f"Bilinmeyen torna işi: '{ad}'")
        return self._bellek(
            "torna", ad, lambda: getattr(o, ad)(self.parametreler.get(ad), self.islem_parametreleri.get(ad))
        )

    def montaj(self, ad: str):
        """Güncel parametrelerle `MontajTanimi` (önbellekli). Bilinmeyen ad → KeyError."""
        from tezgah import ornekler_25 as o

        if ad not in o.MONTAJLAR:
            raise KeyError(f"Bilinmeyen montaj: '{ad}'")
        return self._bellek("tanim", ad, lambda: getattr(o, ad)(self.parametreler))

    def is_json(self, ad: str) -> dict:
        """Güncel parametrelerle torna işinin `Is` sözlüğü (önbellekli). Bilinmeyen ad → KeyError."""
        from tezgah import torna

        return self._bellek("is", ad, lambda: torna.is_json(self.torna_isi(ad)))

    def montaj_json(self, ad: str) -> dict:
        """Güncel parametrelerle `Montaj` sözlüğü (önbellekli). Bilinmeyen ad → KeyError."""
        from tezgah.montaj import montaj_json

        return self._bellek("montaj", ad, lambda: montaj_json(self.montaj(ad)))

    def _bag(self, montaj_ad: str, is_ad: str, anahtar: str) -> Bag:
        tanim = self.montaj(montaj_ad)
        for b in tanim.baglar:
            if (b.is_ad, b.anahtar) == (is_ad, anahtar):
                return b
        raise CamError(f"'{montaj_ad}' montajında {is_ad}.{anahtar} parametre bağı yok")

    def ayarla(self, montaj_ad: str, is_ad: str, anahtar: str, deger: float) -> dict:
        """Parametreyi ayarlar; {"montaj": Montaj, "is": Is, "sure_farki": s} (K15).

        Aralık dışı → CamError. sure_farki = yeni − eski toplam süre [s].
        """
        from tezgah import ornekler_25 as o

        self._bag(montaj_ad, is_ad, anahtar)
        yeni = copy.deepcopy(self.parametreler)
        yeni[is_ad][anahtar] = deger
        o.parametre_dogrula(is_ad, yeni[is_ad])  # doğrula: aralık dışı → CamError (parametre değişmez)
        eski_sure = self.is_json(is_ad)["sure"]["toplam"]
        self.parametreler = yeni
        Is = self.is_json(is_ad)
        return {
            "montaj": self.montaj_json(montaj_ad),
            "is": Is,
            "sure_farki": Is["sure"]["toplam"] - eski_sure,
        }

    def oneri(self, montaj_ad: str, is_ad: str, anahtar: str, cift: tuple[str, str]) -> Oneri:
        """Bağlı parametre için girişimi sıfırlayan öneri (K16). Parametreyi değiştirmez."""
        from tezgah import ornekler_25 as o
        from tezgah.montaj import cift_hacmi

        bag = self._bag(montaj_ad, is_ad, anahtar)
        a, b = cift

        def v(p: float) -> float:
            yeni = copy.deepcopy(self.parametreler)
            yeni[is_ad][anahtar] = p
            return cift_hacmi(getattr(o, montaj_ad)(yeni), a, b)

        return oneri(v, self.parametreler[is_ad][anahtar], bag.min, bag.max)

    def islem_ayarla(self, is_ad: str, islem: int, anahtar: str, deger: float) -> dict:
        """Torna işinde bir işlemin kesme değerini ayarlar (müfettiş); {"is": Is, "sure_farki": s}.

        Bilinmeyen iş → KeyError; bilinmeyen işlem / anahtar, geçersiz değer → CamError (değer değişmez).
        """
        from tezgah import ornekler_25 as o

        if is_ad not in o.TORNA_ISLERI:
            raise KeyError(f"Bilinmeyen torna işi: '{is_ad}'")
        yeni = copy.deepcopy(self.islem_parametreleri)
        yeni.setdefault(is_ad, {}).setdefault(islem, {})[anahtar] = deger
        o.islem_parametre_dogrula(yeni[is_ad])
        eski_sure = self.is_json(is_ad)["sure"]["toplam"]
        onceki = self.islem_parametreleri
        self.islem_parametreleri = yeni
        try:
            Is = self.is_json(is_ad)  # SPEC 20 reddederse (ör. çok büyük paso) eski değerler kalır
        except Exception:
            self.islem_parametreleri = onceki
            raise
        return {"is": Is, "sure_farki": Is["sure"]["toplam"] - eski_sure}

    def disa_aktar(self) -> dict:
        """A3 "torna_isleri" bölümü (SPEC 37 tablosu `{ad: {parametreler}}`):
        {"sema", ad: {"parametreler", "islem_parametreleri"}}.

        islem_parametreleri'nde işlem sırası metin anahtardır (JSON); değiştirilmemiş iş için boş.
        """
        from tezgah import SEMA

        belge: dict = {"sema": SEMA}
        for ad, p in self.parametreler.items():
            Q = self.islem_parametreleri.get(ad, {})
            belge[ad] = {
                "parametreler": copy.deepcopy(p),
                "islem_parametreleri": {str(i): dict(d) for i, d in sorted(Q.items())},
            }
        return belge

    def ice_aktar(self, belge: dict) -> None:
        """`disa_aktar` belgesini yükler. Önce hepsi doğrulanır; belgede olmayan iş varsayılana döner.

        Bozuk belge → ValueError / KeyError / TypeError, çekirdeğin reddettiği değer → CamError.
        Atomik: hata olursa depo değişmez.
        """
        from tezgah import SEMA
        from tezgah import ornekler_25 as o

        sema = belge["sema"]
        if not isinstance(sema, int) or isinstance(sema, bool) or sema != SEMA:
            raise ValueError(f"'torna_isleri' bölümünün şeması {SEMA} olmalı, {sema!r} verildi")
        isler = {ad: d for ad, d in belge.items() if ad != "sema"}
        bilinmeyen = sorted(set(isler) - set(o.TORNA_ISLERI))
        if bilinmeyen:
            raise KeyError(f"Bilinmeyen torna işi: {bilinmeyen}")
        yeni = _varsayilan()
        yeni_q: dict[str, dict[int, dict[str, float]]] = {}
        for ad, d in isler.items():
            if not isinstance(d, dict):
                raise TypeError(f"{ad!r} sözlük olmalı, {type(d).__name__} verildi")
            yeni[ad] = o.parametre_dogrula(ad, d["parametreler"])
            Q = d.get("islem_parametreleri", {})
            if not isinstance(Q, dict):
                raise TypeError(f"islem_parametreleri sözlük olmalı, {type(Q).__name__} verildi")
            if not Q:
                continue
            q = {int(i): {str(k): v for k, v in P.items()} for i, P in Q.items()}
            o.islem_parametre_dogrula(q)
            yeni_q[ad] = {i: {k: float(v) for k, v in P.items()} for i, P in q.items()}
        self.parametreler, self.islem_parametreleri = yeni, yeni_q
