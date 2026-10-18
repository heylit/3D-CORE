"""
SPEC 61 — Tasarım için imalat (DFM) denetimi.

Model değiştiği anda işlenemeyecek ya da zor işlenecek yerleri bulur: iç köşe, derin dar cep, delik,
erişilemeyen yüz, ince duvar, torna kanalı / iç çap / köşe. CAM yolu üretmez; geometriye, takım kütüphanesine
ve izin verilen takım yönlerine bakar. Her bulgu ölçülen değeri, sınırı ve öneriyi sayıyla söyler.

Kural dosyası (`atolye/dfm_kurallari.json`): `{grup: {anahtar: {"deger": float, "kaynak": str}}}`.
Yerel ezme dosyası aynı biçimde, değer yalın sayı: `{"ince_duvar": {"aluminyum": 0.5}}`.
`kurallari_oku` her yaprağı `{"deger", "kaynak", "yerel"}` olarak döndürür; ezilen yaprakta `yerel = True`.
Bulgunun sınırı ezilmiş bir kuraldan geliyorsa `Bulgu.kural` "grup.anahtar (yerel)" olur,
değilse "grup.anahtar".
Yerel dosyada bilinmeyen grup ya da anahtar → `CamError`.
"""

from __future__ import annotations

import copy
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cam.features import recognize
from cam.model import CamError, LatheTool, LatheToolKind, Tool, ToolKind, ToolLibrary
from cam.offset import Region, offset
from geometry.part import GeometryError, Part

DERECELER = ("hata", "uyari", "bilgi")
TURLER = (
    "ic_kose",
    "derin_cep",
    "delik",
    "erisilemez",
    "ince_duvar",
    "torna_kanal",
    "torna_ic_cap",
    "torna_kose",
)
_ACI_TOL = 0.5  # rad: ağ açısal sapması gevşek, yoğunluğu kiriş sapması belirler (geometry/mesh ile aynı)
_CIFT = 2_000_000  # ışın izdüşümünde tek blokta değerlendirilen en çok (ışın, üçgen) çifti
KURAL_DOSYASI = Path(__file__).with_name("dfm_kurallari.json")


@dataclass(frozen=True)
class Bulgu:
    """Tek DFM bulgusu: bir yüze ya da noktaya bağlı, sayılı mesaj ve öneri."""

    tur: str
    derece: str
    yuzler: tuple[int, ...]  # Part yüz indisleri (Tezgah vurgusu); boş olabilir
    nokta: tuple[float, float, float] | None
    olculen: float
    sinir: float
    mesaj: str  # Türkçe, sayılı
    oneri: str  # Türkçe, sayılı; yoksa ""
    kural: str  # kural dosyasındaki anahtar ("grup.anahtar", ezilmişse sonuna " (yerel)")


@dataclass(frozen=True)
class Rapor:
    """Denetim sonucu: bulgular derece (hata → bilgi), sonra tur, sonra ilk yüz indisine göre sıralı."""

    bulgular: tuple[Bulgu, ...]
    tamam: bool  # bütçe aşıldıysa False ("kısmi" uyarısıyla)
    sure_s: float


# ---------------------------------------------------------------- kurallar


def _yaprak_deger(v, ad: str) -> float:
    if isinstance(v, dict):
        v = v.get("deger")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise CamError(f"DFM kuralı '{ad}' sonlu sayı olmalı ({v!r})")
    return float(v)


def kurallari_oku(yerel: str | Path | None = "yerel_parcalar/dfm-kurallari.json") -> dict:
    """Repodaki kural dosyası + (varsa) yerel ezme dosyası. Yerel dosya yoksa yalnız repodaki kurallar."""
    taban = json.loads(KURAL_DOSYASI.read_text(encoding="utf-8"))
    K = {
        g: {
            k: {"deger": _yaprak_deger(v, f"{g}.{k}"), "kaynak": str(v["kaynak"]), "yerel": False}
            for k, v in A.items()
        }
        for g, A in taban.items()
    }
    if yerel is None or not Path(yerel).is_file():
        return K
    try:
        ez = json.loads(Path(yerel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CamError(f"Yerel DFM kural dosyası okunamadı ({yerel}): {e}") from None
    if not isinstance(ez, dict):
        raise CamError(f"Yerel DFM kural dosyası sözlük olmalı ({yerel})")
    for g, A in ez.items():
        if g not in K:
            raise CamError(f"Yerel DFM kuralında bilinmeyen grup '{g}' (bilinenler: {', '.join(K)})")
        if not isinstance(A, dict):
            raise CamError(f"Yerel DFM kuralı '{g}' sözlük olmalı")
        for k, v in A.items():
            if k not in K[g]:
                raise CamError(
                    f"Yerel DFM kuralında bilinmeyen anahtar '{g}.{k}' (bilinenler: {', '.join(K[g])})"
                )
            K[g][k] = {"deger": _yaprak_deger(v, f"{g}.{k}"), "kaynak": f"yerel: {yerel}", "yerel": True}
    return K


class _Kurallar:
    """Kural sözlüğünden değer + Bulgu.kural adı."""

    def __init__(self, K: dict) -> None:
        if not isinstance(K, dict):
            raise CamError("kurallar sözlük olmalı (kurallari_oku çıktısı)")
        self.K = K

    def _yaprak(self, g: str, k: str):
        try:
            return self.K[g][k]
        except (KeyError, TypeError):
            raise CamError(f"DFM kuralı eksik: '{g}.{k}'") from None

    def __call__(self, g: str, k: str) -> float:
        return _yaprak_deger(self._yaprak(g, k), f"{g}.{k}")

    def ad(self, g: str, k: str) -> str:
        v = self._yaprak(g, k)
        return f"{g}.{k} (yerel)" if isinstance(v, dict) and v.get("yerel") else f"{g}.{k}"

    def has(self, g: str, k: str) -> bool:
        return isinstance(self.K.get(g), dict) and k in self.K[g]


# ---------------------------------------------------------------- yardımcılar


def _sayi(v: float) -> str:
    return f"{v:.3g}" if abs(v) < 1e4 else f"{v:.0f}"


def _frezeler(lib: ToolLibrary) -> list[Tool]:
    return [t for t in lib.tools if isinstance(t, Tool) and t.kind is ToolKind.FLAT]


def _birim(v, ad: str) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    if a.shape != (3,) or not np.all(np.isfinite(a)) or not np.linalg.norm(a) > 0:
        raise CamError(f"{ad}: 3 bileşenli, sonlu, sıfır olmayan vektör olmalı ({v!r})")
    return a / np.linalg.norm(a)


class _Baglam:
    """Denetimler arasında paylaşılan, tembel hesaplanan geometri (ağ, yüz örnekleri)."""

    def __init__(self, part: Part, Kr: _Kurallar) -> None:
        self.part = part
        self.Kr = Kr
        lo, hi = part.bbox
        self.lo, self.hi = np.asarray(lo, float), np.asarray(hi, float)
        self.diag = float(np.linalg.norm(self.hi - self.lo))
        self.tol = max(0.01, 1e-3 * self.diag)  # ağ kiriş sapması [mm]
        self.eps = 3.0 * self.tol  # ışın başlangıcının yüzeyden kaydırılması [mm]
        self._yuz: dict[int, np.ndarray] | None = None  # yüz indisi → üçgen köşeleri (t, 3, 3), dışa yönlü
        self._mesh: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._ornek: dict[int, tuple[np.ndarray, np.ndarray]] | None = None
        self._izd: dict[tuple, tuple] = {}
        self.planar = {f.index: f for f in part.planar_faces()}
        self.cyl = {f.index: f for f in part.cylindrical_faces()}

    def yuz_aglari(self) -> dict[int, np.ndarray]:
        """Yüz yüz üçgenleme (tek BRepMesh, girdi parçanın kopyasında: parçaya ağ yazılmaz)."""
        if self._yuz is None:
            kopya = copy.deepcopy(self.part.shape)
            kopya.mesh(self.tol, _ACI_TOL)
            self._yuz = {}
            for i, yuz in enumerate(kopya.faces()):
                V, T = yuz.tessellate(self.tol, _ACI_TOL)
                if T:
                    V = np.array([(v.X, v.Y, v.Z) for v in V], dtype=float)
                    self._yuz[i] = V[np.asarray(T)]
        return self._yuz

    @property
    def mesh(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Tüm yüzlerin üçgenleri (m, 3, 3), birim dış normaller (m, 3) ve her üçgenin yüz indisi (m,)."""
        if self._mesh is None:
            Y = self.yuz_aglari()
            P = np.concatenate(list(Y.values()))
            f = np.concatenate([np.full(len(v), i) for i, v in Y.items()])
            n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            A = np.linalg.norm(n, axis=1)
            iyi = A > 0
            self._mesh = (P[iyi], n[iyi] / A[iyi, None], f[iyi])
        return self._mesh

    def _izdusum(self, d: np.ndarray):
        """d'ye dik düzleme izdüşürülmüş ağ (yön başına bir kez): taban, köşeler, kutular, det, geçerli."""
        anahtar = tuple(np.round(d, 12))
        if anahtar not in self._izd:
            e1 = np.cross(d, np.eye(3)[int(np.argmin(np.abs(d)))])
            e1 /= np.linalg.norm(e1)
            Bz = np.stack([e1, np.cross(d, e1), d], axis=1)  # dünya → (u, v, derinlik)
            T = self.mesh[0] @ Bz
            v0, v1 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
            den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
            olcek = np.hypot(v0[:, 0], v0[:, 1]) * np.hypot(v1[:, 0], v1[:, 1])
            gecerli = np.abs(den) > 1e-12 * olcek  # d'ye paralel üçgen: izdüşümü çizgi
            self._izd[anahtar] = (Bz, T, T[:, :, :2].min(axis=1), T[:, :, :2].max(axis=1), den, gecerli)
        return self._izd[anahtar]

    def isin(self, R0: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Ortak yönlü ışınlar R0 + s·d (s > 0): en yakın isabet uzaklığı s (yoksa inf) ve üçgen indisi (−1).

        Ağ d'ye dik düzleme izdüşürülür; nokta-üçgen testi iki boyutlu barisentrik koordinatla, isabet
        derinliği üçgen düzleminden. d'ye paralel üçgenler (izdüşümü çizgi) atlanır. Üçgenler önce ışın
        kümesinin kutusuyla budanır.
        """
        Bz, T, tlo, thi, den, gecerli = self._izdusum(d)
        Q = R0 @ Bz  # (n, 3): (u, v, derinlik)
        n = len(Q)
        s_en = np.full(n, np.inf)
        k_en = np.full(n, -1)
        if n == 0:
            return s_en, k_en
        lo, hi = Q[:, :2].min(axis=0), Q[:, :2].max(axis=0)
        aday = gecerli & np.all(thi >= lo - 1e-9, axis=1) & np.all(tlo <= hi + 1e-9, axis=1)
        aday &= T[:, :, 2].max(axis=1) > Q[:, 2].min()
        idx = np.nonzero(aday)[0]
        if not idx.size:
            return s_en, k_en
        a, v0, v1 = T[idx, 0], T[idx, 1] - T[idx, 0], T[idx, 2] - T[idx, 0]
        inv = 1.0 / den[idx]
        blok = max(1, _CIFT // len(idx))
        for b in range(0, n, blok):
            q = Q[b : b + blok]
            wx = q[:, None, 0] - a[None, :, 0]
            wy = q[:, None, 1] - a[None, :, 1]
            l1 = (wx * v1[None, :, 1] - v1[None, :, 0] * wy) * inv
            l2 = (v0[None, :, 0] * wy - wx * v0[None, :, 1]) * inv
            ic = (l1 >= -1e-12) & (l2 >= -1e-12) & (l1 + l2 <= 1 + 1e-12)
            z = a[None, :, 2] + l1 * v0[None, :, 2] + l2 * v1[None, :, 2] - q[:, None, 2]
            z = np.where(ic & (z > 1e-9), z, np.inf)
            j = np.argmin(z, axis=1)
            sj = z[np.arange(len(q)), j]
            s_en[b : b + blok] = sj
            k_en[b : b + blok] = np.where(np.isfinite(sj), idx[j], -1)
        return s_en, k_en

    def ornekler(self) -> dict[int, tuple[np.ndarray, np.ndarray]]:
        """Yüz indisi → (N, 3) örnek noktalar ve (N, 3) dış normaller; alan ağırlıklı, sabit tohumlu."""
        if self._ornek is not None:
            return self._ornek
        N = int(self.Kr("ornek", "N"))
        rng = np.random.default_rng(int(self.Kr("ornek", "tohum")))
        out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for i, P in self.yuz_aglari().items():
            n2 = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            A = np.linalg.norm(n2, axis=1)
            if not A.sum() > 0:
                continue
            k = rng.choice(len(P), size=N, p=A / A.sum())
            u, v = rng.random(N), rng.random(N)
            ters = u + v > 1
            u[ters], v[ters] = 1 - u[ters], 1 - v[ters]
            Q = P[k, 0] + u[:, None] * (P[k, 1] - P[k, 0]) + v[:, None] * (P[k, 2] - P[k, 0])
            if i in self.planar:
                Nn = np.repeat(self.planar[i].normal[None, :], N, axis=0)
            else:
                Nn = n2[k] / np.where(A[k] > 0, A[k], 1.0)[:, None]
            out[i] = (Q, Nn)
        self._ornek = out
        return out

    def ham_yuz(self, f) -> bool:
        """Düzlemsel yüz ham parça (sınır kutusu) düzleminde mi: bağlama / ham yüz, işlenmez."""
        n = f.normal
        j = int(np.argmax(np.abs(n)))
        if abs(n[j]) < 1 - 1e-9:
            return False
        sinir = self.hi[j] if n[j] > 0 else self.lo[j]
        return abs(float(f.origin[j]) - float(sinir)) < self.tol


def _bulgu(tur, derece, yuzler, nokta, olculen, sinir, mesaj, oneri, kural) -> Bulgu:
    return Bulgu(
        tur=tur,
        derece=derece,
        yuzler=tuple(sorted(int(i) for i in yuzler)),
        nokta=None if nokta is None else tuple(float(x) for x in nokta),
        olculen=float(olculen),
        sinir=float(sinir),
        mesaj=mesaj,
        oneri=oneri,
        kural=kural,
    )


# ---------------------------------------------------------------- freze özellikleri (§1–§3)


def _bolge_noktalari(region) -> np.ndarray:
    return np.array([s.point(t) for lp in region.loops for s in lp.segments for t in (0.0, 0.5)], dtype=float)


def _yan_yuzler(B: _Baglam, region, z0: float, z1: float) -> list[int]:
    """Bölgenin sınır kutusu ve [z0, z1] içindeki dik duvar yüzleri (düzlem ya da Z eksenli silindir)."""
    Q = _bolge_noktalari(region)
    a, b = Q.min(axis=0) - B.tol, Q.max(axis=0) + B.tol
    out = []
    for f in B.planar.values():
        if abs(f.normal[2]) < 1e-6 and z0 - B.tol <= f.origin[2] <= z1 + B.tol:
            if np.all(f.origin[:2] >= a) and np.all(f.origin[:2] <= b):
                out.append(f.index)
    for f in B.cyl.values():
        if abs(abs(f.axis[2]) - 1) < 1e-6:
            zm = f.origin[2] + 0.5 * f.length * f.axis[2]
            if z0 - B.tol <= zm <= z1 + B.tol and np.all(f.origin[:2] >= a) and np.all(f.origin[:2] <= b):
                out.append(f.index)
    return out


def _r_kose(loops) -> float:
    """SPEC 27 §8 ile aynı: bölgeden bakınca ccw yaylar ve keskin sola dönüşler (0) arasında en küçüğü."""
    r = math.inf
    for lp in loops:
        segs = lp.segments
        for k, s in enumerate(segs):
            if hasattr(s, "c") and s.ccw:
                r = min(r, float(s.R))
            t1, t2 = segs[k - 1].tangent(1.0), s.tangent(0.0)
            if float(t1[0] * t2[1] - t1[1] * t2[0]) > 1e-6:
                r = 0.0
    return r


def _sigar(region, r: float) -> bool:
    """r yarıçaplı daire bölgeye sığar mı (iç ofset boş değil)."""
    if r <= 0:
        return True
    try:
        return bool(offset(region, r))
    except CamError:
        return False


def _genislik(region, tol: float) -> float:
    """Bölgeye sığan en büyük dairenin çapı: iç ofset boşalana kadar ikiye bölme (SPEC 61 §2)."""
    Q = _bolge_noktalari(region)
    lo, hi = 0.0, 0.5 * float(np.min(Q.max(axis=0) - Q.min(axis=0))) + tol
    while hi - lo > 0.5 * tol:
        m = 0.5 * (lo + hi)
        lo, hi = (m, hi) if _sigar(region, m) else (lo, m)
    return lo + hi


def _ic_kose(B: _Baglam, lib, r: float, h: float, yuzler, nokta) -> list[Bulgu]:
    Kr = B.Kr
    frezeler = _frezeler(lib)
    uygun = [t for t in frezeler if t.flute_length >= h - 1e-9]
    if not uygun:
        boy = max((t.flute_length for t in frezeler), default=0.0)
        return [
            _bulgu(
                "ic_kose",
                "hata",
                yuzler,
                nokta,
                h,
                boy,
                f"derinlik h = {_sayi(h)} mm için kütüphanede boyu yeten freze yok (en uzun kesici boy "
                f"{_sayi(boy)} mm)",
                f"kesici boyu ≥ {_sayi(h)} mm freze ekleyin ya da derinliği azaltın",
                "ic_kose",
            )
        ]
    R_min = min(t.D for t in uygun) / 2
    D_min = 2 * R_min
    if r == 0.0:
        return [
            _bulgu(
                "ic_kose",
                "hata",
                yuzler,
                nokta,
                0.0,
                R_min,
                f"keskin iç köşe frezeyle işlenemez (EDM ya da R ≥ {_sayi(R_min)}; en küçük uygun freze "
                f"Ø{_sayi(D_min)})",
                f"R ≥ {_sayi(R_min)}",
                "ic_kose",
            )
        ]
    if r < R_min - 1e-9:
        return [
            _bulgu(
                "ic_kose",
                "hata",
                yuzler,
                nokta,
                r,
                R_min,
                f"iç köşe R{_sayi(r)} → en az R{_sayi(R_min)}: kütüphanedeki en küçük uygun freze "
                f"Ø{_sayi(D_min)}, "
                f"boy {_sayi(min(t.flute_length for t in uygun if t.D == D_min))}",
                f"R ≥ {_sayi(R_min)}",
                "ic_kose",
            )
        ]
    oran = Kr("ic_kose", "oran_uyari")
    if r < oran * R_min - 1e-9:
        s = oran * R_min
        return [
            _bulgu(
                "ic_kose",
                "uyari",
                yuzler,
                nokta,
                r,
                s,
                f"iç köşe R{_sayi(r)} takım yarıçapına (R{_sayi(R_min)}) çok yakın: takım köşede tam "
                "sarılır, titreşim",
                f"R ≥ {_sayi(s)}",
                Kr.ad("ic_kose", "oran_uyari"),
            )
        ]
    return []


def _derin_cep(B: _Baglam, lib, region, h: float, yuzler, nokta) -> list[Bulgu]:
    Kr = B.Kr
    boylu = [t for t in _frezeler(lib) if t.flute_length >= h - 1e-9]
    if not boylu:
        return []  # boyu yeten freze yok: iç köşe denetimi söyledi
    tol = Kr("derin_cep", "genislik_tol")
    D_k = min(t.D for t in boylu)
    if h / D_k <= Kr("derin_cep", "lambda_uyari") and _sigar(region, D_k / 2 - tol):
        return []  # en ince uygun freze sığıyor ve onunla bile L/D sınırın altında: w gerekmez
    w = _genislik(region, tol)
    uygun = [t for t in boylu if t.D <= w + tol]
    if not uygun:
        D_k = min(t.D for t in boylu)
        return [
            _bulgu(
                "derin_cep",
                "hata",
                yuzler,
                nokta,
                w,
                D_k,
                f"cep genişliği {_sayi(w)} mm: derinlik {_sayi(h)} mm için boyu yeten frezelerin en "
                f"küçüğü Ø{_sayi(D_k)}",
                f"genişlik ≥ {_sayi(D_k)} mm ya da Ø ≤ {_sayi(w)}, boy ≥ {_sayi(h)} freze",
                Kr.ad("derin_cep", "lambda_hata"),
            )
        ]
    D = max(t.D for t in uygun)
    lam = h / D
    for k, derece in (("lambda_hata", "hata"), ("lambda_uyari", "uyari")):
        s = Kr("derin_cep", k)
        if lam > s:
            return [
                _bulgu(
                    "derin_cep",
                    derece,
                    yuzler,
                    nokta,
                    lam,
                    s,
                    f"derin dar cep: genişlik {_sayi(w)} mm, derinlik {_sayi(h)} mm, Ø{_sayi(D)} frezeyle "
                    f"L/D = {_sayi(lam)} > {_sayi(s)}",
                    f"derinliği ≤ {_sayi(s * D)} mm yapın ya da cebi genişletin",
                    Kr.ad("derin_cep", k),
                )
            ]
    return []


def _delik_yuzleri(B: _Baglam, hole) -> list[int]:
    a = hole.axis / np.linalg.norm(hole.axis)
    out = []
    for f in B.cyl.values():
        if f.concave and abs(abs(float(f.axis @ a)) - 1) < 1e-6 and abs(f.radius - hole.d / 2) < 1e-3:
            d = f.origin - hole.origin
            if np.linalg.norm(d - (d @ a) * a) < 1e-3:
                out.append(f.index)
    return out


def _duz_dip(B: _Baglam, hole) -> int | None:
    """Kör deliğin düz dip yüzü (normal −axis, eksen üzerinde, derinlikte); yoksa None."""
    a = hole.axis / np.linalg.norm(hole.axis)
    dip = hole.origin + hole.depth * a
    for f in B.planar.values():
        if float(f.normal @ a) < -1 + 1e-6 and np.linalg.norm(f.origin - dip) < max(1e-3, B.tol):
            return f.index
    return None


def _delik(B: _Baglam, lib, hole) -> list[Bulgu]:
    Kr = B.Kr
    d, h = float(hole.d), float(hole.depth)
    yuzler = _delik_yuzleri(B, hole)
    nokta = hole.origin
    out = []
    oran = h / d
    for k, derece, ek in (
        ("oran_hata", "hata", "tabancalı / BTA delme gerekir"),
        ("oran_uyari", "uyari", "gagalama ya da tabancalı matkap"),
    ):
        s = Kr("delik", k)
        if oran > s:
            out.append(
                _bulgu(
                    "delik",
                    derece,
                    yuzler,
                    nokta,
                    oran,
                    s,
                    f"derin delik Ø{_sayi(d)} × {_sayi(h)}: h/d = {_sayi(oran)} > {_sayi(s)} ({ek})",
                    f"derinliği ≤ {_sayi(s * d)} mm yapın ya da iki taraftan delin",
                    Kr.ad("delik", k),
                )
            )
            break
    tol = Kr("delik", "matkap_tol")
    matkaplar = [t for t in lib.tools if isinstance(t, Tool) and t.kind is ToolKind.DRILL]
    if not any(abs(t.D - d) <= tol for t in matkaplar):
        frezeler = _frezeler(lib)
        D_f = min((t.D for t in frezeler), default=math.inf)
        if frezeler and d < D_f:
            out.append(
                _bulgu(
                    "delik",
                    "hata",
                    yuzler,
                    nokta,
                    d,
                    D_f,
                    f"Ø{_sayi(d)} delik için kütüphanede matkap yok ve en küçük freze Ø{_sayi(D_f)} "
                    "delikten büyük",
                    f"Ø{_sayi(d)} matkap ekleyin ya da deliği Ø ≥ {_sayi(D_f)} yapın",
                    Kr.ad("delik", "matkap_tol"),
                )
            )
        else:
            en_yakin = min(matkaplar, key=lambda t: abs(t.D - d), default=None)
            yakin = f"; en yakın matkap Ø{_sayi(en_yakin.D)}" if en_yakin is not None else ""
            out.append(
                _bulgu(
                    "delik",
                    "bilgi",
                    yuzler,
                    nokta,
                    d,
                    en_yakin.D if en_yakin is not None else 0.0,
                    f"Ø{_sayi(d)} için kütüphanede matkap yok (tolerans ±{_sayi(tol)}){yakin}: frezeyle "
                    "helisel açılır",
                    f"çapı standart matkaba çekin (Ø{_sayi(en_yakin.D)})" if en_yakin is not None else "",
                    Kr.ad("delik", "matkap_tol"),
                )
            )
    if not hole.through:
        dip = _duz_dip(B, hole)
        if dip is not None:
            out.append(
                _bulgu(
                    "delik",
                    "bilgi",
                    [*yuzler, dip],
                    nokta,
                    0.0,
                    0.0,
                    f"kör delik Ø{_sayi(d)} dibi düz: matkap ucu açısı yok, düz dipli matkap ya da freze "
                    "gerekir",
                    "dip açısını matkap ucu açısıyla (118°) modelleyin",
                    "delik",
                )
            )
    return out


def _freze(B: _Baglam, lib) -> list[Bulgu]:
    try:
        F = recognize(B.part)
    except CamError:
        return []  # 2.5D değil: özellik denetimleri yapılamaz, erişim / ince duvar yine çalışır
    out: list[Bulgu] = []
    for p in F.pockets:
        h = p.z_top - p.z_bottom
        yuzler = _yan_yuzler(B, p.region, p.z_bottom, p.z_top)
        nokta = (*_bolge_noktalari(p.region)[0], p.z_bottom)
        out += _ic_kose(B, lib, p.r_corner, h, yuzler, nokta)
        out += _derin_cep(B, lib, p.region, h, yuzler, nokta)
    for o in F.opens:
        h = o.z_top - o.z_bottom
        try:
            region = Region(o.boundary, list(o.islands))
        except CamError:
            continue
        yuzler = _yan_yuzler(B, region, o.z_bottom, o.z_top)
        nokta = (*_bolge_noktalari(region)[0], o.z_bottom)
        r = _r_kose(region.holes)
        if math.isfinite(r):
            out += _ic_kose(B, lib, r, h, yuzler, nokta)
        out += _derin_cep(B, lib, region, h, yuzler, nokta)
    for hf in F.holes:
        out += _delik(B, lib, hf.hole)
    return out


# ---------------------------------------------------------------- erişim (§4)


def _erisim(B: _Baglam, yonler: list[np.ndarray]) -> list[Bulgu]:
    Kr = B.Kr
    S = B.ornekler()
    idx = [i for i in sorted(S) if not (i in B.planar and B.ham_yuz(B.planar[i]))]
    if not idx:
        return []
    P = np.concatenate([S[i][0] for i in idx])
    erisir_l = []
    for i in idx:
        Q, Nn = S[i]
        Oi = Q + B.eps * Nn
        e = np.zeros(len(Q), dtype=bool)
        for d in yonler:
            k = np.nonzero((Nn @ d >= -1e-9) & ~e)[0]
            if k.size:
                e[k[~np.isfinite(B.isin(Oi[k], d)[0])]] = True
        erisir_l.append(e)
    erisir = np.concatenate(erisir_l)
    out = []
    s_uyari = Kr("erisim", "oran_uyari")
    n0 = 0
    for i in idx:
        N = len(S[i][0])
        e = erisir[n0 : n0 + N]
        rho = float(e.mean())
        if rho < s_uyari:
            nokta = P[n0 + int(np.argmin(e))]
            derece = "hata" if rho == 0.0 else "uyari"
            out.append(
                _bulgu(
                    "erisilemez",
                    derece,
                    [i],
                    nokta,
                    rho,
                    s_uyari,
                    f"yüz {i}: yüzün %{_sayi(100 * (1 - rho))}'i izin verilen hiçbir takım yönünden "
                    "görünmüyor "
                    "(alttan kesik)",
                    "başka bir bağlama yönü ekleyin ya da alttan kesiği kaldırın",
                    Kr.ad("erisim", "oran_uyari"),
                )
            )
        n0 += N
    return out


# ---------------------------------------------------------------- ince duvar (§5)


def _malzeme_siniri(Kr: _Kurallar, grup: str | None) -> tuple[float, str, str]:
    """(t_min, kural adı, grup) — grup None → en sıkı (en büyük) sınır."""
    gruplar = [k for k in Kr.K.get("ince_duvar", {}) if k not in ("H_t_uyari", "paralel_aci_derece")]
    if grup is None:
        g = max(gruplar, key=lambda k: Kr("ince_duvar", k))
    else:
        g = str(grup)
        if g not in gruplar:
            raise CamError(f"Bilinmeyen malzeme grubu '{g}' (ince duvar kuralları: {', '.join(gruplar)})")
    return Kr("ince_duvar", g), Kr.ad("ince_duvar", g), g


def _ince_duvar(B: _Baglam, yonler: list[np.ndarray], grup: str | None) -> list[Bulgu]:
    Kr = B.Kr
    t_min, kural_t, g = _malzeme_siniri(Kr, grup)
    s_Ht = Kr("ince_duvar", "H_t_uyari")
    cos_p = math.cos(math.radians(Kr("ince_duvar", "paralel_aci_derece")))
    S = B.ornekler()
    duzlem = list(B.planar.values())

    def H(i: int) -> float:
        """Yüzün izin verilen takım eksenleri boyunca en büyük uzunluğu."""
        V = B.yuz_aglari().get(i)
        return 0.0 if V is None else max(float(np.ptp(V.reshape(-1, 3) @ d)) for d in yonler)

    out = []
    goruldu: set[tuple[int, ...]] = set()
    for f in sorted(duzlem, key=lambda f: f.index):
        if f.index not in S:
            continue
        P, _ = S[f.index]
        n = f.normal
        Oi = P - B.eps * n
        sk, kk = B.isin(Oi, -n)
        gecerli = np.isfinite(sk)
        gecerli[gecerli] = B.mesh[1][kk[gecerli]] @ n < -cos_p  # karşıt yüz paralel değil (kama): sayılmaz
        if not gecerli.any():
            continue
        k = int(np.argmin(np.where(gecerli, sk, np.inf)))
        t_en = float(sk[k]) + B.eps
        g_en = int(B.mesh[2][kk[k]])
        p_en = P[k]
        cift = (min(f.index, g_en), max(f.index, g_en))
        if cift in goruldu:
            continue
        goruldu.add(cift)
        if t_en < t_min - 1e-9:
            out.append(
                _bulgu(
                    "ince_duvar",
                    "hata",
                    cift,
                    p_en,
                    t_en,
                    t_min,
                    f"ince duvar t = {_sayi(t_en)} mm < {_sayi(t_min)} mm ({g}); sezgisel kural, FEM / "
                    "titreşim "
                    "hesabı değil",
                    f"duvar kalınlığı ≥ {_sayi(t_min)} mm",
                    kural_t,
                )
            )
            continue
        Hd = max(H(i) for i in cift)
        if Hd / t_en > s_Ht:
            out.append(
                _bulgu(
                    "ince_duvar",
                    "uyari",
                    cift,
                    p_en,
                    Hd / t_en,
                    s_Ht,
                    f"duvar yüksekliği / kalınlığı H/t = {_sayi(Hd)}/{_sayi(t_en)} = {_sayi(Hd / t_en)} > "
                    f"{_sayi(s_Ht)}: titreşim riski (sezgisel kural, FEM / titreşim hesabı değil)",
                    f"kalınlığı ≥ {_sayi(Hd / s_Ht)} mm yapın ya da yüksekliği azaltın",
                    Kr.ad("ince_duvar", "H_t_uyari"),
                )
            )
    return out


# ---------------------------------------------------------------- torna (§6)


class _Kenar:
    """Yönlendirilmiş kesit kenarı (z, x): P noktaları uç uca, yay için merkez ve dönüş yönü."""

    def __init__(self, P: np.ndarray, tur: str, c, ccw: bool) -> None:
        self.P, self.tur, self.c, self.ccw = P, tur, c, ccw

    def ters(self) -> _Kenar:
        return _Kenar(self.P[::-1], self.tur, self.c, not self.ccw)

    def teget(self, bas: bool) -> np.ndarray:
        if self.tur == "arc" and self.c is not None:
            r = (self.P[0] if bas else self.P[-1]) - self.c
            t = np.array([-r[1], r[0]]) if self.ccw else np.array([r[1], -r[0]])
        else:
            t = self.P[1] - self.P[0] if bas else self.P[-1] - self.P[-2]
        return t / np.linalg.norm(t)


def _zincir(edges, dis: bool) -> list[_Kenar]:
    """Kesit halkasının kenarlarını uç uca yönlendirir: dış halka CCW, iç halka CW (malzeme solda)."""
    K = [
        _Kenar(
            np.asarray(e.points, float),
            e.kind,
            None if e.center is None else np.asarray(e.center, float),
            e.ccw,
        )
        for e in edges
    ]
    if len(K) > 1:
        sonraki = K[1].P[[0, -1]]
        if np.min(np.linalg.norm(sonraki - K[0].P[0], axis=1)) < np.min(
            np.linalg.norm(sonraki - K[0].P[-1], axis=1)
        ):
            K[0] = K[0].ters()
        for k in range(1, len(K)):
            if np.linalg.norm(K[k].P[-1] - K[k - 1].P[-1]) < np.linalg.norm(K[k].P[0] - K[k - 1].P[-1]):
                K[k] = K[k].ters()
    Q = np.array([k.P[0] for k in K])
    alan = 0.5 * float(np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1]))
    if (alan < 0) == dis:
        K = [k.ters() for k in reversed(K)]
    return K


def _icine(z: float, x: float, polys: list[np.ndarray]) -> bool:
    ic = False
    for Q in polys:
        for k in range(len(Q)):
            (z1, x1), (z2, x2) = Q[k - 1], Q[k]
            if (x1 > x) != (x2 > x) and z < z1 + (x - x1) * (z2 - z1) / (x2 - x1):
                ic = not ic
    return ic


def _torna(B: _Baglam, lib) -> tuple[bool, list[Bulgu]]:
    """(dönel mi, bulgular). Dönel: eksen bulunur ve tüm yüzler o eksene göre dönel."""
    if not B.cyl:
        return False, []
    try:
        sec = B.part.axial_section(axis="auto")
    except GeometryError:
        return False, []
    if sec.off_axis_faces or sec.unknown_faces or not sec.faces:
        return False, []
    Kr = B.Kr
    o, a = np.asarray(sec.origin, float), np.asarray(sec.axis, float)
    halkalar = [_zincir(f.outer, True) for f in sec.faces] + [
        _zincir(h, False) for f in sec.faces for h in f.holes
    ]
    polys = [np.concatenate([k.P[:-1] for k in hl]) for hl in halkalar]
    zs = np.concatenate([Q[:, 0] for Q in polys])
    z_min, z_max = float(zs.min()), float(zs.max())
    tol = max(1e-3, B.tol)

    def silindirler(x: float, z0: float, z1: float) -> list[int]:
        out = []
        for f in B.cyl.values():
            if abs(f.radius - x) < tol and abs(abs(float(f.axis @ a)) - 1) < 1e-6:
                u0 = float((f.origin - o) @ a)
                u1 = u0 + f.length * float(f.axis @ a)
                if min(u0, u1) < max(z0, z1) - tol and max(u0, u1) > min(z0, z1) + tol:
                    out.append(f.index)
        return out

    kanal = [
        t for t in lib.tools if isinstance(t, LatheTool) and t.kind is LatheToolKind.GROOVE and t.width > 0
    ]
    tornalar = [
        t
        for t in lib.tools
        if isinstance(t, LatheTool) and t.kind in (LatheToolKind.TURN, LatheToolKind.BORE)
    ]
    w_min = min((t.width for t in kanal), default=None)
    r_burun = min((t.nose_r for t in tornalar), default=None)
    out: list[Bulgu] = []
    for hl in halkalar:
        E = list(hl)
        for k, e in enumerate(E):
            p0, p1 = e.P[0], e.P[-1]
            if e.tur == "arc" and not e.ccw and r_burun is not None and e.c is not None:
                R = float(np.linalg.norm(p0 - e.c))
                if R < r_burun - 1e-9:
                    out.append(
                        _bulgu(
                            "torna_kose",
                            "hata",
                            silindirler(R, p0[0], p1[0]),
                            o + p0[0] * a,
                            R,
                            r_burun,
                            f"iç köşe R{_sayi(R)} kütüphanedeki en küçük uç burun yarıçapından "
                            f"(r{_sayi(r_burun)}) küçük",
                            f"R ≥ {_sayi(r_burun)}",
                            "torna",
                        )
                    )
            if e.tur != "line" or abs(p1[1] - p0[1]) > tol or p0[1] < tol:
                continue
            onceki, sonraki = E[k - 1], E[(k + 1) % len(E)]
            t_on, t, t_son = onceki.teget(False), e.teget(True), sonraki.teget(True)
            ic1 = float(t_on[0] * t[1] - t_on[1] * t[0]) < -1e-6
            ic2 = float(t[0] * t_son[1] - t[1] * t_son[0]) < -1e-6
            x = float(p0[1])
            z0, z1 = sorted((float(p0[0]), float(p1[0])))
            w = z1 - z0
            if ic1 and ic2 and w_min is not None and w < w_min - 1e-9:
                out.append(
                    _bulgu(
                        "torna_kanal",
                        "hata",
                        silindirler(x, z0, z1),
                        o + 0.5 * (z0 + z1) * a,
                        w,
                        w_min,
                        f"kanal genişliği {_sayi(w)} mm < kütüphanedeki en dar kanal ucu {_sayi(w_min)} mm",
                        f"kanal genişliği ≥ {_sayi(w_min)} mm ya da {_sayi(w)} mm kanal ucu ekleyin",
                        "torna",
                    )
                )
            if p1[0] > p0[0]:  # +z yönünde ilerleyen yatay kenar: malzeme üstte → iç çap
                arka = any(_icine(z, 0.5 * x, polys) for z in np.linspace(z_min, z0, 9)[:-1] + 1e-6)
                on = any(_icine(z, 0.5 * x, polys) for z in np.linspace(z1, z_max, 9)[1:] - 1e-6)
                boylar = ([z1 - z_min] if not arka else []) + ([z_max - z0] if not on else [])
                if not boylar:
                    continue
                L, D = min(boylar), 2 * x
                for kk, derece in (("ic_cap_hata", "hata"), ("ic_cap_uyari", "uyari")):
                    s = Kr("torna", kk)
                    if L / D > s:
                        out.append(
                            _bulgu(
                                "torna_ic_cap",
                                derece,
                                silindirler(x, z0, z1),
                                o + 0.5 * (z0 + z1) * a,
                                L / D,
                                s,
                                f"iç çap Ø{_sayi(D)}, boy {_sayi(L)} mm: L/D = {_sayi(L / D)} > {_sayi(s)} "
                                "(delik çubuğu sarkması)",
                                f"boyu ≤ {_sayi(s * D)} mm yapın ya da çapı büyütün",
                                Kr.ad("torna", kk),
                            )
                        )
                        break
    return True, out


# ---------------------------------------------------------------- denetle


_ADIM_TURU = {"torna": "torna_kanal", "freze": "ic_kose", "ince duvar": "ince_duvar", "erişim": "erisilemez"}


def _sira(b: Bulgu) -> tuple:
    return (DERECELER.index(b.derece), TURLER.index(b.tur), b.yuzler[0] if b.yuzler else -1, b.mesaj)


def denetle(
    part: Part,
    lib: ToolLibrary,
    yonler: Sequence[tuple[float, float, float]] = ((0, 0, 1),),
    malzeme_grubu: str | None = None,
    kurallar: dict | None = None,
    butce_s: float | None = 1.0,
) -> Rapor:
    """Parçayı DFM kurallarıyla denetler. malzeme_grubu None ise ince duvar için en sıkı sınır kullanılır."""
    t0 = time.perf_counter()
    if not isinstance(lib, ToolLibrary):
        raise CamError(f"lib ToolLibrary olmalı ({type(lib).__name__})")
    if butce_s is not None and not (
        isinstance(butce_s, (int, float)) and math.isfinite(butce_s) and butce_s > 0
    ):
        raise CamError(f"butce_s pozitif sonlu sayı ya da None olmalı ({butce_s!r})")
    Y = [_birim(d, "yön") for d in yonler]
    if not Y:
        raise CamError("En az bir takım yönü gerekir")
    Kr = _Kurallar(kurallari_oku() if kurallar is None else kurallar)
    _malzeme_siniri(Kr, malzeme_grubu)  # bilinmeyen grup baştan hata
    B = _Baglam(part, Kr)
    bulgular: list[Bulgu] = []
    donel = [False]

    def torna() -> list[Bulgu]:
        donel[0], b = _torna(B, lib)
        return b

    adimlar = [
        ("freze", lambda: [] if donel[0] else _freze(B, lib)),
        ("ince duvar", lambda: _ince_duvar(B, Y, malzeme_grubu)),
        ("erişim", lambda: [] if donel[0] else _erisim(B, Y)),
    ]
    adimlar.insert(0, ("torna", torna))
    kalan: list[str] = []
    for ad, adim in adimlar:
        if butce_s is not None and time.perf_counter() - t0 > butce_s:
            kalan.append(ad)
            continue
        bulgular += adim()
    tamam = not kalan
    if kalan:
        sure = time.perf_counter() - t0
        bulgular.append(
            _bulgu(
                _ADIM_TURU[kalan[0]],
                "uyari",
                (),
                None,
                sure,
                float(butce_s),
                f"kısmi denetim: {_sayi(sure)} s bütçesi ({_sayi(float(butce_s))} s) aştı; denetlenmeyen: "
                f"{', '.join(kalan)}",
                "denetim arka planda tamamlanınca bulgular güncellenir",
                "butce",
            )
        )
    bulgular.sort(key=_sira)
    return Rapor(bulgular=tuple(bulgular), tamam=tamam, sure_s=time.perf_counter() - t0)
