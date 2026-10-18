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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from geometry.part import Part
from sketch.model import Plane, Sketch, SketchRegion

if TYPE_CHECKING:  # A2 arayüzü (geometry/part.py) birleşince doğrudan import edilir
    from geometry.part import FaceRef

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


def dogrula(agac: Agac) -> None:
    """Tekil / biçimli kimlik, yalnız önceki özelliğe referans, bilinen tür; aksi `GeometryError`."""
    raise NotImplementedError("SPEC 18: dogrula")


def insa(
    agac: Agac,
    onbellek: Onbellek | None = None,
    kadar: str | None = None,
    coz: Coz | None = None,
) -> Sonuc:
    """Ağacı sırayla kurar; `kadar` verilirse o özellik dahil durur (bilinmeyen kimlik → `GeometryError`)."""
    raise NotImplementedError("SPEC 18: insa")


def bagimlilar(agac: Agac, kimlik: str) -> tuple[str, ...]:
    """Doğrudan ve dolaylı bağımlılar, liste sırasıyla."""
    raise NotImplementedError("SPEC 18: bagimlilar")


def tasi(agac: Agac, kimlik: str, yeni_sira: int) -> Agac:
    """Özelliği yeni sıraya taşır; bağımlılığı bozan taşıma → `GeometryError` (adlarla)."""
    raise NotImplementedError("SPEC 18: tasi")


def sil(agac: Agac, kimlik: str, zincir: bool = False) -> Agac:
    """Bağımlısı varken zincir=False → `GeometryError`; zincir=True → bağımlılarla birlikte siler."""
    raise NotImplementedError("SPEC 18: sil")


def to_dict(agac: Agac) -> dict:
    """{"sema": 1, "ozellikler": [...]} (JSON uyumlu)."""
    raise NotImplementedError("SPEC 18: to_dict")


def from_dict(d: dict) -> Agac:
    """to_dict'in tersi; sema ≠ 1 ya da bilinmeyen tür → `GeometryError`."""
    raise NotImplementedError("SPEC 18: from_dict")
