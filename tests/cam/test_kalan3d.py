"""SPEC 39 K1–K9, K17 — 3B kalan malzeme: kalınlık, bölgeler, girme derinliği, süzgeç, kalan işleme.

Testler SPEC 39 "Teori", "Arayüz" ve "Kabul kriterleri" bölümlerinden yazıldı; cam/kalan3d.py kodu okunmadı.
Durumlar elle (`ZMap.from_stock` + `z` atama, `DexelMap.subtract`) ya da SPEC 05 `simulate` ile kurulur.

Kaynaklar (SPEC 39):
- Taban b(q) = max(z_P(q) + δ, zmin); z-haritası t = max(z − b, 0); dexel t = Σ max(u − max(l, b), 0).
- Bölgeler: M = {t > t_min}, 8 komşulu bileşenler; hacim Σ t·dx·dy; bbox hücre kenarlarıyla;
  sıra: hacim azalan, eşitlikte en küçük hücre indeksi c = j·nx + i.
- Girme: e(q) = min{z(t) + f(d(t)) : d(t) ≤ R}, e_üst = L_f + max{z(t) : d(t) ≤ R};
  z-haritası r = max(z − max(e, zmin), 0), dexel r = |I ∩ [e, e_üst]|; g_k = max_q r(q).
  Yay: n = ⌈|Δθ| / (2·acos(1 − ε/r))⌉ kiriş, g_k = kirişlerin en büyüğü.
- Süzgeç: g_k > t_min → tut ve kaldır; bağlantı G0 z_safe, G0 XY, G0 z_yak, G1 plunge_feed;
  z_yak = min(z_safe, max(C_z, max_{d(q,C) ≤ R} top(q)) + clearance).
- İç köşe: z₁(x) = R₁ − √(R₁² − (R₁ − x)²), A(R) = (1 − π/4)·R², w(t) = R − √(R² − (R − t)²).

06b bağımlılığı: torik ve konik takımın profili `cam.cutter.Cutter` (SPEC 06b). Konik takım `ToolKind.CONE`
arayüz ekiyle gelir; ek yoksa konik testler atlanır. Torik takımla SPEC 06 `finish` 06b ile çalışır; bu yüzden
torik testler önce `Cutter.from_tool` çağırır (06b gelmeden "uygulanmamış" görünür).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh
from cam.kalan3d import (
    RestPath,
    engagement,
    rest_filter,
    rest_finish,
    rest_regions,
    rest_rough,
    rest_thickness,
)
from cam.model import (
    CamError,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Stock,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.ops3d import Raster, finish, rough
from cam.sim import DexelMap, ZMap, mesh_zmap, simulate, sweep_envelope
from tests.cam.simref import G0, G1, RPM, ball, bull, drill, flat, path, rect_pocket

KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}
HAS_CONE = hasattr(ToolKind, "CONE")


def cone(D: float = 6.0, tip_angle: float = 90.0, Lf: float = 20.0) -> Tool:
    """Konik takım (SPEC 06b arayüz eki: ToolKind.CONE, tip_angle tam uç açısı)."""
    return Tool(9, "konik", ToolKind.CONE, D, Lf, tip_angle=tip_angle)


def _cutter_gerekli(tool: Tool) -> None:
    """Torik / konik takımın profili SPEC 06b Cutter'dan gelir; 06b yoksa NotImplementedError."""
    from cam.cutter import Cutter

    Cutter.from_tool(tool)


def _t_ref(z, zP, zmin: float, delta: float = 0.0) -> np.ndarray:
    """z-haritası kalınlığı: t = max(z − max(z_P + δ, zmin), 0)."""
    b = np.maximum(zP + delta, zmin)
    return np.maximum(z - b, 0.0)


def _kesmeler(tp: Toolpath) -> list[tuple[tuple, Move]]:
    """Kesme hareketleri (G1, G2, G3) ve başlangıç noktaları."""
    out = []
    p0 = tp.start
    for m in tp.moves:
        if m.type in KESME:
            out.append((p0, m))
        p0 = m.end
    return out


def _ayni_hareket(a: Move, b: Move) -> bool:
    return a.type is b.type and a.end == b.end and a.feed == b.feed and a.center == b.center


def _seg_dist_pt(p0, p1, q) -> float:
    """XY'de q noktasının [p0, p1] doğru parçasına uzaklığı."""
    a = np.array(p0[:2], dtype=float)
    v = np.array(p1[:2], dtype=float) - a
    w = np.array(q, dtype=float) - a
    L2 = float(v @ v)
    t = 0.0 if L2 == 0.0 else min(max(float(w @ v) / L2, 0.0), 1.0)
    return float(np.hypot(*(w - t * v)))


# ------------------------------------------------------------------ K1 kalınlık

K1_STOK = Stock(0.0, 0.0, -10.0, 4.0, 3.0, 0.0)  # cell 1 → 4 × 3 hücre


def _k1_zmap() -> tuple[ZMap, np.ndarray]:
    g = ZMap.from_stock(K1_STOK, 1.0)
    g.z = np.array([[0.0, -1.0, -2.5, -10.0], [-0.5, -3.0, -4.0, -6.0], [-9.0, -2.0, -0.25, 0.0]])
    zP = np.array([[-1.0, -1.0, -3.0, -np.inf], [-np.inf, -2.5, -4.0, -7.0], [-20.0, -2.5, -np.inf, -0.3]])
    return g, zP


def test_k1_kalinlik_hucre_formulu():
    g, zP = _k1_zmap()
    t = rest_thickness(g, zP)
    assert t.shape == (3, 4)
    np.testing.assert_allclose(t, _t_ref(g.z, zP, g.zmin), rtol=0, atol=1e-12)
    # çakılmış hücre (z < z_P: [1, 1]) negatif değil 0
    assert t[1, 1] == 0.0
    assert np.all(t >= 0.0)


def test_k1_parca_yok_z_eksi_zmin():
    g, _ = _k1_zmap()
    np.testing.assert_allclose(rest_thickness(g), g.z - g.zmin, rtol=0, atol=1e-12)
    zP = np.full((3, 4), -np.inf)
    np.testing.assert_allclose(rest_thickness(g, zP), g.z - g.zmin, rtol=0, atol=1e-12)


def test_k1_pay_tabani_yukseltir_zmin_altina_inmez():
    g, zP = _k1_zmap()
    delta = 0.4
    t = rest_thickness(g, zP, allowance=delta)
    np.testing.assert_allclose(t, _t_ref(g.z, zP, g.zmin, delta), rtol=0, atol=1e-12)
    # z_P = −20 hücresi [2, 0]: z_P + δ = −19.6 < zmin → taban zmin, t = z − zmin = 1
    assert t[2, 0] == pytest.approx(1.0, abs=1e-12)
    # pay kalınlığı azaltır ya da değiştirmez
    assert np.all(t <= rest_thickness(g, zP) + 1e-12)


def test_k1_dexel_iki_aralik_toplami():
    d = DexelMap.from_stock(K1_STOK, 1.0)
    d.subtract(1, 1, -7.0, -3.0)  # hücre (1, 1): [−10, −7] ∪ [−3, 0]
    d.subtract(2, 0, -2.0, 0.0)  # hücre (2, 0): [−10, −2]
    zP = np.full((3, 4), -np.inf)
    zP[1, 1] = -8.0  # taban −8: [−8, −7] 1 + [−3, 0] 3 = 4
    zP[0, 2] = -5.0  # taban −5: [−5, −2] = 3
    t = rest_thickness(d, zP)
    assert t[1, 1] == pytest.approx(4.0, abs=1e-12)
    assert t[0, 2] == pytest.approx(3.0, abs=1e-12)
    # parça yok: aralık boyları toplamı
    assert rest_thickness(d)[1, 1] == pytest.approx(3.0 + 3.0, abs=1e-12)
    # taban ikinci aralığın içinde: [−3, 0] ∩ [−1.5, ∞) = 1.5
    zP[1, 1] = -1.5
    assert rest_thickness(d, zP)[1, 1] == pytest.approx(1.5, abs=1e-12)
    # pay: taban −8 + 0.5 = −7.5 → [−7.5, −7] 0.5 + 3 = 3.5
    zP[1, 1] = -8.0
    assert rest_thickness(d, zP, allowance=0.5)[1, 1] == pytest.approx(3.5, abs=1e-12)
    # dokunulmamış hücre: [−10, 0], parça yok → 10
    assert rest_thickness(d)[2, 3] == pytest.approx(10.0, abs=1e-12)


@pytest.mark.parametrize("delta", [-0.1, math.nan, math.inf])
def test_k1_hatali_pay(delta):
    g, zP = _k1_zmap()
    with pytest.raises(CamError):
        rest_thickness(g, zP, allowance=delta)


def test_k1_sekil_uyusmazligi():
    g, _ = _k1_zmap()
    with pytest.raises(CamError):
        rest_thickness(g, np.zeros((4, 3)))
    with pytest.raises(CamError):
        rest_thickness(DexelMap.from_stock(K1_STOK, 1.0), np.zeros((3, 5)))


# ------------------------------------------------------------------ K2 bölgeler

# x0 = 1, y0 = 2, dx = dy = 0.5; nx = 10, ny = 6
K2_STOK = Stock(1.0, 2.0, -5.0, 6.0, 5.0, 0.0)


def _k2_state() -> ZMap:
    g = ZMap.from_stock(K2_STOK, 0.5)
    rng = np.random.default_rng(39)
    g.z = -rng.uniform(0.0, 4.0, (g.ny, g.nx))
    return g


def _hucreler(reg) -> set[tuple[int, int]]:
    c = np.asarray(reg.cells)
    assert c.ndim == 2 and c.shape[1] == 2
    return {(int(i), int(j)) for i, j in c}


def _bolge_ref(g: ZMap, t: np.ndarray, cells: set[tuple[int, int]]):
    """(hacim, t_max, at, bbox) SPEC formülleriyle."""
    V = sum(t[j, i] for i, j in cells) * g.dx * g.dy
    i_m, j_m = max(cells, key=lambda c: (t[c[1], c[0]], -(c[1] * g.nx + c[0])))
    is_ = [i for i, _ in cells]
    js = [j for _, j in cells]
    bbox = (
        g.x0 + min(is_) * g.dx,
        g.x0 + (max(is_) + 1) * g.dx,
        g.y0 + min(js) * g.dy,
        g.y0 + (max(js) + 1) * g.dy,
    )
    at = (g.x0 + (i_m + 0.5) * g.dx, g.y0 + (j_m + 0.5) * g.dy, float(g.z[j_m, i_m]))
    return V, float(t[j_m, i_m]), at, bbox


def _bolge_kontrol(g, t, reg, cells) -> None:
    assert _hucreler(reg) == cells
    V, tmax, at, bbox = _bolge_ref(g, t, cells)
    assert reg.volume == pytest.approx(V, rel=1e-12)
    assert reg.t_max == pytest.approx(tmax, abs=1e-12)
    np.testing.assert_allclose(reg.at, at, rtol=0, atol=1e-12)
    np.testing.assert_allclose(reg.bbox, bbox, rtol=0, atol=1e-12)


def test_k2_iki_ayrik_blok_hacme_gore_sirali():
    g = _k2_state()
    t = np.zeros((g.ny, g.nx))
    kucuk = {(1, 1), (2, 1), (1, 2), (2, 2)}  # 2 × 2 blok
    buyuk = {(i, j) for i in range(6, 9) for j in range(2, 5)}  # 3 × 3 blok
    for i, j in kucuk:
        t[j, i] = 0.5
    for i, j in buyuk:
        t[j, i] = 0.3 + 0.1 * i + 0.01 * j  # en kalın (8, 4)
    regs = rest_regions(g, t, 0.02)
    assert len(regs) == 2
    _bolge_kontrol(g, t, regs[0], buyuk)  # hacim 9 hücre > 4 hücre
    _bolge_kontrol(g, t, regs[1], kucuk)
    assert regs[0].t_max == pytest.approx(0.3 + 0.8 + 0.04, abs=1e-12)
    assert regs[0].at[:2] == pytest.approx((1.0 + 8.5 * 0.5, 2.0 + 4.5 * 0.5), abs=1e-12)


def test_k2_koseden_degen_iki_hucre_tek_bolge():
    g = _k2_state()
    t = np.zeros((g.ny, g.nx))
    t[1, 3] = 0.7
    t[2, 4] = 0.2  # (3, 1) ile (4, 2) yalnız köşeden değer
    regs = rest_regions(g, t, 0.02)
    assert len(regs) == 1
    _bolge_kontrol(g, t, regs[0], {(3, 1), (4, 2)})
    assert regs[0].bbox == pytest.approx((2.5, 3.5, 2.5, 3.5), abs=1e-12)


def test_k2_halka_tek_bolge_delik_sayilmaz():
    g = _k2_state()
    t = np.zeros((g.ny, g.nx))
    halka = {(i, j) for i in range(2, 7) for j in range(1, 5) if i in (2, 6) or j in (1, 4)}
    for i, j in halka:
        t[j, i] = 1.0
    t[2, 4] = 0.02  # deliğin içinde, t = t_min → maskede değil (t > t_min)
    regs = rest_regions(g, t, 0.02)
    assert len(regs) == 1
    _bolge_kontrol(g, t, regs[0], halka)


def test_k2_bos_ve_esik():
    g = _k2_state()
    t = np.full((g.ny, g.nx), 0.02)
    assert rest_regions(g, t, 0.02) == []
    assert rest_regions(g, np.zeros((g.ny, g.nx)), 0.0) == []
    # t_min = 0: her pozitif hücre maskede
    t = np.zeros((g.ny, g.nx))
    t[0, 0] = 1e-9
    assert len(rest_regions(g, t, 0.0)) == 1


def test_k2_esit_hacimde_en_kucuk_hucre_indeksi_once():
    g = _k2_state()
    t = np.zeros((g.ny, g.nx))
    # A: (8, 1) → c = 1·10 + 8 = 18; B: (1, 4) → c = 41; C: (5, 0) → c = 5; eşit hacim
    for i, j in ((8, 1), (1, 4), (5, 0)):
        t[j, i] = 0.6
    regs = rest_regions(g, t, 0.02)
    assert [_hucreler(r) for r in regs] == [{(5, 0)}, {(8, 1)}, {(1, 4)}]


def test_k2_dexel_durumunda_at_top():
    d = DexelMap.from_stock(K2_STOK, 0.5)
    d.subtract(3, 2, -1.25, 0.0)  # top = −1.25
    t = np.zeros((d.ny, d.nx))
    t[2, 3] = 2.0
    regs = rest_regions(d, t, 0.02)
    assert len(regs) == 1
    np.testing.assert_allclose(regs[0].at, (1.0 + 3.5 * 0.5, 2.0 + 2.5 * 0.5, -1.25), rtol=0, atol=1e-12)


def test_k2_hatalar():
    g = _k2_state()
    with pytest.raises(CamError):
        rest_regions(g, np.zeros((g.ny, g.nx)), -0.01)
    with pytest.raises(CamError):
        rest_regions(g, np.zeros((g.nx, g.ny)), 0.02)


# ------------------------------------------------------------------ K3 girme derinliği

K3_STOK = Stock(0.0, 0.0, -20.0, 20.0, 12.0, 0.0)  # cell 0.5 → 40 × 24


def _tek_hucre(g: ZMap, i: int, j: int) -> ZMap:
    """Yalnız (i, j) hücresinde malzeme (z = zmax), diğerleri zmin: g_k = zmax − max(e, zmin)."""
    h = g.copy()
    h.z[:] = h.zmin
    h.z[j, i] = h.zmax
    return h


@pytest.mark.parametrize("tool", [flat(6.0), ball(6.0), bull(6.0, 1.5)], ids=["duz", "kuresel", "torik"])
def test_k3_e_sweep_envelope_ile_ayni(tool):
    g = ZMap.from_stock(K3_STOK, 0.5)
    p0, p1 = (3.0, 4.0, -3.0), (15.0, 8.0, -1.0)  # rampa
    X, Y = g.centers()
    e = sweep_envelope(tool, p0, p1, X, Y)  # SPEC 05
    aday = np.argwhere(np.isfinite(e) & (e < g.zmax - 1e-3) & (e > g.zmin))
    rng = np.random.default_rng(3)
    secim = aday[rng.choice(len(aday), 8, replace=False)]
    for j, i in secim:
        h = _tek_hucre(g, int(i), int(j))
        gk = engagement(tool, p0, G1(*p1), h)
        assert g.zmax - gk == pytest.approx(e[j, i], abs=1e-9)
    # durum değişmez
    h = _tek_hucre(g, 10, 10)
    z0 = h.z.copy()
    engagement(tool, p0, G1(*p1), h)
    np.testing.assert_array_equal(h.z, z0)


def _brute_cone_e(R: float, cot: float, q, p0, p1, n: int = 100_001) -> float:
    """Konik e(q) kaba kuvvetle: [0, 1] üzerinde n örnek, sonra en iyinin ±2 adımında n örnek (g dışbükey)."""

    def g_t(t):
        px = p0[0] + t * (p1[0] - p0[0])
        py = p0[1] + t * (p1[1] - p0[1])
        pz = p0[2] + t * (p1[2] - p0[2])
        d = np.hypot(q[0] - px, q[1] - py)
        return np.where(d <= R, pz + d * cot, np.inf)  # f(ρ) = ρ·cot θ

    t = np.linspace(0.0, 1.0, n)
    v = g_t(t)
    k = int(np.argmin(v))
    h = 1.0 / (n - 1)
    t2 = np.linspace(max(0.0, t[k] - 2 * h), min(1.0, t[k] + 2 * h), n)
    return float(min(v[k], np.min(g_t(t2))))


@pytest.mark.skipif(not HAS_CONE, reason="ToolKind.CONE arayüz eki (SPEC 06b) yok")
def test_k3_konik_kaba_kuvvet():
    tool = cone(6.0, 90.0)  # θ = 45°, cot θ = 1
    _cutter_gerekli(tool)
    g = ZMap.from_stock(K3_STOK, 0.5)
    p0, p1 = (3.0, 4.0, -4.0), (15.0, 8.0, -1.5)
    for i, j in ((6, 8), (10, 10), (20, 13), (27, 17), (14, 14)):
        q = (g.x0 + (i + 0.5) * g.dx, g.y0 + (j + 0.5) * g.dy)
        e = _brute_cone_e(3.0, 1.0, q, p0, p1)
        assert math.isfinite(e) and g.zmin < e < g.zmax
        gk = engagement(tool, p0, G1(*p1), _tek_hucre(g, i, j))
        assert g.zmax - gk == pytest.approx(e, abs=1e-6)


@pytest.mark.parametrize(
    "tool, h",
    [
        (flat(6.0), 0.0),
        (ball(6.0), 3.0 - math.sqrt(9.0 - 1.65**2)),  # R − √(R² − d²)
        (bull(6.0, 1.5), 1.5 - math.sqrt(1.5**2 - (1.65 - 1.5) ** 2)),  # r_c − √(r_c² − (d − R + r_c)²)
    ],
    ids=["duz", "kuresel", "torik"],
)
def test_k3_basamakli_yuzey_kapali_form(tool, h):
    """Yatay hareket z_c = −3, y = 5.25 (hücre merkez sırası), x: 2 → 10.6; x ≥ 12 basamak z = −1, aksi −5.

    Alçak hücreler e ≥ −3 > −5 → r = 0. Yüksek hücrelerin en yakını merkez (12.25, 5.25), d = 1.65 < R:
    g_k = (−1) − (−3) − h(d) = 2 − h(1.65).
    """
    g = ZMap.from_stock(Stock(0.0, 0.0, -20.0, 20.0, 10.0, 0.0), 0.5)
    X, _ = g.centers()
    g.z = np.where(X >= 12.0, -1.0, -5.0)
    gk = engagement(tool, (2.0, 5.25, -3.0), G1(10.6, 5.25, -3.0), g)
    assert gk == pytest.approx(2.0 - h, abs=1e-9)


def test_k3_dexel_iki_aralik_kesisim_boyu():
    stok = Stock(0.0, 0.0, -20.0, 4.0, 4.0, 0.0)  # cell 1 → 4 × 4
    d = DexelMap.from_stock(stok, 1.0)
    for i in range(4):
        for j in range(4):
            if (i, j) != (1, 1):
                d.subtract(i, j, -20.0, 0.0)  # malzemesiz hücre
    d.subtract(1, 1, -12.0, -6.0)  # (1, 1): [−20, −12] ∪ [−6, 0]
    # L_f = 10, z = −13: [−13, −3] ∩ I = [−13, −12] (1) + [−6, −3] (3) = 4
    t10 = Tool(1, "duz", ToolKind.FLAT, 2.0, 10.0)
    assert engagement(t10, (0.5, 1.5, -13.0), G1(3.5, 1.5, -13.0), d) == pytest.approx(4.0, abs=1e-9)
    # L_f = 4, z = −14: [−14, −10] ∩ I = [−14, −12] = 2 (kesicinin üstü sayılmaz)
    t4 = Tool(1, "duz", ToolKind.FLAT, 2.0, 4.0)
    assert engagement(t4, (0.5, 1.5, -14.0), G1(3.5, 1.5, -14.0), d) == pytest.approx(2.0, abs=1e-9)
    # durum değişmez
    assert d.intervals(1, 1) == pytest.approx([(-20.0, -12.0), (-6.0, 0.0)])


def test_k3_yay_kirislerinin_en_buyugu():
    """G3 yay: g_k = SPEC 05 kuralıyla bölünmüş kirişlerin g_k'larının en büyüğü."""
    g = ZMap.from_stock(K3_STOK, 0.5)
    rng = np.random.default_rng(7)
    g.z = -rng.uniform(0.0, 3.0, (g.ny, g.nx))
    tool = ball(4.0)
    c, Rc, a0, a1, z = (10.0, 6.0), 4.0, 0.3, 2.6, -2.0
    p0 = (c[0] + Rc * math.cos(a0), c[1] + Rc * math.sin(a0), z)
    p1 = (c[0] + Rc * math.cos(a1), c[1] + Rc * math.sin(a1), z)
    eps = 1e-2
    n = math.ceil((a1 - a0) / (2 * math.acos(1 - eps / Rc)))
    th = np.linspace(a0, a1, n + 1)
    pts = [(c[0] + Rc * math.cos(a), c[1] + Rc * math.sin(a), z) for a in th]
    beklenen = max(engagement(tool, pts[k], G1(*pts[k + 1]), g) for k in range(n))
    yay = Move(MoveType.ARC_CCW, p1, 600.0, c)
    assert engagement(tool, p0, yay, g, arc_tol=eps) == pytest.approx(beklenen, abs=1e-12)


# ------------------------------------------------------------------ K4 süzgeç uç durumları

K4_STOK = Stock(0.0, 0.0, -10.0, 30.0, 20.0, 0.0)


def test_k4_tamamen_havada_yol():
    g = ZMap.from_stock(K4_STOK, 0.5)
    g.z[:, :30] = -2.0
    z0 = g.z.copy()
    tp = path(
        flat(6.0),
        (2.0, 2.0, 10.0),
        [G1(2.0, 2.0, 1.0), G1(28.0, 2.0, 1.0), G1(28.0, 18.0, 0.5), G0(28, 18, 10)],
    )
    rp = rest_filter(tp, g)
    assert isinstance(rp, RestPath)
    assert rp.toolpath is None
    assert rp.kept == []
    assert rp.removed == pytest.approx(0.0, abs=1e-12)
    np.testing.assert_array_equal(rp.state.z, z0)
    np.testing.assert_array_equal(g.z, z0)  # girdi değişmez


def test_k4_tamamen_malzemede_yol():
    g = ZMap.from_stock(K4_STOK, 0.5)
    z0 = g.z.copy()
    tool = flat(6.0)
    # dalma + zigzag (sıra aralığı 4 < D), her hareket taze malzemeye 2 mm girer
    mv = [G0(4.0, 4.0, 3.0), G1(4.0, 4.0, -2.0, 300.0)]
    for k, y in enumerate((4.0, 8.0, 12.0, 16.0)):
        xa, xb = (4.0, 26.0) if k % 2 == 0 else (26.0, 4.0)
        if k:
            mv.append(G1(xa, y, -2.0))
        mv.append(G1(xb, y, -2.0))
    mv.append(G0(4.0, 16.0, 10.0))
    tp = path(tool, (4.0, 4.0, 10.0), mv, "cep")
    rp = rest_filter(tp, g, t_min=0.02, clearance=1.0)
    kesme_idx = [k for k, m in enumerate(tp.moves) if m.type in KESME]
    assert rp.kept == kesme_idx
    out = rp.toolpath
    assert out is not None
    out.validate()
    assert out.name == "cep (kalan)"
    assert out.rpm == tp.rpm
    # tek koşu: başlangıç ilk koşunun üstü, z_safe = girdi start z
    C = tp.moves[0].end  # koşunun ilk noktası = ilk tutulan hareketin başlangıcı
    assert out.start == pytest.approx((C[0], C[1], 10.0), abs=1e-12)
    kes = [m for m in out.moves if m.type is not MoveType.RAPID]
    tutulan = [tp.moves[k] for k in kesme_idx]
    # bağlantı dalması + tutulan hareketler aynı sırada ve uç noktalarıyla
    assert len(kes) == len(tutulan) + 1
    dalma = kes[0]
    assert dalma.type is MoveType.LINEAR and dalma.end == pytest.approx(C, abs=1e-12)
    assert dalma.feed == pytest.approx(300.0)  # plunge_feed = yolun ilk G1 beslemesi
    assert all(_ayni_hareket(a, b) for a, b in zip(kes[1:], tutulan, strict=True))
    # dalmadan önceki G0 z_yak'ta: min(z_safe, max(C_z, max top) + clearance) = min(10, max(3, 0) + 1) = 4
    i_d = out.moves.index(dalma)
    onceki = out.moves[i_d - 1]
    assert onceki.type is MoveType.RAPID
    assert onceki.end == pytest.approx((C[0], C[1], 4.0), abs=1e-12)
    # son: G0 ile z_safe'e
    son = out.moves[-1]
    assert son.type is MoveType.RAPID and son.end[2] == pytest.approx(10.0)
    assert son.end[:2] == pytest.approx(tutulan[-1].end[:2])
    # girdi değişmez, kaldırılan hacim = fark
    np.testing.assert_array_equal(g.z, z0)
    assert rp.removed == pytest.approx(g.volume() - rp.state.volume(), rel=1e-12)
    assert rp.removed > 0


# ------------------------------------------------------------------ K5 süzgeç özellikleri

K5_STOK = Stock(0.0, 0.0, -6.0, 30.0, 20.0, 0.0)
K5_CELL = 0.5
Z_SAFE = 10.0


def _rastgele_program(tool: Tool, seed: int, n_kosu: int = 6) -> Toolpath:
    """Sabit tohumlu 3 eksen program: koşular G0 z_safe'te, dalma G1, sonra rastgele G1 / G2 / G3 (düzlemsel).

    Kesme noktaları x ∈ [−3, 33], y ∈ [−3, 23], z ∈ [−4, 0.5] (bir kısmı havada); G0'lar z_safe'te.
    """
    rng = np.random.default_rng(seed)
    x, y = float(rng.uniform(0, 30)), float(rng.uniform(0, 20))
    start = (x, y, Z_SAFE)
    mv: list[Move] = []
    for k in range(n_kosu):
        if k:
            x, y = float(rng.uniform(0, 30)), float(rng.uniform(0, 20))
            mv.append(G0(x, y, Z_SAFE))
        z = float(rng.uniform(-4.0, 0.5))
        mv.append(G1(x, y, z, 300.0))
        for _ in range(int(rng.integers(3, 7))):
            if rng.random() < 0.7:
                x, y, z = (
                    float(rng.uniform(-3, 33)),
                    float(rng.uniform(-3, 23)),
                    float(rng.uniform(-4.0, 0.5)),
                )
                mv.append(G1(x, y, z))
            else:
                Rc = float(rng.uniform(2.0, 6.0))
                a0 = float(rng.uniform(0, 2 * math.pi))
                c = (x - Rc * math.cos(a0), y - Rc * math.sin(a0))
                a1 = a0 + float(rng.uniform(0.3, 4.0)) * (1 if rng.random() < 0.5 else -1)
                x, y = c[0] + Rc * math.cos(a1), c[1] + Rc * math.sin(a1)
                tip = MoveType.ARC_CCW if a1 > a0 else MoveType.ARC_CW
                mv.append(Move(tip, (x, y, z), 600.0, c))
        mv.append(G0(x, y, Z_SAFE))
    tp = Toolpath("rastgele", tool, start, mv, RPM)
    tp.validate()
    return tp


def _rastgele_durum(model: str, seed: int):
    g = ZMap.from_stock(K5_STOK, K5_CELL)
    rng = np.random.default_rng(seed)
    z = -rng.uniform(0.05, 2.5, (g.ny, g.nx))
    if model == "zmap":
        g.z = z
        return g
    d = DexelMap.from_stock(K5_STOK, K5_CELL)
    for j in range(d.ny):
        for i in range(d.nx):
            d.subtract(i, j, float(z[j, i]), 0.0)
    return d


def _top(s) -> np.ndarray:
    return s.z if isinstance(s, ZMap) else s.top()


def _sim_son(res, model: str):
    return res.zmap if model == "zmap" else res.dexel


@pytest.mark.parametrize("model", ["zmap", "dexel"])
@pytest.mark.parametrize("tool", [flat(6.0), ball(6.0)], ids=["duz", "kuresel"])
def test_k5_suzgec_ozellikleri(model, tool):
    t_min = 0.2
    tp = _rastgele_program(tool, seed=39)
    S0 = _rastgele_durum(model, seed=5)
    top0 = _top(S0).copy()
    rp = rest_filter(tp, S0, t_min=t_min)
    np.testing.assert_array_equal(_top(S0), top0)  # girdi değişmez

    kesme_idx = [k for k, m in enumerate(tp.moves) if m.type in KESME]
    assert rp.kept == sorted(rp.kept) and set(rp.kept) <= set(kesme_idx)
    assert 0 < len(rp.kept) < len(kesme_idx)  # kurgu hem tutulan hem atılan hareket üretir

    # (a) geçerli, z_safe'te başlar ve biter
    out = rp.toolpath
    out.validate()
    assert out.start[2] == pytest.approx(Z_SAFE)
    assert out.moves[-1].type is MoveType.RAPID and out.moves[-1].end[2] == pytest.approx(Z_SAFE)
    # tutulan hareketler aynı sırayla çıktıda
    kes = [m for m in out.moves if m.type in KESME]
    it = iter(kes)
    assert all(any(_ayni_hareket(tp.moves[k], m) for m in it) for k in rp.kept)

    # (b) SPEC 05 simülasyonu son durumla aynı, hızlı çarpma yok
    res = simulate([out], K5_STOK, K5_CELL, initial=S0, model=model)
    son = _sim_son(res, model)
    np.testing.assert_allclose(_top(son), _top(rp.state), rtol=0, atol=1e-9)
    assert son.volume() == pytest.approx(rp.state.volume(), abs=1e-9 * son.nx * son.ny)
    assert not [c for c in res.collisions if c.kind == "hizli_carpma"]
    assert rp.removed == pytest.approx(S0.volume() - rp.state.volume(), rel=1e-9, abs=1e-9)

    # (c) süzülmemiş yola göre 0 ≤ z_süzülmüş − z_tam ≤ t_min
    tam = _sim_son(simulate([tp], K5_STOK, K5_CELL, initial=S0, model=model), model)
    fark = _top(son) - _top(tam)
    assert fark.min() >= -1e-9
    assert fark.max() <= t_min + 1e-9

    # (d) sıralı yeniden oynatma: tutulanın g_k > t_min, atılanınki ≤ t_min
    S = S0.copy()
    p0 = tp.start
    for k, m in enumerate(tp.moves):
        if m.type in KESME:
            gk = engagement(tool, p0, m, S)
            if k in rp.kept:
                assert gk > t_min
                adim = Toolpath("adim", tool, p0, [m], RPM)
                S = _sim_son(simulate([adim], K5_STOK, K5_CELL, initial=S, model=model), model)
            else:
                assert gk <= t_min
        p0 = m.end
    np.testing.assert_allclose(_top(S), _top(rp.state), rtol=0, atol=1e-9)


# ------------------------------------------------------------------ K6 / K8 iç köşe, ince işleme

R1 = 3.0  # başlangıç durumu: küresel R₁'in bıraktığı yüzey
KOSE_L = 4.0  # köşe boyu (Y)
KOSE_H = 10.0  # duvar yüksekliği (x < 0 malzeme, üstü z = 10)
KOSE_STOK = Stock(-2.0, 0.0, -1.0, 7.0, KOSE_L, KOSE_H)
KOSE_CELL = 0.05


def _kose_agi() -> tuple[np.ndarray, np.ndarray]:
    """Duvar üstü [−2, 0] × [0, L] z = H, düşey duvar x = 0, taban [0, 8] × [0, L] z = 0."""
    H, L = KOSE_H, KOSE_L
    V = np.array(
        [[-2, 0, H], [0, 0, H], [0, L, H], [-2, L, H], [0, 0, 0], [8, 0, 0], [8, L, 0], [0, L, 0]],
        dtype=float,
    )
    T = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [4, 7, 2], [4, 2, 1]])
    return V, T


def _z1(X: np.ndarray) -> np.ndarray:
    """Küresel R₁ iç köşede: z₁(x) = R₁ − √(R₁² − (R₁ − x)²), 0 ≤ x ≤ R₁; x > R₁ → 0; x < 0 → duvar H."""
    ic = R1 - np.sqrt(np.clip(R1**2 - (R1 - X) ** 2, 0.0, None))
    return np.where(X < 0, KOSE_H, np.where(X <= R1, ic, 0.0))


def _A(R: float) -> float:
    return (1 - math.pi / 4) * R**2


def _w(R: float, t: float) -> float:
    return R - math.sqrt(R**2 - (R - t) ** 2)


def _kose_durum() -> tuple[ZMap, np.ndarray, TriMesh]:
    g = ZMap.from_stock(KOSE_STOK, KOSE_CELL)
    X, _ = g.centers()
    g.z = _z1(X)
    V, T = _kose_agi()
    return g, mesh_zmap(V, T, g), TriMesh(V, T)


def _kose_raster(R: float, s: float) -> Raster:
    """Köşeye paralel (Y) sıralar; ilk sıra x = R + 1e-6 (takım duvara teğet, kenara değmez)."""
    x0 = R + 1e-6
    return Raster(x0, x0 + 20 * s, 0.0, KOSE_L, s, 0.5, 1e-3, 0.05, 600.0, 200.0, 8000.0, 15.0, "y", 1.0)


def _kesit(state: ZMap, zP: np.ndarray) -> float:
    """Köşe kesit alanı: Σ t·dx·dy / L."""
    return float(np.sum(rest_thickness(state, zP)) * state.dx * state.dy / KOSE_L)


def _kose_ince(tool: Tool, s: float, t_min: float = 0.02):
    g, zP, mesh = _kose_durum()
    r = _kose_raster(tool.D / 2, s)
    rp = rest_finish(mesh, tool, r, g, t_min=t_min)
    assert rp.toolpath is not None and rp.kept
    res = simulate([rp.toolpath], KOSE_STOK, KOSE_CELL, part_z=zP, initial=g)
    return g, zP, mesh, r, rp, res


def test_k6_ic_kose_kuresel_kalan_ince():
    R2, s, t_min = 1.0, 0.25, 0.02
    tool = ball(2 * R2, 20.0)
    g, zP, mesh, r, rp, res = _kose_ince(tool, s, t_min)
    # başlangıç kesiti ≈ A(R₁) (kurgu denetimi, ızgara)
    assert _kesit(g, zP) == pytest.approx(_A(R1), abs=R1 * KOSE_CELL)
    # (a) tutulan kesme hareketleri x ≤ w(t_min) + R₂ + s bandında
    tam = finish(mesh, tool, r)
    bant = _w(R1, t_min) + R2 + s
    p0 = tam.start
    noktalar = {}
    for k, m in enumerate(tam.moves):
        noktalar[k] = (p0, m.end)
        p0 = m.end
    for k in rp.kept:
        a, b = noktalar[k]
        assert tam.moves[k].type in KESME
        assert max(a[0], b[0]) <= bant + 1e-9
    # (b) son kesit = A(R₂), hata ≤ R₁·(Δ + scallop_flat(R₂, s))
    scallop = R2 - math.sqrt(R2**2 - (s / 2) ** 2)  # SPEC 06 düz yüzey tarak yüksekliği
    D = max(res.zmap.dx, res.zmap.dy)
    assert _kesit(res.zmap, zP) == pytest.approx(_A(R2), abs=R1 * (D + scallop))
    # (c) çakma yok, hızlı çarpma yok
    kinds = {c.kind for c in res.collisions}
    assert "cakma" not in kinds and "hizli_carpma" not in kinds
    # süzülmüş yolun simülasyonu süzgeç durumuyla aynı (K5 b)
    np.testing.assert_allclose(res.zmap.z, rp.state.z, rtol=0, atol=1e-9)


def test_k8_ic_kose_torik_kalan_ince():
    """Torik (R = 2, r_c = 1.5): köşede kalan kesit (1 − π/4)·r_c²; s = 0.25 ≤ 2(R − r_c) → taban tarağı 0."""
    R, rc, s = 2.0, 1.5, 0.25
    tool = bull(2 * R, rc, 20.0)
    _cutter_gerekli(tool)
    _, zP, _, _, rp, res = _kose_ince(tool, s)
    D = max(res.zmap.dx, res.zmap.dy)
    assert _kesit(res.zmap, zP) == pytest.approx(_A(rc), abs=R1 * D)
    assert "cakma" not in {c.kind for c in res.collisions}
    np.testing.assert_allclose(res.zmap.z, rp.state.z, rtol=0, atol=1e-9)


def test_k8_ic_kose_rc_sifir_kalan_sifir():
    """r_c → 0 (düz uç, R = 2): köşede kalan kesit → 0."""
    tool = flat(4.0, 20.0)
    _, zP, _, _, _, res = _kose_ince(tool, 0.25)
    D = max(res.zmap.dx, res.zmap.dy)
    assert _kesit(res.zmap, zP) == pytest.approx(0.0, abs=R1 * D)
    assert _kesit(res.zmap, zP) < _A(1.5) - R1 * D  # torik köşeden açıkça küçük


@pytest.mark.skipif(not HAS_CONE, reason="ToolKind.CONE arayüz eki (SPEC 06b) yok")
def test_k8_konik_takim_suzgecte_kabul():
    tool = cone(6.0, 90.0)
    _cutter_gerekli(tool)
    g = ZMap.from_stock(K4_STOK, 0.5)
    tp = path(
        tool, (5.0, 10.0, 10.0), [G1(5.0, 10.0, -1.0, 300.0), G1(25.0, 10.0, -1.0), G0(25.0, 10.0, 10.0)]
    )
    rp = rest_filter(tp, g)
    assert rp.kept == [0, 1]
    assert rp.toolpath is not None and rp.toolpath.tool is tool
    assert rp.removed > 0


# ------------------------------------------------------------------ K7 iç köşe, kaba işleme

CEP_STOK = Stock(0.0, 0.0, 0.0, 30.0, 20.0, 10.0)
CEP = (5.0, 25.0, 5.0, 15.0)  # x0, x1, y0, y1 (duvarlar hücre kenarlarında)
CEP_TABAN = 4.0
CEP_H = 10.0 - CEP_TABAN
CEP_CELL = 0.1


def _cep_agi() -> tuple[np.ndarray, np.ndarray]:
    """Keskin köşeli dikdörtgen cepli blok: üst halka z = 10, cep tabanı z = 4, dört cep duvarı."""
    x0, x1, y0, y1 = CEP
    Ht, zf = 10.0, CEP_TABAN
    V = np.array(
        [
            [0, 0, Ht], [30, 0, Ht], [30, 20, Ht], [0, 20, Ht],
            [x0, y0, Ht], [x1, y0, Ht], [x1, y1, Ht], [x0, y1, Ht],
            [x0, y0, zf], [x1, y0, zf], [x1, y1, zf], [x0, y1, zf],
        ],
        dtype=float,
    )  # fmt: skip
    T = np.array(
        [
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
            [8, 9, 10], [8, 10, 11],
            [4, 5, 9], [4, 9, 8], [5, 6, 10], [5, 10, 9], [6, 7, 11], [6, 11, 10], [7, 4, 8], [7, 8, 11],
        ]
    )  # fmt: skip
    return V, T


def _koseler() -> list[tuple[float, float]]:
    x0, x1, y0, y1 = CEP
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _kose_bolgeleri(regs) -> dict[int, object]:
    """Her bölgeyi en yakın cep köşesine eşle (at noktasına göre)."""
    out = {}
    for reg in regs:
        k = int(np.argmin([math.hypot(reg.at[0] - cx, reg.at[1] - cy) for cx, cy in _koseler()]))
        assert k not in out
        out[k] = reg
    return out


@pytest.mark.slow
def test_k7_ic_kose_kalan_kaba():
    R1_, R2 = 3.0, 1.0
    V, T = _cep_agi()
    mesh = TriMesh(V, T)
    g = ZMap.from_stock(CEP_STOK, CEP_CELL)
    zP = mesh_zmap(V, T, g)
    x0, x1, y0, y1 = CEP
    # başlangıç: düz R₁ ile elle cep (SPEC 05 simülasyonu; süpürülen bölge köşe yarıçapı R₁)
    cep1 = rect_pocket(flat(2 * R1_, 30.0), x0, y0, x1 - x0, y1 - y0, CEP_TABAN, z_safe=15.0)
    S1 = simulate([cep1], CEP_STOK, CEP_CELL, part_z=zP).zmap
    t1 = rest_thickness(S1, zP)
    regs1 = rest_regions(S1, t1, 0.02)
    assert len(regs1) == 4
    for reg in regs1:  # ızgara toleransı P·Δ·H, P = (π/2)·R₁
        assert reg.volume == pytest.approx(_A(R1_) * CEP_H, abs=math.pi / 2 * R1_ * CEP_CELL * CEP_H)

    # kalan kaba: düz R₂, CL dikdörtgeni duvarlardan R₂ + 1e-6 içeride, s = 0.5 (duvar boyu kalıntı kalmaz)
    tool = flat(2 * R2, 30.0)
    e = 1e-6
    r = Raster(
        x0 + R2 + e, x1 - R2 - e, y0 + R2 + e, y1 - R2 - e, 0.5, 1.0, 1e-3, 0.1, 600.0, 200.0, 8000.0, 15.0
    )
    rp = rest_rough(mesh, CEP_STOK, tool, r, 2.0, CEP_TABAN, S1)
    assert rp.toolpath is not None
    regs2 = rest_regions(rp.state, rest_thickness(rp.state, zP), 0.02)
    assert len(regs2) == 4
    b1, b2 = _kose_bolgeleri(regs1), _kose_bolgeleri(regs2)
    assert set(b2) == {0, 1, 2, 3}
    for k in range(4):
        assert b2[k].volume == pytest.approx(_A(R2) * CEP_H, abs=math.pi / 2 * R2 * CEP_CELL * CEP_H)
        assert b2[k].volume < b1[k].volume
    # tutulan hareketler köşelerin R₁ + R₂ yakınında
    tam = rough(mesh, CEP_STOK, tool, r, 2.0, CEP_TABAN)
    p0 = tam.start
    for k, m in enumerate(tam.moves):
        if k in rp.kept:
            assert min(_seg_dist_pt(p0, m.end, c) for c in _koseler()) <= R1_ + R2 + 1e-9
        p0 = m.end
    # kalan kaba yol tam yoldan kısa. Kesme boyu (G1/G2/G3, bağlantı dalmaları dahil) karşılaştırılır: köşe
    # başına çok sayıda kısa koşu olduğundan z_safe'e çıkan G0 bağlantıları toplam boyu uzatabilir.
    assert rp.toolpath.length(KESME) < tam.length(KESME)
    # SPEC 05 simülasyonu süzgeç durumuyla aynı, çakma yok
    res = simulate([rp.toolpath], CEP_STOK, CEP_CELL, part_z=zP, initial=S1)
    np.testing.assert_allclose(res.zmap.z, rp.state.z, rtol=0, atol=1e-9)
    assert not {c.kind for c in res.collisions} & {"cakma", "hizli_carpma"}


# ------------------------------------------------------------------ K9 hatalar


def _basit_yol(tool, **kw) -> Toolpath:
    return Toolpath("y", tool, (5.0, 5.0, 10.0), [G1(5.0, 5.0, -1.0, 300.0), G1(20.0, 5.0, -1.0)], RPM, **kw)


@pytest.fixture
def k9_durum() -> ZMap:
    return ZMap.from_stock(K4_STOK, 0.5)


def test_k9_torna_takimi(k9_durum):
    lt = LatheTool(1, "dis", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0)
    tp = Toolpath("torna", lt, (20.0, 0.0, 5.0), [Move(MoveType.LINEAR, (20.0, 0.0, -10.0), 0.2)], RPM)
    tp.plane = Plane.ZX
    with pytest.raises(CamError):
        rest_filter(tp, k9_durum)


def test_k9_matkap(k9_durum):
    with pytest.raises(CamError):
        rest_filter(_basit_yol(drill()), k9_durum)


def test_k9_g18_ve_g95(k9_durum):
    tp = Toolpath("g18", flat(), (5.0, 0.0, 10.0), [Move(MoveType.LINEAR, (5.0, 0.0, -1.0), 300.0)], RPM)
    tp.plane = Plane.ZX
    with pytest.raises(CamError):
        rest_filter(tp, k9_durum)
    with pytest.raises(CamError):
        rest_filter(_basit_yol(flat(), feed_mode=FeedMode.PER_REV), k9_durum)


def test_k9_gecersiz_yol(k9_durum):
    tp = _basit_yol(flat())
    tp.moves.append(Move(MoveType.LINEAR, (25.0, 5.0, -1.0), None))  # ilerleme yok → validate hatası
    with pytest.raises(CamError):
        rest_filter(tp, k9_durum)
    tp = _basit_yol(flat())
    tp.rpm = 0.0
    with pytest.raises(CamError):
        rest_filter(tp, k9_durum)


@pytest.mark.parametrize(
    "kw",
    [
        {"t_min": -0.01},
        {"clearance": -0.5},
        {"plunge_feed": 0.0},
        {"plunge_feed": -100.0},
        {"z_safe": 0.0},  # = zmax
        {"z_safe": -1.0},
        {"arc_tol": 0.0},
        {"arc_tol": -1e-3},
    ],
)
def test_k9_hatali_parametre(k9_durum, kw):
    with pytest.raises(CamError):
        rest_filter(_basit_yol(flat()), k9_durum, **kw)


def test_k9_yol_baslangici_zmax_ustunde_olmali(k9_durum):
    """z_safe = None → path.start[2]; zmax'ın üstünde değilse CamError."""
    tp = Toolpath("alcak", flat(), (5.0, 5.0, 0.0), [G1(5.0, 5.0, -1.0, 300.0)], RPM)
    with pytest.raises(CamError):
        rest_filter(tp, k9_durum)


def test_k9_rest_rough_izgara_stok_uyusmazligi():
    V, T = _cep_agi()
    mesh = TriMesh(V, T)
    r = Raster(6.0, 24.0, 6.0, 14.0, 0.5, 1.0, 1e-3, 0.1, 600.0, 200.0, 8000.0, 15.0)
    for baska in (Stock(0.0, 0.0, 0.0, 30.0, 20.0, 11.0), Stock(1.0, 0.0, 0.0, 30.0, 20.0, 10.0)):
        with pytest.raises(CamError):
            rest_rough(mesh, CEP_STOK, flat(2.0), r, 2.0, CEP_TABAN, ZMap.from_stock(baska, CEP_CELL))


def test_k9_rest_finish_matkap():
    _, _, mesh = _kose_durum()
    g = ZMap.from_stock(KOSE_STOK, KOSE_CELL)
    with pytest.raises(CamError):
        rest_finish(mesh, drill(2.0), _kose_raster(1.0, 0.25), g)


# ------------------------------------------------------------------ K17 OCCT uçtan uca


@pytest.mark.occt
@pytest.mark.slow
def test_k17_occt_cepli_blok(tmp_path):
    from cam.sim.ikiz import deviation, twin_mesh
    from geometry.features import block, pocket

    part = pocket(block(30.0, 20.0, 10.0), 15.0, 10.0, 16.0, 8.0, 5.0, r=0.0)  # iç köşe radyüssüz
    V, T = part.mesh(0.01)
    mesh = TriMesh(V, T)
    stock = Stock(0.0, 0.0, 0.0, 30.0, 20.0, 10.0)
    cell = 0.5
    zP = mesh_zmap(V, T, ZMap.from_stock(stock, cell))
    r1 = Raster(-0.5, 30.5, -0.5, 20.5, 1.0, 0.5, 1e-4, 0.01, 600.0, 200.0, 8000.0, 15.0)
    res1 = simulate([finish(mesh, ball(6.0, 30.0), r1)], stock, cell, part_z=zP)
    assert "cakma" not in {c.kind for c in res1.collisions}
    S1 = res1.zmap
    r2 = Raster(5.0, 25.0, 4.0, 16.0, 0.5, 0.5, 1e-4, 0.01, 600.0, 200.0, 8000.0, 15.0)
    rp = rest_finish(mesh, ball(2.0, 30.0), r2, S1)
    assert rp.toolpath is not None
    res2 = simulate([rp.toolpath], stock, cell, part_z=zP, initial=S1)
    assert not {c.kind for c in res2.collisions} & {"cakma", "hizli_carpma"}
    assert np.sum(rest_thickness(res2.zmap, zP)) < np.sum(rest_thickness(S1, zP))
    yol = tmp_path / "ikiz.stl"
    twin_mesh(res2.zmap).to_stl(yol)
    assert yol.stat().st_size > 84
    assert deviation(res2.zmap, V, T).max_gouge <= 1e-3
