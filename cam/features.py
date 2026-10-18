"""
SPEC 27 — İşleme özelliği tanıma (freze, 3 eksen, üstten −Z takım yönü).

Parça yatay yüz seviyeleri arasında dilimlere bölünür; her dilim tek bir
`Part.section_z` kesitiyle tanımlanır.
Cep = kesitte iç halka, açık bölge = zarf dikdörtgeni ile dış halkalar arası boşluk, delik = eksenli silindir.
Yaylar dik silindirik yüzlerin tam merkez ve yarıçapıyla geri kurulur. 2.5D olmayan parça → CamError.
Yalnızca geometry/part.py arayüzü kullanılır. Birimler: mm, derece.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError, Stock
from cam.profile import Arc, Line, Profile, Region, Segment
from geometry.part import GeometryError, Hole, Part

ANG = 1e-6  # yön toleransı
TOL_KESIT = 0.01  # mm, section_z kiriş sapması
ALAN_REL = 1e-6  # alan dengesi bağıl toleransı
_EPS = 1e-9  # mm, sıfır boy
ASAGI = np.array([0.0, 0.0, -1.0])


@dataclass(frozen=True)
class FaceFeature:
    """Yüz alma: stok üstünden parça üstüne (z) kadar, zarf dikdörtgeni boyunca."""

    z: float  # yüz alma son seviyesi (parça üstü)
    depth: float  # stock.zmax − z
    boundary: Profile  # zarf dikdörtgeni E (CCW)


@dataclass(frozen=True)
class PocketFeature:
    """Kapalı cep: dış halka + adalar, [z_bottom, z_top] aralığında aynı boşluk imzası."""

    region: Region  # dış = cep halkası, holes = adalar
    z_top: float
    z_bottom: float
    r_corner: float  # bölgeden bakınca dışbükey en küçük köşe yarıçapı; keskin köşe → 0.0, köşe yok → inf

    @property
    def max_tool_d(self) -> float:
        """Köşelere tam giren en büyük takım çapı: 2 · r_corner."""
        return 2.0 * self.r_corner


@dataclass(frozen=True)
class OpenFeature:
    """Açık bölge (basamak, dış kontur): boşluk = boundary ∖ ∪ islands."""

    boundary: Profile  # E
    islands: tuple[Profile, ...]
    z_top: float
    z_bottom: float


@dataclass(frozen=True)
class HoleFeature:
    """Delik: kayıttan ("kayit") ya da silindirden tanınmış ("tanima")."""

    hole: Hole
    source: str  # "kayit" | "tanima"

    @property
    def top_access(self) -> bool:
        """Delme yönü −Z mi (üstten delinebilir)?"""
        return bool(np.all(np.abs(self.hole.axis - ASAGI) <= ANG))


@dataclass(frozen=True)
class Features:
    """Tanınan özellikler, SPEC 27'deki sıralarla."""

    faces: tuple[FaceFeature, ...]  # 0 veya 1 eleman
    pockets: tuple[PocketFeature, ...]  # z_top azalan, z_bottom azalan, dış halkanın ilk köşesi (x, y) artan
    opens: tuple[OpenFeature, ...]  # z_top azalan
    holes: tuple[HoleFeature, ...]  # önce kayıtlılar, sonra tanınanlar


# ---------------------------------------------------------------- silindirler


@dataclass
class _Cyl:
    """Birleştirilmiş silindir (aynı eksen, yarıçap ve z aralığı olan yüzler)."""

    c: np.ndarray  # (2,) eksenin xy'si
    R: float
    z_b: float
    z_e: float
    angle: float
    concave: bool

    @property
    def full(self) -> bool:
        return self.angle >= 360.0 - ANG

    @property
    def L(self) -> float:
        return self.z_e - self.z_b


def _merge_cylinders(faces, tol: float) -> list[_Cyl]:
    out: list[_Cyl] = []
    for f in faces:
        z0 = float(f.origin[2])
        z1 = z0 + float(f.axis[2]) * f.length
        c = np.array(f.origin[:2], dtype=float)
        zb, ze = min(z0, z1), max(z0, z1)
        for g in out:
            ayni = (
                np.hypot(*(g.c - c)) <= tol
                and abs(g.R - f.radius) <= tol
                and abs(g.z_b - zb) <= tol
                and abs(g.z_e - ze) <= tol
                and g.concave == f.concave
            )
            if ayni:
                g.angle += f.angle
                break
        else:
            out.append(_Cyl(c, float(f.radius), zb, ze, float(f.angle), bool(f.concave)))
    return out


def _line_dist(p: np.ndarray, o: np.ndarray, a: np.ndarray) -> float:
    d = p - o
    return float(np.linalg.norm(d - (d @ a) * a))


def _matches_record(f, h: Hole, tol: float) -> bool:
    """Silindirik yüz bir delik kaydının mı (eksen paralel, eksen doğrusu origin'den geçer, yarıçap uyar)."""
    a = np.asarray(f.axis, dtype=float)
    if abs(abs(float(a @ h.axis)) - 1.0) > ANG:
        return False
    if _line_dist(h.origin, np.asarray(f.origin, dtype=float), a) > tol:
        return False
    return any(abs(f.radius - r) <= tol for r in (h.d / 2, h.cbore_d / 2) if r > 0)


def _rho(h: Hole, t: float) -> float:
    """Delik yarıçapı, girişten eksen boyunca t derinlikte (SPEC 27 §2)."""
    if h.cbore_d > 0 and t < h.cbore_depth:
        return h.cbore_d / 2
    if h.csk_d > 0:
        tan = math.tan(math.radians(h.csk_angle) / 2)
        if t < (h.csk_d - h.d) / (2 * tan):
            return h.csk_d / 2 - t * tan
    return h.d / 2


def _is_hole_loop(P: np.ndarray, z: float, holes: list[Hole], tol: float) -> bool:
    for h in holes:
        ok = True
        for v in P:
            p = np.array([v[0], v[1], z])
            t = float((p - h.origin) @ h.axis)
            if t < -tol or t > h.depth + tol or abs(_line_dist(p, h.origin, h.axis) - _rho(h, t)) > tol:
                ok = False
                break
        if ok:
            return True
    return False


# ---------------------------------------------------------------- çokgen → profil


def _cross(a, b) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _merge_lines(segs: list[Segment], tol: float, closed: bool) -> list[Segment]:
    """Ortadaki köşesi komşularından geçen doğruya ≤ tol uzak olan ardışık doğruları birleştirir."""

    def birlesir(a: Segment, b: Segment) -> bool:
        if not (isinstance(a, Line) and isinstance(b, Line)):
            return False
        u = b.p1 - a.p0
        n = float(np.hypot(*u))
        if n <= _EPS:
            return False
        w = a.p1 - a.p0
        return abs(u[0] * w[1] - u[1] * w[0]) / n <= tol and float(u @ w) > 0

    segs = list(segs)
    changed = True
    while changed and len(segs) > 1:
        changed = False
        n = len(segs)
        rng = range(n) if closed else range(n - 1)
        for i in rng:
            j = (i + 1) % n
            if birlesir(segs[i], segs[j]):
                merged = Line(segs[i].p0, segs[j].p1)
                if j == 0:
                    segs = [merged, *segs[1:i]]
                else:
                    segs[i : j + 1] = [merged]
                changed = True
                break
    return segs


def _loop_profile(P: np.ndarray, cyls: list[_Cyl], tol: float) -> Profile:
    """Kesit çokgeninden yayları geri kurulmuş kapalı profil (SPEC 27 §4)."""
    pts = [np.asarray(p, dtype=float) for p in P]
    pts = [p for i, p in enumerate(pts) if np.hypot(*(p - pts[i - 1])) > _EPS] or pts[:1]
    n = len(pts)

    def on(v, g: _Cyl, t: float) -> bool:
        return abs(float(np.hypot(*(v - g.c))) - g.R) <= t

    grp: list[int | None] = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        gi = None
        for k, g in enumerate(cyls):
            if on(a, g, tol) and on(b, g, tol) and on((a + b) / 2, g, TOL_KESIT + tol):
                gi = k
                break
        grp.append(gi)

    def proj(v, g: _Cyl) -> np.ndarray:
        d = v - g.c
        return g.c + g.R * d / float(np.hypot(*d))

    if all(g is not None and g == grp[0] for g in grp):
        g = cyls[grp[0]]
        p = proj(pts[0], g)
        ccw = _cross(pts[0] - g.c, pts[1] - g.c) > 0
        return Profile([Arc(p, p, g.c, ccw)])

    # başlangıcı bir grup sınırına kaydır (yay ortasından başlamasın)
    start = next((i for i in range(n) if grp[i] != grp[i - 1] or grp[i] is None), 0)
    order = [(start + k) % n for k in range(n)]
    snapped = {i: pts[i] for i in range(n)}
    segs: list[Segment] = []
    k = 0
    while k < n:
        i = order[k]
        g = grp[i]
        if g is None:
            segs.append(("L", i, (i + 1) % n))
            k += 1
            continue
        j = k
        while j < n and grp[order[j]] == g:
            j += 1
        i_end = (order[j - 1] + 1) % n
        c = cyls[g]
        snapped[i] = proj(pts[i], c)
        snapped[i_end] = proj(pts[i_end], c)
        ccw = _cross(pts[i] - c.c, pts[(i + 1) % n] - c.c) > 0
        segs.append(("A", i, i_end, g, ccw))
        k = j
    out: list[Segment] = []
    for s in segs:
        if s[0] == "L":
            a, b = snapped[s[1]], snapped[s[2]]
            if np.hypot(*(b - a)) > _EPS:
                out.append(Line(a, b))
        else:
            c = cyls[s[3]]
            out.append(Arc(snapped[s[1]], snapped[s[2]], c.c, s[4]))
    return Profile(_merge_lines(out, tol, closed=True))


def _seg_eq(a: Segment, b: Segment, tol: float) -> bool:
    if type(a) is not type(b):
        return False
    if np.hypot(*(a.p0 - b.p0)) > tol or np.hypot(*(a.p1 - b.p1)) > tol:
        return False
    if isinstance(a, Arc):
        return np.hypot(*(a.c - b.c)) <= tol and a.ccw == b.ccw
    return True


def _loop_eq(P: Profile, Q: Profile, tol: float) -> bool:
    """İki kapalı halka eşit mi (döngüsel kaydırmayla parça parça)."""
    a, b = P.segments, Q.segments
    n = len(a)
    if n != len(b):
        return False
    if n == 1:
        s, t = a[0], b[0]
        if isinstance(s, Arc) and isinstance(t, Arc) and s.full and t.full:
            return np.hypot(*(s.c - t.c)) <= tol and abs(s.R - t.R) <= tol and s.ccw == t.ccw
    return any(all(_seg_eq(a[i], b[(i + k) % n], tol) for i in range(n)) for k in range(n))


def _set_eq(A: list[Profile], B: list[Profile], tol: float) -> bool:
    if len(A) != len(B):
        return False
    kalan = list(B)
    for p in A:
        for i, q in enumerate(kalan):
            if _loop_eq(p, q, tol):
                del kalan[i]
                break
        else:
            return False
    return True


def _inside(p: np.ndarray, P: np.ndarray) -> bool:
    """Işın yöntemiyle nokta çokgen içinde mi."""
    x, y = p
    ic = False
    n = len(P)
    for i in range(n):
        x0, y0 = P[i - 1]
        x1, y1 = P[i]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            ic = not ic
    return ic


def _poly_area(P: np.ndarray) -> float:
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _r_corner(region: Region) -> float:
    """§8: ccw yayların yarıçapı ve keskin sola dönüşler (0) arasında en küçüğü; yoksa inf."""
    r = math.inf
    for loop in region.loops:
        segs = loop.segments
        for k, s in enumerate(segs):
            if isinstance(s, Arc) and s.ccw:
                r = min(r, s.R)
            t1, t2 = segs[k - 1].tangent(1.0), s.tangent(0.0)
            if float(t1[0] * t2[1] - t1[1] * t2[0]) > ANG:
                r = 0.0
    return r


# ---------------------------------------------------------------- denetimler


def _sonlu_pozitif(ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise CamError(f"{ad} sonlu ve pozitif olmalı ({v!r})")
    return float(v)


def _levels(values: list[float], tol: float) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _runs(sigs: list, eq) -> list[tuple[int, int]]:
    """Ardışık eşit imzalı dilim dizileri: (ilk, son) indeksleri; imza None olan dilimler atlanır."""
    out: list[tuple[int, int]] = []
    for k, s in enumerate(sigs):
        if s is None:
            continue
        if out and out[-1][1] == k - 1 and eq(sigs[k - 1], s):
            out[-1] = (out[-1][0], k)
        else:
            out.append((k, k))
    return out


# ---------------------------------------------------------------- ana işlev


def recognize(
    part: Part, stock: Stock | None = None, tol: float = 1e-3, hole_d_max: float = 20.0
) -> Features:
    """Parçadan yüz alma, cep, açık bölge ve delik özelliklerini çıkarır (SPEC 27 §1–8)."""
    if not isinstance(part, Part):
        raise CamError(f"recognize: Part bekleniyor ({type(part).__name__})")
    tol = _sonlu_pozitif("tol", tol)
    hole_d_max = _sonlu_pozitif("hole_d_max", hole_d_max)
    if stock is not None and not isinstance(stock, Stock):
        raise CamError("stock Stock olmalı")

    try:
        pfaces = part.planar_faces()
        cfaces = part.cylindrical_faces()
        A_part = part.area
    except GeometryError as e:
        raise CamError(str(e)) from e
    records = list(part.holes)

    # §1 ön koşullar
    zs = [float(f.origin[2]) for f in pfaces]
    if not zs:
        raise CamError("Parçada düzlemsel yüz yok: 2.5D değil")
    for f in pfaces:
        nz = abs(float(f.normal[2]))
        if not (nz >= 1 - ANG or nz <= ANG):
            raise CamError(f"Eğik düzlemsel yüz (yüz {f.index}, n = {np.round(f.normal, 6)}): 2.5D değil")
    alt = [float(f.origin[2]) for f in pfaces if f.normal[2] <= -1 + ANG]
    up = [float(f.origin[2]) for f in pfaces if f.normal[2] >= 1 - ANG]
    zmin = min(alt) if alt else min(zs)
    zmax = max(up) if up else max(zs)
    for f in pfaces:
        if f.normal[2] <= -1 + ANG and f.origin[2] > zmin + tol:
            raise CamError(f"Alttan erişilen yüz (z = {f.origin[2]}): 3 eksen üstten işlenemez")
    dik = []
    for f in cfaces:
        if abs(float(f.axis[2])) >= 1 - ANG:
            dik.append(f)
        elif not any(_matches_record(f, h, tol) for h in records):
            raise CamError(f"Ekseni Z'ye paralel olmayan silindir (yüz {f.index}): 2.5D değil")
    A_csk = 0.0
    for h in records:
        if h.csk_d > 0:
            R, r = h.csk_d / 2, h.d / 2
            A_csk += math.pi * (R + r) * (R - r) / math.sin(math.radians(h.csk_angle) / 2)
    fark = A_part - sum(f.area for f in pfaces) - sum(f.area for f in cfaces) - A_csk
    if abs(fark) > ALAN_REL * A_part:
        raise CamError(f"Düzlem / silindir dışı yüzey var (alan farkı {fark:.6g} mm²): 2.5D değil")

    # §2 delikler
    dik_kayitsiz = [f for f in dik if not any(_matches_record(f, h, tol) for h in records)]
    cyls_all = _merge_cylinders(dik, tol)
    adaylar = [
        g for g in _merge_cylinders(dik_kayitsiz, tol) if g.concave and g.full and 2 * g.R <= hole_d_max + tol
    ]
    adaylar.sort(key=lambda g: -g.z_e)
    taninan: list[Hole] = []
    kullanildi: set[int] = set()
    for i, g in enumerate(adaylar):
        if i in kullanildi:
            continue
        zincir = [i]
        while True:
            son = adaylar[zincir[-1]]
            sonraki = next(
                (
                    j
                    for j, h in enumerate(adaylar)
                    if j not in kullanildi
                    and j not in zincir
                    and np.hypot(*(h.c - son.c)) <= tol
                    and abs(h.z_e - son.z_b) <= tol
                ),
                None,
            )
            if sonraki is None:
                break
            zincir.append(sonraki)
        if len(zincir) >= 3:
            raise CamError(f"Kademeli delik ({len(zincir)} kademe, x = {g.c[0]}, y = {g.c[1]}): kapsam dışı")
        kullanildi.update(zincir)
        ust = adaylar[zincir[0]]
        if len(zincir) == 2 and ust.R > adaylar[zincir[1]].R + tol:
            alt = adaylar[zincir[1]]
            h = Hole(
                origin=(ust.c[0], ust.c[1], ust.z_e),
                axis=ASAGI,
                d=2 * alt.R,
                depth=ust.L + alt.L,
                through=alt.z_b <= zmin + tol,
                cbore_d=2 * ust.R,
                cbore_depth=ust.L,
            )
            taninan.append(h)
        else:
            for j in zincir:
                c = adaylar[j]
                taninan.append(
                    Hole(
                        origin=(c.c[0], c.c[1], c.z_e),
                        axis=ASAGI,
                        d=2 * c.R,
                        depth=c.L,
                        through=c.z_b <= zmin + tol,
                    )
                )
    taninan.sort(key=lambda h: (-h.origin[2], h.origin[0], h.origin[1]))
    holes = [HoleFeature(h, "kayit") for h in records] + [HoleFeature(h, "tanima") for h in taninan]
    hole_list = records + taninan

    # §3 seviyeler ve dilimler
    H = _levels([zmin, zmax, *up], tol)
    slabs = []  # her dilim: (z_alt, z_üst, [(outer, [inner...], outer_poly, [inner_poly...])])
    for k in range(len(H) - 1):
        zk = (H[k] + H[k + 1]) / 2
        cyl_k = [g for g in cyls_all if g.z_b - tol <= zk <= g.z_e + tol]
        try:
            regs = part.section_z(zk, TOL_KESIT)
        except GeometryError as e:
            raise CamError(str(e)) from e
        bolgeler = []
        for r in regs:
            outer = np.asarray(r.outer, dtype=float)
            inners = [np.asarray(q, dtype=float) for q in r.holes]
            inners = [q for q in inners if not _is_hole_loop(q, zk, hole_list, tol)]
            bolgeler.append(
                (
                    _loop_profile(outer, cyl_k, tol),
                    [_loop_profile(q, cyl_k, tol) for q in inners],
                    outer,
                    inners,
                )
            )
        slabs.append((H[k], H[k + 1], bolgeler))

    # zarf E
    if stock is not None:
        ex0, ey0, ex1, ey1 = stock.xmin, stock.ymin, stock.xmax, stock.ymax
    else:
        lows, highs = [], []
        for _, _, bl in slabs:
            for o, _, _, _ in bl:
                lo, hi = o.bbox()
                lows.append(lo)
                highs.append(hi)
        if not lows:
            raise CamError("Parçada kesit yok")
        ex0, ey0 = np.min(lows, axis=0)
        ex1, ey1 = np.max(highs, axis=0)
    if stock is not None:
        for _, _, bl in slabs:
            for o, _, _, _ in bl:
                lo, hi = o.bbox()
                if lo[0] < ex0 - tol or lo[1] < ey0 - tol or hi[0] > ex1 + tol or hi[1] > ey1 + tol:
                    raise CamError("Parça stok kutusundan taşıyor")
        if zmin < stock.zmin - tol or zmax > stock.zmax + tol:
            raise CamError("Parça stok kutusundan taşıyor (z)")
    E = Profile.rectangle(float(ex0), float(ey0), float(ex1 - ex0), float(ey1 - ey0))

    # §5 kapalı cepler: her dilimde (L, adalar) imzaları
    pockets: list[PocketFeature] = []
    imzalar: list[list[tuple[Profile, list[Profile]]]] = []
    for _, _, bl in slabs:
        inner_all = [(L, Lp) for _, ins, _, inp in bl for L, Lp in zip(ins, inp, strict=True)]
        sig = []
        for L, _ in inner_all:
            adalar = []
            for o, _, op, _ in bl:
                v = op[0]
                kaps = [(abs(_poly_area(Qp)), Q) for Q, Qp in inner_all if _inside(v, Qp)]
                if kaps and min(kaps, key=lambda t: t[0])[1] is L:
                    adalar.append(o)
            sig.append((L, adalar))
        imzalar.append(sig)

    def cavity_eq(a, b) -> bool:
        return _loop_eq(a[0], b[0], tol) and _set_eq(a[1], b[1], tol)

    kullanilan = [set() for _ in slabs]
    for k in range(len(slabs)):
        for i, s in enumerate(imzalar[k]):
            if i in kullanilan[k]:
                continue
            kullanilan[k].add(i)
            ust = k
            while ust + 1 < len(slabs):
                j = next(
                    (
                        j
                        for j, t in enumerate(imzalar[ust + 1])
                        if j not in kullanilan[ust + 1] and cavity_eq(s, t)
                    ),
                    None,
                )
                if j is None:
                    break
                kullanilan[ust + 1].add(j)
                ust += 1
            region = Region(s[0], list(s[1]))
            pockets.append(PocketFeature(region, slabs[ust][1], slabs[k][0], _r_corner(region)))

    def ilk_kose(p: PocketFeature) -> tuple[float, float]:
        v = min((tuple(s.p0) for s in p.region.outer.segments), key=lambda t: (t[0], t[1]))
        return float(v[0]), float(v[1])

    pockets.sort(key=lambda p: (-p.z_top, -p.z_bottom, *ilk_kose(p)))

    # §6 açık bölgeler
    acik_sig: list[list[Profile] | None] = []
    for _, _, bl in slabs:
        dislar = [o for o, _, _, _ in bl]
        if len(dislar) == 1 and _loop_eq(dislar[0], E, tol):
            acik_sig.append(None)
        else:
            acik_sig.append(dislar)
    opens = []
    for a, b in _runs(acik_sig, lambda x, y: _set_eq(x, y, tol)):
        dislar = sorted(acik_sig[a], key=lambda p: tuple(p.bbox()[0]))
        opens.append(OpenFeature(E, tuple(dislar), slabs[b][1], slabs[a][0]))
    opens.sort(key=lambda o: -o.z_top)

    # §7 yüz alma
    faces = []
    if stock is not None and stock.zmax - zmax > tol:
        faces.append(FaceFeature(zmax, stock.zmax - zmax, E))

    return Features(tuple(faces), tuple(pockets), tuple(opens), tuple(holes))
