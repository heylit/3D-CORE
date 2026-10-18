"""
Montaj ağacı: gezinme, doğrulama, düz montaja dönüşüm ve geri dönüş (SPEC 07).

Düğüm tipi `assy.model.Node`'dur. Saf Python + numpy; OCCT gerektirmez.

Dünya dönüşümü:  T_dünya(n_k) = T(n₀) · T(n₁) · … · T(n_k)   (Craig, Bölüm 2.3)
Geri dönüş:      T(n_k) = T_dünya(n_{k−1})⁻¹ · T_dünya,yeni(n_k),   T⁻¹ = [[Rᵀ, −Rᵀ t], [0, 1]]
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import numpy as np

from assy.model import Assembly, AssyError, Component, Node

TOL_TANIM = 1e-9  # aynı tanımlı alt montajların T karşılaştırması (mm, R bileşenleri)


def _inv(T: np.ndarray) -> np.ndarray:
    """Rijit dönüşümün tersi: [[Rᵀ, −Rᵀ t], [0, 1]]."""
    R, t = T[:3, :3], T[:3, 3]
    Ti = np.eye(4)
    Ti[:3, :3] = R.T
    Ti[:3, 3] = -R.T @ t
    return Ti


def _ayni_icerik(a: Node, b: Node) -> bool:
    """İki alt montaj tanımının içeriği aynı mı: çocuk adları, parçaları, tanımları, T'leri (özyinelemeli)."""
    if len(a.children) != len(b.children):
        return False
    for ca, cb in zip(a.children, b.children, strict=True):
        if ca.name != cb.name or ca.part != cb.part or ca.definition != cb.definition:
            return False
        if not np.allclose(ca.T, cb.T, rtol=0, atol=TOL_TANIM):
            return False
        if ca.part is None and not _ayni_icerik(ca, cb):
            return False
    return True


def validate(root: Node) -> None:
    """Ağaç bütünlüğü: kardeş adları, boş alt montaj, aynı nesnenin tekrarı, tanımların tutarlılığı."""
    gorulen: set[int] = set()
    parca_tanim: set[str] = set()
    montaj_tanim: dict[str, Node] = {}

    def gez(n: Node, yol: str) -> None:
        if id(n) in gorulen:
            raise AssyError(
                f"Aynı düğüm nesnesi ağaçta iki kez: '{yol or n.name}' (paylaşım ref ile yapılır)"
            )
        gorulen.add(id(n))
        if n.part is not None:
            parca_tanim.add(n.part)
            return
        if not n.children:
            raise AssyError(f"Çocuksuz alt montaj: '{yol or n.name}'")
        adlar = [c.name for c in n.children]
        yinelenen = sorted({a for a in adlar if adlar.count(a) > 1})
        if yinelenen:
            raise AssyError(f"'{yol or n.name}' altında yinelenen ad: {yinelenen}")
        ilk = montaj_tanim.setdefault(n.definition, n)
        if ilk is not n and not _ayni_icerik(ilk, n):
            raise AssyError(f"Alt montaj tanımı '{n.definition}' iki yerde farklı içerikte ('{yol}')")
        for c in n.children:
            gez(c, f"{yol}/{c.name}" if yol else c.name)

    gez(root, "")
    ortak = sorted(parca_tanim & montaj_tanim.keys())
    if ortak:
        raise AssyError(f"Ad hem parça kimliği hem alt montaj tanımı: {ortak}")


def walk(root: Node) -> Iterator[tuple[str, Node, np.ndarray]]:
    """Derinlik öncelikli, düğüm çocuklarından önce: (yol, düğüm, T_dünya). Kökün yolu ""."""

    def gez(n: Node, yol: str, T_ust: np.ndarray) -> Iterator[tuple[str, Node, np.ndarray]]:
        T = T_ust @ n.T
        yield yol, n, T
        for c in n.children:
            yield from gez(c, f"{yol}/{c.name}" if yol else c.name, T)

    yield from gez(root, "", np.eye(4))


def world(root: Node, path: str) -> np.ndarray:
    """Yoldaki düğümün dünya dönüşümü. Bilinmeyen yol → AssyError."""
    validate(root)
    n, T = root, root.T.copy()
    if path == "":
        return T
    for ad in path.split("/"):
        bulunan = next((c for c in n.children if c.name == ad), None)
        if bulunan is None:
            raise AssyError(f"Bilinmeyen yol: '{path}'")
        n, T = bulunan, T @ bulunan.T
    return T


def flatten(root: Node, fixed: Iterable[str] = ()) -> Assembly:
    """Her yaprak bir Component(name=yol, part=parça kimliği, T=T_dünya), walk sırasıyla."""
    validate(root)
    yapraklar = [(y, n, T) for y, n, T in walk(root) if n.part is not None]
    yollar = {y for y, _, _ in yapraklar}
    sabit = set(fixed)
    bilinmeyen = sorted(sabit - yollar)
    if bilinmeyen:
        raise AssyError(f"fixed içinde yaprak olmayan yol: {bilinmeyen}")
    return Assembly(
        name=root.name,
        components=[Component(name=y, part=n.part, T=T.copy(), fixed=y in sabit) for y, n, T in yapraklar],
    )


def apply(root: Node, assy: Assembly) -> Node:
    """Yaprakların dünya dönüşümü assy'deki aynı adlı bileşenin T'si olacak şekilde yeni ağaç.

    Alt montaj düğümlerinin T'si değişmez; yaprak için T = T_dünya(ebeveyn)⁻¹ · T_bileşen.
    """
    validate(root)
    bilesen = {c.name: c for c in assy.components}
    yollar = {y for y, n, _ in walk(root) if n.part is not None}
    if len(bilesen) != len(assy.components) or set(bilesen) != yollar:
        eksik, fazla = sorted(yollar - set(bilesen)), sorted(set(bilesen) - yollar)
        raise AssyError(f"Bileşenler yaprak yollarıyla uyuşmuyor (eksik: {eksik}, fazla: {fazla})")

    def kur(n: Node, yol: str, T_ust: np.ndarray) -> Node:
        if n.part is not None:
            T = _inv(T_ust) @ bilesen[yol].T
            return Node(name=n.name, T=T, part=n.part)
        T_dunya = T_ust @ n.T
        cocuklar = [kur(c, f"{yol}/{c.name}" if yol else c.name, T_dunya) for c in n.children]
        return Node(name=n.name, T=n.T.copy(), children=cocuklar, ref=n.ref)

    yeni = kur(root, "", np.eye(4))
    validate(yeni)  # paylaşımlı tanım ayrıştıysa AssyError
    return yeni
