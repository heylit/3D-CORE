"""SPEC 04b — G82 / G84 yazımı ve okunması: Fanuc, Haas, GRBL (K8–K11) ve tezgâh denetimi (K13).

Testler yalnız SPEC 04b metninden (Örnek A / B altın metinleri, "Paylaşılan dosyalara ekler" 1–8,
K8–K13) yazıldı; `cam/cevrimler.py`, `cam/gcode/` ve `cam/post/` uygulaması okunmadı.
SPEC 30'un `cam/post/` blok ekleri (`Cycle` G82/G84, `RigidTap`, `Dwell`, `Dialect.rigid_tap`) birleşene
dek bu dosyadaki testlerin kırmızı / uygulanmamış kalması beklenir.

Satır numaraları: Fanuc metninde `N` numaraları altın metnin parçasıdır; okuyucu hata mesajlarında
'satır <n>' metindeki 1 tabanlı satır sırasıdır (SPEC 04).
"""

from __future__ import annotations

import pytest

from cam.gcode import FANUC, GRBL
from cam.gcode import read as _read
from cam.gcode import write as _write
from cam.model import CamError
from tests.cam.cevrimler_ortak import (
    G1,
    HOLES3,
    kilavuz,
    ornek_a,
    ornek_b,
    punta,
    spec30_gerekli,
    with_retract,
)

TOL = 0.5e-3 + 1e-9  # mm, SPEC 04 gidiş-dönüş toleransı (3 ondalık)


def write(ops, dialect, **kw) -> str:
    spec30_gerekli()
    return _write(ops, dialect, **kw)


def read(text, tools, dialect):
    spec30_gerekli()
    return _read(text, tools, dialect)


def haas():
    spec30_gerekli()
    from cam.post import HAAS

    return HAAS


def satirlar(text: str) -> list[str]:
    assert text.endswith("\n")
    return text[:-1].split("\n")


# ---------------------------------------------------------------- altın metinler (SPEC 04b)

FANUC_A = """\
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T3 M6
N30 S2000 M3
N40 G0 G43 X0. Y0. Z5. H3
N50 G98 G82 X10. Y10. Z-3. R2. P500 F200.
N60 X30.
N70 G80
N80 M5
N90 M30
%
"""

GRBL_A = """\
G21 G90 G17 G94
T3
S2000 M3
G0 X0. Y0. Z5.
X10. Y10.
Z2.
G1 Z-3. F200.
G4 P0.5
G0 Z5.
X30.
Z2.
G1 Z-3.
G4 P0.5
G0 Z5.
M5
M30
"""

FANUC_B = """\
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T5 M6
N30 S500 M3
N40 G0 G43 X0. Y0. Z5. H5
N50 M29 S500
N60 G98 G84 X10. Y10. Z-15.75 R2. F625.
N70 G80
N80 M5
N90 M30
%
"""

HAAS_B = """\
%
O00001
G21 G90 G17 G94 G40 G49 G80 G54
T5 M06
S500 M3
G0 G43 X0. Y0. Z5. H05
G98 G84 X10. Y10. Z-15.75 R2. F625.
G80
M5
M30
%
"""


# ---------------------------------------------------------------- K8: Fanuc


def test_K8_fanuc_spot_golden():
    """K8: Örnek A Fanuc: `G98 G82 X Y Z R P F`, P tam sayı milisaniye (P500 = 0.5 s)."""
    out = write([ornek_a()], FANUC)
    assert satirlar(out) == satirlar(FANUC_A)
    assert out == FANUC_A


def test_K8_fanuc_tap_golden():
    """K8: Örnek B Fanuc: G84'ten önce `M29 S500` (Karar 2), satır `G98 G84 X Y Z R F` (Q yok)."""
    out = write([ornek_b()], FANUC)
    assert satirlar(out) == satirlar(FANUC_B)
    assert out == FANUC_B


@pytest.mark.parametrize("w, p", [(0.2, "P200"), (1.0, "P1000"), (0.001, "P1")])
def test_K8_fanuc_dwell_milliseconds(w, p):
    """Ek 6: Fanuc `P` tam sayı milisaniye."""
    ls = satirlar(write([ornek_a(dwell=w)], FANUC))
    assert f"N50 G98 G82 X10. Y10. Z-3. R2. {p} F200." in ls


def test_K8_fanuc_g99():
    """G99'da çevrim satırı `G99 G82` / `G99 G84` ile başlar."""
    assert "N50 G99 G82 X10. Y10. Z-3. R2. P500 F200." in satirlar(write([ornek_a("G99")], FANUC))
    assert "N60 G99 G84 X10. Y10. Z-15.75 R2. F625." in satirlar(write([ornek_b("G99")], FANUC))


def test_K8_fanuc_m29_before_each_g84():
    """Karar 2: her G84'ten önce `M29 S<rpm>`: iki kılavuz op'u → her G84'ün önünde (öncekinden sonra) M29."""
    b2 = ornek_b(holes=[(40.0, 10.0)])
    b2.name = "kilavuz-2"
    ls = [ln.split(" ", 1)[1] for ln in satirlar(write([ornek_b(), b2], FANUC)) if ln.startswith("N")]
    i84 = [i for i, ln in enumerate(ls) if " G84 " in f" {ln} "]
    assert len(i84) == 2
    onceki = -1
    for i in i84:
        assert "M29 S500" in ls[onceki + 1 : i], ls
        onceki = i


# ---------------------------------------------------------------- K9: Haas


def test_K9_haas_tap_golden():
    """K9: Örnek B Haas: `M29` yok, `T5 M06`, `H05`, satır numarası yok."""
    out = write([ornek_b()], haas())
    assert satirlar(out) == satirlar(HAAS_B)
    assert "M29" not in out


def test_K9_haas_spot_decimal_seconds():
    """K9: Örnek A Haas: `P` ondalıklı saniye (P0.5)."""
    ls = satirlar(write([ornek_a()], haas()))
    assert "G98 G82 X10. Y10. Z-3. R2. P0.5 F200." in ls
    assert "T3 M06" in ls
    i = ls.index("G98 G82 X10. Y10. Z-3. R2. P0.5 F200.")
    assert ls[i + 1 : i + 3] == ["X30.", "G80"]


# ---------------------------------------------------------------- K10: GRBL


def test_K10_grbl_spot_expanded_golden():
    """K10: Örnek A GRBL: açılmış G0/G1 + `G4 P0.5` (saniye), çevrim kelimesi yok."""
    out = write([ornek_a()], GRBL)
    assert satirlar(out) == satirlar(GRBL_A)
    assert out == GRBL_A
    words = set(out.split())
    assert not words & {"G80", "G82", "G84", "G98", "G99", "M29"}


@pytest.mark.parametrize("w, p", [(0.2, "G4 P0.2"), (1.25, "G4 P1.25")])
def test_K10_grbl_dwell_format(w, p):
    """Ek 3: GRBL `G4 P<s>`, s saniye, 3 ondalık biçimi."""
    ls = satirlar(write([ornek_a(dwell=w)], GRBL))
    assert ls.count(p) == 2


@pytest.mark.parametrize(
    "ops",
    [
        pytest.param(lambda: [ornek_b()], id="yalniz-kilavuz"),
        pytest.param(lambda: [ornek_a(), ornek_b()], id="punta-sonra-kilavuz"),
    ],
)
def test_K10_grbl_tap_raises_without_text(ops):
    """K10: GRBL'de eşzamanlı iş mili yok: TapOp içeren liste → CamError, hiç metin dönmüyor."""
    out = None
    with pytest.raises(CamError):
        out = write(ops(), GRBL)
    assert out is None


# ---------------------------------------------------------------- K11: gidiş-dönüş


def _dialects():
    return [pytest.param(lambda: FANUC, id="Fanuc"), pytest.param(haas, id="Haas")]


def assert_same(got, exp) -> None:
    """Hareket tipleri aynı, uçlar ≤ 0.5e-3 mm, G1'lerde F tam."""
    assert [m.type for m in got.moves] == [m.type for m in exp.moves]
    for i, (g, e) in enumerate(zip(got.moves, exp.moves, strict=True)):
        assert max(abs(a - b) for a, b in zip(g.end, e.end, strict=True)) <= TOL, (i, g.end, e.end)
        if e.type is G1:
            assert g.feed == e.feed, (i, g.feed, e.feed)
    assert max(abs(a - b) for a, b in zip(got.start, exp.start, strict=True)) <= TOL


OPS = [
    pytest.param(lambda: ornek_a(), id="A"),
    pytest.param(lambda: ornek_b(), id="B"),
    pytest.param(lambda: ornek_a("G99", holes=HOLES3), id="A-3-G99"),
    pytest.param(lambda: ornek_b("G99", holes=HOLES3), id="B-3-G99"),
    pytest.param(lambda: ornek_a("G98", holes=HOLES3), id="A-3-G98"),
    pytest.param(lambda: ornek_b("G98", holes=HOLES3), id="B-3-G98"),
]


@pytest.mark.parametrize("make", OPS)
@pytest.mark.parametrize("dialect", _dialects())
def test_K11_roundtrip(dialect, make):
    """K11: yazılıp okununca yol `to_toolpath()` ile aynı (G99'da program sonu geri çekme dahil, 04 Ek B)."""
    op = make()
    d = dialect()
    (got,) = read(write([op], d), {op.tool.id: op.tool}, d)
    got.validate()
    assert got.rpm == op.rpm
    assert got.tool == op.tool
    assert_same(got, with_retract(op.to_toolpath(d), op.start[2]))


def test_K11_roundtrip_spot_then_tap():
    """İki takımlı program (punta T3, kılavuz T5) Fanuc'ta iki yol olarak okunur."""
    a, b = ornek_a(), ornek_b()
    got = read(write([a, b], FANUC), {3: a.tool, 5: b.tool}, FANUC)
    assert [g.tool.id for g in got] == [3, 5]
    assert [g.rpm for g in got] == [2000.0, 500.0]
    assert [m.feed for m in got[1].moves if m.type is G1] == [625.0, 625.0]


def test_K11_reader_m29_missing_fanuc():
    """K11 / Ek 7: Fanuc'ta G84'ten önce aynı S ile M29 yoksa → CamError, 'satır 7' (G84 satırı)."""
    text = FANUC_B.replace("N50 M29 S500\n", "")
    with pytest.raises(CamError, match=r"satır 7\b"):
        read(text, {5: kilavuz()}, FANUC)


def test_K11_reader_g84_without_spindle():
    """K11 / Ek 7: iş mili dönmüyorken (M3 yok) G84 → CamError, satır 7 (Haas metninde G84 satırı)."""
    text = HAAS_B.replace("S500 M3\n", "S500\n")
    with pytest.raises(CamError, match=r"satır 7\b"):
        read(text, {5: kilavuz()}, haas())


def test_K11_reader_g84_with_m4():
    """Ek 7: G84 M4 (ters iş mili) ile → CamError."""
    text = HAAS_B.replace("S500 M3\n", "S500 M4\n")
    with pytest.raises(CamError):
        read(text, {5: kilavuz()}, haas())


@pytest.mark.parametrize("dialect", _dialects())
def test_K11_reader_g84_peck_q(dialect):
    """K11 / Ek 7: `G84 ... Q` (gagalı kılavuz) kapsam dışı → CamError, mesajda G84 satırı."""
    d = dialect()
    if d is FANUC:
        text = FANUC_B.replace("R2. F625.", "R2. Q3. F625.")
        n = 8
    else:
        text = HAAS_B.replace("R2. F625.", "R2. Q3. F625.")
        n = 7
    with pytest.raises(CamError, match=rf"satır {n}\b"):
        read(text, {5: kilavuz()}, d)


def test_K11_reader_g82_requires_p():
    """Ek 7: `G82` satırında P zorunlu: P'siz → CamError, satır 7."""
    text = FANUC_A.replace(" P500", "")
    with pytest.raises(CamError, match=r"satır 7\b"):
        read(text, {3: punta()}, FANUC)


def test_K11_reader_g4_dwell_grbl():
    """Ek 7: `G4 P` okunur ve yola yansımaz: GRBL Örnek A → `to_toolpath()`."""
    op = ornek_a()
    (got,) = read(GRBL_A, {3: op.tool}, GRBL)
    assert_same(got, op.to_toolpath(GRBL))


# ---------------------------------------------------------------- K13: tezgâh denetimi


def _profil(feed_max: float):
    from cam.model import MachineProfile

    return MachineProfile(
        name="TEST-600",
        controller="fanuc",
        rpm_min=0.0,
        rpm_max=10_000.0,
        feed_max=feed_max,
        program_no_range=(1, 9999),
    )


def test_K13_tap_feed_over_machine_limit():
    """K13 / Ek 8: kılavuz F de feed_max'e tabi: feed_max = 600, Örnek B (F = 625) → post() CamError."""
    op = ornek_b()
    spec30_gerekli()
    from cam.post import post

    with pytest.raises(CamError):
        post([op], _profil(600.0))


def test_K13_tap_feed_at_limit_passes():
    """Sınır: feed_max = 625 → geçer ve kılavuz satırı yazılır."""
    op = ornek_b()
    spec30_gerekli()
    from cam.post import post

    out = post([op], _profil(625.0))
    assert any("G84" in ln and "F625." in ln for ln in satirlar(out))


def test_K13_spot_feed_over_machine_limit():
    """Ek 8: açılım DrillOp gibi denetlenir: Örnek A F200 > feed_max 150 → CamError."""
    op = ornek_a()
    spec30_gerekli()
    from cam.post import post

    with pytest.raises(CamError):
        post([op], _profil(150.0))
