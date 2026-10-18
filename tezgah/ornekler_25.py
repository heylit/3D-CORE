"""
SPEC 25 — Örnekler (uydurma geometri, gizlilik kuralı).

"kademeli_mil" (torna): C45, ham Ø50 × 101. Ön uçtan arkaya Ø24 × L, Ø35 × 30, Ø44 × 30, Ø50 kalan.
    İşlemler: alın, kaba boyuna, ince profil, kanal (SPEC 20). Parça eş eksenli silindirlerden (SPEC 02/09),
    profil parçadan (SPEC 28) çıkarılır. Parametre: L (uç boyu, varsayılan 20, aralık [5, 30]).
"yatak_grubu" (montaj): plaka 120 × 80 × 30 (üst yüz z = 0, Ø40,02 × 10 cep, dört Ø8,02 × 20 kör delik),
    rulman (iç Ø24,02, dış Ø40, genişlik 10), kademeli_mil, dört pim Ø8 × 24.
    Sıra: plaka, rulman, mil, pimler.
    L > 10 ise girişim hacmi V = π·12²·(L − 10) mm³; öneri L* = 10.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from assy.model import Mate, MateKind, Node, Ref, RefKind, rot_x, transform
from cam.model import CamError, CylinderStock, LatheTool, LatheToolKind, Setup, Wcs
from cam.profile import Profile

if TYPE_CHECKING:
    from geometry.part import Part
    from tezgah.montaj import MontajTanimi
    from tezgah.torna import TornaIsi

TORNA_ISLERI: tuple[str, ...] = ("kademeli_mil",)
MONTAJLAR: tuple[str, ...] = ("yatak_grubu",)
VARSAYILAN: dict[str, dict[str, float]] = {"kademeli_mil": {"L": 20.0}}
ARALIK: dict[tuple[str, str], tuple[float, float]] = {("kademeli_mil", "L"): (5.0, 30.0)}

# Kademeli mil ölçüleri [mm]: (çap, boy) ön uçtan arkaya; Ø24'ün boyu L, Ø50 kalan
BOY = 100.0  # bitmiş parça boyu (ham 101: alında 1 mm)
KADEMELER = ((35.0, 30.0), (44.0, 30.0))
D_HAM, D_UC = 50.0, 24.0
KANAL_G, KANAL_T = 3.0, 1.0  # kanal: Ø44 üstünde, Ø50 omzunun dibinde genişlik × derinlik
AYNA_BOY = 6.0  # ayna çenesinin tuttuğu boy (arka uçtan)

# Yoğunluklar [t/mm³]
RHO_CELIK, RHO_RULMAN = 7.85e-9, 7.81e-9

# Yatak grubu ölçüleri [mm]
PLAKA = (120.0, 80.0, 30.0)
CEP_D, CEP_T = 40.02, 10.0
DELIK_D, DELIK_T = 8.02, 20.0
DELIKLER = ((-45.0, -25.0), (45.0, -25.0), (45.0, 25.0), (-45.0, 25.0))  # plaka merkezine göre
RULMAN = (40.0, 24.02, 10.0)  # dış çap, iç çap, genişlik
PIM = (8.0, 24.0)  # çap, boy

EZ = (0.0, 0.0, 1.0)
EZ_ALT = (0.0, 0.0, -1.0)


# kademeli_mil işlemlerinin müfettişte değiştirilebilen kesme değerleri (sırayla alın, kaba, ince, kanal).
# Vc [m/min] → G96 kesme hızı, f [mm/dev], n_max [dev/dk] → G96 devir sınırı,
# n [dev/dk] → G97 sabit devir, a_p [mm]
ISLEM_VARSAYILAN: tuple[dict[str, float], ...] = (
    {"Vc": 200.0, "f": 0.2, "n_max": 3000.0},
    {"a_p": 2.0, "f": 0.25, "Vc": 200.0, "n_max": 2500.0},
    {"f": 0.1, "Vc": 250.0, "n_max": 3000.0},
    {"f": 0.05, "n": 1200.0},
)
_ALIN_A_P = 1.0  # alın pasosu [mm] (müfettişte yok)


def islem_parametre_dogrula(
    islem_parametreleri: dict[int, dict[str, float]] | None,
) -> list[dict[str, float]]:
    """ISLEM_VARSAYILAN'ın üstüne verilenler.

    Bilinmeyen işlem / anahtar, sonlu ve pozitif olmayan değer → CamError.
    """
    q = [dict(d) for d in ISLEM_VARSAYILAN]
    for i, d in (islem_parametreleri or {}).items():
        if not (isinstance(i, int) and 0 <= i < len(q)):
            raise CamError(f"kademeli_mil işinde {i} numaralı işlem yok (0..{len(q) - 1})")
        for k, v in d.items():
            if k not in q[i]:
                raise CamError(f"kademeli_mil işlem {i}: '{k}' parametresi yok (var olanlar: {sorted(q[i])})")
            if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
                raise CamError(f"kademeli_mil işlem {i}: {k} sonlu ve pozitif olmalı ({v!r})")
            q[i][k] = float(v)
    return q


def _kesme(d: dict[str, float], a_p: float | None = None):
    """Müfettiş değerlerinden SPEC 20 TurnCut: Vc varsa G96 (rpm = n_max sınırı), yoksa G97 n."""
    from cam.lathe_ops import TurnCut

    rpm = d["n_max"] if "Vc" in d else d["n"]
    return TurnCut(feed=d["f"], rpm=rpm, css=d.get("Vc"), a_p=d.get("a_p", a_p))


def parametre_dogrula(is_ad: str, parametreler: dict[str, float] | None) -> dict[str, float]:
    """Varsayılanların üstüne verilen değerler; bilinmeyen anahtar ya da aralık dışı → CamError."""
    p = dict(VARSAYILAN[is_ad])
    for k, v in (parametreler or {}).items():
        if k not in p:
            raise CamError(f"'{is_ad}' işinde '{k}' parametresi yok (var olanlar: {sorted(p)})")
        p[k] = v
    for k, v in p.items():
        lo, hi = ARALIK[(is_ad, k)]
        if not (isinstance(v, (int, float)) and math.isfinite(v)):
            raise CamError(f"{is_ad}.{k} sonlu bir sayı olmalı ({v!r})")
        if v <= 0:
            raise CamError(f"{is_ad}.{k} pozitif olmalı ({v})")
        if not lo <= v <= hi:
            raise CamError(f"{is_ad}.{k} = {v} aralık dışında [{lo}, {hi}]")
        p[k] = float(v)
    return p


def _silindir(r: float, z0: float, z1: float) -> Part:
    from geometry.features import cylinder

    return cylinder(r, z1 - z0).moved(transform(t=(0.0, 0.0, z0)))


def _govde(L: float) -> Part:
    """Kanalsız kademeli gövde: ön yüz z = 0, arka yüz z = −BOY (torna kuralı: ayna −Z tarafında)."""
    if not (math.isfinite(L) and 0 < L < BOY - sum(b for _, b in KADEMELER)):
        from geometry.part import GeometryError

        raise GeometryError(f"Kademeli mil: uç boyu L geçersiz ({L})")
    p = _silindir(D_UC / 2, -L, 0.0)
    z = -L
    for d, b in KADEMELER:
        p = p.fuse(_silindir(d / 2, z - b, z))
        z -= b
    return p.fuse(_silindir(D_HAM / 2, -BOY, z))


def _kanal_z(L: float) -> tuple[float, float]:
    """Kanalın (z_sol, z_sag): Ø44 kademesinin arka ucunda, Ø50 omzuna dayalı."""
    z_omuz = -L - sum(b for _, b in KADEMELER)
    return z_omuz, z_omuz + KANAL_G


def mil_parcasi(L: float) -> Part:
    """Kademeli mil katısı, kendi koordinatında (ön yüz z = 0, eksen Z). L ≤ 0 → GeometryError."""
    p = _govde(L)
    z0, z1 = _kanal_z(L)
    r = KADEMELER[-1][0] / 2
    halka = _silindir(r + 1.0, z0, z1).cut(_silindir(r - KANAL_T, z0 - 1.0, z1 + 1.0))
    p = p.cut(halka)
    p.name = "kademeli_mil"
    return p


def _islenen(profil: Profile) -> Profile:
    """Dış profilin işlenen kısmı: ham yüzeyinde (x = D/2) kalan arka parçalar (aynada tutulan Ø50) atılır."""
    S = list(profil.segments)
    while S and min(S[-1].p0[1], S[-1].p1[1]) >= D_HAM / 2 - 1e-9:
        S.pop()
    if not S:
        raise CamError("Kademeli mil: işlenecek profil kalmadı")
    return Profile(S, closed=False)


def _takimlar() -> tuple[LatheTool, LatheTool, LatheTool]:
    kaba = LatheTool(1, "CNMG 120408", LatheToolKind.TURN, 0.8, 3, 95.0, 80.0, edge_len=8.0)
    ince = LatheTool(2, "DNMG 110404", LatheToolKind.TURN, 0.4, 3, 93.0, 55.0, edge_len=6.0)
    kanal = LatheTool(3, "Kanal 3 mm", LatheToolKind.GROOVE, 0.2, 3, 90.0, 90.0, width=KANAL_G, edge_len=5.0)
    return kaba, ince, kanal


def kademeli_mil(
    parametreler: dict[str, float] | None = None,
    islem_parametreleri: dict[int, dict[str, float]] | None = None,
) -> TornaIsi:
    """Torna işi; parametreler None → VARSAYILAN. Aralık dışı → CamError.

    islem_parametreleri: işlem sırası → {anahtar: değer}; ISLEM_VARSAYILAN'ın üstüne yazılır (müfettiş).

    Profil parçadan SPEC 28 ile (`cam.turn_profile`) çıkarılır; kaba ve ince profil kanalsız gövdeden,
    kanal SPEC 20 kanal işlemiyle. İşlemler: alın, kaba boyuna, ince profil, kanal.
    """
    from cam.lathe_ops import face, finish, groove, rough
    from cam.turn_profile import turn_profile
    from tezgah.torna import TornaIsi, TornaIslem

    p = parametre_dogrula("kademeli_mil", parametreler)
    L = p["L"]
    parca = mil_parcasi(L)
    profil = _islenen(turn_profile(_govde(L)).outer)
    stok = CylinderStock(D=D_HAM, zmin=-BOY, zmax=1.0)
    alinmis = CylinderStock(D=D_HAM, zmin=-BOY, zmax=0.0)  # alın sonrası: kaba ve ince bunun üstünde
    ayna = CylinderStock(D=90.0, zmin=-BOY, zmax=-BOY + AYNA_BOY, d=D_HAM)
    kurulum = Setup(name="ayna", wcs=Wcs("G54"), stock=stok, fixtures=[ayna])
    kaba, ince, kanal = _takimlar()
    z0, z1 = _kanal_z(L)
    r44 = KADEMELER[-1][0] / 2
    q = islem_parametre_dogrula(islem_parametreleri)
    islemler = [
        TornaIslem("alin", "Alın", face(stok, kaba, _kesme(q[0], _ALIN_A_P), 0.0), q[0]),
        TornaIslem(
            "kaba",
            "Kaba boyuna",
            rough(profil, alinmis, kaba, _kesme(q[1]), allowance=0.2, name="kaba"),
            q[1],
        ),
        TornaIslem("ince", "İnce profil", finish(profil, alinmis, ince, _kesme(q[2])), q[2]),
        TornaIslem("kanal", "Kanal", groove(alinmis, kanal, _kesme(q[3]), z0, z1, r44, r44 - KANAL_T), q[3]),
    ]
    return TornaIsi(ad="kademeli_mil", kurulum=kurulum, malzeme="C45", islemler=islemler, parca=parca)


# ---------------------------------------------------------------- yatak grubu


def _plaka() -> Part:
    from geometry.features import block, hole

    a, b, c = PLAKA
    p = hole(block(a, b, c), a / 2, b / 2, CEP_D, CEP_T)
    for x, y in DELIKLER:
        p = hole(p, a / 2 + x, b / 2 + y, DELIK_D, DELIK_T)
    p = p.moved(transform(t=(-a / 2, -b / 2, -c)))  # üst yüz z = 0, merkez başlangıçta
    p.name = "plaka"
    return p


def _rulman() -> Part:
    D, d, B = RULMAN
    p = _silindir(D / 2, 0.0, B).cut(_silindir(d / 2, -1.0, B + 1.0))
    p.name = "rulman"
    return p


def _pim() -> Part:
    d, h = PIM
    p = _silindir(d / 2, 0.0, h)
    p.name = "pim"
    return p


def _eksen(bilesen: str, nokta, yon=EZ) -> Ref:
    return Ref(bilesen, RefKind.AXIS, tuple(nokta), tuple(yon))


def _duzlem(bilesen: str, nokta, normal) -> Ref:
    return Ref(bilesen, RefKind.PLANE, tuple(nokta), tuple(normal))


def yatak_grubu(parametreler: dict[str, dict[str, float]] | None = None) -> MontajTanimi:
    """Montaj; parametreler iş adı → {anahtar: değer}, None → VARSAYILAN.

    Plaka sabit (üst yüz z = 0); rulman cebe, mil rulmana (omuz rulman üst yüzünde, uç z = −L'de),
    dört pim kör deliklere. Bileşenler başlangıçta kısıtları sağlayan konumdadır.
    """
    from tezgah.iplik import Bag
    from tezgah.montaj import MontajTanimi

    bilinmeyen = sorted(set(parametreler or {}) - set(VARSAYILAN))
    if bilinmeyen:
        raise CamError(f"Bilinmeyen iş: {bilinmeyen}")
    L = parametre_dogrula("kademeli_mil", (parametreler or {}).get("kademeli_mil"))["L"]
    pimler = [f"pim{i + 1}" for i in range(len(DELIKLER))]
    agac = Node(
        "yatak_grubu",
        children=[
            Node("plaka", part="plaka"),
            Node("rulman", T=transform(t=(0.0, 0.0, -CEP_T)), part="rulman"),
            Node("mil", T=transform(R=rot_x(180.0), t=(0.0, 0.0, -L)), part="mil"),
            Node(
                "pimler",
                children=[
                    Node(ad, T=transform(t=(x, y, -DELIK_T)), part="pim")
                    for ad, (x, y) in zip(pimler, DELIKLER, strict=True)
                ],
            ),
        ],
    )
    B = RULMAN[2]
    kisitlar = [
        Mate(MateKind.CONCENTRIC, _eksen("plaka", (0, 0, 0)), _eksen("rulman", (0, 0, 0))),
        Mate(MateKind.COINCIDENT, _duzlem("plaka", (0, 0, -CEP_T), EZ), _duzlem("rulman", (0, 0, 0), EZ_ALT)),
        Mate(MateKind.CONCENTRIC, _eksen("rulman", (0, 0, 0)), _eksen("mil", (0, 0, 0))),
        Mate(MateKind.COINCIDENT, _duzlem("rulman", (0, 0, B), EZ), _duzlem("mil", (0, 0, -L), EZ)),
    ]
    for ad, (x, y) in zip(pimler, DELIKLER, strict=True):
        yol = f"pimler/{ad}"
        kisitlar += [
            Mate(MateKind.CONCENTRIC, _eksen("plaka", (x, y, 0)), _eksen(yol, (0, 0, 0))),
            Mate(
                MateKind.COINCIDENT, _duzlem("plaka", (x, y, -DELIK_T), EZ), _duzlem(yol, (0, 0, 0), EZ_ALT)
            ),
        ]
    lo, hi = ARALIK[("kademeli_mil", "L")]
    return MontajTanimi(
        ad="yatak_grubu",
        agac=agac,
        parcalar={"plaka": _plaka(), "rulman": _rulman(), "mil": mil_parcasi(L), "pim": _pim()},
        malzemeler={
            "plaka": ("C45", RHO_CELIK),
            "rulman": ("100Cr6", RHO_RULMAN),
            "mil": ("C45", RHO_CELIK),
            "pim": ("C45", RHO_CELIK),
        },
        kisitlar=kisitlar,
        sabit=("plaka",),
        sira=["plaka", "rulman", "mil", *(f"pimler/{ad}" for ad in pimler)],
        kaynaklar={"mil": ("kademeli_mil", "torna")},
        baglar=[Bag("kademeli_mil", "L", L, lo, hi, ("mil",))],
    )
