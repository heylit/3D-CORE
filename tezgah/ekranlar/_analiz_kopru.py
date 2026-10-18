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
      "egriler": [{"ad", "p0", "p1", "s": [...], "deger": [...]}],   # analitik eğriler (ör. Kirsch)
      "yakinsama": [{"h", "dugum", "u_max", "vm_max", "neden"}] | None,
      "kontroller": [Kontrol],
    }
    Kontrol = {"kimlik", "baslik", "deger", "birim", "durum": "tamam"|"uyari"|"hata", "aciklama", "spec"}

- `secimler[].tanim`: düzlem → {"nokta": [x,y,z], "normal": [nx,ny,nz], "tol"} ya da örnek kilidinde
  {"duzlemler": [{"nokta", "normal", "tol" | "tol_h"}, ...]} (düzlemlerin kesişimi; "tol_h": tol = tol_h · h);
  silindir → {"nokta", "eksen", "r", "tol"}.
  `dugumler`: düğüm kimlikleri (1 tabanlı, `select_nodes` sırası); `ucgenler`: (m, 3) düğüm kimliği satırları
  (`select_triangles`), JSON'da liste listesi.
  `kilitli`: örnek dosyasının koşulu (silinemez, `sifirla` korur).
- `kosullar[].deger`: mesnet → dof listesi (ör. ["ux"]); cekme → [tx, ty, tz] MPa; basinc → p MPa.
- `cozum` koşullar değişince ya da yeniden ağ kurulunca None olur.

Hata: geçersiz girdi `ModelError` fırlatır (altın kural 5); ekran ucu bunu 422'ye çevirir.
"""

from __future__ import annotations

import dataclasses
import math
import struct
from dataclasses import dataclass, field

import numpy as np

from core.model import Material, Model, ModelError
from core.post import nodal_stress_tensors, principal_stresses, von_mises
from core.solver import solve
from fileio.calculix import to_inp
from mesh import (
    add_pressure,
    add_traction,
    boundary_triangles,
    fix,
    on_cylinder,
    on_plane,
    select_nodes,
    select_triangles,
    tet_mesh,
    triangle_areas,
    triangle_normals,
)

SEMA = 1
SONDA_N_MAX = 2000  # sonda nokta sayısı üst sınırı
BARISENTRIK_EPS = 1e-9  # λ ≥ −eps → nokta tetin içinde
TOL_KUTU = 1e-6  # seçim düzlem / silindir toleransı = TOL_KUTU · L_kutu
OLCEK_KUTU = 0.1  # deforme ölçeği = OLCEK_KUTU · L_kutu / u_max
YAKINSAMA_ORANLARI = (1.0, 1.5, 2.25)  # h, h/1.5, h/2.25
ANALITIK_ESIK = 0.10  # |fark| > eşik → analitik_sapma uyari
YAKINSAMA_ESIK = 0.05  # son iki ağın vm_max bağıl farkı > eşik → yakinsama uyari
AG_HACMI_ESIK = 1e-2  # ag hacmi ↔ Part.volume bağıl farkı > eşik → uyari
DENGE_ESIK = 1e-6  # max|e| > DENGE_ESIK · max(|yuk|, 1) → hata
BILESENLER = ("vm", "sxx", "syy", "szz", "sxy", "sxz", "syz", "s1", "s2", "s3")  # sonda bileşenleri
DOFLAR = ("ux", "uy", "uz")
KOSUL_TURLERI = ("mesnet", "cekme", "basinc")


@dataclass(frozen=True)
class Secim:
    """Bir sınır yüzü seçimi. Düğüm ve üçgenler ağdan türetilir; yeniden ağda `tanim`dan yeniden uygulanır.

    dugum_sayisi: seçim kurulurken ağda bulunan düğüm sayısı (None: bilinmiyor, ör. örnek dosyası).
    """

    kimlik: str
    tur: str  # "duzlem" | "silindir"
    tanim: dict
    kilitli: bool = False
    dugum_sayisi: int | None = None


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
    """Örnek işe özgü kapalı form satırı. fem = çözümden okunan değer / bolen.

    fem: "u_max" | "vm_max" | "sxx_max" | None (karşılaştırma yok).
    """

    ad: str
    formul: str
    deger: float
    birim: str
    fem: str | None = None
    bolen: float = 1.0


@dataclass(frozen=True)
class Egri:
    """Sonda grafiğine çizilen analitik eğri: [p0, p1] doğrusu üzerinde (s, değer) çiftleri."""

    ad: str
    p0: tuple[float, float, float]
    p1: tuple[float, float, float]
    s: tuple[float, ...]
    deger: tuple[float, ...]


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
    egriler: tuple[Egri, ...] = ()


@dataclass
class Ag:
    """Bir tanımın ağı: temiz (koşulsuz) model ve türetilmiş diziler."""

    model: Model
    X: np.ndarray  # (nd, 3) düğüm konumları, model.nodes sırası
    kimlik: np.ndarray  # (nd,) int düğüm kimlikleri
    ucgenler: np.ndarray  # (m, 3) sınır üçgenleri, düğüm kimlikleri (boundary_triangles)
    hacim: float  # Σ eleman hacmi
    L_kutu: float  # parça sınır kutusu köşegeni
    h: float = 0.0  # ağ boyu


@dataclass
class Cozum:
    """Çözüm sonucu: düğüm sırası `Ag.kimlik` ile aynı."""

    u: np.ndarray  # (nd, 3)
    sigma: np.ndarray  # (nd, 6) düğüm gerilme tensörü Voigt (xx, yy, zz, xy, xz, yz), core.post sırası
    vm: np.ndarray  # (nd,)
    asal: np.ndarray  # (nd, 3) azalan sırada
    ozet: dict = field(default_factory=dict)  # Analiz["cozum"] sözlüğü


# ---------------------------------------------------------------- yardımcılar


def _sonlu(x, ad: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ModelError(f"{ad} sayı olmalı ({x!r})") from None
    if not math.isfinite(v):
        raise ModelError(f"{ad} sonlu olmalı ({v})")
    return v


def _vektor(v, ad: str) -> list[float]:
    a = np.asarray(v, dtype=float).ravel() if not isinstance(v, str) else np.array([])
    if a.shape != (3,) or not np.all(np.isfinite(a)):
        raise ModelError(f"{ad} üç sonlu bileşenli olmalı ({v!r})")
    return [float(x) for x in a]


def _sonraki_kimlik(onek: str, var: list[str]) -> str:
    n = 0
    for k in var:
        if k.startswith(onek) and k[len(onek) :].isdigit():
            n = max(n, int(k[len(onek) :]))
    return f"{onek}{n + 1}"


def _tet_dizileri(model: Model) -> tuple[np.ndarray, np.ndarray]:
    """(X (nd, 3), tet düğüm indeksleri (ne, 4)) model.nodes sırasıyla."""
    idx = {n.id: i for i, n in enumerate(model.nodes)}
    X = np.array([[n.x, n.y, n.z] for n in model.nodes], dtype=float).reshape(-1, 3)
    E = np.array([[idx[k] for k in e.nodes] for e in model.elements if e.type == "tet4"], dtype=np.int64)
    return X, E.reshape(-1, 4)


def _kontrol(kimlik, baslik, deger, birim, durum, aciklama, spec) -> dict:
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "deger": deger,
        "birim": birim,
        "durum": durum,
        "aciklama": aciklama,
        "spec": spec,
    }


# ---------------------------------------------------------------- ağ ve seçim


def ag_kur(tanim: AnalizTanimi, h: float | None = None) -> Ag:
    """`tet_mesh(parca, h, malzeme, refine, max_nodes)` + `boundary_triangles`. h None → tanim.h."""
    h = tanim.h if h is None else h
    m = tet_mesh(tanim.parca, h, tanim.malzeme, refine=tanim.refine, max_nodes=tanim.max_nodes)
    kimlik = np.array([n.id for n in m.nodes], dtype=np.int64)
    X, E = _tet_dizileri(m)
    P = X[E]
    D = np.linalg.det(np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]], axis=-1))
    lo, hi = tanim.parca.bbox
    return Ag(
        model=m,
        X=X,
        kimlik=kimlik,
        ucgenler=boundary_triangles(m),
        hacim=float(np.abs(D).sum() / 6.0),
        L_kutu=float(np.linalg.norm(np.asarray(hi) - np.asarray(lo))),
        h=float(h),
    )


def _tahmin(ag: Ag, secim: Secim):
    """Seçimin tanımından düğüm tahmini (birden çok düzlem → kesişim)."""
    t = secim.tanim
    if secim.tur == "silindir":
        return on_cylinder(t["nokta"], t["eksen"], t["r"], t["tol"])
    if secim.tur != "duzlem":
        raise ModelError(f"Bilinmeyen seçim türü {secim.tur!r}")
    if "duzlemler" not in t:
        return on_plane(t["nokta"], t["normal"], t["tol"])
    tahminler = [
        on_plane(d["nokta"], d["normal"], d["tol"] if "tol" in d else d["tol_h"] * ag.h)
        for d in t["duzlemler"]
    ]

    def kesisim(X: np.ndarray) -> np.ndarray:
        sonuc = np.ones(len(np.atleast_2d(X)), dtype=bool)
        for p in tahminler:
            sonuc &= p(X)
        return sonuc

    return kesisim


def secim_uygula(ag: Ag, secim: Secim) -> tuple[list[int], np.ndarray, float]:
    """Seçimi ağa uygular → (düğüm kimlikleri `select_nodes`, üçgenler `select_triangles`, Σ üçgen alanı)."""
    pred = _tahmin(ag, secim)
    dugum = select_nodes(ag.model, pred)
    U = select_triangles(ag.model, pred)
    alan = float(triangle_areas(ag.model, U).sum()) if len(U) else 0.0
    return dugum, U, alan


def ucgen_secimi(tanim: AnalizTanimi, ag: Ag, j: int) -> Secim:
    """Sınır üçgeni j'nin düzlemi (ağırlık merkezi, `triangle_normals[j]`, tol = TOL_KUTU·L_kutu) → Secim.

    Kimlik "s<n>" (tanımdaki en büyük numara + 1). j sınır dışı → ModelError.
    """
    m = len(ag.ucgenler)
    if isinstance(j, bool) or not isinstance(j, (int, np.integer)) or not 0 <= int(j) < m:
        raise ModelError(f"Sınır üçgeni indeksi {j!r} geçersiz (0..{m - 1})")
    j = int(j)
    sira = {int(k): i for i, k in enumerate(ag.kimlik)}
    tri = ag.ucgenler[j]
    c = np.mean([ag.X[sira[int(k)]] for k in tri], axis=0)
    n = triangle_normals(ag.model, ag.ucgenler[j : j + 1])[0]
    tanimi = {"nokta": [float(v) for v in c], "normal": [float(v) for v in n], "tol": TOL_KUTU * ag.L_kutu}
    s = Secim(_sonraki_kimlik("s", [x.kimlik for x in tanim.secimler]), "duzlem", tanimi)
    return dataclasses.replace(s, dugum_sayisi=len(secim_uygula(ag, s)[0]))


def silindir_secimi(tanim: AnalizTanimi, ag: Ag, nokta, eksen, r: float) -> Secim:
    """Eksen noktası, yönü ve yarıçapla silindir seçimi (`on_cylinder`). Sıfır eksen, r ≤ 0 → ModelError."""
    tanimi = {
        "nokta": _vektor(nokta, "Eksen noktası"),
        "eksen": _vektor(eksen, "Silindir ekseni"),
        "r": _sonlu(r, "Silindir yarıçapı"),
        "tol": TOL_KUTU * ag.L_kutu,
    }
    on_cylinder(tanimi["nokta"], tanimi["eksen"], tanimi["r"], tanimi["tol"])  # doğrulama → ModelError
    s = Secim(_sonraki_kimlik("s", [x.kimlik for x in tanim.secimler]), "silindir", tanimi)
    return dataclasses.replace(s, dugum_sayisi=len(secim_uygula(ag, s)[0]))


def secim_ekle(tanim: AnalizTanimi, secim: Secim) -> AnalizTanimi:
    """Seçim eklenmiş yeni tanım. Boş seçim (düğüm yok) → ModelError."""
    if secim.dugum_sayisi == 0:
        raise ModelError(f"Seçim {secim.kimlik} ({secim.tur}) hiçbir düğümü kapsamıyor")
    if any(s.kimlik == secim.kimlik for s in tanim.secimler):
        raise ModelError(f"Seçim kimliği {secim.kimlik!r} zaten var")
    return dataclasses.replace(tanim, secimler=(*tanim.secimler, secim))


def _kosul_degeri(tur: str, deger) -> tuple:
    if tur == "mesnet":
        dofs = (
            [deger] if isinstance(deger, str) else list(deger) if isinstance(deger, (list, tuple)) else None
        )
        if (
            not dofs
            or not all(isinstance(d, str) and d in DOFLAR for d in dofs)
            or len(set(dofs)) != len(dofs)
        ):
            raise ModelError(f"Mesnet serbestlik dereceleri {DOFLAR} içinden olmalı ({deger!r})")
        return tuple(dofs)
    if tur == "cekme":
        return tuple(_vektor(deger, "Yüzey çekmesi"))
    v = deger
    if isinstance(v, (list, tuple)):
        if len(v) != 1:
            raise ModelError(f"Basınç tek sayı olmalı ({deger!r})")
        v = v[0]
    if isinstance(v, (bool, str)):
        raise ModelError(f"Basınç sayı olmalı ({deger!r})")
    return (_sonlu(v, "Basınç"),)


def kosul_ekle(tanim: AnalizTanimi, secim: str, tur: str, deger) -> AnalizTanimi:
    """Koşul eklenmiş yeni tanım (kimlik "k<n>"). Bilinmeyen seçim / tür, geçersiz dof, sonlu olmayan değer,
    3 bileşenli olmayan çekme → ModelError."""
    if not any(s.kimlik == secim for s in tanim.secimler):
        raise ModelError(f"Bilinmeyen seçim {secim!r}")
    if tur not in KOSUL_TURLERI:
        raise ModelError(f"Koşul türü {KOSUL_TURLERI} içinden olmalı ({tur!r})")
    k = Kosul(_sonraki_kimlik("k", [x.kimlik for x in tanim.kosullar]), secim, tur, _kosul_degeri(tur, deger))
    return dataclasses.replace(tanim, kosullar=(*tanim.kosullar, k))


def kosul_sil(tanim: AnalizTanimi, kimlik: str) -> AnalizTanimi:
    """Koşulu çıkarır. Bilinmeyen kimlik → KeyError; kilitli (örnek) koşul → ModelError."""
    k = next((x for x in tanim.kosullar if x.kimlik == kimlik), None)
    if k is None:
        raise KeyError(f"Bilinmeyen koşul {kimlik!r}")
    if k.kilitli:
        raise ModelError(f"Koşul {kimlik} örneğin koşulu (kilitli); silinemez")
    return dataclasses.replace(tanim, kosullar=tuple(x for x in tanim.kosullar if x.kimlik != kimlik))


def h_degistir(tanim: AnalizTanimi, h: float) -> AnalizTanimi:
    """Yeni ağ boyu (seçimler tanımlarından yeniden uygulanır). h ≤ 0 ya da sonlu değil → ModelError."""
    if isinstance(h, bool):
        raise ModelError(f"Ağ boyu sayı olmalı ({h!r})")
    h = _sonlu(h, "Ağ boyu h")
    if h <= 0:
        raise ModelError(f"Ağ boyu h pozitif olmalı (h={h})")
    return dataclasses.replace(tanim, h=h)


def model_kur(tanim: AnalizTanimi, ag: Ag) -> Model:
    """Ağın temiz kopyası + koşullar listedeki sırayla: mesnet → `fix`, cekme → `add_traction`,
    basinc → `add_pressure`. `ag.model` değişmez."""
    M = ag.model  # sığ kopya: düğüm / eleman kayıtları değişmez, yalnız bcs / loads listeleri yenidir
    m = dataclasses.replace(
        M,
        nodes=list(M.nodes),
        elements=list(M.elements),
        materials=list(M.materials),
        sections=list(M.sections),
        bcs=list(M.bcs),
        loads=list(M.loads),
    )
    secimler = {s.kimlik: s for s in tanim.secimler}
    for k in tanim.kosullar:
        if k.secim not in secimler:
            raise ModelError(f"Koşul {k.kimlik}: bilinmeyen seçim {k.secim!r}")
        dugum, ucgen, _ = secim_uygula(ag, secimler[k.secim])
        if not dugum:
            raise ModelError(f"Koşul {k.kimlik}: seçim {k.secim} bu ağda hiçbir düğümü kapsamıyor")
        if k.tur == "mesnet":
            fix(m, dugum, tuple(k.deger))
        elif k.tur == "cekme":
            add_traction(m, ucgen, tuple(k.deger))
        else:
            add_pressure(m, ucgen, float(k.deger[0]))
    return m


# ---------------------------------------------------------------- çözüm

# Son çözümler: (tanım, ağ, çözüm), aynı *nesneler* (is) için çözüm yeniden hesaplanmaz. Tanım ve ağ
# değişmez kabul edilir (her düzenleme yeni tanım döndürür), bu yüzden kimlik eşitliği girdi eşitliğidir.
_COZUM_ONBELLEGI = 4
_COZUMLER: list[tuple[AnalizTanimi, Ag, Cozum]] = []


def coz(tanim: AnalizTanimi, ag: Ag) -> Cozum:
    """`solve(model)` + `nodal_stress_tensors` + `von_mises` + `principal_stresses`.

    ozet: u_max = max |u_i|, vm_max ve düğüm kimlikleri; tepki = mesnet tepkilerinin toplamı;
    yuk = Load toplamı; denge = tepki + yuk; guvenlik = Re / vm_max (Re None → None; vm_max = 0 → ModelError);
    olcek = OLCEK_KUTU · L_kutu / u_max (u_max = 0 → None). Mesnet eksik → çekirdeğin ModelError'ı.
    Aynı (tanım, ağ) nesneleri için son çözüm önbellekten döner (K21).
    """
    for t0, a0, c0 in _COZUMLER:
        if t0 is tanim and a0 is ag:
            return c0
    m = model_kur(tanim, ag)
    r = solve(m)
    u = np.asarray(r.u, dtype=float).reshape(-1, 3)
    S = nodal_stress_tensors(m, r.u)
    sigma = np.array([S[n.id] for n in m.nodes], dtype=float).reshape(-1, 6)
    vm = np.asarray(von_mises(sigma), dtype=float)
    asal = np.asarray(principal_stresses(sigma), dtype=float)

    R = np.asarray(r.reactions, dtype=float).reshape(-1, 3).sum(axis=0)
    F = np.zeros(3)
    for ld in m.loads:
        F[DOFLAR.index(ld.dof)] += ld.value
    nu = np.linalg.norm(u, axis=1)
    iu, iv = int(np.argmax(nu)), int(np.argmax(vm))
    u_max, vm_max = float(nu[iu]), float(vm[iv])
    if tanim.Re is None:
        guvenlik = None
    elif vm_max == 0.0:
        raise ModelError("En büyük von Mises 0: güvenlik katsayısı tanımsız (yük yok mu?)")
    else:
        guvenlik = float(tanim.Re) / vm_max
    ozet = {
        "u_max": u_max,
        "u_max_dugum": int(ag.kimlik[iu]),
        "vm_max": vm_max,
        "vm_max_dugum": int(ag.kimlik[iv]),
        "tepki": [float(v) for v in R],
        "yuk": [float(v) for v in F],
        "denge": [float(v) for v in R + F],
        "guvenlik": guvenlik,
        "olcek": OLCEK_KUTU * ag.L_kutu / u_max if u_max > 0.0 else None,
    }
    c = Cozum(u=u, sigma=sigma, vm=vm, asal=asal, ozet=ozet)
    _COZUMLER.insert(0, (tanim, ag, c))
    del _COZUMLER[_COZUM_ONBELLEGI:]
    return c


def sonda_degerleri(
    model: Model, degerler: np.ndarray, p0, p1, n: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """[p0, p1] üzerinde n eşit aralıklı noktada barisentrik ara değer (gmsh'siz, herhangi bir tet4 modeli).

    degerler: (nd,) düğüm değerleri, `model.nodes` sırası. Dönüş (s float64[n] yay uzunluğu,
    deger float64[n], iceride uint8[n]); hiçbir tette olmayan noktada iceride 0, deger 0.
    Birden çok tet içeriyorsa (ortak yüz) ilk eleman. n < 2 ya da n > SONDA_N_MAX, p0 = p1 → ModelError.
    """
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or not 2 <= int(n) <= SONDA_N_MAX:
        raise ModelError(f"Sonda nokta sayısı 2..{SONDA_N_MAX} arasında tam sayı olmalı (n={n!r})")
    n = int(n)
    a, b = np.array(_vektor(p0, "Sonda başı p0")), np.array(_vektor(p1, "Sonda sonu p1"))
    boy = float(np.linalg.norm(b - a))
    if boy == 0.0:
        raise ModelError("Sonda başı ve sonu aynı nokta (p0 = p1)")
    X, E = _tet_dizileri(model)
    v = np.asarray(degerler, dtype=float).ravel()
    if v.shape != (len(X),) or not np.all(np.isfinite(v)):
        raise ModelError(f"Sonda değerleri düğüm sayısı ({len(X)}) kadar sonlu sayı olmalı")

    t = np.linspace(0.0, 1.0, n)
    P = a + t[:, None] * (b - a)
    s = t * boy
    A = X[E]  # (ne, 4, 3)
    lo, hi = A.min(axis=1), A.max(axis=1)
    pay = 1e-9 * max(1.0, float(np.abs(X).max()))
    M = np.stack([A[:, 1] - A[:, 0], A[:, 2] - A[:, 0], A[:, 3] - A[:, 0]], axis=-1)
    Minv = np.linalg.inv(M)
    deger = np.zeros(n)
    iceride = np.zeros(n, dtype=np.uint8)
    for k, p in enumerate(P):
        aday = np.flatnonzero(np.all((p >= lo - pay) & (p <= hi + pay), axis=1))
        if not len(aday):
            continue
        l123 = np.einsum("eij,ej->ei", Minv[aday], p - A[aday, 0])
        lam = np.column_stack([1.0 - l123.sum(axis=1), l123])
        ok = np.flatnonzero((lam >= -BARISENTRIK_EPS).all(axis=1))
        if len(ok):
            e = ok[0]
            deger[k] = float(lam[e] @ v[E[aday[e]]])
            iceride[k] = 1
    return s, deger, iceride


def bilesen_degerleri(cozum: Cozum, bilesen: str) -> np.ndarray:
    """BILESENLER'den biri → (nd,) düğüm değerleri. Bilinmeyen bileşen → ModelError."""
    if bilesen == "vm":
        return cozum.vm
    sutun = {"sxx": 0, "syy": 1, "szz": 2, "sxy": 3, "sxz": 4, "syz": 5}
    if bilesen in sutun:
        return cozum.sigma[:, sutun[bilesen]]
    if bilesen in ("s1", "s2", "s3"):
        return cozum.asal[:, int(bilesen[1]) - 1]
    raise ModelError(f"Bilinmeyen gerilme bileşeni {bilesen!r}; {BILESENLER} içinden olmalı")


def yakinsama(tanim: AnalizTanimi) -> list[dict]:
    """h·{1, 1/1.5, 1/2.25} ağlarında ayrı ayrı kurup çözer → [{h, dugum, u_max, vm_max, neden}].

    Ağ kurulamayan (ör. max_nodes aşılan) satırda dugum/u_max/vm_max None, neden metni dolu (sahte sayı yok).
    """
    satirlar = []
    for k in YAKINSAMA_ORANLARI:
        h = tanim.h / k
        try:
            ag = ag_kur(tanim, h)
        except ModelError as e:
            satirlar.append({"h": h, "dugum": None, "u_max": None, "vm_max": None, "neden": str(e)})
            continue
        c = coz(tanim, ag)
        satirlar.append(
            {
                "h": h,
                "dugum": len(ag.model.nodes),
                "u_max": c.ozet["u_max"],
                "vm_max": c.ozet["vm_max"],
                "neden": None,
            }
        )
    return satirlar


# ---------------------------------------------------------------- analitik ve kontroller


def heywood_kt(d_W: float) -> float:
    """Heywood brüt kesit gerilme yığılması Kt_g = (2 + (1 − d/W)³) / (1 − d/W)."""
    q = 1.0 - _sonlu(d_W, "d/W")
    if not 0.0 < q < 1.0:
        raise ModelError(f"d/W 0 ile 1 arasında olmalı (d/W={d_W})")
    return (2.0 + q**3) / q


def kirsch_sxx(sigma: float, r: float, y) -> np.ndarray:
    """Sonsuz plakada θ = 90° doğrultusunda σ_xx(y) = σ/2·(2 + r²/y² + 3r⁴/y⁴); |y| < r → ModelError."""
    y = np.asarray(y, dtype=float)
    if np.any(np.abs(y) < r):
        raise ModelError(f"Kirsch eğrisi delik dışında tanımlı (|y| ≥ r = {r})")
    return sigma / 2.0 * (2.0 + r**2 / y**2 + 3.0 * r**4 / y**4)


def konsol_sehim(P: float, L: float, E: float, b: float, h: float) -> float:
    """Euler–Bernoulli δ = P·L³ / (3·E·I), I = b·h³/12."""
    I_ = b * h**3 / 12.0
    return P * L**3 / (3.0 * E * I_)


def timoshenko_sehim(P: float, L: float, E: float, nu: float, b: float, h: float) -> float:
    """δ_T = δ + P·L / (κ·G·A), κ = 5/6, G = E / (2(1 + ν)), A = b·h."""
    G = E / (2.0 * (1.0 + nu))
    return konsol_sehim(P, L, E, b, h) + P * L / (5.0 / 6.0 * G * b * h)


def _fem_degeri(cozum: Cozum, anahtar: str) -> float:
    if anahtar == "u_max":
        return cozum.ozet["u_max"]
    if anahtar == "vm_max":
        return cozum.ozet["vm_max"]
    if anahtar == "sxx_max":
        return float(cozum.sigma[:, 0].max())
    raise ModelError(f"Bilinmeyen FEM karşılaştırma anahtarı {anahtar!r}")


def analitik_satirlari(tanim: AnalizTanimi, cozum: Cozum | None) -> list[dict]:
    """Tanımın analitik satırları; fem = çözümden okunan değer (çözüm yoksa None), fark = fem / deger − 1."""
    satirlar = []
    for a in tanim.analitik:
        fem = None if (cozum is None or a.fem is None) else _fem_degeri(cozum, a.fem) / a.bolen
        fark = None if fem is None else fem / a.deger - 1.0
        satirlar.append(
            {"ad": a.ad, "formul": a.formul, "deger": a.deger, "birim": a.birim, "fem": fem, "fark": fark}
        )
    return satirlar


def analitik_sapma_kontrolu(analitik: list[dict]) -> dict | None:
    """|fark| > ANALITIK_ESIK olan satır varsa uyari, aksi tamam; fem'li satır yoksa None (listede yok)."""
    farklar = [r["fark"] for r in analitik if r.get("fem") is not None and r.get("fark") is not None]
    if not farklar:
        return None
    en = max(abs(f) for f in farklar)
    uyari = en > ANALITIK_ESIK
    aciklama = (
        f"FEM ile analitik arasında %{100 * en:.1f} fark: ağ kaba olabilir (bilgi amaçlı)"
        if uyari
        else f"FEM analitik değerlere %{100 * ANALITIK_ESIK:.0f} içinde yakın"
    )
    return _kontrol(
        "analitik_sapma", "Analitik sapma", en, "", "uyari" if uyari else "tamam", aciklama, "SPEC 47"
    )


def _yakinsama_kontrolu(yakin: list[dict]) -> dict:
    vm = [r["vm_max"] for r in yakin if r.get("vm_max") is not None]
    if len(vm) < 2:
        return _kontrol(
            "yakinsama", "Ağ yakınsaması", None, "", "uyari", "Kıyas için en az iki ağ çözülemedi", "SPEC 47"
        )
    fark = abs(vm[-1] / vm[-2] - 1.0)
    uyari = fark > YAKINSAMA_ESIK
    aciklama = (
        f"Son iki ağda en büyük von Mises %{100 * fark:.1f} değişti: ağı inceltin"
        if uyari
        else f"Son iki ağda en büyük von Mises %{100 * fark:.1f} değişti"
    )
    return _kontrol(
        "yakinsama", "Ağ yakınsaması", fark, "", "uyari" if uyari else "tamam", aciklama, "SPEC 47"
    )


def kontroller(tanim: AnalizTanimi, ag: Ag, cozum: Cozum | None, yakin: list[dict] | None) -> list[dict]:
    """denge, ag_hacmi, akma, analitik_sapma, yakinsama (SPEC 47 "Kontroller (Analiz)" tablosu).

    Çözüm yoksa denge / akma / analitik_sapma yok; Re None → akma yok; yakınsama yoksa yakinsama yok.
    """
    K = []
    if cozum is not None:
        e = max(abs(v) for v in cozum.ozet["denge"])
        sinir = DENGE_ESIK * max(max(abs(v) for v in cozum.ozet["yuk"]), 1.0)
        hata = e > sinir
        K.append(
            _kontrol(
                "denge",
                "Denge",
                e,
                "N",
                "hata" if hata else "tamam",
                "Tepkiler ile yüklerin toplamı sıfır değil" if hata else "Tepkiler + yükler = 0",
                "SPEC 11",
            )
        )
    V = float(tanim.parca.volume)
    fark = abs(ag.hacim / V - 1.0) if V > 0 else math.inf
    uyari = fark > AG_HACMI_ESIK
    K.append(
        _kontrol(
            "ag_hacmi",
            "Ağ hacmi",
            fark if math.isfinite(fark) else None,
            "",
            "uyari" if uyari else "tamam",
            f"Ağ hacmi parça hacminden %{100 * fark:.2f} farklı" if uyari else "Ağ hacmi parça hacmine eşit",
            "SPEC 12",
        )
    )
    if cozum is not None and cozum.ozet["guvenlik"] is not None:
        g = cozum.ozet["guvenlik"]
        durum = "hata" if g < 1.0 else "uyari" if g < 1.5 else "tamam"
        aciklama = {
            "hata": "Akma aşılıyor (Re / σ_vM < 1)",
            "uyari": "Güvenlik katsayısı 1.5'ten küçük",
            "tamam": "Güvenlik katsayısı ≥ 1.5",
        }[durum]
        K.append(_kontrol("akma", "Akma güvenliği", g, "", durum, aciklama, "SPEC 13"))
    if cozum is not None:
        a = analitik_sapma_kontrolu(analitik_satirlari(tanim, cozum))
        if a is not None:
            K.append(a)
    if yakin is not None:
        K.append(_yakinsama_kontrolu(yakin))
    return K


def _secim_json(ag: Ag, s: Secim) -> dict:
    dugum, ucgen, alan = secim_uygula(ag, s)
    return {
        "kimlik": s.kimlik,
        "tur": s.tur,
        "tanim": s.tanim,
        "dugumler": [int(i) for i in dugum],
        "ucgenler": np.asarray(ucgen, dtype=np.int64).tolist(),
        "alan": alan,
        "kilitli": s.kilitli,
    }


def _kosul_json(k: Kosul) -> dict:
    deger = list(k.deger) if k.tur != "basinc" else float(k.deger[0])
    return {"kimlik": k.kimlik, "secim": k.secim, "tur": k.tur, "deger": deger, "kilitli": k.kilitli}


def analiz_json(
    tanim: AnalizTanimi, ag: Ag, cozum: Cozum | None = None, yakin: list[dict] | None = None
) -> dict:
    """Analiz sözlüğü (modül belgesindeki şema). nan / inf içermez."""
    p, mz = tanim.parca, tanim.malzeme
    return {
        "sema": SEMA,
        "ad": tanim.ad,
        "parca": {"ad": getattr(p, "name", tanim.ad), "hacim": float(p.volume)},
        "malzeme": {"ad": mz.name, "E": mz.E, "nu": mz.nu, "Re": tanim.Re},
        "ag": {
            "h": tanim.h,
            "dugum": len(ag.model.nodes),
            "eleman": len(ag.model.elements),
            "hacim": ag.hacim,
        },
        "secimler": [_secim_json(ag, s) for s in tanim.secimler],
        "kosullar": [_kosul_json(k) for k in tanim.kosullar],
        "cozum": None if cozum is None else dict(cozum.ozet),
        "analitik": analitik_satirlari(tanim, cozum),
        "egriler": [
            {"ad": e.ad, "p0": list(e.p0), "p1": list(e.p1), "s": list(e.s), "deger": list(e.deger)}
            for e in tanim.egriler
        ],
        "yakinsama": None if yakin is None else [dict(r) for r in yakin],
        "kontroller": kontroller(tanim, ag, cozum, yakin),
    }


def inp(tanim: AnalizTanimi, ag: Ag) -> str:
    """`fileio.calculix.to_inp(model_kur(tanim, ag))`."""
    return to_inp(model_kur(tanim, ag))


# ---------------------------------------------------------------- ikili diziler


def _blok(a: np.ndarray) -> bytes:
    """Dizinin little-endian baytları, 8'in katına sıfırla tamamlanmış."""
    b = np.ascontiguousarray(a).astype(a.dtype.newbyteorder("<"), copy=False).tobytes()
    return b + bytes(-len(b) % 8)


def _oku(veri: bytes, ofs: int, dtype: str, n: int) -> tuple[np.ndarray, int]:
    dt = np.dtype(dtype).newbyteorder("<")
    a = np.frombuffer(veri, dtype=dt, count=n, offset=ofs)
    boy = dt.itemsize * n
    return a.astype(dt.newbyteorder("="), copy=True), ofs + boy + (-boy % 8)


def _sema(veri: bytes) -> None:
    (sema,) = struct.unpack_from("<I", veri, 0)
    if sema != SEMA:
        raise ModelError(f"İkili dizi sürümü {sema}, beklenen {SEMA}")


def ag_ikili(ag: Ag) -> bytes:
    """Little-endian, her blok 8 baytın katına sıfırla tamamlanır (SPEC 24 biçimi):
    başlık uint32 sema, uint32 nd, uint32 m (+4 bayt dolgu); düğüm float32[nd·3]; sınır üçgeni uint32[m·3]
    (düğüm *indeksi*, 0 tabanlı, `kimlik` dizisine göre); düğüm kimliği int32[nd]."""
    sira = {int(k): i for i, k in enumerate(ag.kimlik)}
    U = np.array([[sira[int(k)] for k in tr] for tr in np.asarray(ag.ucgenler)], dtype=np.uint32).reshape(
        -1, 3
    )
    nd, m = len(ag.kimlik), len(U)
    return b"".join(
        [
            struct.pack("<IIII", SEMA, nd, m, 0),
            _blok(np.asarray(ag.X, dtype=np.float32).ravel()),
            _blok(U.ravel()),
            _blok(np.asarray(ag.kimlik, dtype=np.int32)),
        ]
    )


def ag_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`ag_ikili` → {"dugum" (nd, 3) float32, "ucgen" (m, 3) uint32, "kimlik" (nd,) int32}."""
    _sema(veri)
    _, nd, m, _ = struct.unpack_from("<IIII", veri, 0)
    X, ofs = _oku(veri, 16, "f4", nd * 3)
    U, ofs = _oku(veri, ofs, "u4", m * 3)
    K, _ = _oku(veri, ofs, "i4", nd)
    return {"dugum": X.reshape(nd, 3), "ucgen": U.reshape(m, 3), "kimlik": K}


def alan_ikili(cozum: Cozum) -> bytes:
    """başlık uint32 sema, uint32 nd; u float32[nd·3]; vm float32[nd]; asal float32[nd·3];
    tensör float32[nd·6] (xx, yy, zz, xy, xz, yz)."""
    nd = len(cozum.vm)
    return b"".join(
        [
            struct.pack("<II", SEMA, nd),
            _blok(np.asarray(cozum.u, dtype=np.float32).ravel()),
            _blok(np.asarray(cozum.vm, dtype=np.float32)),
            _blok(np.asarray(cozum.asal, dtype=np.float32).ravel()),
            _blok(np.asarray(cozum.sigma, dtype=np.float32).ravel()),
        ]
    )


def alan_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`alan_ikili` → {"u" (nd, 3), "vm" (nd,), "asal" (nd, 3), "tensor" (nd, 6)}, hepsi float32."""
    _sema(veri)
    _, nd = struct.unpack_from("<II", veri, 0)
    u, ofs = _oku(veri, 8, "f4", nd * 3)
    vm, ofs = _oku(veri, ofs, "f4", nd)
    asal, ofs = _oku(veri, ofs, "f4", nd * 3)
    T, _ = _oku(veri, ofs, "f4", nd * 6)
    return {"u": u.reshape(nd, 3), "vm": vm, "asal": asal.reshape(nd, 3), "tensor": T.reshape(nd, 6)}


def sonda_ikili(s: np.ndarray, deger: np.ndarray, iceride: np.ndarray) -> bytes:
    """başlık uint32 sema, uint32 n; s float64[n]; deger float64[n]; iceride uint8[n]."""
    n = len(s)
    if len(deger) != n or len(iceride) != n:
        raise ModelError("Sonda dizilerinin boyları farklı")
    return b"".join(
        [
            struct.pack("<II", SEMA, n),
            _blok(np.asarray(s, dtype=np.float64)),
            _blok(np.asarray(deger, dtype=np.float64)),
            _blok(np.asarray(iceride, dtype=np.uint8)),
        ]
    )


def sonda_coz(veri: bytes) -> dict[str, np.ndarray]:
    """`sonda_ikili` → {"s", "deger", "iceride"}."""
    _sema(veri)
    _, n = struct.unpack_from("<II", veri, 0)
    s, ofs = _oku(veri, 8, "f8", n)
    d, ofs = _oku(veri, ofs, "f8", n)
    ic, _ = _oku(veri, ofs, "u1", n)
    return {"s": s, "deger": d, "iceride": ic}
