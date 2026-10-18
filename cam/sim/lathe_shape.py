"""
SPEC 22 — Torna takımının kesiti: kesici bölge K = Q ⊕ D(r), gövde uzantısı, tutucu; süpürme aralıkları.

Dış çerçevede (T = 3 yönü) C'ye göre kenar yönleri e(α) = (−cos α, sin α), (z, x) sırasında;
ana kenar e₁ = e(κr), arka kenar e₂ = e(κr + εr). İç çerçevede şekil x → −x aynalanır.
Eksenel takım (matkap, x = 0): uç konisi L_uç = (D/2)/tan(φ/2) + flute_length boyunda [−D/2, D/2] dikdörtgen.
Doğrusal süpürme: conv(Q(P0) ∪ Q(P1)) ⊕ D(r); z = z_i doğrusuyla kesişim tek aralık [a, b] (x cinsinden).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import LatheTool, Tool


@dataclass
class LatheShape:
    """Burun merkezi C'ye göre (z, x) çokgenler; core ve body r yarıçaplı diskle genişletilir."""

    core: np.ndarray  # (m, 2) kesici çekirdek Q
    r: float  # burun yarıçapı
    body: np.ndarray  # (p, 2) gövde uzantısı Q_B (kesilmiş)
    holder: np.ndarray | None  # (h, 2) tutucu H
    half_width: float  # tutucunun y yönünde yarı kalınlığı


def cutter_shape(tool: LatheTool | Tool, side: str | None) -> LatheShape:
    """LatheTool: side "dis" veya "ic"; edge_len None, uyumsuz tür/taraf, tutucu K'ye giriyor → CamError.

    Eksenel takım (Tool, DRILL/CONE; SPEC 40 E4): uca göre koni + kesici boy beşgeni, r = 0,
    gövde = sap; side yok sayılır.
    """
    raise NotImplementedError


def sweep_interval(poly: np.ndarray, r: float, p0, p1, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """conv(poly + p0, poly + p1) ⊕ D(r)'nin z doğrularıyla kesişimi (a, b); kesişmeyen a = +inf, b = −inf."""
    raise NotImplementedError


def to_radial(a: np.ndarray, b: np.ndarray, half_width: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """x aralığı [a, b] → r aralığı (eksen geçişi; tutucu kalınlığında üst uç √(x² + b²))."""
    raise NotImplementedError
