"""
SPEC 35 — Delik kayıtlarından otomatik bağlantı (vida / civata) önerisi.

Saf Python + numpy. SPEC 23 Hole kayıtlarından eş eksenli delik dizilerini bulur, ISO tablolarından
vida / civata boyunu seçer, önerilen standart parçaları SPEC 08 kısıtlarıyla (CONCENTRIC + COINCIDENT
PLANE) yerleştirir. Birimler: mm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from assy.model import Assembly, AssyError, Component, Mate, MateKind, Ref, RefKind, rot_x, transform
from geometry.part import Hole
from geometry.standart.tablo import ISO4032, ISO4762, ISO7089, P_KABA, gecis_olcusu, tanim, vida_boyu

EZ = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class DelikRef:
    component: str
    index: int  # Part.holes içindeki sıra


@dataclass
class Oneri:
    kind: str  # "vida" | "civata_somun"
    M: str  # "M8"
    L: float  # mm, seçilen standart boy
    grip: float  # mm, sıkıştırma boyu g
    stack: tuple[DelikRef, ...]  # dizi yönünde sıralı
    components: list[Component]  # eklenecekler; part = kanonik tanım
    mates: list[Mate]


@dataclass
class Eslesmeme:
    stack: tuple[DelikRef, ...]
    neden: str


@dataclass
class _Delik:
    """Bir deliğin dünya koordinatındaki hali. o, a: dizi yönüne göre (gerekirse çevrilmiş) giriş ve yön."""

    ref: DelikRef
    h: Hole
    T: np.ndarray  # bileşenin dünya dönüşümü
    o: np.ndarray
    a: np.ndarray

    @property
    def sabit_yon(self) -> bool:
        """Dişli, lambalı veya havşalı delik ters çevrilemez."""
        return bool(self.h.thread or self.h.cbore_d or self.h.csk_d)

    @property
    def cikis(self) -> np.ndarray:
        return self.o + self.h.depth * self.a


def _kontrol(tol: float, tol_aci: float, kappa: float = 1.0) -> None:
    for ad, v in (("tol", tol), ("tol_aci", tol_aci), ("kappa", kappa)):
        if not (np.isfinite(v) and v > 0):
            raise AssyError(f"{ad} > 0 olmalı ({ad}={v})")


def _delikler(assembly: Assembly, parts: Mapping[str, object]) -> list[_Delik]:
    """Montajdaki bütün delik kayıtları dünyada: o' = R o + t, a' = R a (bileşen ve delik sırasıyla)."""
    sonuc = []
    for c in assembly.components:
        if c.part not in parts:
            raise AssyError(f"Bileşen '{c.name}': parça kimliği '{c.part}' parts içinde yok")
        R, t = c.T[:3, :3], c.T[:3, 3]
        for i, h in enumerate(getattr(parts[c.part], "holes", ())):
            sonuc.append(_Delik(DelikRef(c.name, i), h, c.T, R @ h.origin + t, R @ h.axis))
    return sonuc


def _es_eksen(p: _Delik, q: _Delik, tol: float, tol_aci: float) -> bool:
    return np.linalg.norm(np.cross(p.a, q.a)) <= tol_aci and np.linalg.norm(np.cross(q.o - p.o, p.a)) <= tol


def _gruplar(delikler: list[_Delik], tol: float, tol_aci: float) -> list[list[_Delik]]:
    """Eş eksen ilişkisinin bağlı bileşenleri (en az iki farklı bileşenden); ilk deliğin sırasıyla."""
    ebeveyn = list(range(len(delikler)))

    def kok(i: int) -> int:
        while ebeveyn[i] != i:
            ebeveyn[i] = ebeveyn[ebeveyn[i]]
            i = ebeveyn[i]
        return i

    for i in range(len(delikler)):
        for j in range(i + 1, len(delikler)):
            if _es_eksen(delikler[i], delikler[j], tol, tol_aci):
                ebeveyn[kok(j)] = kok(i)
    gruplar: dict[int, list[_Delik]] = {}
    for i, d in enumerate(delikler):
        gruplar.setdefault(kok(i), []).append(d)
    return [g for g in gruplar.values() if len({d.ref.component for d in g}) >= 2]


def _hizala(grup: list[_Delik]) -> tuple[list[_Delik], bool]:
    """Dizi yönüne göre çevrilmiş ve sıralanmış delikler; ikinci değer: sabit yönler çelişiyor mu."""
    sabit = [d for d in grup if d.sabit_yon]
    a = sabit[0].a if sabit else grup[0].a
    celiski = any(float(d.a @ a) < 0 for d in sabit)
    dizi = []
    for d in grup:
        if float(d.a @ a) < 0 and not d.sabit_yon:  # düz boydan boya delik: aynı silindir, ters kayıt
            d = _Delik(d.ref, d.h, d.T, d.cikis, -d.a)
        dizi.append(d)
    o_ref = grup[0].o
    dizi.sort(key=lambda d: float((d.o - o_ref) @ a))
    return dizi, celiski


def eksen_gruplari(
    assembly: Assembly, parts: Mapping[str, object], tol: float = 1e-3, tol_aci: float = 1e-6
) -> list[tuple[DelikRef, ...]]:
    """En az iki farklı bileşenden delik içeren eş eksen grupları, dizi yönünde sıralı."""
    _kontrol(tol, tol_aci)
    return [tuple(d.ref for d in _hizala(g)[0]) for g in _gruplar(_delikler(assembly, parts), tol, tol_aci)]


def oner(
    assembly: Assembly,
    parts: Mapping[str, object],
    kappa: float = 1.0,
    tol: float = 1e-3,
    tol_aci: float = 1e-6,
) -> tuple[list[Oneri], list[Eslesmeme]]:
    """Her eş eksen grubu için bir Oneri ya da bir Eslesmeme."""
    _kontrol(tol, tol_aci, kappa)
    adlar = _Adlar({c.name for c in assembly.components})
    oneriler: list[Oneri] = []
    eslesmeme: list[Eslesmeme] = []
    for grup in _gruplar(_delikler(assembly, parts), tol, tol_aci):
        dizi, celiski = _hizala(grup)
        sonuc = _dizi_oner(dizi, celiski, kappa, tol, adlar)
        if isinstance(sonuc, str):
            eslesmeme.append(Eslesmeme(tuple(d.ref for d in dizi), sonuc))
        else:
            oneriler.append(sonuc)
    return oneriler, eslesmeme


def uygula(assembly: Assembly, oneriler: list[Oneri]) -> Assembly:
    """Önerilerin bileşen ve kısıtlarını eklenmiş yeni montaj; girdi değişmez."""
    yeni = Assembly(
        name=assembly.name,
        components=[Component(c.name, c.part, c.T.copy(), c.fixed) for c in assembly.components],
        mates=[_mate_kopya(m, {}) for m in assembly.mates],
    )
    adlar = _Adlar({c.name for c in yeni.components})
    for o in oneriler:
        esle = {c.name: adlar.yeni(c.name.rsplit("_", 1)[0]) for c in o.components}
        yeni.components += [Component(esle[c.name], c.part, c.T.copy(), False) for c in o.components]
        yeni.mates += [_mate_kopya(m, esle) for m in o.mates]
    yeni.validate()
    return yeni


# ---------------------------------------------------------------- yardımcılar
class _Adlar:
    """Tür başına sayaçla tekil ad: vida_1, vida_2… (mevcut adlarla çakışırsa sayaç ilerler)."""

    def __init__(self, mevcut: set[str]) -> None:
        self.mevcut = set(mevcut)

    def yeni(self, onek: str) -> str:
        n = 1
        while f"{onek}_{n}" in self.mevcut:
            n += 1
        ad = f"{onek}_{n}"
        self.mevcut.add(ad)
        return ad


def _ref_kopya(r: Ref, esle: dict[str, str]) -> Ref:
    return Ref(esle.get(r.component, r.component), r.kind, r.origin, r.direction)


def _mate_kopya(m: Mate, esle: dict[str, str]) -> Mate:
    return Mate(m.kind, _ref_kopya(m.a, esle), _ref_kopya(m.b, esle), m.value, m.flip)


def _R(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """u birim vektörünü v'ye çeviren en küçük dönme (Rodrigues); u = −v iken rot_x(180)."""
    c = float(u @ v)
    if c > 1 - 1e-15:
        return np.eye(3)
    if c < -1 + 1e-15:
        return rot_x(180)
    k = np.cross(u, v)
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + K + K @ K / (1 + c)


def _yerel(d: _Delik, kind: RefKind, p: np.ndarray, v: np.ndarray) -> Ref:
    """Dünyadaki nokta / yön → deliğin bileşeninin yerel çerçevesinde referans."""
    R, t = d.T[:3, :3], d.T[:3, 3]
    return Ref(d.ref.component, kind, tuple(R.T @ (p - t)), tuple(R.T @ v))


def _eksen(ad: str) -> Ref:
    return Ref(ad, RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))


def _alt_yuz(ad: str) -> Ref:
    """Baş altı / alt alın yüzü: z = 0, normal −Z (malzemeden dışa)."""
    return Ref(ad, RefKind.PLANE, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0))


def _ust_yuz(ad: str, h: float) -> Ref:
    return Ref(ad, RefKind.PLANE, (0.0, 0.0, h), (0.0, 0.0, 1.0))


def _parca(ad: str, part: str, R: np.ndarray, t: np.ndarray) -> Component:
    return Component(ad, part, transform(R, t), fixed=False)


def _dizi_oner(dizi: list[_Delik], celiski: bool, kappa: float, tol: float, adlar: _Adlar) -> Oneri | str:
    """Sıralı bir delik dizisi için öneri ya da eşleşmeme kodu (SPEC 35 Teori)."""
    stack = tuple(d.ref for d in dizi)
    if len({d.ref.component for d in dizi}) < len(dizi):
        return "ayni_bilesen"
    if celiski:
        return "yon"
    ilk, son = dizi[0], dizi[-1]
    a = ilk.a
    if any(d.h.thread for d in dizi[:-1]):
        return "ortada_dis"
    if any(not d.h.through for d in dizi[:-1]):
        return "kor_ara"
    for d, sonraki in zip(dizi[:-1], dizi[1:], strict=True):
        if abs(float((sonraki.o - d.cikis) @ a)) > tol:
            return "bosluk"
    if any(d.h.csk_d for d in dizi):
        return "havsa"
    if son.h.thread:
        if "x" in son.h.thread:
            return "ince_hatve"
        M = f"M{son.h.thread_d:g}"
        if M not in ISO4762:
            return "olcu_uyusmuyor"
        if abs(son.h.pitch - P_KABA[M]) > 1e-9:  # "M8" yazılıp ince hatve kaydedilmiş
            return "ince_hatve"
        gecisler = dizi[:-1]
    else:
        M = gecis_olcusu(ilk.h.d)
        gecisler = dizi
    if M is None or any(gecis_olcusu(d.h.d) != M for d in gecisler):
        return "olcu_uyusmuyor"
    if any(d.h.cbore_d for d in dizi[1:]):
        return "olcu_uyusmuyor"
    d_n = float(M[1:])
    if not son.h.thread:
        if ilk.h.cbore_d:
            return "lamba_somun"
        return _civata_somun(dizi, M, d_n, stack, adlar)
    if ilk.h.cbore_d and ilk.h.cbore_d <= ISO4762[M][0]:
        return "bas_sigmiyor"
    p_s = ilk.o + ilk.h.cbore_depth * a
    g = float((son.o - p_s) @ a)
    L = vida_boyu(M, g + kappa * d_n, seri="4762")
    if L is None:
        return "uzunluk_yok"
    if L > g + son.h.thread_depth + 1e-9:
        return "dis_yetersiz"
    vida = adlar.yeni("vida")
    comps = [_parca(vida, tanim("4762", M=M, L=L), _R(-EZ, a), p_s)]
    mates = [
        Mate(MateKind.CONCENTRIC, _eksen(vida), _yerel(ilk, RefKind.AXIS, ilk.o, a)),
        Mate(MateKind.COINCIDENT, _alt_yuz(vida), _yerel(ilk, RefKind.PLANE, p_s, -a)),
    ]
    return Oneri("vida", M, L, g, stack, comps, mates)


def _civata_somun(dizi: list[_Delik], M: str, d_n: float, stack, adlar: _Adlar) -> Oneri | str:
    """(b) boydan boya geçişe civata + 2 pul + somun; L_min = g + 2h + m + 2P."""
    ilk, son = dizi[0], dizi[-1]
    a = ilk.a
    h = ISO7089[M][2]
    m = ISO4032[M][1]
    g = float((son.cikis - ilk.o) @ a)
    L = vida_boyu(M, g + 2 * h + m + 2 * P_KABA[M], seri="4017")
    if L is None:
        return "uzunluk_yok"
    civata, somun = adlar.yeni("civata"), adlar.yeni("somun")
    pul1, pul2 = adlar.yeni("pul"), adlar.yeni("pul")
    pul = tanim("7089", M=M)
    x_son = son.cikis
    comps = [
        _parca(civata, tanim("4017", M=M, L=L), _R(-EZ, a), ilk.o - h * a),
        _parca(pul1, pul, _R(EZ, -a), ilk.o),
        _parca(pul2, pul, _R(EZ, a), x_son),
        _parca(somun, tanim("4032", M=M), _R(EZ, a), x_son + h * a),
    ]
    eksen_ilk = _yerel(ilk, RefKind.AXIS, ilk.o, a)
    eksen_son = _yerel(son, RefKind.AXIS, son.o, a)
    mates = [
        Mate(MateKind.CONCENTRIC, _eksen(civata), eksen_ilk),
        Mate(MateKind.COINCIDENT, _alt_yuz(civata), _ust_yuz(pul1, h)),
        Mate(MateKind.CONCENTRIC, _eksen(pul1), eksen_ilk),
        Mate(MateKind.COINCIDENT, _alt_yuz(pul1), _yerel(ilk, RefKind.PLANE, ilk.o, -a)),
        Mate(MateKind.CONCENTRIC, _eksen(pul2), eksen_son),
        Mate(MateKind.COINCIDENT, _alt_yuz(pul2), _yerel(son, RefKind.PLANE, x_son, a)),
        Mate(MateKind.CONCENTRIC, _eksen(somun), eksen_son),
        Mate(MateKind.COINCIDENT, _alt_yuz(somun), _ust_yuz(pul2, h)),
    ]
    return Oneri("civata_somun", M, L, g, stack, comps, mates)
