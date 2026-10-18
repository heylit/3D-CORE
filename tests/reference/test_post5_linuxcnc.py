"""SPEC 51 K7 — LinuxCNC `rs274` çapraz kontrolü (yalnız TCP kapalı çıkış).

Testler yalnız SPEC 51 metninden, iskelet imzalarından ve main'deki SPEC 42 işlevlerinden yazıldı.
`rs274` (LinuxCNC'nin bağımsız yorumlayıcısı) programı yorumlar; kanonik `STRAIGHT_FEED` eksen değerleri
bizim eklem değerlerimizle (42 `linearize` → `joint_path`) yazılan ondalık toleransında, G93 kipindeki
`SET_FEED_RATE` değerleri programa yazılan F değerleriyle aynen aynı olmalı (yazılan F'nin 42 `inverse_time`
ile karşılaştırması K6'da). İş sıfırı makine sıfırında (`Wcs()`): rs274'ün
sıfır ofsetleriyle program koordinatı = makine koordinatı. `rs274` PATH'te yoksa test atlanır.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import numpy as np
import pytest

from cam.model import Move, Setup, Stock, Toolpath, Wcs
from cam.multiaxis.linearize import joint_path, linearize
from cam.post import post5
from tests.cam.post5_ortak import (
    G1,
    L_TAKIM,
    RPM,
    TAKIM,
    TAKIMLAR,
    a_masa,
    ac_masa,
    makine,
    meta,
    yay_yolu,
    yon,
)
from tests.cam.test_post5_g93 import g93_tara

RS274 = shutil.which("rs274")
pytestmark = pytest.mark.skipif(
    RS274 is None, reason="LinuxCNC rs274 kurulu değil (CI kapsayıcısında çalışır; yerelde atlanır)"
)

_CANON = re.compile(r"(STRAIGHT_TRAVERSE|STRAIGHT_FEED|SET_FEED_RATE|SET_FEED_MODE)\(([^)]*)\)")
EKSEN_SIRASI = "ABC"  # rs274 STRAIGHT_FEED(x, y, z, a, b, c[, u, v, w])
TOL_L = 0.5e-3 + 1e-9  # mm, 3 ondalık
TOL_ACI = 0.5e-3 + 1e-9  # derece, 3 ondalık
KURULUM0 = Setup("bag", Wcs("G54", (0.0, 0.0, 0.0)), Stock(-80.0, -80.0, -60.0, 80.0, 80.0, 60.0))


def rs274_besleme(text: str, tmp_path) -> list[tuple[np.ndarray, float | None, int]]:
    """Programı rs274 ile yürütür: [(x, y, z, a, b, c), o anki F, besleme kipi] her STRAIGHT_FEED için."""
    src = tmp_path / "prog.ngc"
    govde = [s for s in text.splitlines() if s.strip() != "%" and not re.match(r"^(N\d+\s*)?O\d", s)]
    src.write_text("%\n" + "\n".join(govde) + "\n%\n")
    tbl = tmp_path / "tool.tbl"
    tbl.write_text("".join(f"T{i} P{i} D6 Z0 ;\n" for i in range(1, 10)))
    out = subprocess.run(
        [RS274, "-t", str(tbl), str(src)],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    sonuc = []
    feed, kip = None, 0
    for ad, args in _CANON.findall(out.stdout):
        v = [float(a) for a in args.split(",") if a.strip()]
        if ad == "SET_FEED_RATE":
            feed = v[0]
        elif ad == "SET_FEED_MODE":
            kip = int(v[-1])
        elif ad == "STRAIGHT_FEED":
            sonuc.append((np.array(v[:6]), feed, kip))
    if not sonuc:
        pytest.fail(f"rs274 besleme hareketi üretmedi:\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}")
    return sonuc


def rastgele_ac_yolu(seed: int = 7, n: int = 10) -> Toolpath:
    """AC masa-masada sabit tohumlu yol: küçük adımlar, eğim 20°–40°, kutuptan uzak."""
    rng = np.random.default_rng(seed)
    p = np.array([0.0, 0.0, 5.0])
    tilt, az = 30.0, 20.0
    moves = []
    for _ in range(n):
        p = p + rng.uniform(-6.0, 6.0, size=3)
        tilt = float(np.clip(tilt + rng.uniform(-5.0, 5.0), 20.0, 40.0))
        az += rng.uniform(-8.0, 8.0)
        moves.append(Move(G1, tuple(p), feed=700.0, axis=tuple(yon(tilt, az))))
    a0 = np.array(moves[0].axis)
    start = tuple(np.array([0.0, 0.0, 5.0]) + 10.0 * a0)
    moves.insert(0, Move(G1, (0.0, 0.0, 5.0), feed=300.0, axis=tuple(a0)))
    return Toolpath(name="RASTGELE", tool=TAKIM, start=start, moves=moves, rpm=RPM, meta=meta("5"))


DURUMLAR = {"k6_a_masa": (a_masa, yay_yolu), "ac_masa_rastgele": (ac_masa, rastgele_ac_yolu)}


@pytest.mark.parametrize("ad", list(DURUMLAR))
def test_k7_rs274_eklem_degerleri_ve_g93(ad, tmp_path):
    kin_f, yol_f = DURUMLAR[ad]
    kin, tp = kin_f(), yol_f()
    m = makine("fanuc", kin, tcp="yok")
    metin = post5([tp], m, KURULUM0, TAKIMLAR)

    lin = linearize(tp, kin, KURULUM0.wcs, L_TAKIM, tol_p=1e-3, tol_a=0.05)
    Q = joint_path(lin, kin, KURULUM0.wcs, L_TAKIM)
    sutun = [EKSEN_SIRASI.index(e.name) for e in kin.rotary]

    yazilan, _ = g93_tara(metin)
    assert len(yazilan) == len(lin.moves)

    besleme = rs274_besleme(metin, tmp_path)
    g93 = [(q, f) for q, f, kip in besleme if kip == 1]  # SET_FEED_MODE(1) = ters zaman
    assert len(g93) == len(lin.moves)
    for i, ((q, f), qb, (_, tok)) in enumerate(zip(g93, Q[1:], yazilan, strict=True)):
        np.testing.assert_allclose(q[:3], qb[:3], atol=TOL_L, err_msg=f"hareket {i} XYZ")
        np.testing.assert_allclose(q[3:][sutun], qb[3:], atol=TOL_ACI, err_msg=f"hareket {i} döner")
        assert tok is not None and f is not None
        assert f == pytest.approx(float(tok), rel=1e-12), f"hareket {i}: rs274 F {f} ≠ yazılan F{tok}"
