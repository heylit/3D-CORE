"""
SPEC 06b — Waterline (sabit Z kontur) ince işleme.

Seviye z için girişim bölgesi I(z) = {c : z_CL(c) > z}. Lifler (X ve Y, ortak s_f ızgarası) üzerinde
her (lif, üçgen) çiftinin girişim aralığı tek aralıktır (z_tri içbükey); aralık uçları kontur noktalarıdır.
Örgü (weave) çizgesinin yarım-kenar yüzlerinden kapalı döngüler çıkar; döngüler uyarlamalı bölünür.
Tırmanma (M3): I(z) hareket yönünün sağında → dış sınır CW, iç sınır CCW.

Hız için: köşe testinin aralıkları kapalı formdur (d < f⁻¹(V_z − z)); tanım aralığı bir köşe aralığının
içinde kalan üçgen, birleşimin uçlarını değiştiremeyeceği için atlanır (sonuç değişmez).

Birimler: mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.cutter import Cutter
from cam.dropcutter import TOL, TriMesh, altin, girisim, kesici, tri_z
from cam.model import CamError, Move, MoveType, Tool, Toolpath

_KESIT = 7  # çok parçalı bölmede tur başına iç nokta (aralık 8'e bölünür)
_TUR = 18  # bölme turu: aralık 8⁻¹⁸ = 2⁻⁵⁴ katına iner
_BOLME_TOL = 1e-10  # uyarlamalı bölme noktalarının doğruluğu [mm]
# Lif aralığı uçları makine duyarlığına (≈ 2⁻⁵⁴) iner: uç bir lif çizgisine denk geldiğinde X ve Y
# liflerinin aynı kararı vermesi için kaba doğruluk yetmez (örgü tutarlılığı).
_AZ_SATIR = 64  # uyarlamalı bölmede bundan az satırda çok parçalı bölme
_COK_SATIR = 2000  # bundan çok satırda yüklem satır sayısıyla pahalanır → çok parçalı yerine ikiye bölme
_ORNEK = 8  # uyarlamalı bölmede dik doğrultudaki örnek sayısı


def _gecis(yuklem, a: np.ndarray, b: np.ndarray, kesit: int = _KESIT, tur: int = _TUR) -> np.ndarray:
    """Her satırda yuklem(a) ≠ yuklem(b) olan [a, b] (skaler veya vektör uçlar) aralığında geçiş
    noktası: tur başına `kesit` iç nokta (çok parçalı ikiye bölme). yuklem(t, satırlar) → bool.

    Yüklem ucuzsa çok parçalı bölme Python turunu azaltır; pahalıysa (girişim) kesit = 1 en az
    yüklem çağrısıyla aynı doğruluğa iner."""
    n = len(a)
    satir = np.arange(n)
    durum_a = yuklem(a, satir)
    k = np.arange(1, kesit + 1) / (kesit + 1)
    for _ in range(tur):
        T = a[:, None] + (b - a)[:, None] * k[None, :]  # (n, kesit)
        S = yuklem(T.ravel(), np.repeat(satir, kesit)).reshape(n, kesit)
        degisti = S != durum_a[:, None]
        ilk = np.where(degisti.any(axis=1), degisti.argmax(axis=1), kesit)
        yeni_a = np.where(ilk > 0, T[satir, np.maximum(ilk - 1, 0)], a)
        yeni_b = np.where(ilk < kesit, T[satir, np.minimum(ilk, kesit - 1)], b)
        a, b = yeni_a, yeni_b
    return (a + b) / 2


def _ikiye(yuklem, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Uyarlamalı bölmenin sınır noktası: en uzun aralık _BOLME_TOL'a inene kadar. Az satırda çağrı
    başına sabit maliyet baskın → çok parçalı (az tur); çok satırda ikiye bölme (az yüklem)."""
    boy = float(np.max(np.abs(b - a))) if len(a) else 0.0
    bit = math.log2(max(boy, _BOLME_TOL) / _BOLME_TOL)
    if len(a) <= _AZ_SATIR:
        return _gecis(yuklem, a, b, _KESIT, max(1, math.ceil(bit / 3) + 1))
    return _gecis(yuklem, a, b, 1, max(1, math.ceil(bit) + 1))


def _lif_gecis(yuklem, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Lif aralığı ucu: az satırda çok parçalı (tur sayısı az), çok satırda ikiye bölme (yüklem az)."""
    if len(a) > _COK_SATIR:
        return _gecis(yuklem, a, b, 1, 3 * _TUR + 2)  # 2⁻⁵⁶
    return _gecis(yuklem, a, b)  # 8⁻¹⁸ = 2⁻⁵⁴


# ---------------------------------------------------------------- lifler ve aralıklar


def _lifler(lo: float, hi: float, R: float, s: float) -> np.ndarray:
    """Sınır kutusu R + s büyütülür; x_i = x_min + i·s."""
    bas = lo - R - s
    n = math.floor((hi + R + s - bas) / s + 1e-9)
    return bas + s * np.arange(n + 1)


def _birlestir(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Aralıkların birleşimi (örtüşen veya TOL içinde değenler birleşir); TOL'dan kısa olanlar atılır."""
    if len(A) == 0:
        return A, B
    s = np.argsort(A, kind="stable")
    A, B = A[s], B[s]
    ca, cb = [A[0]], [B[0]]
    for a, b in zip(A[1:], B[1:], strict=True):
        if a <= cb[-1] + TOL:
            cb[-1] = max(cb[-1], b)
        else:
            ca.append(a)
            cb.append(b)
    ca, cb = np.array(ca), np.array(cb)
    uzun = cb - ca >= TOL
    return ca[uzun], cb[uzun]


def _tanim(P: np.ndarray, y0: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """y = y0 doğrusunun {c : dist(c, üçgen_xy) ≤ R} ile kesişimi [ta, tb] (boşsa ta > tb); R üçgen başına.

    Bölge dışbükeydir; sınırı köşe yayları ve R kadar kaydırılmış kenarlardan oluşur → uçlar bu
    parçaların doğruyla kesişimlerinin en küçüğü ve en büyüğü.
    """
    k = len(P)
    R = np.broadcast_to(np.asarray(R, dtype=float), (k,))
    ta = np.full(k, np.inf)
    tb = np.full(k, -np.inf)

    def ekle(x: np.ndarray, ok: np.ndarray) -> None:
        nonlocal ta, tb
        ta = np.where(ok, np.minimum(ta, x), ta)
        tb = np.where(ok, np.maximum(tb, x), tb)

    for j in range(3):
        dy = P[:, j, 1] - y0
        ok = np.abs(dy) <= R
        w = np.sqrt(np.maximum(R * R - dy * dy, 0.0))
        ekle(P[:, j, 0] - w, ok)
        ekle(P[:, j, 0] + w, ok)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        A, B = P[:, i, :2], P[:, j, :2]
        e = B - A
        L = np.hypot(e[:, 0], e[:, 1])
        ok_e = L > TOL
        with np.errstate(divide="ignore", invalid="ignore"):
            nu = np.column_stack([-e[:, 1], e[:, 0]]) / L[:, None]
        for sgn in (1.0, -1.0):
            a = A + sgn * R[:, None] * nu
            ya, yb = a[:, 1] - y0, a[:, 1] + e[:, 1] - y0
            ok = ok_e & (ya * yb <= 0) & (e[:, 1] != 0)
            with np.errstate(divide="ignore", invalid="ignore"):
                t = np.where(ok, -ya / e[:, 1], 0.0)
            ekle(a[:, 0] + t * e[:, 0], ok)
    return ta, tb


def _kose_araliklari(Vu: np.ndarray, K: Cutter, z: float, y0: float) -> tuple[np.ndarray, np.ndarray]:
    """Köşe testinin aralıkları (kapalı form): V_z − f(d) > z ⟺ d < f⁻¹(V_z − z) (h > f(R) ise d ≤ R)."""
    dy = np.abs(Vu[:, 1] - y0)
    h = Vu[:, 2] - z
    rho = K.f_ters(h)
    ok = (h > 0) & ((dy < rho) | ((h > K.height) & (dy <= K.R)))
    w = np.sqrt(np.maximum(rho[ok] ** 2 - dy[ok] ** 2, 0.0))
    return Vu[ok, 0] - w, Vu[ok, 0] + w


def _lif_araliklari(
    P: np.ndarray, n: np.ndarray, Vu: np.ndarray, K: Cutter, z: float, ys: np.ndarray
) -> list[tuple[np.ndarray, np.ndarray]]:
    """X lifleri (y = ys[j]) üzerinde I(z)'nin aralıkları: üçgen başına tek aralık, birleşim."""
    zmax = P[:, :, 2].max(axis=1)
    yuksek = zmax > z  # z_tri ≤ max P_z
    Py, ny = P[yuksek], n[yuksek]
    # z_tri(c) ≤ max P_z − f(dist(c, üçgen_xy)) → girişim yalnız dist < f⁻¹(max P_z − z) iken (uzanım ≤ R)
    uzan = K.f_ters(zmax[yuksek] - z)
    ymin = Py[:, :, 1].min(axis=1) - uzan
    ymax = Py[:, :, 1].max(axis=1) + uzan
    Vy = Vu[Vu[:, 2] > z]
    sonuc = []
    jl, tl, tal, tbl = [], [], [], []
    kose: list[tuple[np.ndarray, np.ndarray]] = []
    for j, y0 in enumerate(ys):
        ka, kb = _birlestir(*_kose_araliklari(Vy, K, z, y0))
        kose.append((ka, kb))
        tri = np.nonzero((ymin <= y0) & (ymax >= y0))[0]
        if len(tri) == 0:
            continue
        ta, tb = _tanim(Py[tri], np.full(len(tri), y0), uzan[tri])
        ok = ta <= tb
        if len(ka):  # tanım aralığı bir köşe aralığının içinde → birleşimi değiştiremez
            i = np.searchsorted(ka, ta, side="right") - 1
            ic = (i >= 0) & (ka[np.maximum(i, 0)] < ta - TOL) & (kb[np.maximum(i, 0)] > tb + TOL)
            ok &= ~ic
        jl.append(np.full(int(ok.sum()), j))
        tl.append(tri[ok])
        tal.append(ta[ok])
        tbl.append(tb[ok])
    if jl:
        J, Tr, TA, TB = (np.concatenate(v) for v in (jl, tl, tal, tbl))
    else:
        J = Tr = np.zeros(0, dtype=int)
        TA = TB = np.zeros(0)
    a_uc, b_uc = _ucgen_araliklari(Py[Tr], ny[Tr], ys[J], TA, TB, K, z)
    for j in range(len(ys)):
        sec = J == j
        ka, kb = kose[j]
        sonuc.append(_birlestir(np.concatenate([ka, a_uc[sec]]), np.concatenate([kb, b_uc[sec]])))
    return sonuc


def _ucgen_araliklari(
    P: np.ndarray, n: np.ndarray, y0: np.ndarray, ta: np.ndarray, tb: np.ndarray, K: Cutter, z: float
) -> tuple[np.ndarray, np.ndarray]:
    """Her (lif, üçgen) çiftinin {t : z_tri(t, y0) > z} aralığı; boşsa (nan, nan)."""
    k = len(P)
    a = np.full(k, np.nan)
    b = np.full(k, np.nan)
    if k == 0:
        return a, b

    def zt(t: np.ndarray, sec: np.ndarray) -> np.ndarray:
        return tri_z(P[sec], n[sec], np.column_stack([t, y0[sec]]), K)

    hepsi = np.arange(k)
    # girişim noktası t*: önce köşelerin dik ayakları ve orta nokta, olmazsa altın oran
    aday = np.column_stack([np.clip(P[:, :, 0], ta[:, None], tb[:, None]), (ta + tb) / 2])
    za = np.column_stack([zt(aday[:, i], hepsi) for i in range(aday.shape[1])])
    i = np.argmax(za, axis=1)
    t_ic = aday[hepsi, i]
    z_ic = za[hepsi, i]
    ara = z_ic <= z
    if np.any(ara):
        s = np.nonzero(ara)[0]
        zm, tm = altin(lambda t, s=s: zt(t, s), ta[s], tb[s])
        t_ic[s], z_ic[s] = tm, zm
    var = z_ic > z
    s = np.nonzero(var)[0]
    if len(s) == 0:
        return a, b

    # sol uç: [ta, t*], sağ uç: [t*, tb]; yüklem z_tri > z (dik duvar sıçramasında da çalışır)
    def yuklem(t: np.ndarray, satir: np.ndarray) -> np.ndarray:
        return zt_esik(t, s[satir]) > z

    def zt_esik(t: np.ndarray, sec: np.ndarray) -> np.ndarray:
        return tri_z(P[sec], n[sec], np.column_stack([t, y0[sec]]), K, esik=z)

    sol_ic = zt_esik(ta[s], s) > z
    sag_ic = zt_esik(tb[s], s) > z
    a[s] = ta[s]
    b[s] = tb[s]
    if np.any(~sol_ic):
        r = np.nonzero(~sol_ic)[0]
        a[s[r]] = _lif_gecis(lambda t, q, r=r: yuklem(t, r[q]), ta[s[r]], t_ic[s[r]])
    if np.any(~sag_ic):
        r = np.nonzero(~sag_ic)[0]
        b[s[r]] = _lif_gecis(lambda t, q, r=r: yuklem(t, r[q]), t_ic[s[r]], tb[s[r]])
    return a, b


# ---------------------------------------------------------------- örgü (weave)


def _orgu(xs: np.ndarray, ys: np.ndarray, X: list, Y: list) -> list[np.ndarray]:
    """Lif aralıklarından döngüler: yarım-kenar yüz yürüyüşü, yüz solda (I(z) sağda)."""
    pos: list[tuple[float, float]] = []
    komsu: list[list[int]] = []  # düğüm: [D, K, B, G] (E, N, W, S); yaprak: [tek komşu]
    yaprak: list[bool] = []

    def yeni(x: float, y: float, uc: bool) -> int:
        pos.append((x, y))
        komsu.append([-1] if uc else [-1, -1, -1, -1])
        yaprak.append(uc)
        return len(pos) - 1

    def icinde(aralik: tuple[np.ndarray, np.ndarray], v: float) -> bool:
        A, B = aralik
        i = int(np.searchsorted(A, v, side="right")) - 1
        return i >= 0 and A[i] < v < B[i]

    dugum: dict[tuple[int, int], int] = {}
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            if icinde(X[j], x) and icinde(Y[i], y):
                dugum[(i, j)] = yeni(float(x), float(y), False)

    def zincir(liste: list[int], ileri: int, geri: int) -> None:
        for u, v in zip(liste[:-1], liste[1:], strict=True):
            if yaprak[u]:
                komsu[u][0] = v
            else:
                komsu[u][ileri] = v
            if yaprak[v]:
                komsu[v][0] = u
            else:
                komsu[v][geri] = u

    for j, y in enumerate(ys):
        for a, b in zip(*X[j], strict=True):
            ic = [dugum[(i, j)] for i in range(len(xs)) if a < xs[i] < b and (i, j) in dugum]
            zincir([yeni(float(a), float(y), True), *ic, yeni(float(b), float(y), True)], 0, 2)
    for i, x in enumerate(xs):
        for c, d in zip(*Y[i], strict=True):
            ic = [dugum[(i, j)] for j in range(len(ys)) if c < ys[j] < d and (i, j) in dugum]
            zincir([yeni(float(x), float(c), True), *ic, yeni(float(x), float(d), True)], 1, 3)

    gorulen = [False] * len(pos)
    donguler = []
    for bas in range(len(pos)):
        if not yaprak[bas] or gorulen[bas]:
            continue
        noktalar = []
        u, v = bas, komsu[bas][0]
        while True:
            if yaprak[v]:
                gorulen[v] = True
                noktalar.append(pos[v])
                u, v = v, u
            else:
                d = komsu[v].index(u)
                u, v = v, komsu[v][(d - 1) % 4]  # gelinen kenardan saat yönünde ilk kenar
            if u == bas and v == komsu[bas][0]:
                break
        donguler.append(np.array(noktalar))
    return donguler


# ---------------------------------------------------------------- uyarlamalı bölme


def _bol(L: np.ndarray, icinde, tol: float, ds_min: float) -> np.ndarray:
    """Parça orta noktasından dik doğrultuda sınır aranır; |q − m| > tol ise q araya girer.

    Döngü I(z) sağda olacak yöndedir → dışa bakan normal sol normaldir. Sonucu belli olan parça (değişim
    yok veya q tol içinde) bir daha sorgulanmaz; yalnız yeni eklenen noktanın iki yanı yeniden bakılır.
    """
    bitti = np.zeros(len(L), dtype=bool)  # i: L[i] → L[i+1] parçası
    while True:
        Q = np.roll(L, -1, axis=0)
        e = Q - L
        boy = np.hypot(e[:, 0], e[:, 1])
        aday = np.nonzero((boy / 2 >= ds_min) & ~bitti)[0]
        if len(aday) == 0:
            return L
        m = (L[aday] + Q[aday]) / 2
        nrm = np.column_stack([-e[aday, 1], e[aday, 0]]) / boy[aday, None]
        ic_m = icinde(m)
        yon = np.where(ic_m[:, None], nrm, -nrm)
        s_lo = np.zeros(len(aday))
        s_hi = np.full(len(aday), np.nan)
        for k in range(1, _ORNEK + 1):
            s = boy[aday] * k / _ORNEK
            bekle = np.isnan(s_hi)
            if not np.any(bekle):
                break
            degisti = bekle & (icinde(m + s[:, None] * yon) != ic_m)
            s_hi = np.where(degisti, s, s_hi)
            s_lo = np.where(bekle & ~degisti, s, s_lo)
        var = ~np.isnan(s_hi)
        bitti[aday[~var]] = True
        if not np.any(var):
            return L
        lo, hi = s_lo[var], s_hi[var]
        mv, yv = m[var], yon[var]
        orta = _ikiye(lambda t, q, mv=mv, yv=yv: icinde(mv[q] + t[:, None] * yv[q]), lo, hi)
        q = mv + orta[:, None] * yv
        uzak = np.hypot(*(q - mv).T) > tol
        bitti[aday[var][~uzak]] = True
        if not np.any(uzak):
            return L
        sira = aday[var][uzak] + 1
        L = np.insert(L, sira, q[uzak], axis=0)
        bitti = np.insert(bitti, sira, False)
        bitti[sira - 1 + np.arange(len(sira))] = False  # bölünen parçanın ilk yarısı


# ---------------------------------------------------------------- arayüz


def _parametreler(fiber_step: float, tol: float, ds_min: float) -> None:
    for ad, v in (("fiber_step", fiber_step), ("tol", tol), ("ds_min", ds_min)):
        if not math.isfinite(v) or v <= 0:
            raise CamError(f"waterline: {ad} pozitif ve sonlu olmalı ({v})")


def waterline_loops(
    mesh: TriMesh,
    tool: Tool | Cutter,
    z: float,
    fiber_step: float,
    tol: float,
    ds_min: float,
    climb: bool = True,
) -> list[np.ndarray]:
    """z seviyesindeki döngüler; her biri (k, 2) XY, kapanış noktası tekrar edilmez."""
    K = kesici(tool)
    _parametreler(fiber_step, tol, ds_min)
    if not math.isfinite(z):
        raise CamError(f"waterline: z sonlu olmalı ({z})")
    lo, hi = mesh.bbox()
    xs = _lifler(lo[0], hi[0], K.R, fiber_step)
    ys = _lifler(lo[1], hi[1], K.R, fiber_step)
    Vu = mesh.V[np.unique(mesh.T)]
    takas = [1, 0, 2]
    X = _lif_araliklari(mesh._P, mesh._n, Vu, K, z, ys)
    Y = _lif_araliklari(mesh._P[:, :, takas], mesh._n[:, takas], Vu[:, takas], K, z, xs)

    def icinde(p: np.ndarray) -> np.ndarray:
        return girisim(mesh, K, p, z)

    donguler = []
    for D in _orgu(xs, ys, X, Y):
        D = _bol(D, icinde, tol, ds_min)
        if len(D) < 3:
            continue
        if not climb:
            D = D[::-1]
        k = int(np.lexsort((D[:, 1], D[:, 0]))[0])
        donguler.append(np.roll(D, -k, axis=0))
    donguler.sort(key=lambda D: (D[0, 0], D[0, 1]))
    return donguler


@dataclass
class Waterline:
    """Waterline yolu parametreleri [mm, mm/dk, dev/dk]; z_levels kesin azalan."""

    z_levels: list[float]
    fiber_step: float
    tol: float
    ds_min: float
    feed: float
    plunge_feed: float
    rpm: float
    z_safe: float
    clearance: float = 1.0
    climb: bool = True

    def __post_init__(self) -> None:
        zs = [float(v) for v in self.z_levels]
        if not zs:
            raise CamError("Waterline: z_levels boş olamaz")
        if not all(math.isfinite(v) for v in zs):
            raise CamError(f"Waterline: z_levels sonlu olmalı ({zs})")
        if any(b >= a for a, b in zip(zs[:-1], zs[1:], strict=True)):
            raise CamError(f"Waterline: z_levels kesin azalan olmalı ({zs})")
        self.z_levels = zs
        _parametreler(self.fiber_step, self.tol, self.ds_min)
        for ad in ("feed", "plunge_feed", "rpm", "z_safe", "clearance"):
            if not math.isfinite(getattr(self, ad)):
                raise CamError(f"Waterline.{ad} sonlu olmalı ({getattr(self, ad)})")
        for ad in ("feed", "plunge_feed", "rpm"):
            if not getattr(self, ad) > 0:
                raise CamError(f"Waterline.{ad} pozitif olmalı ({getattr(self, ad)})")
        if self.clearance < 0:
            raise CamError(f"Waterline.clearance negatif olamaz ({self.clearance})")


def waterline(mesh: TriMesh, tool: Tool, w: Waterline) -> Toolpath:
    """Seviyeler yukarıdan aşağı; her döngü: G0 z_safe, G0 z + clearance, G1 dalma, G1 döngü, G0 z_safe."""
    kesici(tool)  # desteklenmeyen takım → CamError
    z_ust = float(mesh.bbox()[1][2])
    if w.z_safe < z_ust + w.clearance:
        raise CamError(f"waterline: z_safe ağın clearance üstünde olmalı (z_safe={w.z_safe}, z_max={z_ust})")
    hareket: list[Move] = []
    for z in w.z_levels:
        for D in waterline_loops(mesh, tool, z, w.fiber_step, w.tol, w.ds_min, climb=w.climb):
            xs, ys = (float(v) for v in D[0])
            hareket.append(Move(MoveType.RAPID, (xs, ys, w.z_safe)))
            hareket.append(Move(MoveType.RAPID, (xs, ys, z + w.clearance)))
            hareket.append(Move(MoveType.LINEAR, (xs, ys, z), feed=w.plunge_feed))
            for x, y in np.vstack([D[1:], D[:1]]):
                hareket.append(Move(MoveType.LINEAR, (float(x), float(y), z), feed=w.feed))
            hareket.append(Move(MoveType.RAPID, (xs, ys, w.z_safe)))
    bas = hareket[0].end if hareket else (0.0, 0.0, w.z_safe)
    tp = Toolpath(name="waterline", tool=tool, start=bas, rpm=w.rpm)
    tp.moves.extend(hareket)
    tp.validate()
    return tp
