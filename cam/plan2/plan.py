"""SPEC 57 — Otomatik plan: freze (çok bağlama, 3+2 yönelim) ve torna (ters bağlama).

Freze akışı: stok (§1) → aday yönler ve yön başına erişilen özellikler (§2) → bağlama başına ulaşılan
yönler ve çene engeli (§3) → en az bağlama, eşitlikte az yönelim, ana yön, sözlük sırası (§4) → yönelim
başına SPEC 29 planı → bağlama içinde takım değişimini azaltan sıra (§5) → tri-dexel doğrulama (§7).
Stokta parça altında kavrama payı varsa ilk bağlama o paydan tutar (c = −Z; durum/57 netleştirme 6).
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from cam.dropcutter import TriMesh
from cam.gcode import GRBL, Dialect, DrillOp, write
from cam.model import CamError, CylinderStock, Frame, MachineProfile, Setup, Stock, ToolLibrary, Wcs
from cam.multiaxis.indexed import local_stock
from cam.plan import (
    DEFAULT_OPTIONS,
    MillOptions,
    MillPlan,
    Unplanned,
    _check_options,
    check_common,
    plan_mill_features,
)
from cam.plan2.erisim import (
    ANA,
    COS_TOL,
    Access,
    Item,
    candidate_directions,
    frame_for,
    merge_features,
    reachable,
    to_local,
)
from cam.plan2.ortu import covers
from cam.plan2.sira import order_ops, precedence
from cam.plan2.stok import StockSize, select_stock
from cam.plan_turn import TurnOptions, TurnPlan, plan_turn
from cam.plan_verify import PlanCheck, verify_mill
from cam.profile import Line, Profile
from cam.sim.simulate5 import simulate5
from cam.tool_length import length_offsets
from cam.torna_ek import flip_profile, flip_stock
from geometry.part import Part

UNPLANNED_CODES = ("stok_yok", "stok_kucuk", "erisim_yok", "cene_engeli", "kavrama_yuzeyi_yok", "aday_siniri")
CELL = 0.5  # mm: doğrulama tri-dexel hücresi


@dataclass(frozen=True)
class AutoOptions:
    mill: MillOptions = DEFAULT_OPTIONS
    m: float = 1.0
    g: float = 5.0
    clearance: float = 1.0
    c_tc: float = 1.0
    c_rot: float = 0.1
    ang_tol: float = 0.5
    max_candidates: int = 16
    verify: bool = True


DEFAULT_AUTO = AutoOptions()  # dondurulmuş: paylaşılan varsayılan güvenli


@dataclass(frozen=True)
class AutoPlan:
    stock: Stock | CylinderStock
    clamps: tuple[Setup, ...]
    frames: tuple[tuple[Frame, ...], ...]
    plans: tuple[MillPlan, ...]
    order: tuple[tuple[str, ...], ...]
    tool_changes: int
    rotations: int
    unplanned: tuple[Unplanned, ...]
    checks: tuple[PlanCheck, ...]

    def summary(self) -> list[dict]:
        """Bağlama sırasıyla op başına SPEC 29 özeti; `clamp` bağlama, `setup` yönelim indeksi."""
        return [{"clamp": k, **s} for k, m in enumerate(self.plans) for s in m.summary()]

    def gcode(self, lib: ToolLibrary, dialect: Dialect = GRBL) -> list[str]:
        """Bağlama başına bir program; bağlama içinde ardışık aynı yönelimli işlemler bir bölüm.

        Çok yönelimli bağlamada bölümler iş düzlemi notuyla art arda yazılır; döndürme komutu (CYCLE800,
        PLANE SPATIAL) SPEC 41 son işlemcisinin işidir, burada yalnız not düşülür.
        """
        out = []
        for k, (m, frames) in enumerate(zip(self.plans, self.frames, strict=True)):
            bolumler: list[tuple[int, list]] = []
            for o in m.ops:
                if not bolumler or bolumler[-1][0] != o.setup:
                    bolumler.append((o.setup, []))
                bolumler[-1][1].append(o)
            parcalar = []
            for j, ops in bolumler:
                ids = list(dict.fromkeys(o.tool_id for o in ops))
                lo = length_offsets(lib, ids, ref_id=ids[0]) if dialect.name == GRBL.name else None
                metin = write(
                    [o.op for o in ops], dialect, program_no=k + 1, setup=m.setups[j], length_offsets=lo
                )
                if len(m.setups) > 1:
                    z = frames[j].to_world_vec((0.0, 0.0, 1.0))
                    not_ = f"BAGLAMA {k + 1} YONELIM {j + 1}: Z = ({z[0]:.6f}, {z[1]:.6f}, {z[2]:.6f})"
                    metin = _yorum(dialect, not_) + "\n" + metin
                parcalar.append(metin)
            out.append("".join(parcalar))
        return out


def _yorum(dialect: Dialect, metin: str) -> str:
    return f"; {metin}" if dialect.name in ("Sinumerik", "Heidenhain") else f"({metin})"


# ---------------------------------------------------------------- denetim


def _sayi(ad: str, v, alt: float = 0.0, kapali: bool = True) -> float:
    if (
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or (v < alt if kapali else v <= alt)
    ):
        raise CamError(f"Otomatik plan: {ad} sonlu ve {'≥' if kapali else '>'} {alt:g} olmalı ({v!r})")
    return float(v)


def _check_auto(o: AutoOptions) -> None:
    if not isinstance(o, AutoOptions):
        raise CamError(f"Otomatik plan: options AutoOptions olmalı ({type(o).__name__})")
    _check_options(o.mill)
    for ad in ("m", "g", "clearance", "c_tc", "c_rot", "ang_tol"):
        _sayi(ad, getattr(o, ad))
    if isinstance(o.max_candidates, bool) or not isinstance(o.max_candidates, int) or o.max_candidates < 1:
        raise CamError(f"Otomatik plan: max_candidates ≥ 1 tam sayı olmalı ({o.max_candidates!r})")


def _ana(d: np.ndarray) -> bool:
    return any(float(d @ a) >= 1 - COS_TOL for a in ANA)


def _yon_anahtari(d: np.ndarray) -> tuple:
    return tuple(float(v) for v in np.round(d, 9))


# ---------------------------------------------------------------- adres kaydırma

_ADRES = re.compile(r"(faces|pockets|opens|holes)\[([\d,\s]+)\]")


def _kaydir(adres: str, ofs: dict[str, int]) -> str:
    def f(m: re.Match) -> str:
        k = ofs[m.group(1)]
        return f"{m.group(1)}[" + ",".join(str(int(v) + k) for v in m.group(2).split(",")) + "]"

    return _ADRES.sub(f, adres)


# ---------------------------------------------------------------- freze


@dataclass
class _Baglama:
    c: np.ndarray
    frame: Frame
    stock: Stock
    yonler: list[int]  # aday indeksleri, yönelim sırası (yukarı önce)
    kapsar: dict[tuple, int]  # özellik anahtarı → ilk örten yönelim (aday indeksi)
    cene: set[tuple]  # yalnız çene engeliyle düşen anahtarlar


def _baglama_cercevesi(part: Part, c: np.ndarray) -> Frame:
    """Bağlama yerel çerçevesi: z = −c, z = 0 parçanın bu bağlamadaki en alt noktası, x-y parça ortası."""
    F0 = frame_for(-c)
    lo, hi = (np.asarray(v, dtype=float) for v in part.bbox)
    K = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    Kl = F0.to_local(K)
    m = (Kl.min(axis=0) + Kl.max(axis=0)) / 2
    o = F0.to_world(np.array([m[0], m[1], Kl[:, 2].min()]))
    return frame_for(-c, o)


def _taban(part: Part, it: Item, up: np.ndarray) -> float:
    lo, hi = (np.asarray(v, dtype=float) for v in part.bbox)
    K = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    return float((it.z_low @ up).min() - (K @ up).min())


def _secim(U, B, zorunlu):
    """§4: en az bağlama; eşitlikte toplam yönelim, eğik yön sayısı, yön sözlük sırası."""
    cover = {i: set(b.kapsar) for i, b in enumerate(B)}
    en_iyi = None
    boyut = None
    for alt in covers(U, cover):
        if zorunlu is not None and zorunlu not in alt:
            continue
        if boyut is not None and len(alt) > boyut:
            break
        boyut = len(alt)
        sira = sorted(alt, key=lambda i: (i != zorunlu, i))
        atama = _ata(U, [B[i] for i in sira])
        yonelim = len({(k, j) for k, j in atama.values()})
        egik = sum(not _ana(B[i].c) for i in sira)
        anahtar = (yonelim, egik, sorted(_yon_anahtari(B[i].c) for i in sira))
        if en_iyi is None or anahtar < en_iyi[0]:
            en_iyi = (anahtar, sira, atama)
    return ([], {}) if en_iyi is None else (en_iyi[1], en_iyi[2])


def _ata(U, B: list[_Baglama]) -> dict[tuple, tuple[int, int]]:
    """Her özellik ilk örten bağlamaya, orada ilk örten yönelime: anahtar → (bağlama sırası, aday indeksi)."""
    out = {}
    for key in sorted(U, key=repr):
        for k, b in enumerate(B):
            if key in b.kapsar:
                out[key] = (k, b.kapsar[key])
                break
    return out


def plan_auto(
    part: Part,
    lib: ToolLibrary,
    material: str,
    machine: MachineProfile,
    catalog=None,
    stock: Stock | None = None,
    fixtures: Sequence = (),
    options: AutoOptions = DEFAULT_AUTO,
) -> AutoPlan:
    """Stok, en az bağlama, yönelimler, sıralama ve doğrulama (SPEC 57 §1–5, §7)."""
    if not isinstance(part, Part):
        raise CamError(f"Otomatik plan: Part bekleniyor ({type(part).__name__})")
    if not isinstance(machine, MachineProfile):
        raise CamError(f"Otomatik plan: MachineProfile bekleniyor ({type(machine).__name__})")
    check_common(material, lib)
    _check_auto(options)
    o = options
    strict = o.mill.strict
    fixtures = tuple(fixtures)
    if not all(isinstance(f, Stock) for f in fixtures):
        raise CamError("Otomatik plan: fikstürler bağlama yerel çerçevesinde Stock kutuları olmalı")
    tol = o.mill.tol

    def dur(code: str, detail: str, st) -> AutoPlan:
        u = Unplanned("parca", code, detail)
        if strict:
            raise CamError(f"{code}: {detail}")
        return AutoPlan(st, (), (), (), (), 0, 0, (u,), ())

    # §1 stok
    lo, hi = (np.asarray(v, dtype=float) for v in part.bbox)
    if stock is None:
        if catalog is not None:
            bloklar = [s for s in catalog if isinstance(s, StockSize) and s.kind == "blok"]
            try:
                stock, T = select_stock((lo, hi), bloklar, m=o.m, g=o.g)
            except CamError as e:
                if "stok_yok" not in str(e):
                    raise
                return dur("stok_yok", str(e), Stock(*lo, *hi))
            part = part.moved(T)
            lo, hi = (np.asarray(v, dtype=float) for v in part.bbox)
        else:
            stock = Stock(*lo, *hi)
    elif not isinstance(stock, Stock):
        raise CamError(f"Otomatik plan: freze stoğu Stock olmalı ({type(stock).__name__})")
    s_lo = np.array([stock.xmin, stock.ymin, stock.zmin])
    s_hi = np.array([stock.xmax, stock.ymax, stock.zmax])
    if np.any(lo < s_lo - tol) or np.any(hi > s_hi + tol):
        return dur("stok_kucuk", f"Stok parçayı kapsamıyor (parça {lo}–{hi}, stok {s_lo}–{s_hi})", stock)

    # §2 aday yönler ve erişim
    D = candidate_directions(part, o.ang_tol)
    if len(D) > o.max_candidates:
        return dur(
            "aday_siniri",
            f"{len(D)} aday yön > {o.max_candidates}; yönelim listesini kullanıcı vermeli",
            stock,
        )
    E = Access(part, stock, tol=tol, hole_d_max=o.mill.hole_d_max)
    S = [E.items(d) for d in D]
    itemler: dict[tuple, dict[int, Item]] = {}
    for i, its in enumerate(S):
        for it in its:
            itemler.setdefault(it.key, {})[i] = it
    unplanned: list[Unplanned] = []
    for k in range(len(E.regions)):
        if not E._delik_bolgesi[k] and ("bolge", k) not in itemler:
            unplanned.append(Unplanned(f"bolge[{k}]", "erisim_yok", "Hiçbir aday yönden 2.5D erişilemiyor"))

    # §3 bağlamalar
    z_c = max((f.zmax for f in fixtures), default=None)
    B: list[_Baglama] = []
    for d in D:
        c = -d
        R = reachable(c, machine)
        up = -c
        yonler = [j for j in range(len(D)) if R(D[j])]
        yonler.sort(key=lambda j: (float(D[j] @ up) < 1 - COS_TOL, j))
        kapsar: dict[tuple, int] = {}
        cene: set[tuple] = set()
        for key, gorus in itemler.items():
            for j in yonler:
                if j not in gorus:
                    continue
                if z_c is not None and float(D[j] @ up) < 1 - COS_TOL:
                    if _taban(part, gorus[j], up) < z_c + o.clearance - tol:
                        cene.add(key)
                        continue
                kapsar[key] = j
                break
        cene -= set(kapsar)
        F = _baglama_cercevesi(part, c)
        B.append(_Baglama(c, F, local_stock(stock, F), yonler, kapsar, cene))
    U = set(itemler)
    zorunlu = None
    if stock.zmin < lo[2] - tol:  # kavrama payı altta: ilk bağlama −Z
        zorunlu = next(i for i, b in enumerate(B) if float(b.c @ np.array([0.0, 0.0, -1.0])) >= 1 - COS_TOL)
        if not B[zorunlu].kapsar:
            zorunlu = None
    sira, atama = _secim(U, B, zorunlu)
    for key in sorted(U - set(atama), key=repr):
        ad = f"{key[0]}[{key[1]}]"
        if any(key in b.cene for b in B):
            unplanned.append(Unplanned(ad, "cene_engeli", f"Çene üstü {z_c:g} + {o.clearance:g} altında"))
        else:
            unplanned.append(
                Unplanned(ad, "erisim_yok", "Tezgâhın ulaştığı yönlerin hiçbirinden erişilemiyor")
            )

    # §4–5 bağlama başına plan
    clamps, frames, plans, orders = [], [], [], []
    n_tc = n_rot = 0
    sayac = 0
    mill_o = dataclasses.replace(o.mill, strict=False)
    for k, bi in enumerate(sira):
        b = B[bi]
        kullanilan = [j for j in b.yonler if any(v == (k, j) for v in atama.values())]
        if not kullanilan:
            continue
        setups, fr, ops, uns, notes, feats = [], [], [], [], [], []
        ofs = {"faces": 0, "pockets": 0, "opens": 0, "holes": 0}
        for yi, j in enumerate(kullanilan):
            F = frame_for(D[j])
            yerel = local_stock(stock, F)
            anahtarlar = sorted((key for key, v in atama.items() if v == (k, j)), key=repr)
            ff = merge_features([itemler[key][j].features for key in anahtarlar])
            mp = plan_mill_features(ff, yerel.zmin, yerel, lib, material, options=mill_o)
            for op in mp.ops:
                ops.append(dataclasses.replace(op, setup=yi, feature=_kaydir(op.feature, ofs)))
            uns += [dataclasses.replace(u, feature=_kaydir(u.feature, ofs)) for u in mp.unplanned]
            notes += [dataclasses.replace(n, feature=_kaydir(n.feature, ofs)) for n in mp.notes]
            feats.append(ff)
            for ad in ofs:
                ofs[ad] += len(getattr(ff, ad))
            setups.append(Setup(f"baglama-{len(clamps) + 1}-yon-{yi + 1}", Wcs("G54"), yerel, []))
            fr.append(F)
        sira_k, tc, rot = order_ops(ops, precedence(ops), o.c_tc, o.c_rot)
        n_tc += tc
        n_rot += rot
        yeni = []
        for i in sira_k:
            sayac += 1
            op = ops[i]
            ad = f"{sayac:02d}-{op.kind}-T{op.tool_id}"
            op.op.name = ad
            yeni.append(dataclasses.replace(op, name=ad))
        plans.append(
            MillPlan(
                material=material,
                features=merge_features(feats),
                setups=tuple(setups),
                ops=tuple(yeni),
                unplanned=tuple(sorted(uns, key=lambda u: (u.feature, u.code))),
                notes=tuple(sorted(notes, key=lambda n: (n.feature, n.code))),
            )
        )
        orders.append(tuple(op.name for op in yeni))
        frames.append(tuple(fr))
        clamps.append(Setup(f"baglama-{len(clamps) + 1}", Wcs("G54"), b.stock, list(fixtures)))

    unplanned.sort(key=lambda u: (u.feature, u.code))
    if strict and (unplanned or any(m.unplanned for m in plans)):
        hepsi = unplanned + [u for m in plans for u in m.unplanned]
        raise CamError("Otomatik plan eksik: " + "; ".join(f"{u.feature}: {u.code}" for u in hepsi))
    checks = tuple(_dogrula(part, stock, plans, frames)) if o.verify and plans else ()
    return AutoPlan(
        stock=stock,
        clamps=tuple(clamps),
        frames=tuple(frames),
        plans=tuple(plans),
        order=tuple(orders),
        tool_changes=n_tc,
        rotations=n_rot,
        unplanned=tuple(unplanned),
        checks=checks,
    )


def _dogrula(part: Part, stock: Stock, plans, frames) -> list[PlanCheck]:
    """§7 doğrulama.

    Çarpışma, kaldırılan ve kalan hacim: SPEC 43 tri-dexel, bağlama k'nın başlangıç stoğu k − 1'in sonucu
    (Karar 3). Çakma: yönelim başına 05 dexel (29 `verify_mill`, yerel ham stok); tri-dexel'in yan ışınları
    parça ağının kiriş hatasını (yay duvarında ≈ tessellation toleransı) çakma sayar, düşey ışın saymaz.
    """
    V, T = part.mesh()
    mesh = TriMesh(V=np.asarray(V, dtype=float), T=np.asarray(T))
    td = None
    out = []
    for m, fr in zip(plans, frames, strict=True):
        V0 = stock.volume if td is None else td.volume()
        collisions, total, gouge, r = [], 0.0, 0.0, None
        bolumler: list[tuple[int, list]] = []
        for o in m.ops:
            if not bolumler or bolumler[-1][0] != o.setup:
                bolumler.append((o.setup, []))
            bolumler[-1][1].append(o)
        for j, ops in bolumler:
            yollar = []
            for o in ops:
                tp = o.op.to_toolpath() if isinstance(o.op, DrillOp) else o.op
                yollar.append(dataclasses.replace(tp, frame=fr[j]))
            r = simulate5(yollar, stock, CELL, part=mesh, initial=td)
            td = r.tridexel
            collisions += [c for c in r.collisions if c.kind != "cakma"]
            total += r.total_time
            alt = MillPlan(
                m.material,
                m.features,
                (m.setups[j],),
                tuple(dataclasses.replace(o, setup=0) for o in ops),
                (),
                (),
            )
            z = verify_mill(alt, part.moved(to_local(fr[j])), cell=CELL)
            collisions += [c for c in z.collisions if c.kind == "cakma"]
            gouge += z.gouge_volume
        expected = sum(n.value for n in m.notes if n.code == "kose_artigi")
        out.append(
            PlanCheck(
                ok=not collisions,
                collisions=tuple(collisions),
                removed_volume=V0 - td.volume(),
                rest_volume=r.rest_volume(),
                gouge_volume=gouge,
                expected_rest=expected,
                total_time=total,
            )
        )
    return out


# ---------------------------------------------------------------- torna


def _bar(outer: Profile, catalog, m: float, grip: float, saw: float = 3.0) -> CylinderStock:
    """Çubuk seçimi: Ø ≥ 2·x_max + 2m, boy L + m + kavrama + testere; en küçük hacim, eşitlikte ilk satır."""
    lo, hi = outer.bbox()
    L, R = float(hi[0] - lo[0]), float(hi[1])
    en_iyi = None
    for s in catalog:
        if not isinstance(s, StockSize) or s.kind != "cubuk":
            continue
        boy = L + m + grip + saw
        if s.a + 1e-9 < 2 * R + 2 * m or (s.max_len is not None and boy > s.max_len + 1e-9):
            continue
        V = math.pi * s.a**2 / 4 * boy
        if en_iyi is None or V < en_iyi[0] - 1e-9:
            en_iyi = (V, CylinderStock(D=float(s.a), zmin=float(hi[0]) + m - boy, zmax=float(hi[0]) + m))
    if en_iyi is None:
        raise CamError(f"stok_yok: katalogda Ø{2 * R + 2 * m:g} ve boy {L + m + grip + saw:g} uyan çubuk yok")
    return en_iyi[1]


def _kavrama(segs: list, z_min: float, grip: float, tol: float) -> int | None:
    """Boyu ≥ grip, aynaya en az grip + clearance uzaktaki silindirlerden çapı en büyük olanın indeksi."""
    en_iyi = None
    for k, s in enumerate(segs):
        if not isinstance(s, Line) or abs(s.p0[1] - s.p1[1]) > tol or s.p0[1] <= tol:
            continue
        boy = abs(s.p0[0] - s.p1[0])
        if boy + tol < grip or min(s.p0[0], s.p1[0]) < z_min - tol:
            continue
        if en_iyi is None or s.p0[1] > segs[en_iyi].p0[1] + tol:
            en_iyi = k
    return en_iyi


def plan_auto_turn(
    outer: Profile,
    lib: ToolLibrary,
    material: str,
    options: TurnOptions,
    catalog=None,
    stock: CylinderStock | None = None,
    grip: float = 20.0,
    inner: Profile | None = None,
) -> tuple[TurnPlan, ...]:
    """Torna: bir ya da iki bağlama (ters bağlama, SPEC 57 §6).

    Ayna stoğun arka ucunu `grip` boyunca tutar; aynaya grip + clearance'tan yakın bölüm işlenemez. Parça
    tek bağlamada sığmıyorsa boyu ≥ grip silindirlerden çapı en büyüğü ikinci kavrama yüzü olur: bağlama 1
    önden bu silindirin sonuna kadar, bağlama 2 `flip_profile` ile kalan uç. İç profil bağlama 1'dedir.
    """
    if not isinstance(outer, Profile):
        raise CamError(f"Otomatik torna planı: Profile bekleniyor ({type(outer).__name__})")
    if not isinstance(options, TurnOptions):
        raise CamError(f"Otomatik torna planı: options TurnOptions olmalı ({type(options).__name__})")
    grip = _sayi("grip", grip, 0.0, False)
    if stock is None:
        if catalog is None:
            raise CamError("Otomatik torna planı: stok ya da katalog verilmeli")
        stock = _bar(outer, catalog, 1.0, grip)
    if not isinstance(stock, CylinderStock):
        raise CamError(f"Otomatik torna planı: CylinderStock olmalı ({type(stock).__name__})")
    tol = 1e-6
    prof = outer if outer.start[0] >= outer.end[0] else outer.reversed()  # ön → arka
    lo, hi = prof.bbox()
    z_ayna = stock.zmin + grip + options.clearance  # bağlama 1'de işlenebilen en arka z
    if float(lo[0]) >= z_ayna - tol:
        return (plan_turn(outer, stock, lib, material, options, inner=inner),)

    segs = list(prof.segments)
    k = _kavrama(segs, z_ayna, grip, tol)
    if k is None or k == len(segs) - 1:
        u = Unplanned("parca", "kavrama_yuzeyi_yok", f"Boyu ≥ {grip:g} mm, z ≥ {z_ayna:g} silindir yok")
        if options.strict:
            raise CamError(f"kavrama_yuzeyi_yok: {u.detail}")
        p = plan_turn(outer, stock, lib, material, options, inner=inner)
        return (
            dataclasses.replace(
                p, unplanned=tuple(sorted((*p.unplanned, u), key=lambda v: (v.feature, v.code)))
            ),
        )
    z_b = float(segs[k].p1[0])
    p1 = plan_turn(Profile(segs[: k + 1], closed=False), stock, lib, material, options, inner=inner)
    z_ref = stock.zmin + stock.zmax
    ters = flip_stock(stock, z_ref)
    stok2 = CylinderStock(D=stock.D, zmin=z_ref - z_b, zmax=ters.zmax, d=stock.d)
    prof2 = flip_profile(Profile(segs[k + 1 :], closed=False), z_ref)
    p2 = plan_turn(prof2, stok2, lib, material, options, wcs=Wcs("G55"))
    return (p1, p2)
