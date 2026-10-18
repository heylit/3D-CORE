"""
SPEC 20 — Torna profili: yön, aynalama, takım erişimi, burun yarıçapı telafisi.

Profil `cam.profile.Profile`'dır ve koordinatları (u, v) = (z, x)'tir: X yarıçap, ön uç büyük z.
Bu düzende ccw yay G18'de G3'tür (Z'den X'e dönüş). Torna profili açık zincirdir ve ön uçtan arkaya gezilir.

Dış tarafta (side="dis") malzeme profilin altındadır: ön→arka gezide malzeme solda, boşluk sağda;
boş taraf normali n = (t_x, −t_z). İç taraf ("ic") dış tarafın x → −x aynasıdır.

Hayali uç: P = C + q_T, C burun dairesi merkezi, q_T = r·(s_z, s_x) Fanuc uç numarasına göre.
Kaynak: Fanuc 0i-TF "Imaginary tool nose direction"; Smid, CNC Programming Handbook (TNRC).
"""

from __future__ import annotations

import math

import numpy as np

from cam.geom2d import LINK_TOL, TOL, closest, cross, intersect
from cam.model import CamError, LatheTool
from cam.offset import merge_segments
from cam.profile import Arc, Line, Profile, Segment

# Fanuc uç numarası → (s_z, s_x): 1–4 (z, x) düzleminin I–IV. bölgeleri; 5 +Z, 6 +X, 7 −Z, 8 −X; 0, 9 merkez
TIP_DIR: dict[int, tuple[int, int]] = {
    0: (0, 0),
    1: (1, 1),
    2: (-1, 1),
    3: (-1, -1),
    4: (1, -1),
    5: (1, 0),
    6: (0, 1),
    7: (-1, 0),
    8: (0, -1),
    9: (0, 0),
}
_MIRROR_TIP = {0: 0, 1: 4, 2: 3, 3: 2, 4: 1, 5: 5, 6: 8, 7: 7, 8: 6, 9: 9}
SIDES = ("dis", "ic")
KEEP_TOL = 1e-7  # mm: budamada "profile tam ρ uzaklıkta" sayma toleransı
ANGLE_TOL = 1e-9  # derece


def _check_tip(tip: int) -> None:
    if isinstance(tip, bool) or not isinstance(tip, int) or tip not in TIP_DIR:
        raise CamError(f"Uç numarası 0..9 tam sayı olmalı ({tip!r})")


def tip_offset(tip: int, r: float) -> np.ndarray:
    """Burun merkezinden hayali uca vektör q_T = r·(s_z, s_x), (z, x) sırasında."""
    _check_tip(tip)
    if not math.isfinite(r) or r < 0:
        raise CamError(f"Burun yarıçapı negatif olamaz (r={r})")
    s_z, s_x = TIP_DIR[tip]
    return np.array([s_z * r, s_x * r], dtype=float)


def mirror_tip(tip: int) -> int:
    """x → −x aynasında uç numarası: 1↔4, 2↔3, 6↔8; 5, 7, 0, 9 değişmez."""
    _check_tip(tip)
    return _MIRROR_TIP[tip]


def check_side(side: str) -> int:
    """Taraf işareti: "dis" → +1, "ic" → −1."""
    if side not in SIDES:
        raise CamError(f"Taraf 'dis' veya 'ic' olmalı ({side!r})")
    return 1 if side == "dis" else -1


# ---------------------------------------------------------------- profil hazırlığı


def orient(profile: Profile) -> Profile:
    """Profili ön uçtan (büyük z) arkaya çevirir; kapalı profil veya eksenin altı (x < 0) → CamError."""
    if not isinstance(profile, Profile):
        raise CamError("Torna profili Profile olmalı")
    if profile.closed:
        raise CamError("Torna profili açık zincir olmalı")
    lo, _ = profile.bbox()
    if lo[1] < -TOL:
        raise CamError(f"Torna profili eksenin altına iniyor (x = {lo[1]})")
    if profile.start[0] < profile.end[0]:
        return profile.reversed()
    return profile


def _mirror_seg(s: Segment) -> Segment:
    m = np.array([1.0, -1.0])
    if isinstance(s, Arc):
        return Arc(s.p0 * m, s.p1 * m, s.c * m, not s.ccw)
    return Line(s.p0 * m, s.p1 * m)


def mirror(profile: Profile) -> Profile:
    """(z, x) → (z, −x) aynası; yaylar yön değiştirir."""
    return Profile([_mirror_seg(s) for s in profile.segments], profile.closed)


def mirror_segments(segs: list[Segment]) -> list[Segment]:
    return [_mirror_seg(s) for s in segs]


def prepare(profile: Profile, side: str) -> Profile:
    """Yönlendirilmiş profil, iç tarafta aynalanmış (dış çerçeve)."""
    sgn = check_side(side)
    p = orient(profile)
    return p if sgn > 0 else mirror(p)


# ---------------------------------------------------------------- açılar, erişim


def _phi(t: np.ndarray) -> float:
    """Teğet açısı φ = atan2(t_x, −t_z) [derece]: −Z yönünden +X'e doğru."""
    return math.degrees(math.atan2(t[1], -t[0]))


def _angles_frame(p: Profile) -> tuple[float, float]:
    lo, hi = math.inf, -math.inf
    for s in p.segments:
        phi0 = _phi(s.tangent(0.0))
        if isinstance(s, Arc):
            # ccw yayda teğet standart açıyla artar → φ azalır
            sw = math.degrees(s.sweep)
            a, b = (phi0 - sw, phi0) if s.ccw else (phi0, phi0 + sw)
        else:
            a = b = phi0
        lo, hi = min(lo, a), max(hi, b)
    return lo, hi


def angles(profile: Profile, side: str = "dis") -> tuple[float, float]:
    """Teğet açısı φ'nin en küçük ve en büyük değeri [derece] (yaylarda bütün süpürme)."""
    return _angles_frame(prepare(profile, side))


def _monotone_frame(p: Profile) -> bool:
    lo, hi = _angles_frame(p)
    return lo >= -ANGLE_TOL and hi <= 90.0 + ANGLE_TOL


def is_monotone(profile: Profile, side: str = "dis") -> bool:
    """G71 tip I: her yerde t_z ≤ 0 ve t_x ≥ 0, yani 0 ≤ φ ≤ 90°."""
    return _monotone_frame(prepare(profile, side))


def _reach_frame(p: Profile, tool: LatheTool) -> None:
    lo, hi = _angles_frame(p)
    kr2 = 180.0 - tool.kappa_r - tool.eps_r  # arka kenar açısı κr'
    if hi > tool.kappa_r + ANGLE_TOL:
        raise CamError(f"Takım '{tool.name}' profili izleyemez: φ = {hi:.4f}° > κr = {tool.kappa_r}°")
    if lo < -kr2 - ANGLE_TOL:
        raise CamError(f"Takım '{tool.name}' profili izleyemez: φ = {lo:.4f}° < −κr' = {-kr2}°")


def check_reach(profile: Profile, tool: LatheTool, side: str = "dis") -> None:
    """−κr' ≤ φ ≤ κr değilse CamError (κr' = 180 − κr − εr)."""
    _reach_frame(prepare(profile, side), tool)


# ---------------------------------------------------------------- burun merkezi yolu (açık ofset)


def _right(t: np.ndarray) -> np.ndarray:
    """Boş taraf normali n = (t_x, −t_z)."""
    return np.array([t[1], -t[0]])


def _raw(p: Profile, rho: float) -> tuple[list[Segment], list[int | None], list[int]]:
    """Ham ofset: parçalar, kaynak profil parçası (bağlantılar None), düşen içbükey yaylar."""
    segs = p.segments
    out: list[Segment] = []
    src: list[int | None] = []
    dropped: list[int] = []

    def add(s: Segment, i: int | None) -> None:
        out.append(s)
        src.append(i)

    for i, s in enumerate(segs):
        a = s.p0 + rho * _right(s.tangent(0.0))
        b = s.p1 + rho * _right(s.tangent(1.0))
        if isinstance(s, Line):
            add(Line(a, b), i)
        else:
            Rn = s.R + rho if s.ccw else s.R - rho
            if Rn > TOL:
                add(Arc(a, b, s.c, s.ccw), i)
            else:
                dropped.append(i)
                for q0, q1 in ((a, s.c), (s.c, b)):
                    if np.hypot(*(q1 - q0)) > TOL:
                        add(Line(q0, q1), None)
        if i == len(segs) - 1:
            break
        nxt = segs[i + 1]
        sp = nxt.p0 + rho * _right(nxt.tangent(0.0))
        if np.hypot(*(sp - b)) <= LINK_TOL:
            continue
        V = s.p1
        k = cross(s.tangent(1.0), nxt.tangent(0.0))
        if k > 0:  # sola dönüş: boş tarafta boşluk, burun köşenin etrafında döner
            add(Arc(b, sp, V, True), None)
        else:  # içbükey köşe: budanacak bağlantı doğruları
            for q0, q1 in ((b, V), (V, sp)):
                if np.hypot(*(q1 - q0)) > TOL:
                    add(Line(q0, q1), None)
    return out, src, dropped


def _split(
    pieces: list[Segment], src: list[int | None], cutters: list[Segment]
) -> tuple[list[Segment], list[int | None]]:
    """Parçaları ikili kesişimlerden ve yalnız bölen `cutters` (yola girmez) ile kesişimlerden böler."""
    params: list[list[float]] = [[0.0, 1.0] for _ in pieces]
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            for ti, tj in intersect(pieces[i], pieces[j]):
                params[i].append(ti)
                params[j].append(tj)
        L = pieces[i].length
        for c in cutters:  # uçtaki (teğet) dokunuşlar parçayı kaydırmasın
            params[i].extend(t for t, _ in intersect(pieces[i], c) if LINK_TOL < t * L < L - LINK_TOL)
    out: list[Segment] = []
    osrc: list[int | None] = []
    for s, ts, k in zip(pieces, params, src, strict=True):
        ts = sorted(ts)
        for t0, t1 in zip(ts[:-1], ts[1:], strict=True):
            if (t1 - t0) * s.length > LINK_TOL:
                out.append(s.sub(t0, t1))
                osrc.append(k)
    return out, osrc


def _dist(q: np.ndarray, p: Profile) -> float:
    return min(closest(q, s)[1] for s in p.segments)


def _nose_frame(p: Profile, rho: float, strict: bool) -> list[Segment]:
    """Dış çerçevede burun merkezi yolu (ön→arka)."""
    if not math.isfinite(rho) or rho < 0:
        raise CamError(f"Ofset ρ negatif olamaz (ρ={rho})")
    if rho < TOL:
        return list(p.segments)
    raw, src, dropped = _raw(p, rho)
    if strict and dropped:
        raise CamError(f"İçbükey yay yarıçapı burun yarıçapından küçük: parça {dropped[0]} (ρ={rho})")
    # uç kapakları: profil uçları etrafındaki ρ daireleri; içine giren alt parçalar atılsın diye bölücü
    caps = [Arc(q + np.array([rho, 0.0]), q + np.array([rho, 0.0]), q) for q in (p.start, p.end)]
    pieces, psrc = _split(raw, src, caps)
    keep = [(s, k) for s, k in zip(pieces, psrc, strict=True) if _dist(s.point(0.5), p) >= rho - KEEP_TOL]
    start = raw[0].p0
    idx = [i for i, (s, _) in enumerate(keep) if np.hypot(*(s.p0 - start)) <= LINK_TOL]
    if not idx:
        raise CamError("Burun yolu profil başlangıcından kurulamadı (başlangıç erişilemez)")
    unused = set(range(len(keep)))
    cur = idx[0]
    unused.discard(cur)
    chain = [keep[cur]]
    while True:
        end = chain[-1][0].p1
        cands = [k for k in unused if np.hypot(*(keep[k][0].p0 - end)) <= LINK_TOL]
        if not cands:
            break
        t_in = chain[-1][0].tangent(1.0)

        def turn(k, t_in=t_in):
            t_out = keep[k][0].tangent(0.0)
            return math.atan2(cross(t_in, t_out), float(np.dot(t_in, t_out)))

        k = min(cands, key=turn)  # boş tarafta en dışta kalan: en çok sağa dönen
        unused.discard(k)
        chain.append(keep[k])
    if strict:
        if unused:
            raise CamError("Profilin bir kısmına burun ulaşamıyor (dar kanal / erişilemeyen bölge)")
        seen = {k for _, k in chain if k is not None}
        missing = sorted(set(range(len(p.segments))) - seen)
        if missing:
            raise CamError(f"Profil parçası {missing[0]} burun yarıçapı için çok dar (ρ = {rho}), işlenemez")
    return merge_segments([s for s, _ in chain], closed=False)


def _shift(segs: list[Segment], q: np.ndarray) -> list[Segment]:
    out: list[Segment] = []
    for s in segs:
        if isinstance(s, Arc):
            out.append(Arc(s.p0 + q, s.p1 + q, s.c + q, s.ccw))
        else:
            out.append(Line(s.p0 + q, s.p1 + q))
    return out


def nose_path(profile: Profile, rho: float, side: str = "dis", strict: bool = True) -> list[Segment]:
    """Burun merkezi yolu: profilin boş tarafa ρ ofseti (budamalı, ön→arka). ρ = 0 → profilin kendisi."""
    sgn = check_side(side)
    segs = _nose_frame(prepare(profile, side), rho, strict)
    return segs if sgn > 0 else mirror_segments(segs)


def tip_path(
    profile: Profile, tool: LatheTool, side: str = "dis", allowance: float = 0.0, strict: bool = True
) -> list[Segment]:
    """Hayali uç yolu: nose_path(profile, r + δ) parçalarının q_T kaydırılmışı."""
    if not math.isfinite(allowance) or allowance < 0:
        raise CamError(f"Talaş payı negatif olamaz (δ={allowance})")
    segs = nose_path(profile, tool.nose_r + allowance, side, strict)
    return _shift(segs, tip_offset(tool.tip, tool.nose_r))
