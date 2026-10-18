"""
SPEC 47c — Analiz ekranının köprüsü: tet4 ağı, yüz seçimi, koşullar, çözüm, sonda, yakınsama, kontroller.

Saf fonksiyonlar, FastAPI'siz test edilir (`tezgah/ekranlar/analiz.py` yalnız bunları çağırır).
Modül adı `_` ile başlar: A3 `ekranlar()` keşfi bu modülü ekran olarak import etmez.
Birimler N – mm – MPa. Her JSON yanıtında `"sema": SEMA` alanı vardır.

Analiz sözlüğü (`analiz_json`):
    {
      "sema": 1, "ad": str,
      "parca": {"ad", "hacim"},
      "malzeme": {"ad", "E", "nu", "Re"},            # Re [MPa] ya da None; yalnız güvenlik katsayısı için
      "ag": {"h", "dugum", "eleman", "hacim"},       # hacim = Σ eleman hacmi
      "secimler": [{"kimlik", "tur": "duzlem"|"silindir", "tanim", "dugumler", "ucgenler", "alan",
                    "kilitli"}],
      "kosullar": [{"kimlik", "secim", "tur": "mesnet"|"cekme"|"basinc", "deger", "kilitli"}],
      "cozum": {"u_max", "u_max_dugum", "vm_max", "vm_max_dugum", "tepki": [Rx,Ry,Rz], "yuk": [Fx,Fy,Fz],
                "denge": [ex,ey,ez], "guvenlik": Re/vm_max | None, "olcek"} | None,
      "analitik": [{"ad", "formul", "deger", "birim", "fem", "fark"}],
      "yakinsama": [{"h", "dugum", "u_max", "vm_max", "neden"}] | None,
      "kontroller": [Kontrol],
    }
    Kontrol = {"kimlik", "baslik", "deger", "birim", "durum": "tamam"|"uyari"|"hata", "aciklama", "spec"}

- `secimler[].tanim`: düzlem → {"nokta": [x,y,z], "normal": [nx,ny,nz], "tol"} ya da örnek kilidinde
  {"duzlemler": [{"nokta", "normal", "tol"}, ...]} (düzlemlerin kesişimi);
  silindir → {"nokta", "eksen", "r", "tol"}.
  `dugumler`: düğüm kimlikleri (1 tabanlı, `select_nodes` sırası); `ucgenler`: (m, 3) düğüm kimliği satırları
  (`select_triangles`), JSON'da liste listesi.
  `kilitli`: örnek dosyasının koşulu (silinemez, `sifirla` korur).
- `kosullar[].deger`: mesnet → dof listesi (ör. ["ux"]); cekme → [tx, ty, tz] MPa; basinc → p MPa.
- `cozum` koşullar değişince ya da yeniden ağ kurulunca None olur.

Hata: geçersiz girdi `ModelError` fırlatır (altın kural 5); ekran ucu bunu 422'ye çevirir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.model import Material, Model

SEMA = 1
SONDA_N_MAX = 2000  # sonda nokta sayısı üst sınırı
BARISENTRIK_EPS = 1e-9  # λ ≥ −eps → nokta tetin içinde
TOL_KUTU = 1e-6  # seçim düzlem / silindir toleransı = TOL_KUTU · L_kutu
OLCEK_KUTU = 0.1  # deforme ölçeği = OLCEK_KUTU · L_kutu / u_max
YAKINSAMA_ORANLARI = (1.0, 1.5, 2.25)  # h, h/1.5, h/2.25
ANALITIK_ESIK = 0.10  # |fark| > eşik → analitik_sapma uyari
YAKINSAMA_ESIK = 0.05  # son iki ağın vm_max bağıl farkı > eşik → yakinsama uyari
AG_HACMI_ESIK = 1e-2  # ag hacmi ↔ Part.volume bağıl farkı > eşik → uyari
BILESENLER = ("vm", "sxx", "syy", "szz", "sxy", "syz", "sxz", "s1", "s2", "s3")  # sonda bileşenleri


@dataclass(frozen=True)
class Secim:
    """Bir sınır yüzü seçimi. Düğüm ve üçgenler ağdan türetilir; yeniden ağda `tanim`dan yeniden uygulanır."""

    kimlik: str
    tur: str  # "duzlem" | "silindir"
    tanim: dict
    kilitli: bool = False


@dataclass(frozen=True)
class Kosul:
    """Bir seçime uygulanan mesnet / yük. Model her çözümde listedeki sırayla yeniden kurulur."""

    kimlik: str
    secim: str  # Secim.kimlik
    tur: str  # "mesnet" | "cekme" | "basinc"
    deger: tuple  # mesnet: dof adları; cekme: (tx, ty, tz); basinc: (p,)
    kilitli: bool = False


@dataclass(frozen=True)
class Analitik:
    """Örnek işe özgü kapalı form satırı. `fem` çözümden okunur: "u_max" | "vm_max" | "u_ucta" | None."""

    ad: str
    formul: str
    deger: float
    birim: str
    fem: str | None = None


@dataclass(frozen=True)
class AnalizTanimi:
    """Bir analiz işinin girdisi (değişmez; her düzenleme yeni tanım döndürür).

    parca: geometry.part.Part (OCCT); malzeme: core.model.Material; Re: akma [MPa] ya da None.
    h: ağ boyu; refine: mesh.Refine demeti; max_nodes: tet_mesh sınırı.
    """

    ad: str
    parca: object
    malzeme: Material
    h: float
    Re: float | None = None
    refine: tuple = ()
    max_nodes: int = 200_000
    secimler: tuple[Secim, ...] = ()
    kosullar: tuple[Kosul, ...] = ()
    analitik: tuple[Analitik, ...] = ()


@dataclass
class Ag:
    """Bir tanımın ağı: temiz (koşulsuz) model ve türetilmiş diziler."""

    model: Model
    X: np.ndarray  # (nd, 3) düğüm konumları, model.nodes sırası
    kimlik: np.ndarray  # (nd,) int düğüm kimlikleri
    ucgenler: np.ndarray  # (m, 3) sınır üçgenleri, düğüm kimlikleri (boundary_triangles)
    hacim: float  # Σ eleman hacmi
    L_kutu: float  # parça sınır kutusu köşegeni


@dataclass
class Cozum:
    """Çözüm sonucu: düğüm sırası `Ag.kimlik` ile aynı."""

    u: np.ndarray  # (nd, 3)
    sigma: np.ndarray  # (nd, 6) düğüm gerilme tensörü (sxx, syy, szz, sxy, syz, sxz)
    vm: np.ndarray  # (nd,)
    asal: np.ndarray  # (nd, 3) azalan sırada
    ozet: dict = field(default_factory=dict)  # Analiz["cozum"] sözlüğü


# ---------------------------------------------------------------- ağ ve seçim


def ag_kur(tanim: AnalizTanimi, h: float | None = None) -> Ag:
    """`tet_mesh(parca, h, malzeme, refine, max_nodes)` + `boundary_triangles`. h None → tanim.h."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def ucgen_secimi(tanim: AnalizTanimi, ag: Ag, j: int) -> Secim:
    """Sınır üçgeni j'nin düzlemi (ağırlık merkezi, `triangle_normals[j]`, tol = TOL_KUTU·L_kutu) → Secim.

    Kimlik "s<n>" (n: tanımdaki seçim sayısı + 1). j sınır dışı → ModelError.
    """
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def silindir_secimi(tanim: AnalizTanimi, ag: Ag, nokta, eksen, r: float) -> Secim:
    """Eksen noktası, yönü ve yarıçapla silindir seçimi (`on_cylinder`). Sıfır eksen, r ≤ 0 → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def secim_uygula(ag: Ag, secim: Secim) -> tuple[list[int], np.ndarray, float]:
    """Seçimi ağa uygular → (düğüm kimlikleri `select_nodes`, üçgenler `select_triangles`, Σ üçgen alanı)."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def secim_ekle(tanim: AnalizTanimi, secim: Secim) -> AnalizTanimi:
    """Seçim eklenmiş yeni tanım. Boş seçim (düğüm yok) → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def kosul_ekle(tanim: AnalizTanimi, secim: str, tur: str, deger) -> AnalizTanimi:
    """Koşul eklenmiş yeni tanım (kimlik "k<n>"). Bilinmeyen seçim / tür, geçersiz dof, sonlu olmayan değer,
    3 bileşenli olmayan çekme → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def kosul_sil(tanim: AnalizTanimi, kimlik: str) -> AnalizTanimi:
    """Koşulu çıkarır. Bilinmeyen kimlik → KeyError; kilitli (örnek) koşul → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def h_degistir(tanim: AnalizTanimi, h: float) -> AnalizTanimi:
    """Yeni ağ boyu (seçimler tanımlarından yeniden uygulanır). h ≤ 0 ya da sonlu değil → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def model_kur(tanim: AnalizTanimi, ag: Ag) -> Model:
    """Ağın temiz kopyası + koşullar listedeki sırayla: mesnet → `fix`, cekme → `add_traction`,
    basinc → `add_pressure`. `ag.model` değişmez."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


# ---------------------------------------------------------------- çözüm


def coz(tanim: AnalizTanimi, ag: Ag) -> Cozum:
    """`solve(model)` + `nodal_stress_tensors` + `von_mises` + `principal_stresses`.

    ozet: u_max = max |u_i|, vm_max ve düğüm kimlikleri; tepki = mesnet tepkilerinin toplamı;
    yuk = Load toplamı;
    denge = tepki + yuk; guvenlik = Re / vm_max (Re None → None; vm_max = 0 → ModelError);
    olcek = OLCEK_KUTU · L_kutu / u_max. Mesnet eksik → çekirdeğin ModelError'ı.
    """
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def sonda_degerleri(
    model: Model, degerler: np.ndarray, p0, p1, n: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """[p0, p1] üzerinde n eşit aralıklı noktada barisentrik ara değer (gmsh'siz, herhangi bir tet4 modeli).

    degerler: (nd,) düğüm değerleri, `model.nodes` sırası. Dönüş (s float64[n] yay uzunluğu,
    deger float64[n], iceride uint8[n]); hiçbir tette olmayan noktada iceride 0, deger 0.
    n < 2 ya da n > SONDA_N_MAX, p0 = p1 → ModelError.
    """
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def bilesen_degerleri(cozum: Cozum, bilesen: str) -> np.ndarray:
    """BILESENLER'den biri → (nd,) düğüm değerleri. Bilinmeyen bileşen → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def yakinsama(tanim: AnalizTanimi) -> list[dict]:
    """h·{1, 1/1.5, 1/2.25} ağlarında ayrı ayrı kurup çözer → [{h, dugum, u_max, vm_max, neden}].

    max_nodes aşılan ağda dugum/u_max/vm_max None, neden metni dolu (sahte sayı yok).
    """
    raise NotImplementedError("SPEC 47c: uygulanmadı")


# ---------------------------------------------------------------- analitik ve kontroller


def heywood_kt(d_W: float) -> float:
    """Heywood brüt kesit gerilme yığılması Kt_g = (2 + (1 − d/W)³) / (1 − d/W)."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def kirsch_sxx(sigma: float, r: float, y) -> np.ndarray:
    """Sonsuz plakada θ = 90° doğrultusunda σ_xx(y) = σ/2·(2 + r²/y² + 3r⁴/y⁴); |y| < r → ModelError."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def konsol_sehim(P: float, L: float, E: float, b: float, h: float) -> float:
    """Euler–Bernoulli δ = P·L³ / (3·E·I), I = b·h³/12."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def timoshenko_sehim(P: float, L: float, E: float, nu: float, b: float, h: float) -> float:
    """δ_T = δ + P·L / (κ·G·A), κ = 5/6, G = E / (2(1 + ν)), A = b·h."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def analitik_satirlari(tanim: AnalizTanimi, cozum: Cozum | None) -> list[dict]:
    """Tanımın analitik satırları; fem = çözümden okunan değer (çözüm yoksa None), fark = fem / deger − 1."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def analitik_sapma_kontrolu(analitik: list[dict]) -> dict | None:
    """|fark| > ANALITIK_ESIK olan satır varsa uyari, aksi tamam; fem'li satır yoksa None (listede yok)."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def kontroller(tanim: AnalizTanimi, ag: Ag, cozum: Cozum | None, yakin: list[dict] | None) -> list[dict]:
    """denge, ag_hacmi, akma, analitik_sapma, yakinsama (SPEC 47 "Kontroller (Analiz)" tablosu).

    Çözüm yoksa denge / akma / analitik_sapma yok; Re None → akma yok; yakınsama yoksa yakinsama yok.
    """
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def analiz_json(
    tanim: AnalizTanimi, ag: Ag, cozum: Cozum | None = None, yakin: list[dict] | None = None
) -> dict:
    """Analiz sözlüğü (modül belgesindeki şema). nan / inf içermez."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def inp(tanim: AnalizTanimi, ag: Ag) -> str:
    """`fileio.calculix.to_inp(model_kur(tanim, ag))`."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


# ---------------------------------------------------------------- ikili diziler


def ag_ikili(ag: Ag) -> bytes:
    """Little-endian, her blok 8 baytın katına sıfırla tamamlanır (SPEC 24 biçimi):
    başlık uint32 sema, uint32 nd, uint32 m; düğüm float32[nd·3]; sınır üçgeni uint32[m·3] (düğüm *indeksi*,
    0 tabanlı, `kimlik` dizisine göre); düğüm kimliği int32[nd]."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def ag_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`ag_ikili` → {"dugum" (nd, 3) float32, "ucgen" (m, 3) uint32, "kimlik" (nd,) int32}."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def alan_ikili(cozum: Cozum) -> bytes:
    """başlık uint32 sema, uint32 nd; u float32[nd·3]; vm float32[nd]; asal float32[nd·3];
    tensör float32[nd·6]."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def alan_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`alan_ikili` → {"u" (nd, 3), "vm" (nd,), "asal" (nd, 3), "tensor" (nd, 6)}, hepsi float32."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def sonda_ikili(s: np.ndarray, deger: np.ndarray, iceride: np.ndarray) -> bytes:
    """başlık uint32 sema, uint32 n; s float64[n]; deger float64[n]; iceride uint8[n]."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def sonda_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`sonda_ikili` → {"s", "deger", "iceride"}."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")
