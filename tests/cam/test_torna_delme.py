"""SPEC 40 A — tornada eksenel delme ve punta testleri (K1–K6).

Testler yalnız SPEC 40 metninden ve sabit arayüzlerden (cam/model.py, cam/torna_ek.py imzaları) yazıldı;
uygulama gövdesi okunmadı. Geometri uydurmadır.

Beklenen değerler (SPEC 40 Teori A):
- L_uç = (D/2)/tan(φ/2); D = 10, φ = 118° → 5/tan 59° = 3,0043030951…  (T1)
- t = (d_c/2)/tan(φ/2); φ = 90°, d_c = 6 → 3; φ = 60° → 3√3            (T2)
- n = ⌈H/q⌉, z_k = z_top − k·H/n; H = 25, q = 6 → n = 5, adım 5         (T3)
- "tam": G1 z_1; her sonraki paso G0 z_top + cl, G0 z_{k−1} + e, G1 z_k; sonda G0 z_top + cl
- "kirma": her sonraki paso G0 z_{k−1} + e, G1 z_k; sonda G0 z_top + cl
- K6 hacmi: π/4·D²·(H − L_uç) + π/3·(D/2)²·L_uç (silindir + koni), tolerans π·(D/2)²·dz.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.torna_ek import DrillCut, center_depth, lathe_center, lathe_drill, tip_length

TOL = 1e-9
G0, G1 = MoveType.RAPID, MoveType.LINEAR

BAR = CylinderStock(D=50.0, zmin=-100.0, zmax=0.0)
TUBE = CylinderStock(D=50.0, zmin=-100.0, zmax=0.0, d=12.0)

_HAS_TIP_ANGLE = "tip_angle" in {f.name for f in dataclasses.fields(Tool)}
_HAS_CONE = hasattr(ToolKind, "CONE")


def _tool(kind=ToolKind.DRILL, D: float = 10.0, phi: float | None = None, flute: float = 60.0) -> Tool:
    """Matkap / konik takım; uç açısı arayüzü (PR #60) yoksa uygulanmamış sayılır."""
    if phi is not None and not _HAS_TIP_ANGLE:
        raise NotImplementedError("Tool.tip_angle yok (Ek 2 dalga 2 arayüzü, PR #60)")
    kw = {} if phi is None else {"tip_angle": phi}
    return Tool(id=1, name=f"{kind}-{D}", kind=kind, D=D, flute_length=flute, **kw)


def _cone(D: float = 12.0, phi: float = 90.0, flute: float = 20.0) -> Tool:
    if not _HAS_CONE:
        raise NotImplementedError("ToolKind.CONE yok (Ek 2 dalga 2 arayüzü, PR #60)")
    return _tool(ToolKind.CONE, D, phi, flute)


def _cut(**kw) -> DrillCut:
    base = {"feed": 0.15, "rpm": 800.0}
    base.update(kw)
    return DrillCut(**base)


def _expected_moves(z_top: float, tips: list[float], mode: str, cl: float, e: float) -> list[tuple]:
    """SPEC 40 A hareket dizisi: (tür, z)."""
    R = z_top + cl
    out = [(G1, tips[0])]
    for k in range(1, len(tips)):
        if mode == "tam":
            out.append((G0, R))
        out.append((G0, tips[k - 1] + e))
        out.append((G1, tips[k]))
    out.append((G0, R))
    return out


def _check_moves(tp: Toolpath, expected: list[tuple], feed: float) -> None:
    assert len(tp.moves) == len(expected)
    for m, (mt, z) in zip(tp.moves, expected, strict=True):
        assert m.type is mt
        assert m.end[0] == pytest.approx(0.0, abs=TOL)
        assert m.end[1] == pytest.approx(0.0, abs=TOL)
        assert m.end[2] == pytest.approx(z, abs=TOL)
        if mt is G0:
            assert m.feed is None
        else:
            assert m.feed == pytest.approx(feed, abs=TOL)


def _check_common(tp: Toolpath, tool: Tool, cut: DrillCut, z_top: float) -> None:
    R = (0.0, 0.0, z_top + cut.clearance)
    assert tp.tool is tool
    assert tp.plane is Plane.ZX
    assert tp.feed_mode is FeedMode.PER_REV
    assert tp.css is None
    assert tp.rpm == pytest.approx(cut.rpm)
    assert tp.start == pytest.approx(R, abs=TOL)
    assert tp.moves[-1].end == pytest.approx(R, abs=TOL)
    tp.validate()
    p0 = tp.start
    for m in tp.moves:
        assert m.type in (G0, G1)  # yay yok, çevrim yok
        assert math.dist(p0, m.end) > TOL  # sıfır boylu hareket yok
        p0 = m.end


# ------------------------------------------------------------------ K1 DrillCut, tip_length, center_depth


class TestK1Parametreler:
    def test_drillcut_varsayilanlar(self):
        c = DrillCut(feed=0.1, rpm=500.0)
        assert c.peck is None
        assert c.mode == "tam"
        assert c.retract == pytest.approx(0.5)
        assert c.clearance == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "kw",
        [
            {"feed": 0.0},
            {"feed": -0.1},
            {"feed": math.nan},
            {"feed": math.inf},
            {"rpm": 0.0},
            {"rpm": -100.0},
            {"rpm": math.nan},
            {"peck": 0.0},
            {"peck": -2.0},
            {"peck": math.nan},
            {"mode": "G83"},
            {"mode": ""},
            {"retract": 0.0},
            {"retract": -0.5},
            {"retract": math.inf},
            {"clearance": 0.0},
            {"clearance": -1.0},
            {"clearance": math.nan},
        ],
    )
    def test_drillcut_gecersiz(self, kw):
        with pytest.raises(CamError):
            _cut(**kw)

    @pytest.mark.parametrize("mode", ["tam", "kirma"])
    def test_drillcut_modlar(self, mode):
        assert _cut(mode=mode, peck=3.0).mode == mode

    def test_tip_length_T1(self):
        # T1: L_uç = 5 / tan 59°
        assert tip_length(_tool(D=10.0, phi=118.0)) == pytest.approx(5 / math.tan(math.radians(59)), abs=TOL)
        assert tip_length(_tool(D=10.0, phi=118.0)) == pytest.approx(3.0043030951, abs=1e-9)

    def test_tip_length_konik(self):
        # φ = 90° → L_uç = D/2
        assert tip_length(_cone(D=12.0, phi=90.0)) == pytest.approx(6.0, abs=TOL)

    def test_tip_length_uc_acisi_yok(self):
        # varsayılan 118° kabul edilmez
        with pytest.raises(CamError):
            tip_length(_tool(D=10.0, phi=None))

    @pytest.mark.parametrize("kind", [ToolKind.FLAT, ToolKind.BALL])
    def test_tip_length_yanlis_tur(self, kind):
        with pytest.raises(CamError):
            tip_length(Tool(id=2, name="freze", kind=kind, D=10.0, flute_length=30.0))

    def test_tip_length_torna_takimi(self):
        lt = LatheTool(id=3, name="T", kind=LatheToolKind.TURN, nose_r=0.4, tip=3, kappa_r=95, eps_r=80)
        with pytest.raises(CamError):
            tip_length(lt)

    def test_center_depth_T2(self):
        # T2: φ = 90° → t = 3; φ = 60° → t = 3·√3
        assert center_depth(_cone(D=12.0, phi=90.0), 6.0) == pytest.approx(3.0, abs=TOL)
        assert center_depth(_cone(D=12.0, phi=60.0, flute=20.0), 6.0) == pytest.approx(
            3 * math.sqrt(3), abs=TOL
        )
        assert center_depth(_cone(D=12.0, phi=60.0, flute=20.0), 6.0) == pytest.approx(5.1961524, abs=1e-7)

    def test_center_depth_matkap(self):
        # DRILL da sivri uçludur: t = (d_c/2)/tan 59°
        t = center_depth(_tool(D=10.0, phi=118.0), 4.0)
        assert t == pytest.approx(2 / math.tan(math.radians(59)), abs=TOL)

    def test_center_depth_d_c_esit_D(self):
        # 0 < d_c ≤ D: sınır dahil
        assert center_depth(_cone(D=12.0, phi=90.0), 12.0) == pytest.approx(6.0, abs=TOL)

    @pytest.mark.parametrize("d_c", [0.0, -1.0, 12.5, math.nan])
    def test_center_depth_gecersiz_cap(self, d_c):
        with pytest.raises(CamError):
            center_depth(_cone(D=12.0, phi=90.0), d_c)

    def test_center_depth_uc_acisi_yok(self):
        with pytest.raises(CamError):
            center_depth(_tool(D=10.0, phi=None), 4.0)

    def test_center_depth_yanlis_tur(self):
        with pytest.raises(CamError):
            center_depth(Tool(id=2, name="freze", kind=ToolKind.FLAT, D=10.0, flute_length=30.0), 4.0)


# ------------------------------------------------------------------ K2 paso bölmesi


class TestK2PasoBolmesi:
    def test_T3_bes_paso(self):
        # T3: H = 25, q = 6 → n = 5, uçlar z_top − 5k, son paso tam z_uç
        tool = _tool(D=10.0)
        cut = _cut(peck=6.0, mode="kirma")
        tp = lathe_drill(BAR, tool, cut, z_top=0.0, z_bottom=-25.0)
        g1 = [m for m in tp.moves if m.type is G1]
        assert len(g1) == 5
        for k, m in enumerate(g1, start=1):
            assert m.end[2] == pytest.approx(-5.0 * k, abs=TOL)
        assert g1[-1].end[2] == pytest.approx(-25.0, abs=TOL)

    def test_tam_bolunen_boy(self):
        # H = 24, q = 6 → n = 4 (1e-9 toleranslı tavan, beşinci paso yok)
        tp = lathe_drill(BAR, _tool(), _cut(peck=6.0), z_top=0.0, z_bottom=-24.0)
        g1 = [m for m in tp.moves if m.type is G1]
        assert [m.end[2] for m in g1] == pytest.approx([-6.0, -12.0, -18.0, -24.0], abs=TOL)

    def test_esit_olmayan_paso(self):
        # H = 20, q = 7 → n = 3, z_k = −20k/3
        tp = lathe_drill(BAR, _tool(), _cut(peck=7.0), z_top=-2.0, z_bottom=-22.0)
        g1 = [m for m in tp.moves if m.type is G1]
        assert [m.end[2] for m in g1] == pytest.approx([-2.0 - 20.0 * k / 3 for k in (1, 2, 3)], abs=TOL)

    def test_peck_none_tek_G1(self):
        tool = _tool()
        cut = _cut()
        tp = lathe_drill(BAR, tool, cut, z_top=0.0, z_bottom=-30.0)
        _check_moves(tp, [(G1, -30.0), (G0, 1.0)], cut.feed)

    def test_paso_hersey_buyuk(self):
        # q > H → tek paso
        tp = lathe_drill(BAR, _tool(), _cut(peck=50.0), z_top=0.0, z_bottom=-30.0)
        assert [m.type for m in tp.moves] == [G1, G0]

    def test_full_diameter_ucu_derine_indirir(self):
        tool = _tool(D=10.0, phi=118.0)
        L = 5 / math.tan(math.radians(59))
        tp = lathe_drill(BAR, tool, _cut(), z_top=0.0, z_bottom=-20.0, full_diameter=True)
        g1 = [m for m in tp.moves if m.type is G1]
        assert len(g1) == 1
        assert g1[0].end[2] == pytest.approx(-20.0 - L, abs=TOL)

    def test_full_diameter_paso_bolmesi(self):
        # H = 20 + L_uç; q = 6 → n = ⌈(20 + L)/6⌉ = 4, eşit paso
        tool = _tool(D=10.0, phi=118.0)
        L = 5 / math.tan(math.radians(59))
        tp = lathe_drill(BAR, tool, _cut(peck=6.0), z_top=0.0, z_bottom=-20.0, full_diameter=True)
        g1 = [m.end[2] for m in tp.moves if m.type is G1]
        H = 20.0 + L
        n = math.ceil(H / 6.0)
        assert n == 4
        assert g1 == pytest.approx([-k * H / n for k in range(1, n + 1)], abs=TOL)

    def test_full_diameter_uc_acisi_yok(self):
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(phi=None), _cut(), z_top=0.0, z_bottom=-20.0, full_diameter=True)

    def test_full_diameter_false_uc_acisi_gerekmez(self):
        # uç derinliği doğrudan verilince L_uç gerekmez
        tp = lathe_drill(BAR, _tool(phi=None), _cut(), z_top=0.0, z_bottom=-20.0)
        assert tp.moves[0].end[2] == pytest.approx(-20.0, abs=TOL)


# ------------------------------------------------------------------ K3 hareket dizisi


class TestK3Hareketler:
    @pytest.mark.parametrize("mode", ["tam", "kirma"])
    def test_hareket_dizisi(self, mode):
        tool = _tool(D=10.0)
        cut = _cut(peck=6.0, mode=mode, retract=0.4, clearance=2.0)
        tp = lathe_drill(BAR, tool, cut, z_top=-1.0, z_bottom=-26.0)
        tips = [-1.0 - 5.0 * k for k in range(1, 6)]
        _check_moves(tp, _expected_moves(-1.0, tips, mode, 2.0, 0.4), cut.feed)
        _check_common(tp, tool, cut, -1.0)

    def test_tam_tahliye_her_pasoda(self):
        cut = _cut(peck=6.0, mode="tam")
        tp = lathe_drill(BAR, _tool(), cut, z_top=0.0, z_bottom=-25.0)
        R = cut.clearance
        g0_top = [m for m in tp.moves if m.type is G0 and abs(m.end[2] - R) <= TOL]
        # n − 1 tahliye + bitiş
        assert len(g0_top) == 5

    def test_kirma_tahliye_yok(self):
        cut = _cut(peck=6.0, mode="kirma")
        tp = lathe_drill(BAR, _tool(), cut, z_top=0.0, z_bottom=-25.0)
        R = cut.clearance
        g0_top = [m for m in tp.moves if m.type is G0 and abs(m.end[2] - R) <= TOL]
        assert len(g0_top) == 1  # yalnız bitiş
        assert tp.moves[-1].type is G0

    def test_ilk_G1_yaklasma_noktasindan(self):
        # ilk G1 R'den başlar: önünde G0 yok, start = R
        cut = _cut(peck=6.0, mode="tam", retract=0.5)
        tp = lathe_drill(BAR, _tool(), cut, z_top=0.0, z_bottom=-25.0)
        assert tp.moves[0].type is G1
        assert tp.start == pytest.approx((0.0, 0.0, 1.0), abs=TOL)

    def test_ad_varsayilan_ve_verilen(self):
        assert lathe_drill(BAR, _tool(), _cut(), 0.0, -10.0).name == "delme"
        assert lathe_drill(BAR, _tool(), _cut(), 0.0, -10.0, name="D1").name == "D1"

    def test_boru_delik_buyutme(self):
        # D > d: delik büyütme kabul
        tp = lathe_drill(TUBE, _tool(D=14.0), _cut(), z_top=0.0, z_bottom=-30.0)
        assert tp.moves[0].end[2] == pytest.approx(-30.0, abs=TOL)

    def test_on_yuzde_baslangic_tolerans(self):
        # z_top ≤ zmax + TOL
        tp = lathe_drill(BAR, _tool(), _cut(), z_top=1e-10, z_bottom=-10.0)
        assert tp.start[2] == pytest.approx(1.0 + 1e-10, abs=TOL)

    def test_tabana_kadar(self):
        # z_uç = zmin kabul
        tp = lathe_drill(BAR, _tool(flute=120.0), _cut(), z_top=0.0, z_bottom=-100.0)
        assert tp.moves[0].end[2] == pytest.approx(-100.0, abs=TOL)


# ------------------------------------------------------------------ K4 punta


class TestK4Punta:
    @pytest.mark.parametrize(("phi", "t"), [(90.0, 3.0), (60.0, 3 * math.sqrt(3))])
    def test_tek_paso_T2(self, phi, t):
        tool = _cone(D=12.0, phi=phi, flute=20.0)
        cut = _cut(rpm=1500.0, feed=0.05)
        tp = lathe_center(BAR, tool, cut, z_top=-0.5, d_c=6.0)
        _check_moves(tp, [(G1, -0.5 - t), (G0, -0.5 + cut.clearance)], cut.feed)
        _check_common(tp, tool, cut, -0.5)
        assert tp.name == "punta"

    def test_matkapla_punta(self):
        tool = _tool(D=10.0, phi=118.0)
        tp = lathe_center(BAR, tool, _cut(), z_top=0.0, d_c=4.0)
        assert tp.moves[0].end[2] == pytest.approx(-2 / math.tan(math.radians(59)), abs=TOL)

    def test_peck_verilmisse_hata(self):
        with pytest.raises(CamError):
            lathe_center(BAR, _cone(), _cut(peck=1.0), z_top=0.0, d_c=6.0)

    def test_d_c_buyuk_hata(self):
        with pytest.raises(CamError):
            lathe_center(BAR, _cone(D=12.0), _cut(), z_top=0.0, d_c=13.0)

    def test_freze_takimi_hata(self):
        with pytest.raises(CamError):
            lathe_center(
                BAR, Tool(id=2, name="F", kind=ToolKind.FLAT, D=12.0, flute_length=30.0), _cut(), 0.0, 6.0
            )

    def test_torna_takimi_hata(self):
        lt = LatheTool(id=3, name="T", kind=LatheToolKind.TURN, nose_r=0.4, tip=3, kappa_r=95, eps_r=80)
        with pytest.raises(CamError):
            lathe_center(BAR, lt, _cut(), 0.0, 6.0)


# ------------------------------------------------------------------ K5 delme hataları


class TestK5Hatalar:
    def test_uc_aynaya_gecer(self):
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(flute=150.0), _cut(), z_top=0.0, z_bottom=-100.5)

    def test_full_diameter_ucu_aynaya_gecer(self):
        # tam çap −98'de, uç −98 − 3,004 < zmin
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(phi=118.0, flute=150.0), _cut(), 0.0, -98.0, full_diameter=True)

    def test_baslangic_stogun_onunde(self):
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(), _cut(), z_top=0.5, z_bottom=-10.0)

    @pytest.mark.parametrize("D", [10.0, 12.0])
    def test_boruda_hava_delme(self, D):
        # D ≤ d → CamError (d = 12)
        with pytest.raises(CamError):
            lathe_drill(TUBE, _tool(D=D), _cut(), z_top=0.0, z_bottom=-10.0)

    def test_kesici_boy_asimi(self):
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(flute=20.0), _cut(), z_top=0.0, z_bottom=-20.5)

    def test_kesici_boy_sinir(self):
        # H = flute_length kabul
        tp = lathe_drill(BAR, _tool(flute=20.0), _cut(), z_top=0.0, z_bottom=-20.0)
        assert tp.moves[0].end[2] == pytest.approx(-20.0, abs=TOL)

    def test_kesici_boy_ucla_asim(self):
        # full_diameter: H = 18 + L_uç > 20
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(phi=118.0, flute=20.0), _cut(), 0.0, -18.0, full_diameter=True)

    def test_torna_takimi(self):
        lt = LatheTool(id=3, name="T", kind=LatheToolKind.TURN, nose_r=0.4, tip=3, kappa_r=95, eps_r=80)
        with pytest.raises(CamError):
            lathe_drill(BAR, lt, _cut(), 0.0, -10.0)

    @pytest.mark.parametrize("kind", [ToolKind.FLAT, ToolKind.BALL])
    def test_freze_takimi(self, kind):
        with pytest.raises(CamError):
            lathe_drill(BAR, Tool(id=2, name="F", kind=kind, D=10.0, flute_length=30.0), _cut(), 0.0, -10.0)

    def test_konik_takimla_delme(self):
        # lathe_drill takımı DRILL
        with pytest.raises(CamError):
            lathe_drill(BAR, _cone(D=12.0, phi=90.0), _cut(), 0.0, -5.0)

    @pytest.mark.parametrize("z_bottom", [0.0, 2.0])
    def test_bos_delme(self, z_bottom):
        # H ≤ 0
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(), _cut(), z_top=0.0, z_bottom=z_bottom)

    @pytest.mark.parametrize(("z_top", "z_bottom"), [(math.nan, -10.0), (0.0, math.nan), (0.0, -math.inf)])
    def test_sonlu_olmayan(self, z_top, z_bottom):
        with pytest.raises(CamError):
            lathe_drill(BAR, _tool(), _cut(), z_top=z_top, z_bottom=z_bottom)

    def test_kutu_stok(self):
        from cam.model import Stock

        with pytest.raises(CamError):
            lathe_drill(Stock(-10, -10, -50, 10, 10, 0), _tool(), _cut(), 0.0, -10.0)


# ------------------------------------------------------------------ K6 G-code ve simülasyon çapraz kontrolü

TC = (60.0, 50.0)


def _probe_drill_path(tool: Tool) -> Toolpath:
    """lathe_drill'den bağımsız, elle kurulmuş en basit eksenel delme yolu (E3/E4 varlık sınaması)."""
    return Toolpath(
        name="sinama",
        tool=tool,
        start=(0.0, 0.0, 1.0),
        moves=[Move(G1, (0.0, 0.0, -5.0), 0.1), Move(G0, (0.0, 0.0, 1.0))],
        rpm=800.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
    )


def _need_e3(tool: Tool):
    import cam.gcode.lathe as lathe

    try:
        lathe.write_lathe([_probe_drill_path(tool)], "M3", TC)
    except (CamError, AttributeError, TypeError) as e:
        raise NotImplementedError("E3 (write_lathe eksenel delme yolu) henüz birleşmedi") from e
    return lathe


def _need_e4(tool: Tool):
    import cam.sim as sim

    if not hasattr(sim, "simulate_lathe") or not hasattr(sim, "cutter_shape"):
        raise NotImplementedError("SPEC 22 torna simülasyonu yok (PR #41)")
    try:
        sim.cutter_shape(tool, "dis")
    except (CamError, AttributeError, TypeError) as e:
        raise NotImplementedError("E4 (cutter_shape eksenel takım) henüz birleşmedi") from e
    return sim


class TestK6CaprazKontrol:
    @pytest.mark.parametrize("mode", ["tam", "kirma"])
    def test_gcode_gidis_donus(self, mode):
        tool = _tool(D=10.0, phi=118.0)
        lathe = _need_e3(tool)
        cut = _cut(peck=6.0, mode=mode)
        tp = lathe_drill(BAR, tool, cut, z_top=0.0, z_bottom=-25.0, full_diameter=True)
        text = lathe.write_lathe([tp], "M3", TC)
        assert "G96" not in text
        assert "G97" in text
        back = lathe.read_lathe(text, {tool.id: tool})
        assert len(back) == 1
        rd = back[0]
        assert rd.css is None
        assert rd.plane is Plane.ZX
        assert rd.feed_mode is FeedMode.PER_REV
        # okunan yol = [takım değişiminden yaklaşma G0'ları] + özgün hareketler + [geri çekme G0'ları]
        n = len(tp.moves)
        cands = []
        for k in range(len(rd.moves) - n + 1):
            seq = rd.moves[k : k + n]
            if all(
                a.type is b.type
                and abs(a.end[0] - b.end[0]) <= 0.25e-3
                and abs(a.end[2] - b.end[2]) <= 0.25e-3
                and (a.feed is None) == (b.feed is None)
                and (a.feed is None or abs(a.feed - b.feed) <= 0.5e-3)
                for a, b in zip(seq, tp.moves, strict=True)
            ):
                cands.append(k)
        assert cands, "delme hareketleri okunan yolda bulunamadı"

    def test_simulasyon_hacmi(self):
        tool = _tool(D=10.0, phi=118.0, flute=60.0)
        sim = _need_e4(tool)
        L = 5 / math.tan(math.radians(59))
        cut = _cut(peck=8.0, mode="tam")
        tp = lathe_drill(BAR, tool, cut, z_top=0.0, z_bottom=-20.0, full_diameter=True)
        dz_cell = 0.25
        res = sim.simulate_lathe([tp], BAR, cell=dz_cell)
        H = 20.0 + L
        V = math.pi / 4 * 10.0**2 * (H - L) + math.pi / 3 * 5.0**2 * L
        assert res.removed_volume == pytest.approx(V, abs=math.pi * 5.0**2 * res.rmap.dz)
        assert res.rmap.dz <= dz_cell + 1e-12
        assert res.collisions == []
