"""
SPEC 08 — Montaj konum çözücü: Gauss–Newton, en küçük normlu adım; rank ile serbestlik sayımı.

    δx = −J⁺ r   (np.linalg.lstsq),   x ← x + α δx   (geri izleme)
    DOF = 6·n_serbest − rank(J)
Ölçekli artıklar: yön satırları (birimsiz) karakteristik uzunluk L ile çarpılır, böylece hem
adım hem durma ölçütü (max|r| ≤ tol) mm cinsindendir. L = referans noktalarının başlangıçtaki
dünya çapı, en az 1 mm: L boyundaki parçada ε rad'lık yön hatası uçta ≈ ε·L mm kayma demektir.
Kaynak: Nocedal–Wright, Numerical Optimization, Bölüm 10.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from assy.mates import angular_rows, jacobian, residual, rodrigues
from assy.model import Assembly, AssyError, Component

# Geri izlemede en küçük adım katsayısı: α = 2⁻¹⁰
_MIN_HALVINGS = 10
# Sayısal rank eşiği: σ_i > 1e-8 · σ_max
_RANK_RTOL = 1e-8


@dataclass
class SolveResult:
    T: dict[str, np.ndarray]
    iterations: int
    residual: float  # son ölçekli max|r| (mm; yön satırları L ile çarpılmış)
    dof: int

    def apply(self, assembly: Assembly) -> None:
        """Çözülmüş T'leri montajın bileşenlerine yazar."""
        for name, T in self.T.items():
            assembly.component(name).T = np.array(T, dtype=float)


def residuals(assembly: Assembly) -> np.ndarray:
    """Tüm kısıtların artıkları ard arda."""
    if not assembly.mates:
        return np.zeros(0)
    return np.concatenate([residual(assembly, m) for m in assembly.mates])


def _unknowns(assembly: Assembly) -> list[str]:
    """Sabit olmayan bileşenlerin adları (montajdaki sırayla)."""
    return [c.name for c in assembly.components if not c.fixed]


def _jacobian(assembly: Assembly, unknowns: list[str]) -> np.ndarray:
    """Tüm kısıtların Jacobian'ı alt alta: (Σm, 6·n_serbest)."""
    if not assembly.mates:
        return np.zeros((0, 6 * len(unknowns)))
    return np.vstack([jacobian(assembly, m, unknowns) for m in assembly.mates])


def _scale(assembly: Assembly) -> np.ndarray:
    """Artık satırı başına ölçek: yön satırları L, uzunluk satırları 1 (bkz. modül açıklaması)."""
    if not assembly.mates:
        return np.zeros(0)
    p = np.array([assembly.world(ref)[0] for m in assembly.mates for ref in (m.a, m.b)])
    L = max(1.0, float(np.max(np.linalg.norm(p[:, None, :] - p[None, :, :], axis=2))))
    return np.concatenate([np.where(angular_rows(assembly, m), L, 1.0) for m in assembly.mates])


def _rank(J: np.ndarray) -> int:
    """Sayısal rank: σ_i > 1e-8 · σ_max olan tekil değer sayısı (J boşsa veya σ_max = 0 ise 0)."""
    if J.size == 0:
        return 0
    sigma = np.linalg.svd(J, compute_uv=False)
    sigma_max = float(sigma.max())
    if sigma_max == 0.0:
        return 0
    return int(np.sum(sigma > _RANK_RTOL * sigma_max))


def _dof(assembly: Assembly, unknowns: list[str]) -> int:
    return 6 * len(unknowns) - _rank(_jacobian(assembly, unknowns))


def dof(assembly: Assembly) -> int:
    """Mevcut konumda kalan serbestlik derecesi (çözmez)."""
    assembly.validate()
    return _dof(assembly, _unknowns(assembly))


def _copy(assembly: Assembly) -> Assembly:
    """Bileşenleri (T kopyalarıyla) yeni bir montaja kopyalar; kısıtlar salt okunur, paylaşılır."""
    components = [
        Component(name=c.name, part=c.part, T=c.T.copy(), fixed=c.fixed) for c in assembly.components
    ]
    return Assembly(name=assembly.name, components=components, mates=list(assembly.mates))


def _nearest_rotation(R: np.ndarray) -> np.ndarray:
    """R'ye en yakın ortonormal matris (SVD: R = U Σ Vᵀ → U Vᵀ); yuvarlama birikimini temizler."""
    U, _, Vt = np.linalg.svd(R)
    Q = U @ Vt
    if np.linalg.det(Q) < 0:  # rotasyona yakın R için olmaz; yine de det = +1 güvencesi
        U[:, -1] *= -1
        Q = U @ Vt
    return Q


def _apply_step(work: Assembly, T0: dict[str, np.ndarray], unknowns: list[str], dx: np.ndarray) -> None:
    """work'teki bilinmeyenleri T0 + dx konumuna getirir: R = exp([ω]×) R0, t = t0 + Δt."""
    for i, name in enumerate(unknowns):
        dt, omega = dx[6 * i : 6 * i + 3], dx[6 * i + 3 : 6 * i + 6]
        T = T0[name].copy()
        T[:3, :3] = rodrigues(omega) @ T[:3, :3]
        T[:3, 3] = T[:3, 3] + dt
        work.component(name).T = T


def _worst_mate_message(work: Assembly) -> str:
    """En büyük artığa sahip kısıtın sırası ve türü."""
    worst = max(range(len(work.mates)), key=lambda i: float(np.max(np.abs(residual(work, work.mates[i])))))
    m = work.mates[worst]
    r_max = float(np.max(np.abs(residual(work, m))))
    return (
        f"kısıt {worst} ({m.kind.name} {m.a.kind.name}–{m.b.kind.name}, "
        f"'{m.a.component}' – '{m.b.component}'), max|r| = {r_max:.3e}"
    )


def solve(assembly: Assembly, tol: float = 1e-10, max_iter: int = 50) -> SolveResult:
    """Kısıtları sağlayan konumları bulur; girdiyi değiştirmez. Çelişki → AssyError."""
    assembly.validate()
    if not any(c.fixed for c in assembly.components):
        raise AssyError("Montajda sabit bileşen yok: montaj dünyaya bağlı değil")

    work = _copy(assembly)
    unknowns = _unknowns(work)
    w = _scale(work)  # satır ölçekleri başlangıç konumundan bir kez: çözüm boyunca sabit

    r = w * residuals(work)
    iterations = 0
    while not (r.size == 0 or float(np.max(np.abs(r))) <= tol):
        if iterations >= max_iter:
            raise AssyError(
                f"Çözücü {max_iter} iterasyonda yakınsamadı (çelişkili kısıt veya yerel minimum): "
                + _worst_mate_message(work)
            )
        J = w[:, None] * _jacobian(work, unknowns)
        # En küçük normlu Gauss–Newton adımı: δx = −J⁺ r
        dx = np.linalg.lstsq(J, -r, rcond=None)[0] if J.shape[1] else np.zeros(0)

        T0 = {name: work.component(name).T.copy() for name in unknowns}
        norm0 = float(np.linalg.norm(r))
        accepted = False
        for k in range(_MIN_HALVINGS + 1):  # α = 1, ½, ..., 2⁻¹⁰
            alpha = 0.5**k
            _apply_step(work, T0, unknowns, alpha * dx)
            r_try = w * residuals(work)
            if float(np.linalg.norm(r_try)) < norm0:
                accepted = True
                break
        if not accepted:
            for name in unknowns:  # son kabul edilen konuma dön (mesaj o konumdan yazılsın)
                work.component(name).T = T0[name]
            raise AssyError(
                "Artık azalmıyor (çelişkili kısıt veya yerel minimum): " + _worst_mate_message(work)
            )

        # Rijitliği koru: birikmiş yuvarlamaya karşı R'yi en yakın rotasyona izdüşür
        for name in unknowns:
            T = work.component(name).T
            T[:3, :3] = _nearest_rotation(T[:3, :3])
        r = w * residuals(work)
        iterations += 1

    return SolveResult(
        T={c.name: c.T.copy() for c in work.components},
        iterations=iterations,
        residual=float(np.max(np.abs(r))) if r.size else 0.0,
        dof=_dof(work, unknowns),
    )
