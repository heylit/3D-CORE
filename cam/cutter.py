"""
SPEC 06b — Dönel simetrik takımın dışbükey profili f(ρ).

f(ρ): eksenden ρ uzaklıkta takım alt yüzeyinin uca göre yüksekliği, ρ ∈ [0, R]; f(0) = 0,
azalmayan ve dışbükey; ρ > R için +∞ (üstünde dik silindir). Profil meridyen düzleminde doğru ve
çember yaylarından oluşur. Düz, küresel, torik ve konik takımlar ile bunların δ ofsetleri (işleme payı).

Destek (Legendre) fonksiyonu: f*(m) = max_{ρ ∈ [0, R]} (m·ρ − f(ρ)), en büyüğü veren ρ*(m).

Parça gösterimi (ρ aralığı [ρ0, ρ1]):
    ("dogru", ρ0, ρ1, z0, k)      z = z0 + k(ρ − ρ0)
    ("yay", ρ0, ρ1, ρc, zc, a)     z = zc − √(a² − (ρ − ρc)²)   (çemberin alt yarısı)

Birimler: mm, açı derece.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError, Tool, ToolKind

_ESIT = 1e-13  # destek fonksiyonunda eşit sayılan değer farkı (en küçük ρ* seçilir)


def _sayi(nerede: str, **degerler: float) -> None:
    for ad, v in degerler.items():
        if not math.isfinite(v):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


def _sin_egim(p: tuple, rho: float) -> float:
    """Parçanın ρ'daki eğim açısının sinüsü (aşağı-dışa bakan normalin ρ bileşeni)."""
    if p[0] == "dogru":
        k = p[4]
        return k / math.hypot(1.0, k)
    return (rho - p[3]) / p[5]


def _deger(p: tuple, rho: np.ndarray) -> np.ndarray:
    if p[0] == "dogru":
        _, r0, _, z0, k = p
        return z0 + k * (rho - r0)
    _, _, _, rc, zc, a = p
    return zc - np.sqrt(np.maximum(a * a - (rho - rc) ** 2, 0.0))


@dataclass(frozen=True)
class Cutter:
    """Dışbükey takım profili; dış yarıçap R [mm], parçalar doğru ve yay (ρ artan sırada)."""

    R: float
    parcalar: tuple = ()

    def __post_init__(self) -> None:
        _sayi("Cutter", R=self.R)
        if self.R <= 0:
            raise CamError(f"Cutter: R pozitif olmalı (R={self.R})")
        if not self.parcalar:
            raise CamError("Cutter: profil parçası yok")
        if abs(self.parcalar[0][1]) > 1e-12 or abs(self.parcalar[-1][2] - self.R) > 1e-9 * max(1.0, self.R):
            raise CamError("Cutter: parçalar [0, R] aralığını kaplamalı")

    # ------------------------------------------------------------ kurucular

    @classmethod
    def flat(cls, R: float) -> Cutter:
        _sayi("Cutter.flat", R=R)
        if R <= 0:
            raise CamError(f"Cutter.flat: R pozitif olmalı (R={R})")
        return cls(R, (("dogru", 0.0, R, 0.0, 0.0),))

    @classmethod
    def ball(cls, R: float) -> Cutter:
        _sayi("Cutter.ball", R=R)
        if R <= 0:
            raise CamError(f"Cutter.ball: R pozitif olmalı (R={R})")
        return cls(R, (("yay", 0.0, R, 0.0, R, R),))

    @classmethod
    def torus(cls, R: float, r_c: float) -> Cutter:
        """Köşe radyüslü düz uç: ρ ≤ R_t düz taban, sonra r_c yarıçaplı tüp yayı (R_t = R − r_c)."""
        _sayi("Cutter.torus", R=R, r_c=r_c)
        if R <= 0:
            raise CamError(f"Cutter.torus: R pozitif olmalı (R={R})")
        if not 0 <= r_c <= R:
            raise CamError(f"Cutter.torus: 0 ≤ r_c ≤ R olmalı (r_c={r_c}, R={R})")
        Rt = R - r_c
        p = []
        if Rt > 0:
            p.append(("dogru", 0.0, Rt, 0.0, 0.0))
        if r_c > 0:
            p.append(("yay", Rt, R, Rt, r_c, r_c))
        return cls(R, tuple(p))

    @classmethod
    def cone(cls, R: float, theta: float) -> Cutter:
        """theta: yarı açı [derece], 0 < theta < 90; f = ρ·cot θ."""
        _sayi("Cutter.cone", R=R, theta=theta)
        if R <= 0:
            raise CamError(f"Cutter.cone: R pozitif olmalı (R={R})")
        if not 0 < theta < 90:
            raise CamError(f"Cutter.cone: yarı açı 0..90 derece arasında olmalı (theta={theta})")
        return cls(R, (("dogru", 0.0, R, 0.0, 1 / math.tan(math.radians(theta))),))

    @classmethod
    def from_tool(cls, tool: Tool) -> Cutter:
        """BALL → küresel, FLAT → torik (corner_r = 0 düz), CONE → konik; DRILL → CamError."""
        R = tool.D / 2
        if tool.kind is ToolKind.BALL:
            return cls.ball(R)
        if tool.kind is ToolKind.FLAT:
            return cls.flat(R) if tool.corner_r == 0 else cls.torus(R, tool.corner_r)
        if tool.kind is ToolKind.CONE:
            return cls.cone(R, tool.tip_angle / 2)
        raise CamError(f"Cutter: '{tool.name}' ({tool.kind.value}) için profil yok")

    # ------------------------------------------------------------ sorgular

    @property
    def tur(self) -> str | None:
        """'duz' veya 'kure' (SPEC 06 kapalı formları kullanılır); diğer profillerde None."""
        if len(self.parcalar) == 1:
            p = self.parcalar[0]
            if p[0] == "dogru" and p[3] == 0.0 and p[4] == 0.0:
                return "duz"
            if p[0] == "yay" and p[3] == 0.0 and p[4] == self.R and p[5] == self.R:
                return "kure"
        return None

    @property
    def height(self) -> float:
        """f(R) [mm]."""
        return float(_deger(self.parcalar[-1], np.array([self.R]))[0])

    def f(self, rho: np.ndarray) -> np.ndarray:
        """Profil yüksekliği; rho > R → inf, rho < 0 → CamError."""
        rho = np.asarray(rho, dtype=float)
        if np.any(np.isnan(rho)) or np.any(rho < 0):
            raise CamError("Cutter.f: ρ ≥ 0 olmalı")
        z = self.f_ic(np.minimum(rho, self.R))
        return np.where(rho > self.R, np.inf, z)

    def f_ic(self, rho: np.ndarray) -> np.ndarray:
        """f, denetimsiz; ρ ∈ [0, R] varsayılır (iç hesaplar için)."""
        rho = np.asarray(rho, dtype=float)
        z = np.zeros_like(rho)
        for p in self.parcalar:
            ok = rho >= p[1]
            z = np.where(ok, _deger(p, rho), z)
        return z

    def f_ters(self, h: np.ndarray) -> np.ndarray:
        """sup{ρ ∈ [0, R] : f(ρ) < h}; h ≤ 0 → 0, h > f(R) → R."""
        h = np.asarray(h, dtype=float)
        rho = np.zeros_like(h)
        for p in self.parcalar:
            r0, r1 = p[1], p[2]
            bas, son = (float(v) for v in _deger(p, np.array([r0, r1])))
            if p[0] == "dogru":
                _, _, _, z0, k = p
                r = np.full_like(h, r1) if k == 0 else np.clip(r0 + (h - z0) / k, r0, r1)
            else:
                _, _, _, rc, zc, a = p
                r = np.clip(rc + np.sqrt(np.maximum(a * a - np.clip(zc - h, 0.0, a) ** 2, 0.0)), r0, r1)
            r = np.where(h > son, r1, r)
            rho = np.where(h > bas, np.maximum(rho, r), rho)
        return rho

    def support(self, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(f*(m), ρ*(m)); en büyüğü veren en küçük ρ. m < 0 → CamError."""
        m = np.asarray(m, dtype=float)
        if np.any(np.isnan(m)) or np.any(m < 0):
            raise CamError("Cutter.support: eğim m ≥ 0 olmalı")
        best = np.full(m.shape, -np.inf)
        arg = np.zeros(m.shape)
        for p in self.parcalar:
            if p[0] == "dogru":
                r = np.where(m > p[4], p[2], p[1])
            else:
                _, r0, r1, rc, _, a = p
                r = np.clip(rc + a * m / np.sqrt(1 + m * m), r0, r1)
            v = m * r - _deger(p, r)
            yeni = v > best + _ESIT
            best = np.where(yeni, v, best)
            arg = np.where(yeni, r, arg)
        return best, arg

    def offset(self, delta: float) -> Cutter:
        """δ küreyle Minkowski toplamının alt yüzeyi, ucu 0'a kaydırılmış; delta ≥ 0.

        Her doğru normali boyunca δ kayar, her yayın yarıçapı δ büyür; kırık noktalarda (eksen, parça
        birleşimleri, dik silindire geçiş) δ yarıçaplı yay eklenir.
        """
        _sayi("Cutter.offset", delta=delta)
        if delta < 0:
            raise CamError(f"Cutter.offset: delta negatif olamaz ({delta})")
        if delta == 0:
            return self
        yeni: list[tuple] = []

        def kose(rho: float, z: float, s1: float, s2: float) -> None:
            if s2 > s1 + 1e-15:
                yeni.append(("yay", rho + delta * s1, rho + delta * s2, rho, z, delta))

        # eksen: simetriden gelen eğim 0
        p0 = self.parcalar[0]
        kose(0.0, 0.0, 0.0, _sin_egim(p0, p0[1]))
        for i, p in enumerate(self.parcalar):
            if p[0] == "dogru":
                _, r0, r1, z0, k = p
                s, c = k / math.hypot(1.0, k), 1 / math.hypot(1.0, k)
                yeni.append(("dogru", r0 + delta * s, r1 + delta * s, z0 - delta * c, k))
            else:
                _, r0, r1, rc, zc, a = p
                g = (a + delta) / a
                yeni.append(("yay", rc + (r0 - rc) * g, rc + (r1 - rc) * g, rc, zc, a + delta))
            s_son = _sin_egim(p, p[2])
            s_sonraki = 1.0 if i + 1 == len(self.parcalar) else _sin_egim(self.parcalar[i + 1], p[2])
            kose(p[2], float(_deger(p, np.array([p[2]]))[0]), s_son, s_sonraki)
        kaydir = []
        for p in yeni:
            if p[0] == "dogru":
                kaydir.append((p[0], p[1], p[2], p[3] + delta, p[4]))
            else:
                kaydir.append((p[0], p[1], p[2], p[3], p[4] + delta, p[5]))
        kaydir[0] = (kaydir[0][0], 0.0, *kaydir[0][2:])
        son = kaydir[-1]
        kaydir[-1] = (son[0], son[1], self.R + delta, *son[3:])
        return Cutter(self.R + delta, tuple(kaydir))
