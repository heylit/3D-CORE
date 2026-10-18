"""
SPEC 18 — Özellik ağacı: kararlı yüz referansı, döndürme, pah / yuvarlatma, desen, ayna.

Ağaç sıralı bir özellik listesidir; her özellik bir öncekinin parçasına uygulanır. Özellikler
birbirini kimlikle (`profil`, `ozellikler`) ya da kalıcı yüz adıyla (`FaceRef`, A2 arayüzü) gösterir.
Adlar özelliğin yapısından doğar ve sonraki işlemlere OCCT geçmişiyle (`Modified` / `Generated` /
`IsDeleted`, `UnifySameDomain.History`) taşınır; geometrik "en yakın yüz" geri dönüşü yoktur. Hatalı
özellik uygulanmaz, bağımlıları "atlandi" olur, bağımsız özellikler devam eder (S1). Ağaç sayısal değer
tutar; ifadeler Tezgah'tadır (S4). Birimler: mm, derece.

`sketch`'ten yalnız `sketch.model` import edilir; eskiz çözümü dışarıdan `coz` fonksiyonuyla gelir.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import build123d as bd
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer, BRepFilletAPI_MakeFillet
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopoDS import TopoDS

from geometry.desen import ayna, dairesel, dogrusal, donustur_hole
from geometry.dondur import dondur_arac, kenarlar, profil_yuzleri, uretilen, yuzler
from geometry.features import DV_MIN, PAY, block, cylinder, hole
from geometry.holes import counterbore_hole, countersink_hole, inclined_hole, tapped_hole
from geometry.part import FaceRef, GeometryError, Hole, Part
from sketch.model import Plane, SegArc, SegLine, Sketch, SketchRegion

SEMA = 1  # to_dict / from_dict sürümü

DuzlemRef = "Plane | FaceRef"  # FaceRef → yüze bağlı eskiz düzlemi kuralı (SPEC 18 Teori)
Islem = Literal["yeni", "ekle", "kes"]
Durum = Literal["tamam", "hata", "atlandi", "bastirildi"]


@dataclass(frozen=True)
class EdgeRef:
    """İki adlı yüzün ortak kenarları (pah ve yuvarlatmanın girdisi)."""

    a: FaceRef
    b: FaceRef


# --- Özellikler ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Blok:
    """SPEC 02 block; adlar xmin, xmax, ymin, ymax, zmin, zmax."""

    kimlik: str
    a: float
    b: float
    c: float
    bastir: bool = False


@dataclass(frozen=True)
class Silindir:
    """SPEC 02 cylinder; adlar alt, ust, yan."""

    kimlik: str
    r: float
    h: float
    bastir: bool = False


@dataclass(frozen=True)
class Profil:
    """Eskiz düzlemi + bölgeler. `eskiz` verilirse bölgeler kurulumda `coz(eskiz, duzlem)` ile hesaplanır."""

    kimlik: str
    duzlem: Plane | FaceRef
    bolgeler: tuple[SketchRegion, ...] = ()
    eskiz: Sketch | None = None
    bastir: bool = False


@dataclass(frozen=True)
class Ekstruzyon:
    """Adlar bas, son, yan:<src>. Takım `geometry.extrude.extrude` ile, boolean geçmiş izli kurulur."""

    kimlik: str
    profil: str
    mesafe: float
    islem: Islem = "yeni"
    yon: Literal["ileri", "geri", "simetrik"] = "ileri"
    bitis: Literal["mesafe", "boydan_boya"] = "mesafe"
    bolge_sec: tuple[int, ...] | None = None
    bastir: bool = False


@dataclass(frozen=True)
class Dondurme:
    """Profil uv'sinde eksen (nokta + yön) etrafında döndürme; adlar yan:<src>, açı < 360° ise bas, son."""

    kimlik: str
    profil: str
    eksen_p: tuple[float, float]
    eksen_y: tuple[float, float]
    aci: float = 360.0
    islem: Islem = "yeni"
    bastir: bool = False


@dataclass(frozen=True)
class Delik:
    """Düzlemdeki noktalara delik (SPEC 02 / 23, SPEC 26 "Delik adımı").

    Adlar <n>/duvar, <n>/dip, <n>/havsa, <n>/lamba_duvar, <n>/lamba_dip.
    """

    kimlik: str
    duzlem: Plane | FaceRef
    noktalar: tuple[tuple[float, float], ...]
    d: float
    derinlik: float | None = None  # None → boydan boya
    cesit: Literal["duz", "havsa", "lamba", "dis"] = "duz"
    csk_d: float = 0.0
    csk_angle: float = 0.0
    cbore_d: float = 0.0
    cbore_depth: float = 0.0
    thread: str = ""
    bastir: bool = False


@dataclass(frozen=True)
class Pah:
    """Eşit (d) ya da iki uzaklıklı (d a yüzünde, d2 b yüzünde) pah; adlar <i> ya da <i>.<j>."""

    kimlik: str
    kenarlar: tuple[EdgeRef, ...]
    d: float
    d2: float | None = None
    bastir: bool = False


@dataclass(frozen=True)
class Yuvarlatma:
    """Sabit yarıçaplı yuvarlatma; adlar <i> ya da <i>.<j>."""

    kimlik: str
    kenarlar: tuple[EdgeRef, ...]
    r: float
    bastir: bool = False


@dataclass(frozen=True)
class DogrusalDesen:
    """Kaynakların (Ekstruzyon / Dondurme ekle-kes, Delik) n1 × n2 kopyası; adlar <k>/<kaynak>/<ad>."""

    kimlik: str
    ozellikler: tuple[str, ...]
    e1: tuple[float, float, float]
    s1: float
    n1: int
    e2: tuple[float, float, float] | None = None
    s2: float = 0.0
    n2: int = 1
    bastir: bool = False


@dataclass(frozen=True)
class DaireselDesen:
    """Eksen (dünya, nokta + yön) etrafında n kopya; adlar <k>/<kaynak>/<ad>."""

    kimlik: str
    ozellikler: tuple[str, ...]
    eksen_p: tuple[float, float, float]
    eksen_y: tuple[float, float, float]
    n: int
    aci: float = 360.0
    bastir: bool = False


@dataclass(frozen=True)
class Ayna:
    """Özellik aynası (adlar <kaynak>/<ad>) ya da ozellikler=None ile gövde aynası.

    Gövde aynasında adlar govde/<özellik>/<ad>.
    """

    kimlik: str
    duzlem: Plane | FaceRef
    ozellikler: tuple[str, ...] | None = None
    bastir: bool = False


Ozellik = (
    Blok
    | Silindir
    | Profil
    | Ekstruzyon
    | Dondurme
    | Delik
    | Pah
    | Yuvarlatma
    | DogrusalDesen
    | DaireselDesen
    | Ayna
)


@dataclass(frozen=True)
class Agac:
    """Sıralı özellik listesi."""

    ozellikler: tuple[Ozellik, ...] = ()


# --- Kurulum ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class OzellikRaporu:
    """Bir özelliğin kurulum sonucu. neden: "atlandi" ise hataya yol açan özelliğin kimliği."""

    kimlik: str
    durum: Durum
    mesaj: str = ""
    neden: str | None = None
    dV: float | None = None
    adlar: tuple[FaceRef, ...] = ()


@dataclass(frozen=True)
class Sonuc:
    part: Part | None
    rapor: tuple[OzellikRaporu, ...]
    basarili: bool
    yeniden_hesaplanan: tuple[str, ...] = ()  # bu kurulumda önbellekten değil, yeniden kurulan özellikler


@dataclass
class Onbellek:
    """Önek önbelleği: tanımı ve sırası değişmeyen ilk özelliklerin parçası yeniden kullanılır."""

    kayitlar: list = field(default_factory=list)


Coz = Callable[[Sketch, Plane], Sequence[SketchRegion]]

_TURLER = (
    Blok,
    Silindir,
    Profil,
    Ekstruzyon,
    Dondurme,
    Delik,
    Pah,
    Yuvarlatma,
    DogrusalDesen,
    DaireselDesen,
    Ayna,
)
_DESEN_KAYNAGI = (Ekstruzyon, Dondurme, Delik)
TOL_DUZLEM = 1e-6  # mm: yüze bağlı eskizde parçaların eş düzlemliliği
ASAGI = np.array([0.0, 0.0, -1.0])

Ad = tuple[str, str]  # (özellik kimliği, yerel ad): FaceRef'in iç hali


# --- Doğrulama ve bağımlılık -------------------------------------------------------------------------------


def _referanslar(oz) -> list[str]:
    """Özelliğin doğrudan dayandığı özellik kimlikleri (tekrarsız, sırayla)."""
    k: list[str] = []
    for ad in ("duzlem",):
        v = getattr(oz, ad, None)
        if isinstance(v, FaceRef):
            k.append(v.feature)
    if isinstance(oz, Ekstruzyon | Dondurme):
        k.append(oz.profil)
    if isinstance(oz, Pah | Yuvarlatma):
        for e in oz.kenarlar:
            k += [e.a.feature, e.b.feature]
    if isinstance(oz, DogrusalDesen | DaireselDesen | Ayna) and oz.ozellikler is not None:
        k += list(oz.ozellikler)
    return list(dict.fromkeys(k))


def dogrula(agac: Agac) -> None:
    """Tekil / biçimli kimlik, yalnız önceki özelliğe referans, bilinen tür; aksi `GeometryError`."""
    if not isinstance(agac, Agac):
        raise GeometryError(f"ağaç bekleniyor ({agac!r})")
    onceki: dict[str, object] = {}
    for oz in agac.ozellikler:
        if not isinstance(oz, _TURLER):
            raise GeometryError(f"bilinmeyen özellik türü: {type(oz).__name__}")
        k = oz.kimlik
        if not isinstance(k, str) or not k or ":" in k or "/" in k:
            raise GeometryError(f"özellik kimliği boş olmamalı, ':' ve '/' içermemeli ({k!r})")
        if k in onceki:
            raise GeometryError(f"özellik kimliği tekrar ediyor: '{k}'")
        for r in _referanslar(oz):
            if r not in onceki:
                sonra = any(o.kimlik == r for o in agac.ozellikler)
                neden = "ondan sonra geliyor" if sonra else "ağaçta yok"
                raise GeometryError(f"'{k}' özelliği '{r}' özelliğine bağlı ama '{r}' {neden}")
        if isinstance(oz, Ekstruzyon | Dondurme) and not isinstance(onceki[oz.profil], Profil):
            raise GeometryError(f"'{k}': profil '{oz.profil}' bir Profil değil")
        if isinstance(oz, DogrusalDesen | DaireselDesen | Ayna) and oz.ozellikler is not None:
            if not oz.ozellikler:
                raise GeometryError(f"'{k}': kaynak özellik listesi boş")
            for r in oz.ozellikler:
                q = onceki[r]
                if not isinstance(q, _DESEN_KAYNAGI) or getattr(q, "islem", "kes") == "yeni":
                    raise GeometryError(
                        f"'{k}': '{r}' desen / ayna kaynağı olamaz "
                        "(yalnız ekle / kes ekstrüzyon, döndürme, delik)"
                    )
        onceki[k] = oz


def _graf(agac: Agac) -> dict[str, list[str]]:
    return {oz.kimlik: _referanslar(oz) for oz in agac.ozellikler}


def bagimlilar(agac: Agac, kimlik: str) -> tuple[str, ...]:
    """Doğrudan ve dolaylı bağımlılar, liste sırasıyla."""
    g = _graf(agac)
    if kimlik not in g:
        raise GeometryError(f"ağaçta özellik yok: '{kimlik}'")
    kume = {kimlik}
    sonuc = []
    for oz in agac.ozellikler:
        if oz.kimlik != kimlik and any(r in kume for r in g[oz.kimlik]):
            kume.add(oz.kimlik)
            sonuc.append(oz.kimlik)
    return tuple(sonuc)


def _sira(agac: Agac, kimlik: str) -> int:
    for i, oz in enumerate(agac.ozellikler):
        if oz.kimlik == kimlik:
            return i
    raise GeometryError(f"ağaçta özellik yok: '{kimlik}'")


def tasi(agac: Agac, kimlik: str, yeni_sira: int) -> Agac:
    """Özelliği yeni sıraya taşır; bağımlılığı bozan taşıma → `GeometryError` (adlarla)."""
    i = _sira(agac, kimlik)
    oz = list(agac.ozellikler)
    if not 0 <= yeni_sira < len(oz):
        raise GeometryError(f"yeni sıra aralık dışı ({yeni_sira})")
    o = oz.pop(i)
    oz.insert(yeni_sira, o)
    yeni = Agac(tuple(oz))
    dogrula(yeni)
    return yeni


def sil(agac: Agac, kimlik: str, zincir: bool = False) -> Agac:
    """Bağımlısı varken zincir=False → `GeometryError`; zincir=True → bağımlılarla birlikte siler."""
    _sira(agac, kimlik)
    bag = bagimlilar(agac, kimlik)
    if bag and not zincir:
        raise GeometryError(f"'{kimlik}' silinemez, bağımlıları var: {', '.join(bag)}")
    sil_kume = {kimlik, *bag}
    return Agac(tuple(o for o in agac.ozellikler if o.kimlik not in sil_kume))


# --- OCCT yardımcıları -------------------------------------------------------------------------------------


def _ayni_mi(f, liste) -> bool:
    return any(f.IsSame(g) for g in liste)


def _gecir(adlar: dict[Ad, list], op, yeni, silindi=None) -> dict[Ad, list]:
    """Adları bir işlemin geçmişinden geçirir: silinen düşer, değişen yenisine, değişmeyen kendisi kalır.

    op: `Modified(s)` sunan OCCT işlemi ya da BRepTools_History. Sonuçta olmayan yüz düşer.
    """
    var = yuzler(yeni)
    sil = silindi or (lambda f: op.IsDeleted(f))
    sonuc: dict[Ad, list] = {}
    for ad, fs in adlar.items():
        yeni_fs = []
        for f in fs:
            if sil(f):
                continue
            m = [TopoDS.Face(g) for g in op.Modified(f) if g.ShapeType() == TopAbs_FACE]
            for g in m or [f]:
                if _ayni_mi(g, var) and not _ayni_mi(g, yeni_fs):
                    yeni_fs.append(g)
        if yeni_fs:
            sonuc[ad] = yeni_fs
    return sonuc


def _birlestir_alanlar(shape, adlar: dict[Ad, list]):
    """Eş düzlemli / eş yüzeyli komşu yüzleri birleştirir (UnifySameDomain); adlar History ile taşınır."""
    u = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    u.Build()
    yeni = u.Shape()
    h = u.History()
    return yeni, _gecir(adlar, h, yeni, silindi=lambda f: h.IsRemoved(f))


def _katilar(shape) -> list:
    from OCP.TopExp import TopExp_Explorer

    sonuc = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        sonuc.append(ex.Current())
        ex.Next()
    return sonuc


def _tek_kati(shape, islem: str):
    k = _katilar(shape)
    if len(k) != 1:
        raise GeometryError(f"{islem}: sonuç tek katı değil ({len(k)} katı; ayrık katı)")
    return k[0]


def _hacim(shape) -> float:
    return (
        float(bd.Solid(shape).volume)
        if shape.ShapeType() == TopAbs_SOLID
        else float(bd.Compound(shape).volume)
    )


def _boolean(eski, arac, tur: str, adlar: dict[Ad, list], arac_adlari: dict[Ad, list], islem: str):
    """eski ∓ arac geçmiş izli; dönüş (yeni katı, adlar). kes: ΔV ≤ DV_MIN → hata; ekle: tek katı olmalı."""
    try:
        op = BRepAlgoAPI_Cut(eski, arac) if tur == "kes" else BRepAlgoAPI_Fuse(eski, arac)
        if not op.IsDone():
            raise GeometryError(f"{islem}: OCCT boolean başarısız")
        yeni = op.Shape()
    except GeometryError:
        raise
    except Exception as e:
        raise GeometryError(f"{islem}: OCCT boolean başarısız ({e})") from e
    tum = _gecir({**adlar, **arac_adlari}, op, yeni)
    yeni, tum = _birlestir_alanlar(yeni, tum)
    if tur == "ekle":
        yeni = _tek_kati(yeni, islem)
    else:
        if _hacim(eski) - _hacim(yeni) <= DV_MIN:
            raise GeometryError(f"{islem}: parçadan malzeme kaldırmıyor")
        yeni = _tek_kati(yeni, islem)
    tum = _gecir(tum, _Yok(), yeni)
    return yeni, tum


class _Yok:
    """Değişiklik yapmayan geçmiş (yalnız sonuçta olmayan yüzleri ayıklamak için)."""

    def Modified(self, f):  # noqa: N802 - OCCT adı
        return []

    def IsDeleted(self, f):  # noqa: N802
        return False


def _gp_trsf(T: np.ndarray) -> gp_Trsf:
    t = gp_Trsf()
    t.SetValues(*T[0, :4], *T[1, :4], *T[2, :4])
    return t


def _ayna_trsf(q: np.ndarray, m: np.ndarray) -> gp_Trsf:
    t = gp_Trsf()
    t.SetMirror(gp_Ax2(gp_Pnt(*q), gp_Dir(*m)))
    return t


def _donustur(shape, adlar: dict, trsf: gp_Trsf, yeniden_adla):
    """Şekli dönüştürür; adlar (anahtar → yüzler) dönüşüm geçmişiyle yeni anahtarlara taşınır."""
    op = BRepBuilderAPI_Transform(shape, trsf, True)
    yeni = op.Shape()
    sonuc = {}
    for ad, fs in adlar.items():
        g = [TopoDS.Face(m) for f in fs for m in op.Modified(f)]
        if g:
            sonuc[yeniden_adla(ad)] = g
    return yeni, sonuc


def _yuz_duzlemi(fs: list) -> Plane:
    """Yüze bağlı eskiz düzlemi: düzlemsel (eş düzlemli parçalar), origin ağırlık merkezi, xdir dünya X'i."""
    alan, merkez, normal = 0.0, np.zeros(3), None
    for f in fs:
        if BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane:
            raise GeometryError("eskiz düzlemi: yüz düzlemsel değil")
        y = bd.Face(f)
        c = y.center(bd.CenterOf.MASS)
        c = np.array([c.X, c.Y, c.Z])
        n = y.normal_at(bd.Vector(*c))
        n = np.array([n.X, n.Y, n.Z])
        n /= np.linalg.norm(n)
        if normal is None:
            normal, c0 = n, c
        elif not np.allclose(n, normal, atol=1e-9) or abs(float((c - c0) @ normal)) > TOL_DUZLEM:
            raise GeometryError("eskiz düzlemi: yüz parçaları eş düzlemli değil")
        alan += y.area
        merkez += y.area * c
    origin = merkez / alan
    x = np.array([1.0, 0.0, 0.0]) - normal[0] * normal
    if np.linalg.norm(x) < 1e-6:
        x = np.array([0.0, 1.0, 0.0]) - normal[1] * normal
    return Plane(origin, normal, x / np.linalg.norm(x))


# --- Kurulum durumu ----------------------------------------------------------------------------------------


@dataclass
class _Durum:
    shape: object = None  # TopoDS_Solid
    adlar: dict = field(default_factory=dict)  # Ad → [TopoDS_Face]
    holes: tuple = ()
    profiller: dict = field(default_factory=dict)  # kimlik → (Plane, [SketchRegion])
    araclar: dict = field(default_factory=dict)  # kimlik → desen / ayna kaynağı tarifi
    durumlar: dict = field(default_factory=dict)  # kimlik → (durum, kök neden)

    def kopya(self) -> _Durum:
        return _Durum(
            self.shape,
            {k: list(v) for k, v in self.adlar.items()},
            self.holes,
            dict(self.profiller),
            dict(self.araclar),
            dict(self.durumlar),
        )


def _yuz_bul(d: _Durum, ref: FaceRef) -> list:
    fs = d.adlar.get((ref.feature, ref.name))
    if not fs:
        raise GeometryError(f"referans bulunamadı: {ref}")
    return fs


def _duzlem(d: _Durum, v) -> Plane:
    if isinstance(v, Plane):
        return v
    if isinstance(v, FaceRef):
        return _yuz_duzlemi(_yuz_bul(d, v))
    raise GeometryError(f"düzlem: Plane ya da FaceRef bekleniyor ({v!r})")


def _part(d: _Durum, name: str = "agac") -> Part:
    sekil = bd.Solid(d.shape)
    tum = [f.wrapped for f in sekil.faces()]
    names = {}
    for (oz, ad), fs in d.adlar.items():
        idx = sorted({i for i, g in enumerate(tum) for f in fs if g.IsSame(f)})
        if idx:
            names[FaceRef(oz, ad)] = tuple(idx)
    return Part(sekil, name=name, holes=d.holes, names=names)


def _sonlu(**degerler) -> None:
    for ad, v in degerler.items():
        if not (isinstance(v, int | float) and math.isfinite(v)):
            raise GeometryError(f"{ad} sonlu sayı olmalı ({v!r})")


# --- Özellik uygulayıcıları --------------------------------------------------------------------------------


def _yeni_govde(d: _Durum, shape, adlar: dict[str, list], kimlik: str) -> None:
    if d.shape is not None:
        raise GeometryError(f"'{kimlik}': 'yeni' gövde yalnız ilk katıda (çok gövde kapsam dışı)")
    d.shape = _tek_kati(shape, kimlik)
    d.adlar = _gecir({(kimlik, a): fs for a, fs in adlar.items()}, _Yok(), d.shape)


def _blok(d: _Durum, oz: Blok) -> None:
    p = block(oz.a, oz.b, oz.c)
    adlar: dict[str, list] = {}
    eksen = ("x", "y", "z")
    for f in p.shape.faces():
        n = f.normal_at(f.center())
        n = np.array([n.X, n.Y, n.Z])
        i = int(np.argmax(np.abs(n)))
        adlar[f"{eksen[i]}{'max' if n[i] > 0 else 'min'}"] = [f.wrapped]
    _yeni_govde(d, p.shape.wrapped, adlar, oz.kimlik)


def _silindir(d: _Durum, oz: Silindir) -> None:
    p = cylinder(oz.r, oz.h)
    adlar: dict[str, list] = {}
    for f in p.shape.faces():
        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Plane:
            adlar["ust" if f.center().Z > oz.h / 2 else "alt"] = [f.wrapped]
        else:
            adlar.setdefault("yan", []).append(f.wrapped)
    _yeni_govde(d, p.shape.wrapped, adlar, oz.kimlik)


def _profil(d: _Durum, oz: Profil, coz: Coz | None) -> None:
    plane = _duzlem(d, oz.duzlem)
    if oz.eskiz is not None:
        if coz is None:
            raise GeometryError(f"'{oz.kimlik}': eskizli profil için coz fonksiyonu verilmedi")
        bolgeler = list(coz(oz.eskiz, plane))
    else:
        bolgeler = list(oz.bolgeler)
    if not bolgeler:
        raise GeometryError(f"'{oz.kimlik}': profilde bölge yok")
    d.profiller[oz.kimlik] = (plane, bolgeler)


def _bolgeler(d: _Durum, profil: str, sec) -> tuple[Plane, list]:
    plane, bolgeler = d.profiller[profil]
    if sec is not None:
        try:
            bolgeler = [bolgeler[i] for i in sec]
        except (IndexError, TypeError) as e:
            raise GeometryError(f"bölge seçimi geçersiz ({sec})") from e
    return plane, bolgeler


def _prizma(bolgeler, plane: Plane, kaydir: np.ndarray, vec: np.ndarray):
    """Bölgelerin prizması; yerel adlar bas, son, yan:<src> (OCCT Generated / First / LastShape)."""
    yuz_listesi, eslesme = profil_yuzleri(bolgeler, plane, kaydir)
    kaynak = bd.Compound(yuz_listesi).wrapped if len(yuz_listesi) > 1 else yuz_listesi[0].wrapped
    try:
        op = BRepPrimAPI_MakePrism(kaynak, gp_Vec(*vec))
        govde = op.Shape()
    except Exception as e:
        raise GeometryError(f"ekstrüzyon: OCCT başarısız ({e})") from e
    var = yuzler(govde)
    adlar: dict[str, list] = {}
    for e, src in eslesme:
        if src:
            for f in uretilen(op, e):
                if _ayni_mi(f, var):
                    adlar.setdefault(f"yan:{src}", []).append(f)
    for ad, s in (("bas", op.FirstShape()), ("son", op.LastShape())):
        fs = [f for f in yuzler(s) if _ayni_mi(f, var)]
        if fs:
            adlar[ad] = fs
    return govde, adlar


def _kosegen(d: _Durum) -> float:
    b = bd.Solid(d.shape).bounding_box()
    return float(math.dist((b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)))


def _ekstruzyon_araci(d: _Durum, oz: Ekstruzyon):
    _sonlu(mesafe=oz.mesafe)
    plane, bolgeler = _bolgeler(d, oz.profil, oz.bolge_sec)
    n = plane.normal
    if oz.yon not in ("ileri", "geri", "simetrik") or oz.bitis not in ("mesafe", "boydan_boya"):
        raise GeometryError(f"'{oz.kimlik}': yon / bitis geçersiz ({oz.yon}, {oz.bitis})")
    if oz.islem not in ("yeni", "ekle", "kes"):
        raise GeometryError(f"'{oz.kimlik}': islem geçersiz ({oz.islem})")
    if oz.islem == "kes" and oz.bitis == "boydan_boya":
        if d.shape is None:
            raise GeometryError(f"'{oz.kimlik}': kesilecek parça yok")
        L = _kosegen(d) + PAY
        yon = {"ileri": -1.0, "geri": 1.0}
        if oz.yon == "simetrik":
            kaydir, vec = n * L, -n * 2 * L
        else:
            kaydir, vec = -yon[oz.yon] * n * PAY, yon[oz.yon] * n * L
    else:
        m = oz.mesafe
        if m == 0:
            raise GeometryError(f"'{oz.kimlik}': mesafe sıfır olamaz")
        s = -1.0 if oz.islem == "kes" else 1.0  # kesim malzemeye doğru, −normal
        if oz.yon == "simetrik":
            kaydir, vec = -s * n * m / 2, s * n * m
        else:
            kaydir, vec = np.zeros(3), (s if oz.yon == "ileri" else -s) * n * m
    return _prizma(bolgeler, plane, kaydir, vec)


def _arac_uygula(d: _Durum, govde, yerel: dict[str, list], islem: str, kimlik: str, onek: str = "") -> None:
    """Takım gövdesini parçaya uygular; takım adları (kimlik, onek + yerel ad) olur."""
    adlar = {(kimlik, onek + a): fs for a, fs in yerel.items()}
    if islem == "yeni":
        if onek:
            raise GeometryError(f"'{kimlik}': 'yeni' gövde desenlenemez")
        _yeni_govde(d, govde, yerel, kimlik)
        return
    if d.shape is None:
        raise GeometryError(f"'{kimlik}': '{islem}' için önce bir gövde gerekli")
    d.shape, d.adlar = _boolean(d.shape, govde, islem, d.adlar, adlar, kimlik)


def _ekstruzyon(d: _Durum, oz: Ekstruzyon) -> None:
    govde, yerel = _ekstruzyon_araci(d, oz)
    _arac_uygula(d, govde, yerel, oz.islem, oz.kimlik)
    d.araclar[oz.kimlik] = ("arac", govde, yerel, oz.islem)


def _dondurme(d: _Durum, oz: Dondurme) -> None:
    plane, bolgeler = d.profiller[oz.profil]
    if oz.islem not in ("yeni", "ekle", "kes"):
        raise GeometryError(f"'{oz.kimlik}': islem geçersiz ({oz.islem})")
    govde, yerel = dondur_arac(bolgeler, plane, oz.eksen_p, oz.eksen_y, oz.aci)
    _arac_uygula(d, govde, yerel, oz.islem, oz.kimlik)
    d.araclar[oz.kimlik] = ("arac", govde, yerel, oz.islem)


# Delik: SPEC 02 / 23 fonksiyonları çağrılır (hacim ve Hole kaydı birebir). Ad taşıma için kaldırılan malzeme
# R = eski − yeni, yeni bir takım gövdesi olarak geçmiş izli kesimle yeniden uygulanır; R'nin yüzleri delik
# kaydının ölçüleriyle doğuşta adlandırılır (duvar, dip, havsa, lamba_duvar, lamba_dip).


def _delik_cagir(part: Part, cagri: dict, p: np.ndarray, n: np.ndarray) -> Part:
    """Tek delik: giriş p, delme yönü n. Düşey (n = −Z) ise SPEC 02 / 23 fonksiyonu, değilse eğimli delik."""
    c = cagri["cesit"]
    if np.allclose(n, ASAGI, atol=1e-9):
        x, y = float(p[0]), float(p[1])
        if c == "duz":
            return hole(part, x, y, cagri["d"], cagri["derinlik"])
        if c == "havsa":
            return countersink_hole(
                part, x, y, cagri["d"], cagri["csk_d"], cagri["csk_angle"], cagri["derinlik"]
            )
        if c == "lamba":
            return counterbore_hole(
                part,
                x,
                y,
                d=cagri["d"],
                cbore_d=cagri["cbore_d"],
                cbore_depth=cagri["cbore_depth"],
                depth=cagri["derinlik"],
            )
        if c == "dis":
            return tapped_hole(part, x, y, cagri["thread"], depth=cagri["derinlik"])
        raise GeometryError(f"delik çeşidi bilinmiyor ({c})")
    if c != "duz":
        raise GeometryError(f"bu yüzde yalnız düz delik ({c})")
    return inclined_hole(part, p, n, cagri["d"], cagri["derinlik"])


def _delik_adlari(R, h: Hole) -> dict[str, list]:
    """Kaldırılan malzemenin yüzlerini delik kaydına göre adlandırır."""
    adlar: dict[str, list] = {}
    for f in yuzler(R):
        s = BRepAdaptor_Surface(f)
        t = s.GetType()
        if t == GeomAbs_Cylinder:
            r = s.Cylinder().Radius()
            if abs(r - h.d / 2) < 1e-7:
                adlar.setdefault("duvar", []).append(f)
            elif h.cbore_d and abs(r - h.cbore_d / 2) < 1e-7:
                adlar.setdefault("lamba_duvar", []).append(f)
        elif t == GeomAbs_Cone:
            adlar.setdefault("havsa", []).append(f)
        elif t == GeomAbs_Plane:
            c = bd.Face(f).center(bd.CenterOf.MASS)
            z = float((np.array([c.X, c.Y, c.Z]) - h.origin) @ h.axis)
            if not h.through and abs(z - h.depth) < 1e-6:
                adlar.setdefault("dip", []).append(f)
            elif h.cbore_d and abs(z - h.cbore_depth) < 1e-6:
                adlar.setdefault("lamba_dip", []).append(f)
    return adlar


def _tek_delik(d: _Durum, cagri: dict, p: np.ndarray, n: np.ndarray, kimlik: str, onek: str) -> Hole:
    eski = Part(bd.Solid(d.shape), holes=d.holes)
    yeni = _delik_cagir(eski, cagri, p, n)
    h = yeni.holes[-1]
    try:
        R = (eski.shape - yeni.shape).wrapped
    except Exception as e:
        raise GeometryError(f"'{kimlik}': delik malzemesi ayrılamadı ({e})") from e
    yerel = {onek + a: fs for a, fs in _delik_adlari(R, h).items()}
    d.shape, d.adlar = _boolean(
        d.shape, R, "kes", d.adlar, {(kimlik, a): fs for a, fs in yerel.items()}, kimlik
    )
    d.holes = yeni.holes
    return h


def _delik(d: _Durum, oz: Delik) -> None:
    if d.shape is None:
        raise GeometryError(f"'{oz.kimlik}': delik için önce bir gövde gerekli")
    plane = _duzlem(d, oz.duzlem)
    if not oz.noktalar:
        raise GeometryError(f"'{oz.kimlik}': nokta yok")
    cagri = {
        "cesit": oz.cesit,
        "d": oz.d,
        "derinlik": oz.derinlik,
        "csk_d": oz.csk_d,
        "csk_angle": oz.csk_angle,
        "cbore_d": oz.cbore_d,
        "cbore_depth": oz.cbore_depth,
        "thread": oz.thread,
    }
    kayitlar = []
    for i, uv in enumerate(oz.noktalar):
        p = plane.to_world(uv)
        kayitlar.append(_tek_delik(d, cagri, p, -plane.normal, oz.kimlik, f"{i}/"))
    d.araclar[oz.kimlik] = ("delik", cagri, tuple(kayitlar))


def _kenar_bul(d: _Durum, e: EdgeRef) -> list:
    fa, fb = _yuz_bul(d, e.a), _yuz_bul(d, e.b)
    ka = [k for f in fa for k in kenarlar(f)]
    kb = [k for f in fb for k in kenarlar(f)]
    ortak = []
    for k in ka:
        if _ayni_mi(k, kb) and not _ayni_mi(k, ortak):
            ortak.append(k)
    if not ortak:
        raise GeometryError(f"kenar bulunamadı: {e.a} ve {e.b} ortak kenarı yok")
    return ortak


def _pah_yuvarlatma(d: _Durum, oz) -> None:
    if d.shape is None:
        raise GeometryError(f"'{oz.kimlik}': önce bir gövde gerekli")
    if not oz.kenarlar:
        raise GeometryError(f"'{oz.kimlik}': kenar yok")
    if isinstance(oz, Pah):
        _sonlu(d=oz.d, **({} if oz.d2 is None else {"d2": oz.d2}))
        if oz.d <= 0 or (oz.d2 is not None and oz.d2 <= 0):
            raise GeometryError(f"'{oz.kimlik}': pah uzaklığı > 0 olmalı")
        mk = BRepFilletAPI_MakeChamfer(d.shape)
    else:
        _sonlu(r=oz.r)
        if oz.r <= 0:
            raise GeometryError(f"'{oz.kimlik}': yarıçap > 0 olmalı")
        mk = BRepFilletAPI_MakeFillet(d.shape)
    secim = []
    for i, e in enumerate(oz.kenarlar):
        ks = _kenar_bul(d, e)
        for j, k in enumerate(ks):
            ad = str(i) if len(ks) == 1 else f"{i}.{j}"
            secim.append((ad, k))
            if isinstance(oz, Pah):
                if oz.d2 is None:
                    mk.Add(oz.d, k)
                else:
                    fa = [f for f in _yuz_bul(d, e.a) if _ayni_mi(k, kenarlar(f))][0]
                    mk.Add(oz.d, oz.d2, k, fa)
            else:
                mk.Add(oz.r, k)
    try:
        mk.Build()
        if not mk.IsDone():
            raise GeometryError(f"'{oz.kimlik}': OCCT pah / yuvarlatma başarısız")
        yeni = mk.Shape()
    except GeometryError:
        raise
    except Exception as e:
        raise GeometryError(f"'{oz.kimlik}': OCCT pah / yuvarlatma başarısız ({e})") from e
    yeni = _tek_kati(yeni, oz.kimlik)
    adlar = _gecir(d.adlar, mk, yeni)
    var = yuzler(yeni)
    for ad, k in secim:
        fs = [f for f in uretilen(mk, k) if _ayni_mi(f, var)]
        if fs:
            adlar[(oz.kimlik, ad)] = fs
    d.shape, d.adlar = yeni, adlar


def _kaynak_kopyala(d: _Durum, kaynak: str, T: np.ndarray, trsf: gp_Trsf, kimlik: str, onek: str) -> None:
    """Kaynak özelliğin takımını (ya da deliklerini) T dönüşümüyle kopyalayıp uygular."""
    tarif = d.araclar.get(kaynak)
    if tarif is None:
        raise GeometryError(f"'{kimlik}': kaynak '{kaynak}' uygulanmamış")
    if tarif[0] == "arac":
        _, govde, yerel, islem = tarif
        g2, y2 = _donustur(govde, yerel, trsf, lambda a: a)
        _arac_uygula(d, g2, y2, islem, kimlik, onek)
    else:
        _, cagri, kayitlar = tarif
        for i, h in enumerate(kayitlar):
            h2 = donustur_hole(h, T)
            _tek_delik(d, cagri, h2.origin, h2.axis, kimlik, f"{onek}{i}/")


def _desen(d: _Durum, oz) -> None:
    if isinstance(oz, DogrusalDesen):
        Ts = dogrusal(oz.n1, oz.s1, oz.e1, oz.n2, oz.s2, oz.e2)
    else:
        Ts = dairesel(oz.eksen_p, oz.eksen_y, oz.n, oz.aci)
    for k, T in enumerate(Ts[1:], start=1):
        for kaynak in oz.ozellikler:
            _kaynak_kopyala(d, kaynak, T, _gp_trsf(T), oz.kimlik, f"{k}/{kaynak}/")


def _ayna(d: _Durum, oz: Ayna) -> None:
    if d.shape is None:
        raise GeometryError(f"'{oz.kimlik}': önce bir gövde gerekli")
    plane = _duzlem(d, oz.duzlem)
    q, m = plane.origin, plane.normal
    T, trsf = ayna(q, m), _ayna_trsf(q, m)
    if oz.ozellikler is not None:
        for kaynak in oz.ozellikler:
            _kaynak_kopyala(d, kaynak, T, trsf, oz.kimlik, f"{kaynak}/")
        return
    g2, y2 = _donustur(d.shape, d.adlar, trsf, lambda a: (oz.kimlik, f"govde/{a[0]}/{a[1]}"))
    d.shape, d.adlar = _boolean(d.shape, g2, "ekle", d.adlar, y2, f"'{oz.kimlik}' gövde aynası")
    d.holes = d.holes + tuple(donustur_hole(h, T) for h in d.holes)


def _uygula(d: _Durum, oz, coz: Coz | None) -> None:
    if isinstance(oz, Blok):
        _blok(d, oz)
    elif isinstance(oz, Silindir):
        _silindir(d, oz)
    elif isinstance(oz, Profil):
        _profil(d, oz, coz)
    elif isinstance(oz, Ekstruzyon):
        _ekstruzyon(d, oz)
    elif isinstance(oz, Dondurme):
        _dondurme(d, oz)
    elif isinstance(oz, Delik):
        _delik(d, oz)
    elif isinstance(oz, Pah | Yuvarlatma):
        _pah_yuvarlatma(d, oz)
    elif isinstance(oz, DogrusalDesen | DaireselDesen):
        _desen(d, oz)
    elif isinstance(oz, Ayna):
        _ayna(d, oz)
    else:  # dogrula yakalar
        raise GeometryError(f"bilinmeyen özellik türü: {type(oz).__name__}")


def insa(
    agac: Agac,
    onbellek: Onbellek | None = None,
    kadar: str | None = None,
    coz: Coz | None = None,
) -> Sonuc:
    """Ağacı sırayla kurar; `kadar` verilirse o özellik dahil durur (bilinmeyen kimlik → `GeometryError`)."""
    dogrula(agac)
    ozellikler = list(agac.ozellikler)
    if kadar is not None:
        ozellikler = ozellikler[: _sira(agac, kadar) + 1]
    kayitlar = onbellek.kayitlar if onbellek is not None else []
    d = _Durum()
    raporlar: list[dict] = []
    yeniden: list[str] = []
    gecerli = True
    for i, oz in enumerate(ozellikler):
        anahtar = json.dumps(_oz_sozluk(oz), sort_keys=True)
        if gecerli and i < len(kayitlar) and kayitlar[i][0] == anahtar:
            _, d_kayit, rapor_kayit = kayitlar[i]
            d = d_kayit.kopya()
            raporlar.append(dict(rapor_kayit))
            continue
        if gecerli:
            del kayitlar[i:]
            gecerli = False
        yeniden.append(oz.kimlik)
        raporlar.append(_adim(d, oz, coz))
        kayitlar.append((anahtar, d.kopya(), dict(raporlar[-1])))
    if onbellek is None:
        kayitlar.clear()
    part = _part(d) if d.shape is not None else None
    yasayan = sorted(part.names, key=str) if part is not None else []
    rapor = tuple(
        OzellikRaporu(**r, adlar=tuple(a for a in yasayan if a.feature == r["kimlik"])) for r in raporlar
    )
    basarili = all(r.durum in ("tamam", "bastirildi") for r in rapor)
    return Sonuc(part=part, rapor=rapor, basarili=basarili, yeniden_hesaplanan=tuple(yeniden))


def _adim(d: _Durum, oz, coz: Coz | None) -> dict:
    """Tek özelliği uygular (hata yalıtımıyla); d yerinde güncellenir. Dönüş: rapor alanları."""
    k = oz.kimlik
    if oz.bastir:
        d.durumlar[k] = ("bastirildi", k)
        return {"kimlik": k, "durum": "bastirildi"}
    for r in _referanslar(oz):
        durum, kok = d.durumlar.get(r, ("tamam", None))
        if durum != "tamam":
            d.durumlar[k] = ("atlandi", kok)
            return {"kimlik": k, "durum": "atlandi", "neden": kok, "mesaj": f"'{r}' uygulanmadı"}
    deneme = d.kopya()
    V0 = _hacim(d.shape) if d.shape is not None else 0.0
    try:
        _uygula(deneme, oz, coz)
    except (GeometryError, ValueError) as e:
        d.durumlar[k] = ("hata", k)
        return {"kimlik": k, "durum": "hata", "mesaj": str(e) or type(e).__name__}
    deneme.durumlar[k] = ("tamam", None)
    d.__dict__.update(deneme.__dict__)
    dV = None if isinstance(oz, Profil) or d.shape is None else _hacim(d.shape) - V0
    return {"kimlik": k, "durum": "tamam", "dV": dV}


# --- JSON --------------------------------------------------------------------------------------------------


def _seg_sozluk(s) -> dict:
    if isinstance(s, SegLine):
        return {"tur": "cizgi", "p0": s.p0.tolist(), "p1": s.p1.tolist(), "src": s.src}
    return {
        "tur": "yay",
        "center": s.center.tolist(),
        "r": float(s.r),
        "start": s.start.tolist(),
        "end": s.end.tolist(),
        "ccw": bool(s.ccw),
        "src": s.src,
    }


def _seg_oku(v: dict):
    if v["tur"] == "cizgi":
        return SegLine(v["p0"], v["p1"], src=v["src"])
    if v["tur"] == "yay":
        return SegArc(v["center"], v["r"], v["start"], v["end"], v["ccw"], src=v["src"])
    raise GeometryError(f"bilinmeyen kenar türü: {v['tur']}")


def _deger(ad: str, v):
    """Özellik alanını JSON değerine çevirir."""
    if v is None:
        return None
    if ad == "duzlem":
        return {"yuz": str(v)} if isinstance(v, FaceRef) else {"plane": v.to_dict()}
    if ad == "bolgeler":
        return [
            {
                "outer": [_seg_sozluk(s) for s in r.outer],
                "holes": [[_seg_sozluk(s) for s in h] for h in r.holes],
            }
            for r in v
        ]
    if ad == "eskiz":
        return v.to_dict()
    if ad == "kenarlar":
        return [[str(e.a), str(e.b)] for e in v]
    if isinstance(v, tuple):
        return [list(x) if isinstance(x, tuple) else x for x in v]
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def _oku(ad: str, v):
    if v is None:
        return None
    if ad == "duzlem":
        return FaceRef.parse(v["yuz"]) if "yuz" in v else Plane.from_dict(v["plane"])
    if ad == "bolgeler":
        return tuple(
            SketchRegion(
                tuple(_seg_oku(s) for s in r["outer"]),
                tuple(tuple(_seg_oku(s) for s in h) for h in r["holes"]),
            )
            for r in v
        )
    if ad == "eskiz":
        return Sketch.from_dict(v)
    if ad == "kenarlar":
        return tuple(EdgeRef(FaceRef.parse(a), FaceRef.parse(b)) for a, b in v)
    if ad in ("noktalar",):
        return tuple(tuple(float(x) for x in p) for p in v)
    if ad in ("eksen_p", "eksen_y", "e1", "e2"):
        return tuple(float(x) for x in v)
    if ad in ("bolge_sec", "ozellikler"):
        return tuple(v)
    return v


def _oz_sozluk(oz) -> dict:
    if not isinstance(oz, _TURLER):
        raise GeometryError(f"bilinmeyen özellik türü: {type(oz).__name__}")
    d = {"tur": type(oz).__name__}
    for f in dataclasses.fields(oz):
        d[f.name] = _deger(f.name, getattr(oz, f.name))
    return d


def to_dict(agac: Agac) -> dict:
    """{"sema": 1, "ozellikler": [...]} (JSON uyumlu)."""
    return {"sema": SEMA, "ozellikler": [_oz_sozluk(oz) for oz in agac.ozellikler]}


def from_dict(d: dict) -> Agac:
    """to_dict'in tersi; sema ≠ 1 ya da bilinmeyen tür → `GeometryError`."""
    if not isinstance(d, dict) or d.get("sema") != SEMA:
        raise GeometryError(
            f"ağaç şeması desteklenmiyor (sema={d.get('sema') if isinstance(d, dict) else d!r})"
        )
    turler = {t.__name__: t for t in _TURLER}
    ozellikler = []
    for o in d.get("ozellikler", []):
        t = turler.get(o.get("tur"))
        if t is None:
            raise GeometryError(f"bilinmeyen özellik türü: {o.get('tur')!r}")
        alanlar = {f.name for f in dataclasses.fields(t)}
        try:
            ozellikler.append(t(**{k: _oku(k, v) for k, v in o.items() if k != "tur" and k in alanlar}))
        except TypeError as e:
            raise GeometryError(f"özellik okunamadı ({o.get('tur')}: {e})") from e
    return Agac(tuple(ozellikler))
