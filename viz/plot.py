"""
SPEC 15 — pyvista ile çizim. pyvista yalnızca bu dosyada import edilir.

Aktör adları sabittir: parça `part:<ad>`, bileşen `comp:<ad>`, `toolpath:rapid`, `toolpath:feed`, `stock`.
"""

from __future__ import annotations

import numpy as np
import pyvista as pv

from viz.scene import VizError, assembly_meshes, split_rapid_feed, stock_box, toolpath_polyline

RAPID_COLOR = "red"
FEED_COLOR = "blue"
VIEWS = ("iso", "xy", "xz", "yz")


def _plotter(plotter, off_screen: bool) -> pv.Plotter:
    """Verilen sahneyi kullanır, yoksa beyaz arka planlı yeni bir sahne kurar."""
    if plotter is None:
        plotter = pv.Plotter(off_screen=off_screen)
        plotter.set_background("white")
    return plotter


def _tri_mesh(V: np.ndarray, T: np.ndarray) -> pv.PolyData:
    """Üçgen ağı → PolyData (yüz dizisi: [3, i, j, k, 3, ...])."""
    faces = np.column_stack([np.full(len(T), 3), T]).ravel()
    return pv.PolyData(np.asarray(V, dtype=float), faces)


def _polylines(cizgiler: list[np.ndarray]) -> pv.PolyData:
    """Birden çok çoklu çizgi → tek PolyData (çizgi dizisi: [m, i0, ..., i(m-1), ...])."""
    P = np.vstack(cizgiler)
    lines, bas = [], 0
    for c in cizgiler:
        lines.extend([len(c), *range(bas, bas + len(c))])
        bas += len(c)
    return pv.PolyData(P, lines=np.array(lines))


def plot_part(part, *, plotter=None, color="lightsteelblue", tol=0.01, off_screen=False) -> pv.Plotter:
    """Parçanın üçgen ağını `part:<ad>` aktörü olarak ekler."""
    p = _plotter(plotter, off_screen)
    V, T = part.mesh(tol)
    p.add_mesh(_tri_mesh(V, T), color=color, name=f"part:{part.name}")
    return p


def plot_assembly(assy, parts, *, plotter=None, tol=0.01, off_screen=False) -> pv.Plotter:
    """Her bileşeni dünya koordinatında, PALETTE rengiyle `comp:<ad>` aktörü olarak ekler."""
    meshes = assembly_meshes(assy, parts, tol)
    p = _plotter(plotter, off_screen)
    for m in meshes:
        p.add_mesh(_tri_mesh(m.V, m.T), color=m.color, name=f"comp:{m.name}")
    return p


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
    """Hızlı ve kesme hareketlerini ayrı renkte çizgiler, ham malzemeyi tel kafes olarak ekler.

    Çizgiler aydınlatmasız çizilir: renk ekranda tam olarak rapid_color / feed_color görünür.
    """
    P, kinds = toolpath_polyline(tp, tol)
    hizli, kesme = split_rapid_feed(P, kinds)
    p = _plotter(plotter, off_screen)
    for cizgiler, renk, ad, kalinlik in (
        (hizli, rapid_color, "toolpath:rapid", 1.5),
        (kesme, feed_color, "toolpath:feed", 2.5),
    ):
        if cizgiler:
            p.add_mesh(_polylines(cizgiler), color=renk, line_width=kalinlik, lighting=False, name=ad)
    if stock is not None:
        C, E = stock_box(stock)
        kutu = pv.PolyData(C, lines=np.column_stack([np.full(len(E), 2), E]).ravel())
        p.add_mesh(kutu, color="dimgray", line_width=1.0, lighting=False, name="stock")
    return p


def screenshot(plotter, path=None, *, window_size=(800, 600), view="iso", parallel=False) -> np.ndarray:
    """Kamerayı sahneye oturtur, (h, w, 3) uint8 görüntü döndürür; path verilirse PNG yazar."""
    if view not in VIEWS:
        raise VizError(f"Geçersiz görünüm '{view}' (geçerli: {', '.join(VIEWS)})")
    if not plotter.actors:
        raise VizError("Boş sahne: ekran görüntüsü alınacak aktör yok")
    plotter.window_size = list(window_size)
    getattr(plotter, f"view_{view}" if view != "iso" else "view_isometric")()
    if parallel:
        plotter.enable_parallel_projection()
    else:
        plotter.disable_parallel_projection()
    plotter.reset_camera()
    img = plotter.screenshot(None if path is None else str(path), return_img=True)
    return np.ascontiguousarray(np.asarray(img)[..., :3], dtype=np.uint8)
