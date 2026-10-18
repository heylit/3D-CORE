"""
SPEC 26 — model geçmişi: doğrusal adım listesi, her değişiklikte baştan kurulur (saf, deterministik).

    Model = {sema: 1, ad, parametreler: {ad: ifade}, adimlar: [Adim]}
    Adim  = {kimlik, tur: "eskiz", duzlem: Duzlem, eskiz: Sketch.to_dict(), olculer: {kisit_sirasi: ifade}}
          | {kimlik, tur: "ekstruzyon", eskiz: kimlik, bolgeler: [i] | "hepsi", mesafe: ifade,
             yon: "ileri" | "geri" | "simetrik", islem: "yeni" | "ekle" | "kes",
             bitis: "mesafe" | "boydan_boya"}
          | {kimlik, tur: "delik", eskiz: kimlik, noktalar: [nokta kimliği],
             cesit: "duz" | "havsa" | "lamba" | "dis", d: ifade, derinlik: ifade | None, ...}
    Duzlem = {tur: "XY" | "XZ" | "YZ", ofset: ifade}
           | {tur: "yuz", adim: kimlik, yuz: index, plane: Plane.to_dict()}

Kontrol sözlükleri SPEC 24 biçimindedir (tezgah/kopru.py). FastAPI'siz test edilir.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geometry.extrude import extrude, extrude_add, extrude_cut
from geometry.features import hole
from geometry.holes import counterbore_hole, countersink_hole, inclined_hole, tapped_hole
from geometry.part import GeometryError, Part
from sketch.model import Plane, Sketch, SketchError, SketchRegion
from sketch.regions import area, regions
from sketch.solver import solve
from tezgah.ifade import IfadeError, degerlendir, parametreleri_coz

HACIM_REL = 1e-6  # K9: geometri hacmi = alan · |d|
NORMAL_TOL = 1e-9  # yüz düzlemi: aynı normal
UZAKLIK_TOL = 1e-6  # mm, yüz düzlemi: düzlem uzaklığı


@dataclass
class AdimRaporu:
    """Bir adımın sonucu. eskiz: dof, freedom, celiski; ekstrüzyon: alanlar, dV; hata: çekirdeğin metni."""

    kimlik: str
    tur: str
    hata: str | None = None
    dof: int | None = None
    freedom: dict[str, int] = field(default_factory=dict)
    celiski: tuple[int, ...] = ()
    alanlar: tuple[float, ...] = ()  # seçilen bölgelerin alanları, mm²
    dV: float | None = None  # hacim değişimi, mm³


@dataclass
class Kesim:
    """Tasarım niyeti kaydı ("Tezgah'a gönder" için): bir kes adımının bölgeleri ve düzlemi."""

    kimlik: str
    bolgeler: tuple[SketchRegion, ...]
    plane: Plane
    derinlik: float | None  # None = boydan boya


@dataclass
class Rapor:
    adimlar: list[AdimRaporu] = field(default_factory=list)
    kontroller: list[dict] = field(default_factory=list)
    kesimler: list[Kesim] = field(default_factory=list)

    @property
    def hata(self) -> AdimRaporu | None:
        """İlk başarısız adım (yoksa None)."""
        return next((a for a in self.adimlar if a.hata is not None), None)


def _kontrol(kimlik: str, baslik: str, deger, birim: str, durum: str, aciklama: str, spec: str) -> dict:
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "deger": deger,
        "birim": birim,
        "durum": durum,
        "aciklama": aciklama,
        "spec": spec,
    }


class _Kurulum:
    """Bir insa() çağrısının durumu."""

    def __init__(self, model: dict):
        self.P = parametreleri_coz(model.get("parametreler", {}))
        self.parca: Part | None = None
        self.eskizler: dict[str, Sketch] = {}
        self.rapor = Rapor()

    def deger(self, ifade) -> float:
        return degerlendir(ifade, self.P)

    # --- eskiz ---

    def _duzlem(self, adim: dict) -> Plane:
        d = adim["duzlem"]
        if d["tur"] in ("XY", "XZ", "YZ"):
            pl = getattr(Plane, d["tur"])()
            o = self.deger(d.get("ofset", 0))
            return Plane(pl.origin + o * pl.normal, pl.normal, pl.xdir)
        if d["tur"] != "yuz":
            raise SketchError(f"Bilinmeyen düzlem türü: {d['tur']!r}")
        pl = Plane.from_dict(d["plane"])
        self._duzlem_denetle(adim["kimlik"], pl)
        return pl

    def _duzlem_denetle(self, kimlik: str, pl: Plane) -> None:
        """Saklanan düzlem önceki parçanın bir düzlemsel yüzüyle hâlâ çakışıyor mu (sessiz kayma yok)."""
        cakisik = self.parca is not None and any(
            np.allclose(f.normal, pl.normal, atol=NORMAL_TOL)
            and abs(float((f.origin - pl.origin) @ pl.normal)) <= UZAKLIK_TOL
            for f in self.parca.planar_faces()
        )
        self.rapor.kontroller.append(
            _kontrol(
                "eskiz_duzlemi_kopuk",
                f"Eskiz düzlemi ({kimlik})",
                None,
                "",
                "tamam" if cakisik else "uyari",
                "Saklanan düzlem parçanın bir yüzüyle çakışıyor"
                if cakisik
                else "Saklanan düzlem artık parçanın hiçbir yüzüyle çakışmıyor; "
                "adım saklanan düzlemle çalıştı",
                "SPEC 26",
            )
        )

    def eskiz(self, adim: dict, ar: AdimRaporu) -> None:
        sk = Sketch.from_dict(adim["eskiz"])
        sk.plane = self._duzlem(adim)
        for k, ifade in adim.get("olculer", {}).items():
            i = int(k)
            if not 0 <= i < len(sk.constraints):
                raise SketchError(f"Ölçü: {i} numaralı kısıt yok")
            sk.constraints[i].value = self.deger(ifade)
        sk.validate()
        res = solve(sk)
        res.apply(sk)
        ar.dof, ar.freedom = res.dof, dict(res.freedom)
        self.eskizler[adim["kimlik"]] = sk
        self.rapor.kontroller.append(
            _kontrol(
                f"eskiz_dof_{adim['kimlik']}",
                f"Eskiz serbestliği ({adim['kimlik']})",
                res.dof,
                "",
                "tamam" if res.dof == 0 else "uyari",
                "Tam tanımlı" if res.dof == 0 else f"Eksik tanımlı: {res.dof} serbestlik kaldı",
                "SPEC 17",
            )
        )

    def _eskiz_al(self, adim: dict) -> Sketch:
        k = adim["eskiz"]
        if k not in self.eskizler:
            raise SketchError(f"Adım {adim['kimlik']}: önceki adımlarda {k!r} eskizi yok")
        return self.eskizler[k]

    # --- ekstrüzyon ---

    def ekstruzyon(self, adim: dict, ar: AdimRaporu) -> None:
        sk = self._eskiz_al(adim)
        tum = regions(sk)
        sec = adim.get("bolgeler", "hepsi")
        if sec == "hepsi":
            bol = tum
        else:
            if any(not (isinstance(i, int) and 0 <= i < len(tum)) for i in sec):
                raise GeometryError(f"Bölge seçimi geçersiz: {sec} ({len(tum)} bölge var)")
            bol = [tum[i] for i in sec]
        ar.alanlar = tuple(area(b) for b in bol)
        islem, bitis, yon = adim.get("islem", "yeni"), adim.get("bitis", "mesafe"), adim.get("yon", "ileri")
        if yon not in ("ileri", "geri", "simetrik"):
            raise GeometryError(f"Bilinmeyen yön: {yon!r}")
        d = None if bitis == "boydan_boya" and islem == "kes" else self.deger(adim["mesafe"])
        V0 = 0.0 if self.parca is None else self.parca.volume
        pl = sk.plane
        if islem == "yeni":
            if self.parca is not None:
                raise GeometryError("'yeni' gövde: parça zaten var; 'ekle' ya da 'kes' kullanın")
            self.parca = extrude(bol, pl, -d if yon == "geri" else d, symmetric=yon == "simetrik")
        elif islem == "ekle":
            if self.parca is None:
                raise GeometryError("'ekle': önce bir gövde gerekir")
            self.parca = extrude_add(self.parca, bol, pl, -d if yon == "geri" else d, yon == "simetrik")
        elif islem == "kes":
            if self.parca is None:
                raise GeometryError("'kes': kesilecek gövde yok")
            if yon == "simetrik":
                raise GeometryError("'kes' adımında simetrik yön yok")
            if yon == "geri":
                pl = Plane(pl.origin, -pl.normal, pl.xdir)
            if bitis not in ("mesafe", "boydan_boya"):
                raise GeometryError(f"Bilinmeyen bitiş: {bitis!r}")
            self.parca = extrude_cut(self.parca, bol, pl, d)
            self.rapor.kesimler.append(Kesim(adim["kimlik"], tuple(bol), pl, d))
        else:
            raise GeometryError(f"Bilinmeyen işlem: {islem!r}")
        ar.dV = self.parca.volume - V0
        self._hacim_kontrolu(adim["kimlik"], islem, sum(ar.alanlar), d, ar.dV)
        self._step_kontrolu(adim["kimlik"])

    def _hacim_kontrolu(self, kimlik: str, islem: str, A: float, d: float | None, dV: float) -> None:
        if d is None:
            return  # boydan boya: kapalı form yok
        beklenen = A * abs(d)
        olcum = abs(dV)
        uygun = math.isclose(olcum, beklenen, rel_tol=HACIM_REL)
        durum = "tamam" if uygun else ("hata" if islem == "yeni" else "uyari")
        self.rapor.kontroller.append(
            _kontrol(
                f"hacim_{kimlik}",
                f"Hacim = alan · |d| ({kimlik})",
                olcum,
                "mm³",
                durum,
                f"Geometri {olcum:.6g} mm³, alan · |d| = {beklenen:.6g} mm³"
                + ("" if uygun or islem == "yeni" else " (gövde bölgeyi tam kaplamıyor)"),
                "SPEC 26",
            )
        )

    def _step_kontrolu(self, kimlik: str) -> None:
        with tempfile.TemporaryDirectory() as td:
            yol = Path(td) / "parca.step"
            self.parca.to_step(yol)
            V = Part.from_step(yol).volume
        uygun = math.isclose(V, self.parca.volume, rel_tol=HACIM_REL)
        self.rapor.kontroller.append(
            _kontrol(
                f"step_{kimlik}",
                f"STEP gidiş-dönüş ({kimlik})",
                V,
                "mm³",
                "tamam" if uygun else "hata",
                f"STEP'ten okunan hacim {V:.6g} mm³, parça {self.parca.volume:.6g} mm³",
                "SPEC 26",
            )
        )

    # --- delik ---

    def delik(self, adim: dict, ar: AdimRaporu) -> None:
        if self.parca is None:
            raise GeometryError("Delik: delinecek gövde yok")
        sk = self._eskiz_al(adim)
        pl = sk.plane
        cesit = adim.get("cesit", "duz")
        d = self.deger(adim["d"])
        t = None if adim.get("derinlik") is None else self.deger(adim["derinlik"])
        ust = bool(np.allclose(pl.normal, (0.0, 0.0, 1.0), atol=NORMAL_TOL))
        if not ust and cesit != "duz":
            raise GeometryError(f"Bu yüzde yalnız düz delik açılabilir ({cesit!r} yalnız +Z yüzde)")
        V0 = self.parca.volume
        p = self.parca
        for nk in adim["noktalar"]:
            if nk not in sk.points:
                raise SketchError(f"Delik: eskizde {nk!r} noktası yok")
            q = pl.to_world((sk.points[nk].x, sk.points[nk].y))
            x, y = float(q[0]), float(q[1])
            if not ust:
                p = inclined_hole(p, q, -pl.normal, d, t)
            elif cesit == "duz":
                p = hole(p, x, y, d, t)
            elif cesit == "havsa":
                p = countersink_hole(p, x, y, d, self.deger(adim["csk_d"]), self.deger(adim["csk_angle"]), t)
            elif cesit == "lamba":
                p = counterbore_hole(
                    p, x, y, d=d, cbore_d=self.deger(adim["cbore_d"]),
                    cbore_depth=self.deger(adim["cbore_depth"]), depth=t,
                )  # fmt: skip
            elif cesit == "dis":
                p = tapped_hole(p, x, y, adim["thread"], depth=t)
            else:
                raise GeometryError(f"Bilinmeyen delik çeşidi: {cesit!r}")
        self.parca = p
        ar.dV = p.volume - V0


ADIMLAR = {"eskiz": _Kurulum.eskiz, "ekstruzyon": _Kurulum.ekstruzyon, "delik": _Kurulum.delik}
HATALAR = (SketchError, GeometryError, IfadeError, KeyError, ValueError, TypeError)


def insa(model: dict, k: int | None = None) -> tuple[Part | None, Rapor]:
    """Modeli baştan kurar; k verilirse ilk k adımda durur.

    Parametreleri değerlendirir, ölçüleri eskizlere yazar, SPEC 17 ile çözer, bölgeleri çıkarır, katı
    işlemleri sırayla uygular. Bir adım başarısızsa kurulum orada durur, hata adım kimliğiyle Rapor'a
    yazılır ve önceki adımların parçası döner. Yüze bağlı eskizin düzlemi önceki parçanın bir yüzüyle
    çakışmıyorsa Kontrol(durum="uyari", kimlik="eskiz_duzlemi_kopuk").
    """
    kur = _Kurulum(model)
    adimlar = model.get("adimlar", [])
    for adim in adimlar if k is None else adimlar[:k]:
        ar = AdimRaporu(kimlik=str(adim.get("kimlik", "")), tur=str(adim.get("tur", "")))
        kur.rapor.adimlar.append(ar)
        try:
            if ar.tur not in ADIMLAR:
                raise SketchError(f"Bilinmeyen adım türü: {ar.tur!r}")
            ADIMLAR[ar.tur](kur, adim, ar)
        except HATALAR as e:
            ar.hata = str(e) or type(e).__name__
            if isinstance(e, SketchError):
                ar.celiski = tuple(e.constraints)
            break
    return kur.parca, kur.rapor


# --- Örnek model (uydurma geometri) -------------------------------------------------------------------


def _dikdortgen(x0: float, y0: float, w: float, h: float, z: float) -> dict:
    """Sol alt köşesi sabit, H/V ve iki boyla tam tanımlı dikdörtgen eskizi (kısıt 4: w, 5: h)."""
    return {
        "sema": 1,
        "plane": Plane((0.0, 0.0, z), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)).to_dict(),
        "points": {
            "a": {"x": x0, "y": y0, "fixed": True},
            "b": {"x": x0 + w, "y": y0, "fixed": False},
            "c": {"x": x0 + w, "y": y0 + h, "fixed": False},
            "d": {"x": x0, "y": y0 + h, "fixed": False},
        },
        "entities": {
            "alt": {"tur": "line", "p0": "a", "p1": "b", "construction": False},
            "sag": {"tur": "line", "p0": "b", "p1": "c", "construction": False},
            "ust": {"tur": "line", "p0": "c", "p1": "d", "construction": False},
            "sol": {"tur": "line", "p0": "d", "p1": "a", "construction": False},
        },
        "constraints": [
            {"type": t, "refs": [r], "value": v, "side": 0, "internal": False}
            for t, r, v in (
                ("horizontal", "alt", None),
                ("vertical", "sag", None),
                ("horizontal", "ust", None),
                ("vertical", "sol", None),
                ("length", "alt", w),
                ("length", "sag", h),
            )
        ],
    }


def _flans() -> dict:
    """100 × 70 × 12 plaka, ortada 36 × 24 kör cep 8 mm, köşelerde 4 adet Ø6.6 boydan boya delik."""
    noktalar = {"h1": (12.0, 12.0), "h2": (88.0, 12.0), "h3": (88.0, 58.0), "h4": (12.0, 58.0)}
    delik_eskizi = {
        "sema": 1,
        "plane": Plane((0.0, 0.0, 12.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)).to_dict(),
        "points": {k: {"x": x, "y": y, "fixed": True} for k, (x, y) in noktalar.items()},
        "entities": {},
        "constraints": [],
    }
    ust = {"tur": "XY", "ofset": "=kalinlik"}
    return {
        "sema": 1,
        "ad": "flans",
        "parametreler": {"genislik": "100", "boy": "70", "kalinlik": "12", "cep_derinligi": "8"},
        "adimlar": [
            {
                "kimlik": "plaka_eskizi",
                "tur": "eskiz",
                "duzlem": {"tur": "XY", "ofset": 0},
                "eskiz": _dikdortgen(0.0, 0.0, 100.0, 70.0, 0.0),
                "olculer": {"4": "=genislik", "5": "=boy"},
            },
            {
                "kimlik": "plaka",
                "tur": "ekstruzyon",
                "eskiz": "plaka_eskizi",
                "bolgeler": "hepsi",
                "mesafe": "=kalinlik",
                "yon": "ileri",
                "islem": "yeni",
                "bitis": "mesafe",
            },
            {
                "kimlik": "cep_eskizi",
                "tur": "eskiz",
                "duzlem": ust,
                "eskiz": _dikdortgen(32.0, 23.0, 36.0, 24.0, 12.0),
                "olculer": {},
            },
            {
                "kimlik": "cep",
                "tur": "ekstruzyon",
                "eskiz": "cep_eskizi",
                "bolgeler": "hepsi",
                "mesafe": "=cep_derinligi",
                "yon": "ileri",
                "islem": "kes",
                "bitis": "mesafe",
            },
            {"kimlik": "delik_eskizi", "tur": "eskiz", "duzlem": ust, "eskiz": delik_eskizi, "olculer": {}},
            {
                "kimlik": "delikler",
                "tur": "delik",
                "eskiz": "delik_eskizi",
                "noktalar": list(noktalar),
                "cesit": "duz",
                "d": 6.6,
                "derinlik": None,
            },
        ],
    }


ORNEK_MODELLER = {"flans": _flans}


def ornek_model(ad: str = "flans") -> dict:
    """Uydurma örnek model. "flans": dış dikdörtgen plaka, ortada 8 mm kör cep, 4 boydan boya delik (K8)."""
    if ad not in ORNEK_MODELLER:
        raise KeyError(f"Bilinmeyen örnek model: {ad!r}")
    return ORNEK_MODELLER[ad]()
