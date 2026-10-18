"""
SPEC 15 — hızlı bakış: python -m viz DOSYA [--png CIKTI.png] [--view iso|xy|xz|yz]

.step/.stp → Part.from_step, .json → Toolpath.from_dict. Çıkış kodu: 0 başarı, ≠ 0 hata.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("SPEC 15: komut satırı")


if __name__ == "__main__":
    sys.exit(main())
