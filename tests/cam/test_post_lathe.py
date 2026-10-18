"""SPEC 40 Ek E2 — torna tezgâh profili denetimi ve postprosesörü (K14–K16).

Testler yalnız SPEC 40 D bölümünden, SPEC 30 "Torna yazıcısıyla ilişki" (Ek A) metninden ve sabit arayüzlerden
(`cam/model.py`, `cam.post.check_lathe` / `post_lathe` imzaları, `cam.gcode.lathe.write_lathe`) yazıldı;
uygulama gövdesi okunmadı. Geometri uydurmadır.

Beklenen değerler (SPEC 40 D):
- Kurs: `X_m = 2·(x + o_x)` (profil X kursu çap), `Z_m = z + o_z`; her uç (G0 dahil) ve yayın
  `(x, z)` düzleminde süpürdüğü eksen yönü noktaları; takım değiştirme noktası aynı dönüşümle.
- Bu dosyada `o_x = 0`, `o_z = −300`: X kursu `[0, 400]` → `x ∈ [0, 200]`;
  Z kursu `[−600, 0]` → `z ∈ [−300, 300]`.
- Devir: `S = round(rpm)`, `rpm_min ≤ S ≤ rpm_max`. İlerleme: kesme hareketinde `feed · S ≤ feed_max`.
- Taret: `1 ≤ T ≤ tool_slots`.
- Hata mesajlarının metni sabitlenmez; yalnız op adı ve (kurs ihlalinde) 1 tabanlı hareket sırası aranır
  (SPEC 30 K5 kuralı).
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path

import pytest

import cam.post
from cam.gcode.lathe import FANUC_TORNA, write_lathe
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
    Tool,
    ToolKind,
    Toolpath,
    Wcs,
)
from cam.post import AxisLimits, MachineProfile, check_lathe, load_machine, post, post_lathe, save_machine

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW

PROFIL = Path(cam.post.__file__).parent / "profiles" / "ornek-fanuc-torna.json"
UYARI = "(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)"
POST_SATIRI = "(POST ORNEK-FANUC-TORNA FANUC)"

O_Z = -300.0
TC = (150.0, 50.0)  # takım değiştirme (yarıçap, z) → X_m = 300, Z_m = −250: kurs içinde
BAR = CylinderStock(D=300.0, zmin=-100.0, zmax=0.0)


# ------------------------------------------------------------------ yardımcılar


def torna(**kw) -> MachineProfile:
    """SPEC 40 D örnek profil değerleriyle uydurma torna profili (dosyadan bağımsız)."""
    args = dict(
        name="ORNEK-FANUC-TORNA",
        controller="fanuc",
        kind="lathe",
        x=AxisLimits(0.0, 400.0),
        z=AxisLimits(-600.0, 0.0),
        rpm_min=0.0,
        rpm_max=4000.0,
        feed_max=5000.0,
        tool_slots=12,
        verified=False,
    )
    args.update(kw)
    return MachineProfile(**args)


def freze() -> MachineProfile:
    """Geçerli freze profili (torna yolunu reddetmeli)."""
    return MachineProfile(
        name="TEST DIK",
        controller="fanuc",
        kind="mill",
        x=AxisLimits(-300.0, 300.0),
        y=AxisLimits(-200.0, 200.0),
        z=AxisLimits(-400.0, 0.0),
        rpm_max=8000.0,
        feed_max=5000.0,
    )


def kurulum(o_x: float = 0.0, o_z: float = O_Z) -> Setup:
    return Setup(name="ayna", wcs=Wcs("G54", (o_x, 0.0, o_z)), stock=BAR)


def ttool(id: int = 1) -> LatheTool:
    return LatheTool(id, f"T{id}", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0)


def lpath(
    moves: list[Move],
    start=(150.0, 0.0, 2.0),
    tool: LatheTool | Tool | None = None,
    rpm: float = 1000.0,
    css: float | None = None,
    name: str = "boyop",
) -> Toolpath:
    return Toolpath(
        name=name,
        tool=ttool() if tool is None else tool,
        start=start,
        moves=moves,
        rpm=rpm,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=css,
    )


def boy(x: float, feed: float = 0.2, **kw) -> Toolpath:
    """(150, 2) → G0 z −5 → G1 x (hareket 2) → G1 z −20 → G0 x 150 → G0 z 2; eksen eksen G0."""
    return lpath(
        [
            Move(G0, (150.0, 0.0, -5.0)),
            Move(G1, (x, 0.0, -5.0), feed=feed),
            Move(G1, (x, 0.0, -20.0), feed=feed),
            Move(G0, (150.0, 0.0, -20.0)),
            Move(G0, (150.0, 0.0, 2.0)),
        ],
        **kw,
    )


def hizli(x: float) -> Toolpath:
    """İlk hareket G0 ile x'e (hareket 1); sonra kurs içinde kısa bir kesme."""
    return lpath(
        [
            Move(G0, (x, 0.0, 2.0)),
            Move(G0, (150.0, 0.0, 2.0)),
            Move(G1, (150.0, 0.0, -5.0), feed=0.2),
            Move(G0, (150.0, 0.0, 2.0)),
        ]
    )


def yay(tip: MoveType) -> Toolpath:
    """(190, −9,5) → (190, −30,5), merkez (x, z) = (190, −20), r = 10,5; uçlar X_m = 380.

    ZX düzleminde (u, v) = (z, x): başlangıç açısı 0, bitiş π. G3 (u'dan v'ye) π/2'den, yani x = 200,5
    (X_m = 401 > 400) noktasından geçer → kurs dışı; G2 −π/2'den (x = 179,5) geçer → kurs içinde.
    Yay hareketi 2'dir."""
    return lpath(
        [
            Move(G0, (190.0, 0.0, -9.5)),
            Move(tip, (190.0, 0.0, -30.5), feed=0.2, center=(190.0, -20.0)),
            Move(G0, (195.0, 0.0, -30.5)),
            Move(G0, (195.0, 0.0, 2.0)),
        ],
        start=(195.0, 0.0, 2.0),
        name="kavisop",
    )


def _sira_var(mesaj: str, n: int) -> bool:
    """Mesajda `n` ayrı sayı olarak geçiyor mu (200.001 içindeki 2 sayılmaz)."""
    return re.search(rf"(?<![\d.]){n}(?![\d.])", mesaj) is not None


def _n_siz(text: str) -> list[str]:
    """Satır numaralarını (N10 …) atılmış, boş olmayan satırlar."""
    return [re.sub(r"^N\d+\s*", "", s.strip()) for s in text.splitlines() if s.strip()]


def _ornek() -> MachineProfile:
    """Örnek torna profili kod commit'inde gelir; o zamana dek test "uygulanmamış"."""
    if not PROFIL.is_file():
        raise NotImplementedError("SPEC 40 Ek E2: cam/post/profiles/ornek-fanuc-torna.json yok")
    return load_machine(PROFIL)


# ---------------------------------------------------------------- K14: torna profili doğrulaması


def test_K14_valid_lathe_profile_passes():
    """K14: D bölümündeki kurallara uyan profil geçerli; kurssuz (x ve z None) torna profili de geçerli."""
    torna().validate()
    torna(x=None, z=None).validate()


@pytest.mark.parametrize(
    "bozuk",
    [
        {"controller": "haas"},
        {"controller": "sinumerik"},
        {"controller": "grbl"},
        {"y": AxisLimits(-100.0, 100.0)},
        {"tool_change_z": 0.0},
        {"x": None},
        {"z": None},
        {"rpm_max": math.nan},
        {"feed_max": math.nan},
    ],
    ids=["haas", "sinumerik", "grbl", "y", "tool_change_z", "yalniz_z", "yalniz_x", "nan_rpm", "nan_feed"],
)
def test_K14_each_lathe_rule_raises(bozuk):
    """K14: D bölümündeki her kural ayrı ayrı CamError (kurucuda ya da validate'te)."""
    with pytest.raises(CamError):
        torna(**bozuk).validate()


def test_K14_presets_and_kinematics_raise():
    """K14: torna profilinde presets ve kinematics verilmez."""
    import cam.model as M

    with pytest.raises(CamError):
        torna(presets={"G54": 1}).validate()
    kin = M.Kinematics(rotary=(M.RotaryAxis("C", "masa", (0.0, 0.0, 1.0)),))
    with pytest.raises(CamError):
        torna(kinematics=kin).validate()


def test_K14_example_profile_loads():
    """K14: örnek profil dosyası SPEC 40 D değerleriyle yükleniyor ve `builtin_machines()` içinde."""
    m = _ornek()
    assert m.name == "ORNEK-FANUC-TORNA"
    assert m.controller == "fanuc" and m.kind == "lathe"
    assert (m.x.min, m.x.max) == (0.0, 400.0)
    assert (m.z.min, m.z.max) == (-600.0, 0.0)
    assert m.y is None and m.tool_change_z is None
    assert m.rpm_max == 4000.0 and m.feed_max == 5000.0
    assert m.tool_slots == 12
    assert m.verified is False
    m.validate()
    assert cam.post.builtin_machines()["ORNEK-FANUC-TORNA"] == m


def test_K14_save_load_roundtrip(tmp_path):
    """K14: `save → load` eşit; iki kayıt aynı bayt."""
    m = _ornek()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_machine(m, a)
    save_machine(load_machine(a), b)
    assert load_machine(a) == m
    assert a.read_bytes() == b.read_bytes()


def test_K14_save_load_roundtrip_built_profile(tmp_path):
    """K14: elle kurulan torna profili de `save → load` eşit."""
    m = torna(rpm_min=50.0)
    f = tmp_path / "t.json"
    save_machine(m, f)
    assert load_machine(f) == m


# ---------------------------------------------------------------- K15: torna denetimi


def test_K15_x_travel_edge_passes():
    """K15: x = 200 (yarıçap) → X_m = 400 = kurs sınırı: geçer."""
    check_lathe(torna(), [boy(200.0)], kurulum(), (200.0, 50.0))


def test_K15_x_travel_exceeded_raises_with_op_and_move():
    """K15: x = 200,001 → X_m = 400,002 > 400: CamError; mesajda op adı ve hareket sırası (2)."""
    with pytest.raises(CamError) as e:
        check_lathe(torna(), [boy(200.001)], kurulum(), (200.0, 50.0))
    assert "boyop" in str(e.value)
    assert _sira_var(str(e.value), 2)


def test_K15_x_is_diameter_not_radius():
    """K15: kurs çap cinsinden: x = 300 yarıçap (X_m = 600) [0, 400] kursunu aşar (yarıçap olarak
    karşılaştırılsaydı 300 ≤ 400 geçerdi)."""
    with pytest.raises(CamError):
        check_lathe(torna(), [boy(300.0)], kurulum(), TC)


def test_K15_x_origin_offset_applied():
    """K15: X_m = 2·(x + o_x): o_x = −10 iken x = 210 → X_m = 400 geçer; x = 210,001 → CamError."""
    check_lathe(torna(), [boy(210.0)], kurulum(o_x=-10.0), (150.0, 50.0))
    with pytest.raises(CamError):
        check_lathe(torna(), [boy(210.001)], kurulum(o_x=-10.0), (150.0, 50.0))


def test_K15_rapid_move_checked():
    """K15: G0 de kurs denetiminde: ilk hareket G0 x = 200,001 → CamError (hareket 1)."""
    check_lathe(torna(), [hizli(200.0)], kurulum(), (200.0, 50.0))
    with pytest.raises(CamError) as e:
        check_lathe(torna(), [hizli(200.001)], kurulum(), (200.0, 50.0))
    assert _sira_var(str(e.value), 1)


def test_K15_z_travel_checked():
    """K15: Z_m = z + o_z: o_z = −300'de z = −300 → Z_m = −600 geçer; z = −300,001 → CamError."""

    def derin(z: float) -> Toolpath:
        return lpath(
            [
                Move(G0, (150.0, 0.0, -5.0)),
                Move(G1, (150.0, 0.0, z), feed=0.2),
                Move(G0, (160.0, 0.0, z)),
                Move(G0, (160.0, 0.0, 2.0)),
            ],
            start=(160.0, 0.0, 2.0),
        )

    stock = CylinderStock(D=400.0, zmin=-400.0, zmax=0.0)
    s = Setup(name="ayna", wcs=Wcs("G54", (0.0, 0.0, O_Z)), stock=stock)
    check_lathe(torna(), [derin(-300.0)], s, TC)
    with pytest.raises(CamError):
        check_lathe(torna(), [derin(-300.001)], s, TC)


def test_K15_arc_quadrant_point_caught():
    """K15: uçları kurs içinde, π/2 noktası (x = 200,5 → X_m = 401) dışında kalan G3 → CamError (hareket 2);
    aynı uçlarla ters yönlü G2 bu noktayı süpürmez → geçer."""
    check_lathe(torna(), [yay(G2)], kurulum(), (200.0, 50.0))
    with pytest.raises(CamError) as e:
        check_lathe(torna(), [yay(G3)], kurulum(), (200.0, 50.0))
    assert "kavisop" in str(e.value)
    assert _sira_var(str(e.value), 2)


@pytest.mark.parametrize("tc", [(200.001, 50.0), (150.0, 300.001), (-0.001, 50.0)], ids=["x", "z", "x_eksi"])
def test_K15_tool_change_outside_travel_raises(tc):
    """K15: takım değiştirme noktası aynı dönüşümle kurs dışı → CamError
    (X_m = 400,002; Z_m = 0,001; X_m = −0,002)."""
    with pytest.raises(CamError):
        check_lathe(torna(), [boy(100.0)], kurulum(), tc)


def test_K15_tool_change_on_travel_edge_passes():
    """K15: takım değiştirme noktası tam kurs sınırında (X_m = 400, Z_m = 0) geçer."""
    check_lathe(torna(), [boy(100.0)], kurulum(), (200.0, 300.0))


def test_K15_setup_required_with_travel():
    """K15 / SPEC 30 kuralı: kurslu profilde `setup = None` → CamError; kurssuz profilde gerekmez."""
    with pytest.raises(CamError):
        check_lathe(torna(), [boy(100.0)], None, TC)
    check_lathe(torna(x=None, z=None), [boy(100.0)], None, TC)


def test_K15_css_rpm_limit_rounding_passes():
    """K15: rpm_max = 4000: G96 yolunda rpm = 4000,4 → S = round(4000,4) = 4000 geçer."""
    op = boy(100.0, feed=0.1, rpm=4000.4, css=200.0)
    check_lathe(torna(), [op], kurulum(), TC)


def test_K15_css_rpm_limit_exceeded_raises():
    """K15: S = round(rpm) > rpm_max → CamError, mesajda op adı.

    Not: K15 metnindeki 4000,5 Python `round` ile 4000'e yuvarlanır (çifte yuvarlama); SPEC 30 K8 testindeki
    gibi yuvarlaması tartışmasız 4000,6 (S = 4001) kullanıldı."""
    op = boy(100.0, feed=0.1, rpm=4000.6, css=200.0)
    with pytest.raises(CamError) as e:
        check_lathe(torna(), [op], kurulum(), TC)
    assert "boyop" in str(e.value)


def test_K15_constant_rpm_limits():
    """K15: sabit devirde de S = round(rpm): 4000,6 → CamError; rpm_min = 100'de rpm = 50 → CamError."""
    with pytest.raises(CamError):
        check_lathe(torna(), [boy(100.0, feed=0.1, rpm=4000.6)], kurulum(), TC)
    check_lathe(torna(rpm_min=100.0), [boy(100.0, rpm=100.0)], kurulum(), TC)
    with pytest.raises(CamError):
        check_lathe(torna(rpm_min=100.0), [boy(100.0, rpm=50.0)], kurulum(), TC)


def test_K15_feed_times_S_limit():
    """K15: feed = 0,3 mm/dev, S = 4000: feed·S = 1200 mm/dk; feed_max = 1000 → CamError, 1200 geçer."""
    op = boy(100.0, feed=0.3, rpm=4000.0)
    with pytest.raises(CamError) as e:
        check_lathe(torna(feed_max=1000.0), [op], kurulum(), TC)
    assert "boyop" in str(e.value)
    check_lathe(torna(feed_max=1200.0), [op], kurulum(), TC)


def test_K15_feed_limit_uses_css_rpm_cap():
    """K15: G96 yolunda S = G50 sınırı (round(rpm)); feed·S = 0,3·4000 > 1000 → CamError (güvenli taraf)."""
    op = boy(100.0, feed=0.3, rpm=4000.0, css=200.0)
    with pytest.raises(CamError):
        check_lathe(torna(feed_max=1000.0), [op], kurulum(), TC)
    check_lathe(torna(feed_max=1200.0), [op], kurulum(), TC)


def test_K15_turret_slots():
    """K15: tool_slots = 12: T13 → CamError, T12 geçer; tool_slots = None → T13 geçer."""
    check_lathe(torna(), [boy(100.0, tool=ttool(12))], kurulum(), TC)
    with pytest.raises(CamError):
        check_lathe(torna(), [boy(100.0, tool=ttool(13))], kurulum(), TC)
    check_lathe(torna(tool_slots=None), [boy(100.0, tool=ttool(13))], kurulum(), TC)


@pytest.mark.parametrize(
    "bozuk", [{"plane": Plane.XY}, {"feed_mode": FeedMode.PER_MIN}], ids=["XY", "PER_MIN"]
)
def test_K15_mill_path_on_lathe_profile_raises(bozuk):
    """K15: freze yolu (plane = XY veya feed_mode = PER_MIN) torna profiline → CamError."""
    if "feed_mode" in bozuk:  # torna takımı, ZX düzlemi, ama mm/dk ilerleme
        op = Toolpath(
            name="dkop",
            tool=ttool(),
            start=(150.0, 0.0, 2.0),
            moves=[Move(G0, (100.0, 0.0, 2.0)), Move(G1, (100.0, 0.0, -10.0), feed=200.0)],
            rpm=1000.0,
            plane=Plane.ZX,
            feed_mode=FeedMode.PER_MIN,
        )
    else:
        mill = Tool(id=1, name="F10", kind=ToolKind.FLAT, D=10.0, flute_length=20.0)
        op = Toolpath(
            name="cep",
            tool=mill,
            start=(0.0, 0.0, 5.0),
            moves=[Move(G1, (0.0, 0.0, -1.0), feed=100.0), Move(G1, (10.0, 0.0, -1.0), feed=300.0)],
            rpm=3000.0,
            plane=Plane.XY,
            feed_mode=FeedMode.PER_MIN,
        )
    with pytest.raises(CamError):
        check_lathe(torna(), [op], kurulum(), TC)


def test_K15_mill_profile_rejected():
    """D: check_lathe yalnız `kind = "lathe"` profilde; freze profili → CamError."""
    with pytest.raises(CamError):
        check_lathe(freze(), [boy(100.0)], kurulum(), TC)


def test_K15_dialect_for_lathe_is_fanuc_torna():
    """SPEC 30 Ek A: `dialect_for(torna profili)` → FANUC_TORNA."""
    check_lathe(torna(), [boy(100.0)], kurulum(), TC)  # E2 yoksa "uygulanmamış"
    assert cam.post.dialect_for(torna()) == FANUC_TORNA


def test_K15_post_rejects_lathe_profile():
    """Freze `post()` torna profilinde CamError ("post_lathe kullanın")."""
    check_lathe(torna(), [boy(100.0)], kurulum(), TC)  # E2 yoksa "uygulanmamış"
    with pytest.raises(CamError):
        post([boy(100.0)], torna(), kurulum())


def test_K15_post_lathe_rejects_mill_profile():
    """`post_lathe` freze profilinde CamError."""
    with pytest.raises(CamError):
        post_lathe([boy(100.0)], freze(), kurulum(), "M3", TC)


def test_K15_program_number_range():
    """SPEC 30: program numarası profilin `program_no_range` aralığında; (1, 100)'de 101 → CamError."""
    m = torna(program_no_range=(1, 100))
    check_lathe(m, [boy(100.0)], kurulum(), TC, program_no=100)
    with pytest.raises(CamError):
        check_lathe(m, [boy(100.0)], kurulum(), TC, program_no=101)


def test_K15_no_text_on_violation():
    """SPEC 30: önce bütün denetimler; ihlalde `post_lathe` metin üretmez, CamError fırlatır."""
    with pytest.raises(CamError):
        post_lathe([boy(200.001)], torna(), kurulum(), "M3", (200.0, 50.0))


# ---------------------------------------------------------------- K16: post_lathe = write_lathe + iki yorum


def _iki_op() -> list[Toolpath]:
    """İki takımlı, biri G96 olan, yay içeren uydurma program."""
    a = boy(100.0, feed=0.25, rpm=1200.0, name="kaba")
    b = lpath(
        [
            Move(G0, (90.0, 0.0, 2.0)),
            Move(G1, (90.0, 0.0, -10.0), feed=0.1),
            Move(G2, (100.0, 0.0, -20.0), feed=0.1, center=(100.0, -10.0)),
            Move(G1, (120.0, 0.0, -20.0), feed=0.1),
            Move(G0, (150.0, 0.0, -20.0)),
            Move(G0, (150.0, 0.0, 2.0)),
        ],
        tool=ttool(2),
        rpm=3000.0,
        css=180.0,
        name="ince",
    )
    return [a, b]


def _yorumlu_mu(got: str, beklenen: str, yorumlar: list[str]) -> None:
    g, w = _n_siz(got), _n_siz(beklenen)
    n = len(FANUC_TORNA.header)
    assert g[:n] == w[:n]
    assert g[n : n + len(yorumlar)] == yorumlar
    assert g[n + len(yorumlar) :] == w[n:]


def test_K16_post_lathe_equals_write_lathe_plus_two_comments():
    """K16: doğrulanmamış profilde çıktı = write_lathe çıktısı + FANUC_TORNA başlığından sonra iki yorum
    (`(POST <AD> <DIL>)`, uyarı); satır numaraları yeniden sıralanabileceğinden karşılaştırma N'siz."""
    ops = _iki_op()
    got = post_lathe(ops, torna(), kurulum(), "M3", TC)
    beklenen = write_lathe(ops, "M3", TC, FANUC_TORNA, 1)
    _yorumlu_mu(got, beklenen, [POST_SATIRI, UYARI])


def test_K16_header_lines_exact():
    """K16: başlık `%`, `O0001`, `G21 G18 G40 G99 G54`, ardından iki yorum satırı."""
    got = _n_siz(post_lathe(_iki_op(), torna(), kurulum(), "M4", TC))
    assert got[:5] == ["%", "O0001", "G21 G18 G40 G99 G54", POST_SATIRI, UYARI]


def test_K16_verified_profile_single_comment_and_program_no():
    """K16 / SPEC 30 K13: `verified = True` → yalnız `(POST …)`; program_no başlığa geçer."""
    ops = _iki_op()
    m = torna(verified=True)
    got = post_lathe(ops, m, kurulum(), "M3", TC, program_no=42)
    beklenen = write_lathe(ops, "M3", TC, FANUC_TORNA, 42)
    _yorumlu_mu(got, beklenen, [POST_SATIRI])
    assert UYARI not in got


def test_K16_profile_name_in_comment():
    """K16: yorum satırında profilin adı ve dili (büyük harf)."""
    got = _n_siz(post_lathe(_iki_op(), torna(name="TORNA 2"), kurulum(), "M3", TC))
    assert "(POST TORNA 2 FANUC)" in got


def _delme_yolu() -> Toolpath:
    """Eksenel delme (SPEC 40 A, x = 0) matkap T3, sabit devir."""
    from cam.torna_ek import DrillCut, lathe_drill

    t = Tool(id=3, name="MATKAP", kind=ToolKind.DRILL, D=10.0, flute_length=60.0, tip_angle=118.0)
    return lathe_drill(BAR, t, DrillCut(feed=0.1, rpm=1500.0, peck=6.0), 0.0, -25.0)


def test_K16_axial_drill_program_passes_check():
    """K16: eksenel delme yolu (A) torna yoludur; denetimden geçer."""
    check_lathe(torna(), [*_iki_op(), _delme_yolu()], kurulum(), TC)


def test_K16_axial_drill_turret_and_feed_checked():
    """K16: delme yolu da taret ve feed·S denetiminde: T13 → CamError; 0,1·1500 = 150 > 100 → CamError."""
    d = _delme_yolu()
    d13 = replace(d, tool=replace(d.tool, id=13))
    with pytest.raises(CamError):
        check_lathe(torna(), [d13], kurulum(), TC)
    with pytest.raises(CamError):
        check_lathe(torna(feed_max=100.0), [d], kurulum(), TC)


def _e3_var() -> None:
    """E3 (write_lathe eksenel delme yolunu yazar) birleşmeden test "uygulanmamış" (CI'da kırmızı)."""
    try:
        write_lathe([_delme_yolu()], "M3", TC)
    except (CamError, AttributeError, TypeError, NotImplementedError) as e:
        raise NotImplementedError("SPEC 21 Ek E3 (SPEC 40): write_lathe eksenel delme yolu") from e


def test_K16_axial_drill_post_equals_write_lathe():
    """K16 (E3): delme yolu içeren programda da `post_lathe` = `write_lathe` + iki yorum."""
    _e3_var()
    ops = [*_iki_op(), _delme_yolu()]
    got = post_lathe(ops, torna(), kurulum(), "M3", TC)
    beklenen = write_lathe(ops, "M3", TC, FANUC_TORNA, 1)
    _yorumlu_mu(got, beklenen, [POST_SATIRI, UYARI])
