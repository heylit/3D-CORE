"""
SPEC 15 — pyvista ile çizim. pyvista yalnızca bu dosyada import edilir.

Aktör adları sabittir: parça `part:<ad>`, bileşen `comp:<ad>`, `toolpath:rapid`, `toolpath:feed`, `stock`.
"""

from __future__ import annotations

import numpy as np
import pyvista as pv

RAPID_COLOR = "red"
FEED_COLOR = "blue"


def plot_part(part, *, plotter=None, color="lightsteelblue", tol=0.01, off_screen=False) -> pv.Plotter:
    raise NotImplementedError("SPEC 15: plot_part")


def plot_assembly(assy, parts, *, plotter=None, tol=0.01, off_screen=False) -> pv.Plotter:
    raise NotImplementedError("SPEC 15: plot_assembly")


def plot_toolpath(
    tp,
    *,
    stock=None,
    plotter=None,
    tol=0.01,
    rapid_color=RAPID_COLOR,
    feed_color=FEED_COLOR,
    off_screen=False,
) -> pv.Plotter:
    raise NotImplementedError("SPEC 15: plot_toolpath")


def screenshot(plotter, path=None, *, window_size=(800, 600), view="iso", parallel=False) -> np.ndarray:
    """Kamerayı sahneye oturtur, (h, w, 3) uint8 görüntü döndürür; path verilirse PNG yazar."""
    raise NotImplementedError("SPEC 15: screenshot")
