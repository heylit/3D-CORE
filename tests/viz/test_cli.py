"""
SPEC 15 — komut satırı (K15): python -m viz DOSYA [--png CIKTI.png] [--view ...].

Testler viz.__main__.main(argv) -> çıkış kodu fonksiyonunu süreç içinde çağırır
(`python -m viz` → sys.exit(main())). viz/ kodu okunmadan yazıldı.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("pyvista")

from cam.model import Move, MoveType, Tool, ToolKind, Toolpath  # noqa: E402
from viz.__main__ import main  # noqa: E402

PNG_IMZA = b"\x89PNG\r\n\x1a\n"


def yol_json(tmp_path):
    tp = Toolpath(
        name="cli",
        tool=Tool(id=1, name="T1", kind=ToolKind.FLAT, D=6.0, flute_length=20.0),
        start=(0, 0, 10),
        rpm=8000.0,
        moves=[
            Move(MoveType.RAPID, (10, 0, 2)),
            Move(MoveType.LINEAR, (10, 0, -1), feed=500.0),
            Move(MoveType.ARC_CCW, (-10, 0, -1), feed=500.0, center=(0.0, 0.0)),
        ],
    )
    p = tmp_path / "yol.json"
    p.write_text(json.dumps(tp.to_dict()), encoding="utf-8")
    return p


def test_k15_takim_yolu_json_png(tmp_path):
    cikti = tmp_path / "yol.png"
    assert main([str(yol_json(tmp_path)), "--png", str(cikti), "--view", "xy"]) == 0
    assert cikti.is_file()
    assert cikti.read_bytes()[:8] == PNG_IMZA


@pytest.mark.occt
def test_k15_step_png(tmp_path):
    bd = pytest.importorskip("build123d")
    from geometry.part import Part

    step = tmp_path / "blok.step"
    Part(bd.Box(30, 20, 10), name="blok").to_step(step)
    cikti = tmp_path / "blok.png"
    assert main([str(step), "--png", str(cikti)]) == 0
    assert cikti.read_bytes()[:8] == PNG_IMZA


def test_k15_bilinmeyen_uzanti(tmp_path):
    f = tmp_path / "parca.xyz"
    f.write_text("deneme", encoding="utf-8")
    assert main([str(f), "--png", str(tmp_path / "x.png")]) != 0
    assert not (tmp_path / "x.png").exists()


def test_k15_olmayan_dosya(tmp_path):
    assert main([str(tmp_path / "yok.step"), "--png", str(tmp_path / "x.png")]) != 0
    assert not (tmp_path / "x.png").exists()
