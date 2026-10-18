"""
SPEC 15 — hızlı bakış: python -m viz DOSYA [--png CIKTI.png] [--view iso|xy|xz|yz]

.step/.stp → Part.from_step, .json → Toolpath.from_dict. Çıkış kodu: 0 başarı, ≠ 0 hata.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m viz", description="Parça (STEP) veya takım yolu (JSON) göster"
    )
    ap.add_argument("dosya", help=".step / .stp parça veya .json takım yolu")
    ap.add_argument("--png", help="ekransız çiz ve bu PNG dosyasına yaz")
    ap.add_argument("--view", default="iso", choices=("iso", "xy", "xz", "yz"), help="bakış yönü")
    return ap


def _sahne(dosya: Path, off_screen: bool):
    """Dosyayı uzantısına göre okur ve sahneyi kurar."""
    from viz import plot

    uzanti = dosya.suffix.lower()
    if uzanti in (".step", ".stp"):
        from geometry.part import Part

        return plot.plot_part(Part.from_step(dosya), off_screen=off_screen)
    if uzanti == ".json":
        from cam.model import Toolpath

        tp = Toolpath.from_dict(json.loads(dosya.read_text(encoding="utf-8")))
        return plot.plot_toolpath(tp, off_screen=off_screen)
    raise ValueError(f"bilinmeyen dosya uzantısı '{dosya.suffix}' (desteklenen: .step, .stp, .json)")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:  # argparse hatası veya --help
        return int(e.code or 0)

    dosya = Path(args.dosya)
    try:
        if dosya.suffix.lower() not in (".step", ".stp", ".json"):
            raise ValueError(f"bilinmeyen dosya uzantısı '{dosya.suffix}' (desteklenen: .step, .stp, .json)")
        if not dosya.is_file():
            raise FileNotFoundError(f"dosya yok: {dosya}")
        p = _sahne(dosya, off_screen=args.png is not None)
    except (OSError, ValueError, KeyError, TypeError) as e:
        # okuma / model hatası (GeometryError, CamError, JSON hatası ValueError'dır): iletiyle çık
        print(f"Hata: {e}", file=sys.stderr)
        return 1

    from viz.plot import screenshot

    try:
        if args.png is not None:
            screenshot(p, args.png, view=args.view)
        else:
            getattr(p, "view_isometric" if args.view == "iso" else f"view_{args.view}")()
            p.show()
    finally:
        p.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
