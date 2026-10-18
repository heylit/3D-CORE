"""SPEC 38 — iş föyü çekirdeği: WCS tarifi, takım tablosu, süre, işlem tablosu, güvenlik, uçtan uca, hatalar.

K1–K5, K12. Testler yalnız SPEC 38 metninden yazıldı; `atolye` uygulama kodu okunmadı.
Beklenen değerler Ek A'nın elle hesabıdır (Teori §3, §4); süre çapraz kontrolü SPEC 05 `simulate`.
"""

from __future__ import annotations

import math
import re

import pytest

from atolye import JobSheet, build_job_sheet, wcs_text
from atolye.html import write_job_sheet
from cam.gcode import FANUC
from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Setup,
    Stock,
    Tool,
    ToolKind,
    ToolLibrary,
    Toolpath,
    Wcs,
)
from cam.setups import check_setup
from cam.sim import simulate
from tests.atolye import ek_a

REL = 1e-12
TOL = 1e-9


def job_ek_a(**kw) -> JobSheet:
    """Ek A işi: tek bağlama, T1 cep + T2 delik."""
    args = dict(machine=ek_a.machine())
    args.update(kw)
    lib = args.pop("lib", ek_a.lib())
    ops = args.pop("ops", [ek_a.ops()])
    setups = args.pop("setups", [ek_a.setup()])
    return build_job_sheet("Ek A", setups, ops, lib, ek_a.MATERIAL, **args)


# ---------------------------------------------------------------- K1


def test_wcs_text():
    """§2 tablosu: önce min, sonra max, sonra orta; diğer durumda kenardan uzaklık (format_value)."""
    assert wcs_text(ek_a.setup().stock) == ("sol kenar", "ön kenar", "üst yüz")
    assert wcs_text(Stock(-25, -20, -20, 25, 20, 0)) == ("X ortası", "Y ortası", "üst yüz")
    assert wcs_text(Stock(-2, -3, -20, 48, 37, 2)) == (
        "sol kenardan 2 mm",
        "ön kenardan 3 mm",
        "üst yüzden 2 mm aşağıda",
    )
    assert wcs_text(Stock(-2, -3, -20, 48, 37, -1.5))[2] == "üst yüzden 1,5 mm yukarıda"
    # Tablonun "0 = max" ve Z "0 = min" sütunları
    assert wcs_text(Stock(-50, -40, 0, 0, 0, 20)) == ("sağ kenar", "arka kenar", "alt yüz")
    # Z ortası
    assert wcs_text(Stock(0, 0, -10, 50, 40, 10))[2] == "Z ortası"


# ---------------------------------------------------------------- K2


def test_takim_tablosu():
    job = job_ek_a()
    s = job.setups[0]
    assert s.index == 1
    assert s.wcs == ("sol kenar", "ön kenar", "üst yüz")
    assert [t.T for t in s.tools] == [1, 2]  # ilk kullanım sırası (kütüphane sırası T2, T1)
    t1, t2 = s.tools
    assert (t1.L, t2.L) == pytest.approx((90, 105), abs=TOL)
    assert (t1.offset, t2.offset) == pytest.approx((0, 15), abs=TOL)
    assert s.ref_id == 1
    assert (t1.need, t2.need) == pytest.approx((1, 5), abs=TOL)
    assert (t1.rpm_max, t2.rpm_max) == (10000, 3000)
    assert (t1.name, t1.kind, t1.D, t1.flute_length, t1.stickout, t1.holder) == (
        "freze6",
        ToolKind.FLAT.value,
        6,
        20,
        30,
        "BT30-ER",
    )
    assert t1.corner_r == 0
    assert t1.ops == ("cep",) and t2.ops == ("delik",)
    assert t1.time == pytest.approx(11.6, rel=REL)
    assert t2.time == pytest.approx(18.32, rel=REL)
    assert job.warnings == ()

    # Referans T2: ΔL = L − L_ref
    s = job_ek_a(ref_id=2).setups[0]
    assert s.ref_id == 2
    assert [t.offset for t in s.tools] == pytest.approx([-15, 0], abs=TOL)

    # Fanuc: H kaydı = L, referans yok
    s = job_ek_a(dialect=FANUC).setups[0]
    assert s.ref_id is None
    assert [t.offset for t in s.tools] == pytest.approx([90, 105], abs=TOL)

    # T2'nin tutucusu yok → bağlamada hiçbir ofset yok, uyarı
    t2_yok = ek_a.T2(holder=None)
    job = job_ek_a(lib=ek_a.lib(t2=t2_yok), ops=[[ek_a.tp1(), ek_a.tp2(t2_yok)]])
    s = job.setups[0]
    assert [t.offset for t in s.tools] == [None, None]
    assert s.tools[1].L is None and s.tools[1].holder is None
    assert s.tools[0].L == pytest.approx(90, abs=TOL)
    assert "T2 ölçü boyu bilinmiyor: tezgâhta ölçülecek" in job.warnings

    # Bağlamada olmayan referans takım
    with pytest.raises(CamError):
        job_ek_a(ref_id=7)


# ---------------------------------------------------------------- K3


def test_sure():
    job = job_ek_a()
    s = job.setups[0]
    assert [o.time for o in s.ops] == pytest.approx([11.6, 18.32], rel=REL)
    assert [o.t_end for o in s.ops] == pytest.approx([11.6, 29.92], rel=REL)
    assert s.time == pytest.approx(29.92, rel=REL)
    assert job.total_time == pytest.approx(29.92, rel=REL)
    assert s.tool_changes == 2

    # T1–T2–T1: üçüncü op'a bağlantı G0 (20,20,−5)→(30,30,15) Z sınırlar 20/3000·60 = 0,4 s,
    # takım değişimi 10 s, G1 16 mm F100 = 9,6 s → 20 s
    tp3 = Toolpath(
        "cep2", ek_a.T1(), start=(30, 30, 15), moves=[Move(MoveType.LINEAR, (30, 30, -1), 100)], rpm=10000
    )
    s = job_ek_a(ops=[[ek_a.tp1(), ek_a.tp2(), tp3]]).setups[0]
    assert s.tool_changes == 3
    assert s.ops[2].time == pytest.approx(20.0, rel=REL)
    assert s.time == pytest.approx(49.92, rel=REL)
    assert s.tools[0].ops == ("cep", "cep2")
    assert s.tools[0].time == pytest.approx(31.6, rel=REL)

    # Varsayılan makine (machine=None → Machine()) da hatasız
    assert job_ek_a(machine=None).total_time > 0


def test_sure_simulate_capraz():
    """K12 programında op süreleri SPEC 05 `simulate(...).op_times` ile aynı (G83 DrillOp dahil)."""
    m = ek_a.machine()
    ops1 = [ek_a.tp1(), ek_a.tp2(), ek_a.drill4()]
    ops2 = [ek_a.face2()]
    job = build_job_sheet(
        "iki bağlama", [ek_a.setup(), ek_a.setup2()], [ops1, ops2], ek_a.lib(), "al", machine=m
    )
    for s, ops in zip(job.setups, (ops1, ops2), strict=True):
        beklenen = simulate(ops, s.setup.stock, cell=2, machine=m).op_times
        assert [o.time for o in s.ops] == pytest.approx(beklenen, rel=REL)


# ---------------------------------------------------------------- K4


def test_islem_tablosu():
    s = job_ek_a().setups[0]
    assert [o.no for o in s.ops] == [1, 2]
    assert [o.name for o in s.ops] == ["cep", "delik"]
    assert [o.T for o in s.ops] == [1, 2]
    assert [o.rpm for o in s.ops] == [10000, 3000]
    assert [o.F for o in s.ops] == pytest.approx([300, 150], abs=TOL)
    assert [o.z_min for o in s.ops] == pytest.approx([-1, -5], abs=TOL)

    s = job_ek_a(names=[["Cep frezeleme", "Delik delme"]]).setups[0]
    assert [o.name for o in s.ops] == ["Cep frezeleme", "Delik delme"]
    assert s.tools[0].ops == ("Cep frezeleme",)

    # DrillOp satırı: F = feed, z_min = delik dibi z
    s = job_ek_a(ops=[[ek_a.tp1(), ek_a.tp2(), ek_a.drill4()]]).setups[0]
    assert s.ops[2].F == pytest.approx(120, abs=TOL)
    assert s.ops[2].z_min == pytest.approx(-8, abs=TOL)
    assert s.ops[2].rpm == 2500
    assert s.tools[1].need == pytest.approx(8, abs=TOL)
    assert s.tools[1].rpm_max == 3000


# ---------------------------------------------------------------- K5


def test_guvenlik():
    # Bağlama elemanına giren op: check_setup'ın kendi mesajı aynen yükselir
    carp = Toolpath(
        "carp", ek_a.T1(), start=(-10, 20, 15), moves=[Move(MoveType.LINEAR, (-10, 20, 5), 100)], rpm=8000
    )
    with pytest.raises(CamError) as beklenen:
        check_setup(ek_a.setup(), [carp])
    with pytest.raises(CamError, match=re.escape(str(beklenen.value))):
        job_ek_a(ops=[[ek_a.tp1(), carp]])

    # Kütüphanede olmayan takım
    T3 = Tool(3, "freze10", ToolKind.FLAT, D=10, flute_length=25, stickout=40, holder=ek_a.H)
    yok = Toolpath("yok", T3, start=(25, 20, 15), moves=[Move(MoveType.LINEAR, (25, 20, -1), 100)], rpm=6000)
    with pytest.raises(CamError):
        job_ek_a(ops=[[ek_a.tp1(), yok]])

    # Devir sınırı
    with pytest.raises(CamError):
        job_ek_a(n_max=5000)
    job = job_ek_a(n_max=12000)
    bolum1 = [c for c in job.checks if c.section == 1]
    assert [c.text for c in bolum1] == ["En yüksek devir S10000 ≤ tezgâh sınırı 12000"]
    assert job.checks[0].section == 1
    # n_max verilmezse §1 maddesi yok
    assert not [c for c in job_ek_a().checks if c.section == 1]


# ---------------------------------------------------------------- K12


def test_uctan_uca(tmp_path):
    from html.parser import HTMLParser

    m = ek_a.machine()
    ops1 = [ek_a.tp1(), ek_a.tp2(), ek_a.drill4()]
    ops2 = [ek_a.face2()]
    job = build_job_sheet(
        "Uydurma iş",
        [ek_a.setup(), ek_a.setup2()],
        [ops1, ops2],
        ek_a.lib(),
        "al",
        machine=m,
        program_no=7,
        date="2026-10-18",
    )
    assert job.program_no == 7 and job.date == "2026-10-18"
    assert [s.index for s in job.setups] == [1, 2]
    assert [s.setup.wcs.code for s in job.setups] == ["G55", "G56"]
    # Takım değişimi (elle): bağlama 1 T1, T2, T2 → 2; bağlama 2 T1 → 1
    assert [s.tool_changes for s in job.setups] == [2, 1]
    assert [len(s.ops) for s in job.setups] == [3, 1]
    assert [[t.T for t in s.tools] for s in job.setups] == [[1, 2], [1]]
    # GRBL referansı her bağlamanın ilk takımı
    assert [s.ref_id for s in job.setups] == [1, 1]
    t = [
        simulate(o, s.setup.stock, cell=2, machine=m).op_times
        for o, s in zip((ops1, ops2), job.setups, strict=True)
    ]
    assert job.setups[0].time == pytest.approx(sum(t[0]), rel=REL)
    assert job.setups[1].time == pytest.approx(sum(t[1]), rel=REL)
    assert job.total_time == pytest.approx(job.setups[0].time + job.setups[1].time, rel=REL)
    # Ölçüm: bağlama 1 derinlik 1 ve 5 (Toolpath'ler; DrillOp alınmaz), bağlama 2 derinlik 0,5
    assert [i.text for i in job.inspection] == [
        "on-yuz: derinlik 1",
        "on-yuz: derinlik 5",
        "arka-yuz: derinlik 0,5",
    ]

    yol = write_job_sheet(job, tmp_path / "is")
    assert yol == tmp_path / "is" / "is-foyu.html"
    assert (tmp_path / "is" / "baglama-1.svg").is_file()
    assert (tmp_path / "is" / "baglama-2.svg").is_file()

    class Bolumler(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids: list[str] = []
            self.imgs: list[str] = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "section" and a.get("id"):
                self.ids.append(a["id"])
            if tag == "img":
                self.imgs.append(a.get("src"))

    p = Bolumler()
    p.feed(yol.read_text(encoding="utf-8"))
    assert p.ids == ["baglama-1", "baglama-2"]
    assert p.imgs == ["baglama-1.svg", "baglama-2.svg"]


def _tp(tool, **kw) -> Toolpath:
    return Toolpath(
        "x", tool, start=(25, 20, 15), moves=[Move(MoveType.LINEAR, (25, 20, -1), 100)], rpm=5000, **kw
    )


def _hatali_girdiler():
    """(ad, build_job_sheet argümanları) — hepsi CamError (§Arayüz sonu)."""
    S, L = ek_a.setup(), ek_a.lib()
    ops0 = ek_a.ops()
    temel = dict(title="t", setups=[S], ops=[ops0], lib=L, material="al")

    def d(**kw):
        x = dict(temel)
        x.update(kw)
        return x

    torna = LatheTool(9, "torna", LatheToolKind.TURN, nose_r=0.4, tip=3, kappa_r=93, eps_r=55)
    tp_torna = Toolpath(
        "torna",
        torna,
        start=(10, 0, 5),
        moves=[Move(MoveType.LINEAR, (10, 0, -5), 0.1)],
        rpm=1000,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
    )
    lib_torna = ToolLibrary([*L.tools, torna])
    tp_zx = _tp(ek_a.T1(), plane=Plane.ZX)
    tp_g95 = _tp(ek_a.T1(), feed_mode=FeedMode.PER_REV)
    silindir = Setup("silindir", Wcs("G54", (0, 0, 0)), CylinderStock(D=60, zmin=-20, zmax=0))
    return [
        ("bos baslik", d(title="")),
        ("baslik str degil", d(title=5)),
        ("bos malzeme", d(material="")),
        ("malzeme str degil", d(material=None)),
        ("bos baglama", d(setups=[], ops=[])),
        ("ops uzunlugu", d(ops=[ops0, ops0])),
        ("bos op listesi", d(ops=[[]])),
        ("names sekli", d(names=[["cep"]])),
        ("names baglama sayisi", d(names=[["a", "b"], ["c"]])),
        ("torna takimi", d(ops=[[*ops0, tp_torna]], lib=lib_torna)),
        ("duzlem ZX", d(ops=[[*ops0, tp_zx]])),
        ("G95", d(ops=[[*ops0, tp_g95]])),
        ("silindir ham", d(setups=[silindir], ops=[[ek_a.tp1()]])),
        ("n_max sifir", d(n_max=0)),
        ("n_max negatif", d(n_max=-1)),
        ("n_max sonsuz", d(n_max=math.inf)),
        ("n_max nan", d(n_max=math.nan)),
        ("scale sifir", d(scale=0)),
        ("scale negatif", d(scale=-1)),
        ("scale sonsuz", d(scale=math.inf)),
        ("program_no sifir", d(program_no=0)),
        ("ref_id yok", d(ref_id=7)),
        ("tolerans sinifi", d(tol_class="x")),
        ("devir siniri", d(n_max=5000)),
    ]


@pytest.mark.parametrize("ad,kw", _hatali_girdiler(), ids=[a for a, _ in _hatali_girdiler()])
def test_hatalar(ad, kw):
    with pytest.raises(CamError):
        build_job_sheet(**kw)


def test_hatalar_tolerans_tanimsiz():
    """§6: resim ölçüsü < 0,5 mm → genel tolerans tanımsız → CamError."""
    import numpy as np

    from geometry.drawing.types import Dimension

    dim = Dimension("yatay", np.array([0.0, 0.0]), np.array([0.3, 0.0]), 5.0, 0.3, "0,3")
    with pytest.raises(CamError):
        job_ek_a(dims=[dim])


def test_girdi_degismez():
    """Föy programı değiştirmez, yalnız okur (§1)."""
    ops = ek_a.ops()
    once = [o.to_dict() for o in ops]
    S = ek_a.setup()
    s_once = S.to_dict()
    build_job_sheet("t", [S], [ops], ek_a.lib(), "al", machine=ek_a.machine())
    assert [o.to_dict() for o in ops] == once
    assert S.to_dict() == s_once
