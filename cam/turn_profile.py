"""
SPEC 28 — Katı parçadan torna profili: eksenden geçen yarı düzlem kesitinden SPEC 20 profilleri.

Kesit geometry tarafında alınır (Part.axial_section); burada kenarlar Line/Arc'a çevrilir, bağlanır,
birleştirilir, serbest eğriler doğru + yaya uydurulur ve kapalı kesit dış / iç profile bölünür.
Koordinatlar (u, v) = (z, x).

Birimler: mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.geom2d import LINK_TOL, TOL, TWO_PI
from cam.model import ARC_TOL, CamError
from cam.profile import Arc, Line, Profile, segment_area
from geometry.part import AxialSection, GeometryError, Part, SectionEdge

A_TOL = 1e-9  # rad: art arda iki doğrunun aynı doğru sayılması
R_DUZ = 1e6  # mm: bundan büyük yarıçaplı uydurma yayı doğru sayılır
_GL_T, _GL_W = np.polynomial.legendre.leggauss(32)
_GL_T, _GL_W = 0.5 * (_GL_T + 1.0), 0.5 * _GL_W  # [0, 1] aralığına


@dataclass(frozen=True)
class TurnProfile:
    """Dönel parçanın yarı kesiti ve SPEC 20 profilleri."""

    section: Profile  # kapalı, CCW, (z, x), her noktada x ≥ 0
    outer: Profile  # açık, ön→arka, SPEC 20 side="dis"
    inner: Profile | None  # açık, ön→arka, SPEC 20 side="ic"; delik yoksa None
    origin: np.ndarray  # (3,)
    axis: np.ndarray  # (3,) birim
    xdir: np.ndarray  # (3,) birim
    fitted_length: float  # L_u: serbest eğriden uydurulan kenarların toplam boyu [mm]; tam kesitte 0


# ---------------------------------------------------------------- girdi denetimi


def _tol(tol) -> float:
    try:
        t = float(tol)
    except (TypeError, ValueError) as e:
        raise CamError(f"tol sayı olmalı: {tol!r}") from e
    if not (math.isfinite(t) and t > 0):
        raise CamError(f"tol > 0 ve sonlu olmalı (tol={tol})")
    return t


def _vec3(v, ad: str) -> np.ndarray:
    try:
        a = np.asarray(v, dtype=float).reshape(-1)
    except (TypeError, ValueError) as e:
        raise CamError(f"{ad} 3 bileşenli sayı vektörü olmalı: {v!r}") from e
    if a.shape != (3,) or not np.all(np.isfinite(a)):
        raise CamError(f"{ad} 3 bileşenli sonlu vektör olmalı: {v!r}")
    return a


# ---------------------------------------------------------------- ham kenarlar: bağlama


def _ham(e: SectionEdge) -> list:
    """SectionEdge → değiştirilebilir ham kenar [tür, noktalar (k, 2), merkez, ccw]."""
    P = np.array(e.points, dtype=float)
    if P.ndim != 2 or P.shape[1] != 2 or len(P) < 2 or not np.all(np.isfinite(P)):
        raise CamError(f"kesit kenarı geçersiz noktalar içeriyor: {e.kind}")
    if e.kind == "line" or e.kind == "arc":
        P = P[[0, -1]]
    elif e.kind != "curve":
        raise CamError(f"bilinmeyen kesit kenarı türü: {e.kind!r}")
    c = None if e.center is None else np.array(e.center, dtype=float)
    if e.kind == "arc" and (c is None or c.shape != (2,) or not np.all(np.isfinite(c))):
        raise CamError("yay kenarının merkezi yok")
    return [e.kind, P, c, bool(e.ccw)]


def _ters(h: list) -> list:
    return [h[0], h[1][::-1].copy(), h[2], not h[3]]


def _yakin(p, q) -> bool:
    return float(np.hypot(*(p - q))) <= LINK_TOL


def _bagla(kenarlar) -> list[list]:
    """Halkayı uç uca dizer (ters kenarı çevirir); ortak köşe tek koordinat, |x| ≤ LINK_TOL → x = 0."""
    H = [_ham(e) for e in kenarlar]
    for k in range(1, len(H)):
        son = H[k - 1][1][-1]
        if not _yakin(son, H[k][1][0]):
            if _yakin(son, H[k][1][-1]):
                H[k] = _ters(H[k])
            elif k == 1 and (_yakin(H[0][1][0], H[1][1][0]) or _yakin(H[0][1][0], H[1][1][-1])):
                H[0] = _ters(H[0])
                if not _yakin(H[0][1][-1], H[1][1][0]):
                    H[1] = _ters(H[1])
            else:
                raise CamError(f"kesit halkası kopuk: kenar {k - 1} bitişi {son} ≠ kenar {k} başlangıcı")
    if not _yakin(H[-1][1][-1], H[0][1][0]):
        raise CamError("kesit halkası kapanmıyor")
    n = len(H)
    for k in range(n):
        a, b = H[k], H[(k + 1) % n]
        p = 0.5 * (a[1][-1] + b[1][0])
        if abs(p[1]) <= LINK_TOL:
            p[1] = 0.0
        a[1][-1] = p
        b[1][0] = p.copy()
    for h in H:  # eğri ara noktaları da eksene çekilir
        h[1][np.abs(h[1][:, 1]) <= LINK_TOL, 1] = 0.0
    return H


# ---------------------------------------------------------------- serbest eğri uydurma


def _dogru_uzaklik(Q: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    L2 = float(ab @ ab)
    t = np.clip(((Q - a) @ ab) / L2, 0.0, 1.0)
    return np.hypot(*(Q - (a + t[:, None] * ab)).T)


def _cember(a, m, b):
    """Üç noktadan geçen çember (merkez, R) ya da None (doğrusal)."""
    d = 2.0 * (a[0] * (m[1] - b[1]) + m[0] * (b[1] - a[1]) + b[0] * (a[1] - m[1]))
    if abs(d) < 1e-300:
        return None
    a2, m2, b2 = a @ a, m @ m, b @ b
    c = np.array(
        [
            (a2 * (m[1] - b[1]) + m2 * (b[1] - a[1]) + b2 * (a[1] - m[1])) / d,
            (a2 * (b[0] - m[0]) + m2 * (a[0] - b[0]) + b2 * (m[0] - a[0])) / d,
        ]
    )
    return c, float(np.hypot(*(a - c)))


def _dene_dogru(q: np.ndarray, i: int, j: int, esik: float) -> bool:
    Q = q[i : j + 1]
    M = 0.5 * (Q[1:] + Q[:-1])
    return bool(_dogru_uzaklik(np.vstack([Q, M]), q[i], q[j]).max() <= esik)


def _dene_yay(q: np.ndarray, i: int, j: int, esik: float):
    """q_i, q_m, q_j yayı koşulları sağlıyorsa (merkez, ccw), yoksa None."""
    if j - i < 2:
        return None
    m = (i + j) // 2
    cr = _cember(q[i], q[m], q[j])
    if cr is None or cr[1] > R_DUZ:
        return None
    c, R = cr
    u, w = q[m] - q[i], q[j] - q[i]
    ccw = bool(u[0] * w[1] - u[1] * w[0] > 0)
    Q = q[i : j + 1]
    M = 0.5 * (Q[1:] + Q[:-1])
    if np.abs(np.hypot(*(np.vstack([Q, M]) - c).T) - R).max() > esik:
        return None
    th = np.arctan2(Q[:, 1] - c[1], Q[:, 0] - c[0])
    s = np.unwrap(th - th[0]) if ccw else np.unwrap(th[0] - th)
    s = np.mod(s, TWO_PI)
    s[0] = 0.0
    if np.any(np.diff(s) < -1e-12):  # noktalar yay üzerinde sıralı değil
        return None
    return c, ccw


def _en_uzak(q: np.ndarray, i: int, dene) -> int:
    """dene(i, j) doğru olan en büyük j (ikili arama; i + 1 her zaman denenir)."""
    n = len(q) - 1
    lo, hi = i + 1, n
    if dene(i, hi):
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if dene(i, mid):
            lo = mid
        else:
            hi = mid
    return lo


def _uydur(q: np.ndarray, tol: float) -> list:
    """Çokgen → doğru + yay parçaları (ham kenar), sapma ≤ tol/2 (SPEC 28 açgözlü yöntem)."""
    esik = tol / 2.0
    out, i, n = [], 0, len(q) - 1
    while i < n:
        jl = _en_uzak(q, i, lambda a, b: _dene_dogru(q, a, b, esik))
        ja = _en_uzak(q, i, lambda a, b: _dene_yay(q, a, b, esik) is not None) if n - i >= 2 else i
        if ja > jl:
            c, ccw = _dene_yay(q, i, ja, esik)
            out.append(["arc", np.array([q[i], q[ja]]), c, ccw])
            i = ja
        else:
            out.append(["line", np.array([q[i], q[jl]]), None, True])
            i = jl
    return out


# ---------------------------------------------------------------- Line / Arc, birleştirme


def _parca(h: list):
    if h[0] == "line":
        return Line(h[1][0], h[1][1])
    c = h[2]
    p0, p1 = h[1][0], h[1][1]
    # uçlar bağlamada en çok LINK_TOL kaydı; yarıçap farkı ARC_TOL'u aşarsa merkez korunur, hata Arc'tan gelir
    return Arc(p0, p1, c, h[3])


def _ayni_dogru(s: Line, t: Line) -> bool:
    u, v = s.tangent(0), t.tangent(0)
    return abs(u[0] * v[1] - u[1] * v[0]) <= A_TOL and float(u @ v) > 0


def _ayni_cember(s: Arc, t: Arc) -> bool:
    return s.ccw == t.ccw and _yakin(s.c, t.c) and abs(s.R - t.R) <= ARC_TOL


def _birlesik(s, t):
    """s ve t birleşebiliyorsa birleşik parça, yoksa None."""
    if isinstance(s, Line) and isinstance(t, Line) and _ayni_dogru(s, t):
        return Line(s.p0, t.p1)
    if isinstance(s, Arc) and isinstance(t, Arc) and _ayni_cember(s, t):
        if s.sweep + t.sweep > TWO_PI + 1e-9:
            return None
        return Arc(s.p0, t.p1, s.c, s.ccw)
    return None


def _birlestir(S: list) -> list:
    """Halkada art arda aynı doğru / aynı çember üzerindeki parçaları birleştirir (sarmal dahil)."""
    S = list(S)
    degisti = True
    while degisti and len(S) > 1:
        degisti = False
        for k in range(len(S)):
            j = (k + 1) % len(S)
            b = _birlesik(S[k], S[j])
            if b is not None:
                S[k] = b
                del S[j]
                degisti = True
                break
    return S


# ---------------------------------------------------------------- dış / iç profil


def _uc_adaylari(s):
    """Parçanın z uç değerini alabileceği noktalar: başlangıç ve yayda açı 0 / π noktaları (iç kısımda)."""
    yield s.p0
    if isinstance(s, Arc):
        for th in (0.0, math.pi):
            d = ((th - s.a0) if s.ccw else (s.a0 - th)) % TWO_PI  # p0'dan yay yönünde açı
            if d * s.R > TOL and (s.sweep - d) * s.R > TOL:
                yield s.c + s.R * np.array([math.cos(th), math.sin(th)])


def _uc_nokta(S: list, on: bool) -> np.ndarray:
    """on: en büyük z, eşitlikte en küçük x; arka: en küçük z, eşitlikte en büyük x."""
    aday = [p for s in S for p in _uc_adaylari(s)]
    if on:
        zt = max(p[0] for p in aday)
        es = [p for p in aday if p[0] >= zt - LINK_TOL]
        return min(es, key=lambda p: p[1])
    zt = min(p[0] for p in aday)
    es = [p for p in aday if p[0] <= zt + LINK_TOL]
    return max(es, key=lambda p: p[1])


def _bol(S: list, P: np.ndarray) -> tuple[list, int]:
    """P bir köşe değilse içinden geçtiği yayı ikiye böler; P'de başlayan parçanın sırası."""
    for k, s in enumerate(S):
        if _yakin(s.p0, P):
            return S, k
    for k, s in enumerate(S):
        if isinstance(s, Arc) and abs(float(np.hypot(*(P - s.c))) - s.R) <= LINK_TOL:
            a, b = Arc(s.p0, P, s.c, s.ccw), Arc(P, s.p1, s.c, s.ccw)
            if abs(a.sweep + b.sweep - s.sweep) <= 1e-9:
                return S[:k] + [a, b] + S[k + 1 :], k + 1
    raise CamError(f"uç nokta {P} kesit halkasında bulunamadı")  # pragma: no cover


def _profiller(S: list) -> tuple[Profile, Profile | None]:
    S, _ = _bol(S, _uc_nokta(S, on=True))
    S, _ = _bol(S, _uc_nokta(S, on=False))
    on, arka = _uc_nokta(S, on=True), _uc_nokta(S, on=False)
    k = next(i for i, s in enumerate(S) if _yakin(s.p0, on))
    R = S[k:] + S[:k]  # P_ön'den başlayan CCW halka
    m = next(i for i, s in enumerate(R) if _yakin(s.p0, arka))
    outer = Profile(R[:m], closed=False)
    kalan = R[m:]  # P_arka → P_ön
    z_min = arka[0]
    i = 0
    while (
        i < len(kalan)
        and isinstance(kalan[i], Line)
        and abs(kalan[i].p0[0] - z_min) <= LINK_TOL
        and abs(kalan[i].p1[0] - z_min) <= LINK_TOL
    ):
        i += 1
    kalan = kalan[i:]
    eksen = [j for j, s in enumerate(kalan) if isinstance(s, Line) and max(s.p0[1], s.p1[1]) <= LINK_TOL]
    if eksen:
        kalan = kalan[eksen[-1] + 1 :]
    inner = Profile(kalan, closed=False).reversed() if kalan else None
    return outer, inner


# ---------------------------------------------------------------- Pappus


def _x_integralleri(s) -> tuple[float, float]:
    """(∫ x² dz, ∫ x ds) — Gauss–Legendre, doğruda tam, yayda makine duyarlığında."""
    if isinstance(s, Line):
        z0, x0 = s.p0
        z1, x1 = s.p1
        return (z1 - z0) * (x0 * x0 + x0 * x1 + x1 * x1) / 3.0, s.length * 0.5 * (x0 + x1)
    sg = 1.0 if s.ccw else -1.0
    th = s.a0 + sg * s.sweep * _GL_T
    x = s.c[1] + s.R * np.sin(th)
    dz = -s.R * np.sin(th) * sg * s.sweep
    return float(np.sum(_GL_W * x * x * dz)), float(np.sum(_GL_W * x) * s.length)


def _pappus(section: Profile) -> tuple[float, float]:
    """V_P = 2π (−½ ∮ x² dz), S_P = 2π Σ ∫ x ds."""
    J = [_x_integralleri(s) for s in section.segments]
    return 2.0 * math.pi * (-0.5 * sum(a for a, _ in J)), 2.0 * math.pi * sum(b for _, b in J)


def _x_max(section: Profile) -> float:
    t = np.linspace(0.0, 1.0, 65)
    return max(float(s.point(u)[1]) for s in section.segments for u in t)


# ---------------------------------------------------------------- ana fonksiyonlar


def profile_from_section(sec: AxialSection, tol: float = 1e-3) -> TurnProfile:
    """OCCT'siz: kenarları Line/Arc'a çevirir, bağlar, birleştirir, uydurur, dış/iç profili böler.

    off_axis_faces doluysa, yüz sayısı 1 değilse ya da yüzde iç halka varsa → CamError.
    """
    tol = _tol(tol)
    if not isinstance(sec, AxialSection):
        raise CamError(f"AxialSection bekleniyor: {type(sec).__name__}")
    if sec.off_axis_faces:
        liste = ", ".join(str(i) for i in sec.off_axis_faces)
        raise CamError(f"parça bu eksene göre dönel değil; dönel olmayan yüzler: {liste}")
    if len(sec.faces) == 0:
        raise CamError("eksen parçayı kesmiyor (kesit boş)")
    if len(sec.faces) > 1:
        raise CamError(f"kesit {len(sec.faces)} ayrık yüz veriyor; tek bağlantılı kesit gerekli")
    yuz = sec.faces[0]
    if yuz.holes:
        raise CamError("kesitte iç boşluk var (kapalı toroidal boşluk); tornayla işlenemez")
    if not yuz.outer:
        raise CamError("kesit halkası boş")

    S, L_u = [], 0.0
    for h in _bagla(yuz.outer):
        if h[0] == "curve":
            for g in _uydur(h[1], tol):
                s = _parca(g)
                L_u += s.length
                S.append(s)
        else:
            S.append(_parca(h))
    if sum(segment_area(s) for s in S) < 0:
        S = [s.reversed() for s in reversed(S)]
    S = _birlestir(S)
    section = Profile(S, closed=True)
    if section.area <= 0:
        raise CamError("kesit alanı sıfır")
    if min(float(s.point(u)[1]) for s in S for u in np.linspace(0, 1, 17)) < -LINK_TOL:
        raise CamError("kesit eksenin altına iniyor (x < 0)")
    outer, inner = _profiller(S)
    return TurnProfile(
        section=section,
        outer=outer,
        inner=inner,
        origin=np.array(sec.origin, dtype=float),
        axis=np.array(sec.axis, dtype=float),
        xdir=np.array(sec.xdir, dtype=float),
        fitted_length=float(L_u),
    )


def turn_profile(part: Part, axis=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0), tol: float = 1e-3) -> TurnProfile:
    """part.axial_section + profile_from_section + Pappus hacim ve alan denetimi.

    axis="auto" desteklenir. Tüm hatalar CamError (GeometryError da CamError'a çevrilir, mesaj korunur).
    """
    if not isinstance(part, Part):
        raise CamError(f"Part bekleniyor: {type(part).__name__}")
    tol = _tol(tol)
    if isinstance(axis, str):
        if axis != "auto":
            raise CamError(f'axis bir vektör ya da "auto" olmalı: {axis!r}')
    else:
        a = _vec3(axis, "axis")
        if float(np.linalg.norm(a)) < 1e-12:
            raise CamError("axis sıfır vektör")
    origin = _vec3(origin, "origin")
    try:
        sec = part.axial_section(origin=origin, axis=axis, tol=tol)
    except GeometryError as e:
        raise CamError(str(e)) from e
    tp = profile_from_section(sec, tol)

    V, S = part.volume, part.area
    V_P, S_P = _pappus(tp.section)
    xm, L_u = _x_max(tp.section), tp.fitted_length
    eps_V = 1e-6 * V + 2.0 * math.pi * xm * tol * L_u
    eps_S = 1e-6 * S + 2.0 * math.pi * (xm + L_u) * tol
    if abs(V_P - V) > eps_V or abs(S_P - S) > eps_S:
        raise CamError(
            f"Pappus denetimi tutmuyor, parça dönel simetrik değil: V = {V:.9g}, V_P = {V_P:.9g}, "
            f"S = {S:.9g}, S_P = {S_P:.9g}"
        )
    return tp
