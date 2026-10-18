"""SPEC 35 — assy/oneri.py testleri: eş eksenli delik dizileri ve otomatik bağlantı önerisi (K7–K13).

Testler sadece specs/35-standart-parca.md'deki "Teori", "Arayüz" ve "Kabul kriterleri" bölümlerinden,
assy/model.py ve geometry/part.Hole arayüzlerinden yazıldı; assy/oneri.py gövdesi okunmadı.
OCCT'siz: delikli parça yerine `.holes` özniteliği olan sahte nesne (assy/bom.py testleriyle aynı yaklaşım).

Kurallar (SPEC 35):
- Dünyada o' = R o + t, a' = R a. Eş eksen: |a'_i × a'_j| ≤ tol_aci ve |(o'_j − o'_i) × a'_i| ≤ tol.
- (a) dişliye imbus vida: g = (o'_son − p_s)·a, L_min = g + κ d, L_maks = g + thread_depth.
- (b) boydan boyaya civata + 2 pul + somun: g = (x_son − o'_0)·a, L_min = g + 2h + m + 2P.
- Yerleşim: vida / civata R(−Z → a); baş altı pulu R(+Z → −a); somun altı pulu ve somun R(+Z → a).
  R(u → v) en küçük dönme (Rodrigues; u = −v iken rot_x(180)).
Örnek montajlarda deliklerin delme yönü dünyada −Z'dir (üstten), taban üst yüzü z = 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pytest

from assy.model import Assembly, AssyError, Component, MateKind, RefKind, rot_x, rot_y, rot_z, transform
from assy.oneri import DelikRef, Eslesmeme, Oneri, eksen_gruplari, oner, uygula
from assy.solver import dof, residuals, solve
from geometry.part import Hole

ASAGI = np.array([0.0, 0.0, -1.0])
YUKARI = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class SahteParca:
    """Part yerine: sadece delik kayıtları."""

    holes: tuple[Hole, ...]


# ---------------------------------------------------------------- yardımcılar
def rodrigues(u, v) -> np.ndarray:
    """u birim vektörünü v'ye çeviren en küçük dönme; u = −v iken rot_x(180) (SPEC 35)."""
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    c = float(u @ v)
    if c > 1 - 1e-15:
        return np.eye(3)
    if c < -1 + 1e-15:
        return rot_x(180)
    k = np.cross(u, v)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def delik(T, o, a=ASAGI, **kw) -> Hole:
    """Dünya koordinatında verilen deliği T dönüşümlü bileşenin yerel çerçevesine çevirir."""
    T = np.asarray(T, dtype=float)
    R, t = T[:3, :3], T[:3, 3]
    o_l = R.T @ (np.asarray(o, dtype=float) - t)
    a_l = R.T @ np.asarray(a, dtype=float)
    return Hole(origin=o_l, axis=a_l / np.linalg.norm(a_l), **kw)


def gecis(T, o, depth, d=9.0, a=ASAGI) -> Hole:
    """Düz boydan boya geçiş deliği."""
    return delik(T, o, a, d=d, depth=depth, through=True)


def lamba(T, o, depth, cbore_d=15.0, cbore_depth=8.6, d=9.0) -> Hole:
    """Lambalı boydan boya geçiş deliği (M8 için DIN 974-1: Ø15 × 8.6)."""
    return delik(T, o, d=d, depth=depth, through=True, cbore_d=cbore_d, cbore_depth=cbore_depth)


def disli(T, o, a=ASAGI, thread="M8", thread_d=8.0, pitch=1.25, d=6.8, depth=25.0, thread_depth=20.0,
          through=False) -> Hole:  # fmt: skip
    """Dişli (kılavuzlu) delik."""
    return delik(
        T, o, a, d=d, depth=depth, through=through, thread=thread, thread_d=thread_d, pitch=pitch,
        thread_depth=thread_depth,
    )  # fmt: skip


def montaj(*bilesenler) -> tuple[Assembly, dict[str, SahteParca]]:
    """bilesenler: (ad, T, delikler, fixed). Parça kimliği = 'p_' + ad."""
    comps = []
    parts = {}
    for ad, T, holes, fixed in bilesenler:
        comps.append(Component(name=ad, part=f"p_{ad}", T=np.asarray(T, dtype=float), fixed=fixed))
        parts[f"p_{ad}"] = SahteParca(tuple(holes))
    return Assembly(name="montaj", components=comps), parts


def tek_oneri(asm, parts, **kw) -> Oneri:
    oneriler, eslesmeme = oner(asm, parts, **kw)
    assert eslesmeme == []
    assert len(oneriler) == 1
    return oneriler[0]


def tek_neden(asm, parts, **kw) -> Eslesmeme:
    oneriler, eslesmeme = oner(asm, parts, **kw)
    assert oneriler == []
    assert len(eslesmeme) == 1
    return eslesmeme[0]


def bilesen(oneri: Oneri, part: str) -> list[Component]:
    return [c for c in oneri.components if c.part == part]


def T_ayni(T, beklenen, atol) -> None:
    np.testing.assert_allclose(np.asarray(T, dtype=float), np.asarray(beklenen, dtype=float), atol=atol)


def max_artik(asm: Assembly) -> float:
    r = residuals(asm)
    return float(np.max(np.abs(r))) if r.size else 0.0


# Lambalı plaka T'si: Z etrafında 90° dönük ve ötelenmiş (yerel ≠ dünya)
T_PLAKA = transform(rot_z(90), (5.0, 0.0, 0.0))
XY = (25.0, -10.0)  # dizinin dünya ekseni x, y


def vida_montaji(kalinlik=10.0, lambali=True, thread_depth=20.0):
    """Taban (sabit, z ≤ 0) M8 dişli kör delik + üstünde plaka (sabit, z ∈ [0, kalınlık]) Ø9 geçiş."""
    x, y = XY
    ust = (x, y, kalinlik)
    h_plaka = lamba(T_PLAKA, ust, kalinlik) if lambali else gecis(T_PLAKA, ust, kalinlik)
    return montaj(
        ("plaka", T_PLAKA, [h_plaka], True),
        ("taban", np.eye(4), [disli(np.eye(4), (x, y, 0.0), thread_depth=thread_depth)], True),
    )


def civata_montaji(t1=10.0, t2=15.0):
    """Üst plaka z ∈ [t2, t1 + t2], alt plaka z ∈ [0, t2]; ikisinde de Ø9 düz geçiş (sabit)."""
    T_alt = transform(rot_x(180), (0.0, 0.0, t2 / 2))  # alt plaka ters çevrilmiş çerçevede
    return montaj(
        ("ust", np.eye(4), [gecis(np.eye(4), (0.0, 0.0, t1 + t2), t1)], True),
        ("alt", T_alt, [gecis(T_alt, (0.0, 0.0, t2), t2)], True),
    )


# ---------------------------------------------------------------- K7 eş eksen grupları
def uc_bilesenli():
    """ust (Z etrafında 90° + öteleme), orta (öteleme), alt (birim). Eksenler x = 10 ve x = −10."""
    T_ust = transform(rot_z(90), (0.0, 0.0, 20.0))
    T_orta = transform(None, (0.0, 0.0, 10.0))
    E4 = np.eye(4)
    return montaj(
        ("ust", T_ust, [gecis(T_ust, (10, 0, 30), 10), gecis(T_ust, (-10, 0, 30), 10)], True),
        ("orta", T_orta, [gecis(T_orta, (10, 0, 20), 10), gecis(T_orta, (-10, 0, 20), 10)], True),
        (
            "alt",
            E4,
            [
                gecis(E4, (40, 0, 10), 10),  # tek delikli eksen: dönmez
                gecis(E4, (10, 0, 10), 10),
                gecis(E4, (-10, 0, 0), 10, a=YUKARI),  # ters yönlü düz geçiş: çevrilip gruba girer
            ],
            True,
        ),
    )


def test_k7_gruplar_dunya_koordinatinda_ve_sirali():
    """K7: dünyada eş eksen grupları; grup içi dizi yönünde, gruplar ilk deliğe göre sıralı."""
    asm, parts = uc_bilesenli()
    gruplar = eksen_gruplari(asm, parts)
    assert gruplar == [
        (DelikRef("ust", 0), DelikRef("orta", 0), DelikRef("alt", 1)),
        (DelikRef("ust", 1), DelikRef("orta", 1), DelikRef("alt", 2)),
    ]


def test_k7_tek_delikli_eksen_donmez():
    """K7: tek delikli eksen ve tek bileşenli grup dönmez."""
    E4 = np.eye(4)
    asm, parts = montaj(
        ("a", E4, [gecis(E4, (0, 0, 10), 10), gecis(E4, (50, 0, 10), 5)], True),
        ("b", E4, [gecis(E4, (100, 0, 0), 10)], True),
    )
    assert eksen_gruplari(asm, parts) == []


@pytest.mark.parametrize(("kacik", "gruplu"), [(2e-3, False), (0.5e-3, True)])
def test_k7_eksen_toleransi(kacik, gruplu):
    """K7: varsayılan tol = 1e-3 mm: 2e-3 mm kaçık eksen gruplanmaz, 0.5e-3 mm gruplanır."""
    E4 = np.eye(4)
    T_b = transform(rot_z(30), (3.0, 4.0, 0.0))
    asm, parts = montaj(
        ("a", E4, [gecis(E4, (0, 0, 20), 10)], True),
        ("b", T_b, [gecis(T_b, (kacik, 0, 10), 10)], True),
    )
    gruplar = eksen_gruplari(asm, parts)
    if gruplu:
        assert gruplar == [(DelikRef("a", 0), DelikRef("b", 0))]
    else:
        assert gruplar == []


def test_k7_tol_parametresi():
    """K7: tol büyütülünce 2e-3 mm kaçık eksen de gruplanır."""
    E4 = np.eye(4)
    asm, parts = montaj(
        ("a", E4, [gecis(E4, (0, 0, 20), 10)], True),
        ("b", E4, [gecis(E4, (0, 2e-3, 10), 10)], True),
    )
    assert eksen_gruplari(asm, parts) == []
    assert eksen_gruplari(asm, parts, tol=5e-3) == [(DelikRef("a", 0), DelikRef("b", 0))]


def test_k7_egik_eksen_eslesmez():
    """K7: paralel olmayan (eğik) eksenler aynı noktadan geçse de eş eksen değildir."""
    E4 = np.eye(4)
    a2 = rot_y(1.0) @ ASAGI
    asm, parts = montaj(
        ("a", E4, [gecis(E4, (0, 0, 20), 10)], True),
        ("b", E4, [gecis(E4, (0, 0, 10), 10, a=a2)], True),
    )
    assert eksen_gruplari(asm, parts) == []


# ---------------------------------------------------------------- K8 (a) imbus vida
def test_k8_lambali_plaka_dişliye_vida():
    """K8: 10 mm plaka, M8 lamba 8.6 → p_s 1.4 üstte; g = 1.4, L_min = 9.4, L = 12, "ISO 4762 M8x12"."""
    asm, parts = vida_montaji(kalinlik=10.0, lambali=True)
    o = tek_oneri(asm, parts)
    assert o.kind == "vida"
    assert o.M == "M8"
    assert o.grip == pytest.approx(1.4, abs=1e-9)
    assert o.L == pytest.approx(12.0, abs=1e-12)
    assert o.stack == (DelikRef("plaka", 0), DelikRef("taban", 0))
    assert [c.part for c in o.components] == ["ISO 4762 M8x12"]
    # Vida: R(−Z → a) = I (a = −Z), t = p_s = o'_0 + cbore_depth·a
    x, y = XY
    T_ayni(o.components[0].T, transform(rodrigues(-YUKARI, ASAGI), (x, y, 10.0 - 8.6)), atol=1e-12)
    assert o.components[0].fixed is False


def test_k8_kisitlar_saglaniyor_ve_dof_bir_artiyor():
    """K8: CONCENTRIC (eksen–eksen) + COINCIDENT (düzlem–düzlem); artık ≤ 1e-9, dof tam 1 artar."""
    asm, parts = vida_montaji()
    o = tek_oneri(asm, parts)
    assert len(o.mates) == 2
    turler = sorted(m.kind.value for m in o.mates)
    assert turler == sorted([MateKind.CONCENTRIC.value, MateKind.COINCIDENT.value])
    for m in o.mates:
        beklenen = RefKind.AXIS if m.kind is MateKind.CONCENTRIC else RefKind.PLANE
        assert m.a.kind is beklenen and m.b.kind is beklenen
    yeni = uygula(asm, [o])
    assert max_artik(yeni) <= 1e-9
    assert dof(yeni) - dof(asm) == 1


def test_k8_duz_gecisli_20mm_plaka():
    """K8: düz Ø9 geçişli 20 mm plaka → p_s = üst yüz, g = 20, L_min = 28, L = 30."""
    asm, parts = vida_montaji(kalinlik=20.0, lambali=False)
    o = tek_oneri(asm, parts)
    assert o.kind == "vida"
    assert o.grip == pytest.approx(20.0, abs=1e-9)
    assert o.L == pytest.approx(30.0, abs=1e-12)
    assert [c.part for c in o.components] == ["ISO 4762 M8x30"]
    x, y = XY
    T_ayni(o.components[0].T, transform(np.eye(3), (x, y, 20.0)), atol=1e-12)
    yeni = uygula(asm, [o])
    assert max_artik(yeni) <= 1e-9
    assert dof(yeni) - dof(asm) == 1


def test_k8_kappa_iki():
    """K8: κ = 2 (alüminyum) ile 20 mm plaka → L_min = 20 + 16 = 36, L = 40 (L_maks = 20 + 20 = 40)."""
    asm, parts = vida_montaji(kalinlik=20.0, lambali=False)
    o = tek_oneri(asm, parts, kappa=2.0)
    assert o.L == pytest.approx(40.0, abs=1e-12)
    assert [c.part for c in o.components] == ["ISO 4762 M8x40"]


# ---------------------------------------------------------------- K9 (b) civata + 2 pul + somun
def test_k9_civata_pul_somun():
    """K9: 10 + 15 mm plaka, Ø9 → g = 25, L_min = 25 + 3.2 + 6.8 + 2.5 = 37.5, L = 40; T tablodaki kuralla."""
    asm, parts = civata_montaji()
    o = tek_oneri(asm, parts)
    assert o.kind == "civata_somun"
    assert o.M == "M8"
    assert o.grip == pytest.approx(25.0, abs=1e-9)
    assert o.L == pytest.approx(40.0, abs=1e-12)
    assert o.stack == (DelikRef("ust", 0), DelikRef("alt", 0))
    assert sorted(c.part for c in o.components) == sorted(
        ["ISO 4017 M8x40", "ISO 7089 M8", "ISO 7089 M8", "ISO 4032 M8"]
    )
    a = ASAGI
    o0 = np.array([0.0, 0.0, 25.0])  # ilk deliğin girişi
    x_son = np.array([0.0, 0.0, 0.0])  # son deliğin çıkışı
    h = 1.6
    (civata,) = bilesen(o, "ISO 4017 M8x40")
    T_ayni(civata.T, transform(rodrigues(-YUKARI, a), o0 - h * a), atol=1e-12)
    (somun,) = bilesen(o, "ISO 4032 M8")
    T_ayni(somun.T, transform(rodrigues(YUKARI, a), x_son + h * a), atol=1e-12)
    pullar = bilesen(o, "ISO 7089 M8")
    beklenen = [transform(rodrigues(YUKARI, -a), o0), transform(rodrigues(YUKARI, a), x_son)]
    # pulların sırası şart değil: her beklenen T'ye tam bir pul uyar
    for Tb in beklenen:
        uyan = [p for p in pullar if np.allclose(p.T, Tb, atol=1e-12)]
        assert len(uyan) == 1
    assert all(c.fixed is False for c in o.components)


def test_k9_kisitlar_ve_dof_dort_artiyor():
    """K9: 4 parça × (CONCENTRIC + COINCIDENT) = 8 kısıt; artık ≤ 1e-9; dof tam 4 artar."""
    asm, parts = civata_montaji()
    o = tek_oneri(asm, parts)
    assert len(o.mates) == 8
    assert sum(m.kind is MateKind.CONCENTRIC for m in o.mates) == 4
    assert sum(m.kind is MateKind.COINCIDENT for m in o.mates) == 4
    yeni = uygula(asm, [o])
    assert max_artik(yeni) <= 1e-9
    assert dof(yeni) - dof(asm) == 4


def test_k9_ters_yonlu_delik_ve_bilesen_sirasi():
    """K9: hepsi düz geçişse yön ilk bileşenin deliğinden; ters kayıtlı delik çevrilir, sonuç aynı."""
    E4 = np.eye(4)
    asm, parts = montaj(
        ("ust", E4, [gecis(E4, (0, 0, 25), 10)], True),
        ("alt", E4, [gecis(E4, (0, 0, 0), 15, a=YUKARI)], True),  # alttan kayıtlı
    )
    o = tek_oneri(asm, parts)
    assert o.kind == "civata_somun"
    assert o.grip == pytest.approx(25.0, abs=1e-9)
    assert o.L == pytest.approx(40.0, abs=1e-12)
    assert o.stack == (DelikRef("ust", 0), DelikRef("alt", 0))
    (civata,) = bilesen(o, "ISO 4017 M8x40")
    T_ayni(civata.T, transform(np.eye(3), (0, 0, 26.6)), atol=1e-12)


# ---------------------------------------------------------------- K10 eşleşmeme kodları
def _iki(ust_delikler, alt_delikler, T_ust=None, T_alt=None):
    T_ust = np.eye(4) if T_ust is None else T_ust
    T_alt = np.eye(4) if T_alt is None else T_alt
    return montaj(("ust", T_ust, ust_delikler, True), ("alt", T_alt, alt_delikler, True))


I4 = np.eye(4)
SENARYOLAR = {
    # aynı bileşenden iki delik (bitişik, ölçüleri uygun)
    "ayni_bilesen": lambda: _iki(
        [gecis(I4, (0, 0, 20), 5), gecis(I4, (0, 0, 15), 5)], [disli(I4, (0, 0, 10))]
    ),
    # lambalı delik −Z, dişli delik +Z: çelişen yön
    "yon": lambda: _iki([lamba(I4, (0, 0, 20), 10)], [disli(I4, (0, 0, -20), a=YUKARI)]),
    # 0.5 mm aralık
    "bosluk": lambda: _iki([gecis(I4, (0, 0, 10.5), 10)], [disli(I4, (0, 0, 0))]),
    # son olmayan delik kör
    "kor_ara": lambda: _iki(
        [delik(I4, (0, 0, 10), d=9.0, depth=10.0, through=False)], [disli(I4, (0, 0, 0))]
    ),
    # M6 geçiş + M8 diş
    "olcu_uyusmuyor": lambda: _iki([gecis(I4, (0, 0, 10), 10, d=6.6)], [disli(I4, (0, 0, 0))]),
    # M8x1 ince hatve
    "ince_hatve": lambda: _iki([gecis(I4, (0, 0, 10), 10)], [disli(I4, (0, 0, 0), thread="M8x1", pitch=1.0)]),
    # havşalı ilk delik
    "havsa": lambda: _iki(
        [delik(I4, (0, 0, 10), d=9.0, depth=10.0, through=True, csk_d=16.0, csk_angle=90.0)],
        [disli(I4, (0, 0, 0))],
    ),
    # lamba Ø12 < d_k 13
    "bas_sigmiyor": lambda: _iki([lamba(I4, (0, 0, 10), 10, cbore_d=12.0)], [disli(I4, (0, 0, 0))]),
    # lambalı ilk + dişsiz boydan boya son
    "lamba_somun": lambda: _iki([lamba(I4, (0, 0, 25), 10)], [gecis(I4, (0, 0, 15), 15)]),
    # diş derinliği 5: L = 30 > L_maks = 25
    "dis_yetersiz": lambda: _iki([gecis(I4, (0, 0, 20), 20)], [disli(I4, (0, 0, 0), thread_depth=5.0)]),
    # 300 mm paket: L_min = 312.5 > 80
    "uzunluk_yok": lambda: _iki([gecis(I4, (0, 0, 300), 150)], [gecis(I4, (0, 0, 150), 150)]),
}


@pytest.mark.parametrize("neden", sorted(SENARYOLAR))
def test_k10_eslesmeme_kodlari(neden):
    """K10: her senaryo tek bir eşleşmeme ve doğru kod verir; grup bütün delikleri içerir."""
    asm, parts = SENARYOLAR[neden]()
    e = tek_neden(asm, parts)
    assert e.neden == neden
    beklenen = {DelikRef(c.name, i) for c in asm.components for i in range(len(parts[c.part].holes))}
    assert set(e.stack) == beklenen


def test_k10_olcu_uyusmuyor_iso273_disinda():
    """K10: hiçbir ISO 273 aralığına girmeyen geçiş çapı (Ø8) → olcu_uyusmuyor."""
    asm, parts = _iki([gecis(I4, (0, 0, 25), 10, d=8.0)], [gecis(I4, (0, 0, 15), 15, d=8.0)])
    assert tek_neden(asm, parts).neden == "olcu_uyusmuyor"


def test_k10_ortada_dis():
    """K10: dişli delik dizinin son deliği değil → ortada_dis."""
    asm, parts = montaj(
        ("ust", I4, [gecis(I4, (0, 0, 30), 10)], True),
        ("orta", I4, [disli(I4, (0, 0, 20), depth=10.0, thread_depth=10.0, through=True)], True),
        ("alt", I4, [gecis(I4, (0, 0, 10), 10)], True),
    )
    e = tek_neden(asm, parts)
    assert e.neden == "ortada_dis"
    assert set(e.stack) == {DelikRef("ust", 0), DelikRef("orta", 0), DelikRef("alt", 0)}


def test_k10_oneri_ve_eslesmeme_birlikte():
    """K10: her grup ya bir Oneri ya bir Eslesmeme üretir (aynı montajda ikisi birlikte)."""
    asm, parts = _iki(
        [lamba(I4, (0, 0, 10), 10), gecis(I4, (50, 0, 10.5), 10)],
        [disli(I4, (0, 0, 0)), disli(I4, (50, 0, 0))],
    )
    oneriler, eslesmeme = oner(asm, parts)
    assert [o.stack for o in oneriler] == [(DelikRef("ust", 0), DelikRef("alt", 0))]
    assert [(e.neden, set(e.stack)) for e in eslesmeme] == [
        ("bosluk", {DelikRef("ust", 1), DelikRef("alt", 1)})
    ]


# ---------------------------------------------------------------- K11 uygula
def iki_vidali():
    """İki lambalı delik (x = ±20) + iki dişli delik; montajda zaten sabit bir 'vida_1' var."""
    asm, parts = _iki(
        [lamba(I4, (-20, 0, 10), 10), lamba(I4, (20, 0, 10), 10)],
        [disli(I4, (-20, 0, 0)), disli(I4, (20, 0, 0))],
    )
    asm.components.append(
        Component(name="vida_1", part="ISO 4762 M8x12", T=transform(None, (100, 0, 0)), fixed=True)
    )
    parts["ISO 4762 M8x12"] = SahteParca(())
    return asm, parts


def test_k11_uygula_girdiyi_degistirmez_ve_adlar():
    """K11: girdi montaj değişmez; yeni adlar tekil, mevcut 'vida_1' varken vida_2, vida_3."""
    asm, parts = iki_vidali()
    once = asm.to_dict()
    oneriler, eslesmeme = oner(asm, parts)
    assert eslesmeme == []
    assert len(oneriler) == 2
    yeni = uygula(asm, oneriler)
    assert asm.to_dict() == once
    adlar = [c.name for c in yeni.components]
    assert len(adlar) == len(set(adlar))
    assert adlar[: len(asm.components)] == [c.name for c in asm.components]
    eklenen = yeni.components[len(asm.components) :]
    assert sorted(c.name for c in eklenen) == ["vida_2", "vida_3"]
    assert all(c.fixed is False for c in eklenen)
    assert all(c.part == "ISO 4762 M8x12" for c in eklenen)
    assert len(yeni.mates) == len(asm.mates) + 4


def test_k11_uygula_gecerli_cozulmus_ve_serilesiyor():
    """K11: validate geçer; solve 0 iterasyonla döner; to_dict / from_dict gidiş-dönüşü eşit."""
    asm, parts = iki_vidali()
    oneriler, _ = oner(asm, parts)
    yeni = uygula(asm, oneriler)
    yeni.validate()
    sonuc = solve(yeni)
    assert sonuc.iterations == 0
    assert max_artik(yeni) <= 1e-9
    d = yeni.to_dict()
    assert Assembly.from_dict(d).to_dict() == d


def test_k11_civata_ad_kurali():
    """K11: (b) önerisinde ad kuralı civata_1, pul_1, pul_2, somun_1."""
    asm, parts = civata_montaji()
    oneriler, _ = oner(asm, parts)
    yeni = uygula(asm, oneriler)
    eklenen = {c.name: c.part for c in yeni.components[len(asm.components) :]}
    assert eklenen == {
        "civata_1": "ISO 4017 M8x40",
        "pul_1": "ISO 7089 M8",
        "pul_2": "ISO 7089 M8",
        "somun_1": "ISO 4032 M8",
    }
    yeni.validate()
    assert solve(yeni).iterations == 0


def test_k11_bos_oneri_listesi():
    """K11: boş öneri listesi → aynı içerikli yeni montaj."""
    asm, parts = vida_montaji()
    yeni = uygula(asm, [])
    assert yeni is not asm
    assert yeni.to_dict() == asm.to_dict()


@pytest.mark.occt
def test_k11_eklenen_parcalar_kuruluyor():
    """K11: eklenen her Component.part için parca(...) kuruluyor ve adı tanımla aynı."""
    from geometry.standart.parcalar import parca

    for asm, parts in (iki_vidali(), civata_montaji()):
        oneriler, _ = oner(asm, parts)
        yeni = uygula(asm, oneriler)
        for c in yeni.components[len(asm.components) :]:
            assert parca(c.part).name == c.part


# ---------------------------------------------------------------- K12 rijit hareket değişmezliği
def _tasi(asm: Assembly, G: np.ndarray) -> Assembly:
    return Assembly(
        name=asm.name,
        components=[Component(c.name, c.part, G @ c.T, c.fixed) for c in asm.components],
        mates=list(asm.mates),
    )


G_KEYFI = transform(rot_z(23) @ rot_x(31) @ rot_y(-17), (12.5, -40.0, 7.25))
# Dönme ekseni dizi eksenine (Z) dik: en küçük dönme R(u → G u) = G olduğundan T'ler tam G·T olur
G_DIK = transform(rot_x(37), (-3.0, 8.0, 55.0))


@pytest.mark.parametrize("kur", [vida_montaji, civata_montaji], ids=["vida", "civata_somun"])
def test_k12_keyfi_rijit_hareket(kur):
    """K12: keyfi G ile aynı tür, M, L, g, dizi; eklenen parçaların konumu G·t ve ekseni G·(R e_z)."""
    asm, parts = kur()
    o = tek_oneri(asm, parts)
    o2 = tek_oneri(_tasi(asm, G_KEYFI), parts)
    assert (o2.kind, o2.M, o2.stack) == (o.kind, o.M, o.stack)
    assert o2.L == pytest.approx(o.L, abs=1e-12)
    assert o2.grip == pytest.approx(o.grip, abs=1e-9)
    assert sorted(c.part for c in o2.components) == sorted(c.part for c in o.components)
    Rg = G_KEYFI[:3, :3]
    for c in o.components:
        G_T = G_KEYFI @ c.T
        uyan = [
            c2
            for c2 in o2.components
            if c2.part == c.part
            and np.allclose(c2.T[:3, 3], G_T[:3, 3], atol=1e-9)
            and np.allclose(c2.T[:3, 2], Rg @ c.T[:3, 2], atol=1e-9)
        ]
        assert len(uyan) >= 1
    yeni = uygula(_tasi(asm, G_KEYFI), [o2])
    assert max_artik(yeni) <= 1e-9


@pytest.mark.parametrize("kur", [vida_montaji, civata_montaji], ids=["vida", "civata_somun"])
def test_k12_eklenen_T_ler_G_T(kur):
    """K12: dizi eksenine dik eksenli G ile eklenen T'ler tam G·T (1e-9)."""
    asm, parts = kur()
    o = tek_oneri(asm, parts)
    o2 = tek_oneri(_tasi(asm, G_DIK), parts)
    assert (o2.kind, o2.M, o2.L) == (o.kind, o.M, o.L)
    for c in o.components:
        G_T = G_DIK @ c.T
        uyan = [c2 for c2 in o2.components if c2.part == c.part and np.allclose(c2.T, G_T, atol=1e-9)]
        assert len(uyan) == 1


# ---------------------------------------------------------------- K13 hatalar
def test_k13_parts_ta_olmayan_kimlik():
    """K13: montajdaki parça kimliği parts'ta yoksa AssyError."""
    asm, parts = vida_montaji()
    del parts["p_taban"]
    with pytest.raises(AssyError):
        oner(asm, parts)
    with pytest.raises(AssyError):
        eksen_gruplari(asm, parts)


@pytest.mark.parametrize("kappa", [0.0, -1.0])
def test_k13_kappa_pozitif_olmali(kappa):
    """K13: κ ≤ 0 → AssyError."""
    asm, parts = vida_montaji()
    with pytest.raises(AssyError):
        oner(asm, parts, kappa=kappa)


@pytest.mark.parametrize("tol", [0.0, -1e-3])
def test_k13_tol_pozitif_olmali(tol):
    """K13: tol ≤ 0 → AssyError."""
    asm, parts = vida_montaji()
    with pytest.raises(AssyError):
        oner(asm, parts, tol=tol)
    with pytest.raises(AssyError):
        eksen_gruplari(asm, parts, tol=tol)


def test_k13_uygula_bilinmeyen_bilesen():
    """K13: öneri, montajda olmayan bir bileşenin deliğine bağlıysa uygula AssyError verir."""
    asm, parts = vida_montaji()
    o = tek_oneri(asm, parts)
    baska = Assembly(name="baska", components=[asm.component("taban")])  # plaka yok
    with pytest.raises(AssyError):
        uygula(baska, [o])


def test_mate_referanslari_yerel_cerceve_dunyada_dogru():
    """Teori: delikli parçada eksen referansı dünyada dizi eksenine, vida baş altı oturma noktasına düşer."""
    asm, parts = vida_montaji()
    yeni = uygula(asm, [tek_oneri(asm, parts)])
    x, y = XY
    for m in yeni.mates[len(asm.mates) :]:
        for ref in (m.a, m.b):
            p, n = yeni.world(ref)
            if ref.kind is RefKind.AXIS:
                assert abs(abs(n @ ASAGI) - 1.0) <= 1e-12
                assert math.hypot(p[0] - x, p[1] - y) <= 1e-9
            else:
                assert p[2] == pytest.approx(1.4, abs=1e-9)  # oturma düzlemi = lamba tabanı
