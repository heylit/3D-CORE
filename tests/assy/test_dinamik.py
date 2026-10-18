"""SPEC 69 — assy/dinamik.py testleri (OCCT'siz): ters dinamik, sürücü torku, eklem tepkileri, güç dengesi,
fazla kısıt, sürücü sayısı ve hatalar (K1–K6, K8, K9).

Testler yalnız specs/69-mekanizma-dinamigi.md teorisi ve arayüzünden yazıldı; assy/dinamik.py gövdesi
okunmadı. Montajlar SPEC 33 eklemleriyle (Assembly(joints=[...])) kurulur; kütleler Kutle ile elle verilir.

Kapalı formlar (SPEC 69 "Kapalı formüllü referanslar"):
- Krank–biyel: x = r cos θ + √(l² − r² sin² θ); dx/dθ = −r s − r² s c / S; d²x/dθ² = −r c − r²(c² − s²)/S −
  r⁴s²c²/S³ (S = √(l² − r² s²)); ẋ = ω dx/dθ, ẍ = ω² d²x/dθ² (sabit ω); τ = m ẍ dx/dθ
  (kütlesiz krank ve biyel, g = 0).
- Sürülen sarkaç (düzgün çubuk, pim ucundan): I = m L²/3, τ = I θ̈ + m g (L/2) sin θ; sabit ω'da pim
  tepkisinin radyal bileşeni m ω² L/2 + m g cos θ.
- Güç dengesi: Σ τ q̇ = dE_k/dt + dV_g/dt − P_dış.

Varsayımlar (SPEC'te açık değil, makul varsayılan):
- Güç dengesinde döner sürücü hızı rad/s (q derece verilir): τ [N·mm] · q̇ [rad/s] = N·mm/s; `guc` = Σ τ q̇.
- `tork` işareti güç dengesinden: sürücünün q yönünde verdiği tork / kuvvet (τ q̇ > 0 → mekanizmaya güç
  girer).
- Eklem tepkisinin hangi gövdeye etkidiği (a'dan b'ye ya da tersi) SPEC'te yok: tepki kuvveti testlerde bir
  eklem için tüm zamanlarda tek bir işaretle (±) karşılaştırılır.
- `dis_kuvvetler[bilesen](t) → (F, M)` dünya çerçevesinde, kütle merkezine etkir (testte yalnız dönmeyen
  pistonda kullanılır: uygulama noktası sonucu etkilemez).
- `en_kotu(ad)` bilinmeyen ad → ModelError.
- `Surucu.tablo` scipy CubicSpline varsayılanıyla (not-a-knot): kübik polinomu kesin üretir.
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" (xfail) sayılır.
"""

from __future__ import annotations

import copy
import math
import re
import subprocess
import sys

import numpy as np
import pytest

from assy.dinamik import DinamikSonuc, Kutle, Surucu, ters_dinamik
from assy.kinematik import drive, mobility
from assy.model import Assembly, AssyError, Component, Joint, JointKind, Ref, RefKind, rot_z, transform
from core.model import ModelError

REV, PRI, CYL, SPH = JointKind.REVOLUTE, JointKind.PRISMATIC, JointKind.CYLINDRICAL, JointKind.SPHERICAL
SIFIR_G = (0.0, 0.0, 0.0)

# ---------- Yardımcılar ----------


def eksen(comp: str, o=(0.0, 0.0, 0.0), z=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, o, z)


def nokta(comp: str, o) -> Ref:
    return Ref(comp, RefKind.POINT, o)


def bilesen(name: str, T=None, fixed: bool = False) -> Component:
    return Component(name=name, part=name, T=np.eye(4) if T is None else T, fixed=fixed)


def montaj(components, joints) -> Assembly:
    return Assembly(name="mekanizma", components=list(components), mates=[], joints=list(joints))


def kutlesiz() -> Kutle:
    """K2: kütlesiz bağlantı (m = 1e-12, J ≈ 0 ama pozitif tanımlı)."""
    return Kutle(1e-12, np.zeros(3), 1e-12 * np.eye(3))


def snapshot(asm: Assembly) -> dict[str, np.ndarray]:
    return {c.name: c.T.copy() for c in asm.components}


def yakin(a, b, rel: float, abs_: float) -> None:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    hata = np.abs(a - b)
    sinir = rel * np.abs(b) + abs_
    assert np.all(hata <= sinir), f"en büyük hata {np.max(hata - sinir):.3e} (sınırın üstünde)"


def isaretli_esit(a, b, rel: float, abs_: float) -> None:
    """a = b ya da a = −b (tek işaret, tüm seri için)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    s = 1.0 if np.sum(np.abs(a - b)) <= np.sum(np.abs(a + b)) else -1.0
    yakin(a, s * b, rel, abs_)


# ---------- Krank–biyel (SPEC 69 örneği) ----------

R_K, L_B = 50.0, 200.0  # mm
M_P = 0.002  # t (2 kg)
OMEGA = 100.0  # rad/s
HIZ = math.degrees(OMEGA)  # derece/s


def piston_x(theta, r: float = R_K, l: float = L_B):  # noqa: E741 (formüldeki sembol)
    t = np.radians(theta)
    return r * np.cos(t) + np.sqrt(l * l - (r * np.sin(t)) ** 2)


def dx_dtheta(theta, r: float = R_K, l: float = L_B):  # noqa: E741
    t = np.radians(theta)
    s, c = np.sin(t), np.cos(t)
    S = np.sqrt(l * l - (r * s) ** 2)
    return -r * s - r * r * s * c / S


def d2x_dtheta2(theta, r: float = R_K, l: float = L_B):  # noqa: E741
    t = np.radians(theta)
    s, c = np.sin(t), np.cos(t)
    S = np.sqrt(l * l - (r * s) ** 2)
    return -r * c - r * r * (c * c - s * s) / S - r**4 * s * s * c * c / S**3


def krank_biyel(theta: float = 0.0, r: float = R_K, l: float = L_B) -> Assembly:  # noqa: E741
    """θ'da kapalı formla kurulmuş krank–biyel, düzlem z = 0, piston x ekseninde (SPEC 33 testleriyle aynı
    kurgu).

    krank: orijinde döner, pim yerelde (r, 0, 0); biyel: yerel orijin A'da, öbür pim (l, 0, 0);
    piston: yerel orijin (x, 0, 0), zemine x boyunca PRISMATIC (s = x).
    """
    t = math.radians(theta)
    A = np.array([r * math.cos(t), r * math.sin(t), 0.0])
    x = float(piston_x(theta, r, l))
    phi = math.degrees(math.atan2(-A[1], x - A[0]))
    comps = [
        bilesen("zemin", fixed=True),
        bilesen("krank", T=transform(rot_z(theta))),
        bilesen("biyel", T=transform(rot_z(phi), A)),
        bilesen("piston", T=transform(t=(x, 0.0, 0.0))),
    ]
    ex = (1.0, 0.0, 0.0)
    joints = [
        Joint("J_krank", REV, eksen("zemin"), eksen("krank")),
        Joint("J_A", REV, eksen("krank", (r, 0, 0)), eksen("biyel")),
        Joint("J_B", REV, eksen("biyel", (l, 0, 0)), eksen("piston")),
        Joint("J_kayar", PRI, eksen("zemin", z=ex), eksen("piston", z=ex)),
    ]
    return montaj(comps, joints)


THETA72 = 5.0 * np.arange(72)  # θ ∈ [0, 360), 72 nokta
T72 = THETA72 / HIZ


def kb_kutleler(m_piston: float = M_P) -> dict[str, Kutle]:
    return {
        "krank": kutlesiz(),
        "biyel": kutlesiz(),
        "piston": Kutle(m_piston, np.zeros(3), m_piston * np.eye(3)),
    }


def kb_coz(**kw) -> tuple[Assembly, DinamikSonuc]:
    asm = krank_biyel(0.0)
    res = ters_dinamik(
        asm, kw.pop("kutleler", kb_kutleler()), [Surucu.sabit_hiz("J_krank", 0.0, HIZ)], T72, **kw
    )
    return asm, res


# ---------- Surucu ve sonuç yapısı ----------


def test_surucu_sabit_hiz():
    s = Surucu.sabit_hiz("J", 12.0, 30.0)
    assert s.joint == "J"
    for t in (0.0, 0.5, 2.0):
        assert s.q(t) == pytest.approx(12.0 + 30.0 * t, abs=1e-12)


def test_surucu_tablo_kubik_spline():
    """Not-a-knot kübik spline kübik polinomu kesin üretir: q(t) = t³ − 2t + 5."""
    t = np.linspace(0.0, 2.0, 9)
    s = Surucu.tablo("J", t, t**3 - 2 * t + 5)
    assert s.joint == "J"
    for tt in (0.0, 0.13, 0.77, 1.5, 2.0):
        assert s.q(tt) == pytest.approx(tt**3 - 2 * tt + 5, abs=1e-12)


def test_sonuc_yapisi_ve_girdi_degismez():
    asm = krank_biyel(0.0)
    once = snapshot(asm)
    res = ters_dinamik(asm, kb_kutleler(), [Surucu.sabit_hiz("J_krank", 0.0, HIZ)], T72, g=SIFIR_G)
    assert all(np.array_equal(asm.component(n).T, T) for n, T in once.items())
    s = len(T72)
    np.testing.assert_allclose(res.t, T72, rtol=0, atol=0)
    assert set(res.tork) == {"J_krank"}
    assert res.tork["J_krank"].shape == (s,)
    for j in ("J_krank", "J_A", "J_B", "J_kayar"):
        assert res.q[j].shape == (s,)
        assert res.eklem_kuvveti[j].shape == (s, 3)
        assert res.eklem_momenti[j].shape == (s, 3)
    assert res.guc.shape == (s,)
    # düzlemsel krank–biyel döner eklemlerle uzayda fazla kısıtlıdır (SPEC 33 mobility: redundant 3)
    assert mobility(asm).redundant > 0
    assert res.belirsiz is True


# ---------- K1 kinematik türevler ----------


def test_k1_konum_kapali_form():
    _, res = kb_coz(g=SIFIR_G)
    yakin(res.q["J_krank"], THETA72, 0.0, 1e-9)
    yakin(res.q["J_kayar"], piston_x(THETA72), 0.0, 1e-9)


def test_k1_hiz_dis_kuvvet_sondasi():
    """ẋ: pistona sabit F = −F0 x̂ (dış kuvvet), tüm kütleler ihmal edilebilir. Güç dengesi τ θ̇ = −P_dış =
    F0 ẋ
    → ẋ = τ ω / F0; kapalı form ẋ = ω dx/dθ ile göreli 1e-8. (Atalet katkısı ≈ 1e-12·ẍ·dx/dθ ≪ 1e-8·τ.)"""
    F0 = 1000.0
    dis = {"piston": lambda t: (np.array([-F0, 0.0, 0.0]), np.zeros(3))}
    kut = {"krank": kutlesiz(), "biyel": kutlesiz(), "piston": kutlesiz()}
    _, res = kb_coz(kutleler=kut, g=SIFIR_G, dis_kuvvetler=dis)
    xdot = res.tork["J_krank"] * OMEGA / F0
    yakin(xdot, OMEGA * dx_dtheta(THETA72), 1e-8, 1e-8 * R_K * OMEGA)


def test_k1_ivme_piston_kutlesinden():
    """ẍ = τ / (m dx/dθ) (kütlesiz krank / biyel, g = 0); |dx/dθ| ≥ 0.2 r noktalarında göreli 1e-6."""
    _, res = kb_coz(g=SIFIR_G)
    dxd = dx_dtheta(THETA72)
    secim = np.abs(dxd) >= 0.2 * R_K
    xdd = res.tork["J_krank"][secim] / (M_P * dxd[secim])
    yakin(xdd, OMEGA**2 * d2x_dtheta2(THETA72[secim]), 1e-6, 0.0)


# ---------- K2 krank–biyel torku ----------


def test_k2_krank_biyel_torku():
    _, res = kb_coz(g=SIFIR_G)
    tau = M_P * OMEGA**2 * d2x_dtheta2(THETA72) * dx_dtheta(THETA72)  # τ = m ẍ dx/dθ
    yakin(res.tork["J_krank"], tau, 1e-6, 1e-6 * M_P * R_K * OMEGA**2 * R_K)
    # SPEC örneği: θ = 90°: dx/dθ = −r, d²x/dθ² = r²/√(l² − r²) → τ = −m ω² r³/√(l² − r²)
    k = int(np.argmin(np.abs(THETA72 - 90.0)))
    tau90 = -M_P * OMEGA**2 * R_K**3 / math.sqrt(L_B**2 - R_K**2)
    assert res.tork["J_krank"][k] == pytest.approx(tau90, rel=1e-6)


# ---------- K3 sarkaç ----------

M_S, L_S = 0.001, 300.0  # t, mm
G_S = 9810.0
I_S = M_S * L_S**2 / 3  # pim ucuna göre
OM_S = 2.0  # rad/s


def sarkac(cift: bool = False, limits=None) -> Assembly:
    """Zemin + çubuk, REVOLUTE eksen z orijinde. Çubuk yerel +x boyunca; θ = 0'da g yönünde (g = +x, "aşağı").

    cift=True: aynı eksende ikinci döner eklem (z = 50'de), fazla kısıtlı menteşe (K5)."""
    joints = [Joint("J", REV, eksen("zemin"), eksen("cubuk"), limits=limits)]
    if cift:
        joints.append(Joint("J2", REV, eksen("zemin", (0, 0, 50)), eksen("cubuk", (0, 0, 50))))
    return montaj([bilesen("zemin", fixed=True), bilesen("cubuk")], joints)


def cubuk_kutle() -> dict[str, Kutle]:
    """Düzgün ince çubuk: c = (L/2, 0, 0); J_c = diag(ε, mL²/12, mL²/12) (eksenel ε > 0: pozitif tanımlı)."""
    J = np.diag([M_S * L_S**2 * 1e-4, M_S * L_S**2 / 12, M_S * L_S**2 / 12])
    return {"cubuk": Kutle(M_S, np.array([L_S / 2, 0.0, 0.0]), J)}


G_VEK = (G_S, 0.0, 0.0)
TH_S = np.linspace(0.0, 350.0, 36)
T_S = np.radians(TH_S) / OM_S


def sarkac_sabit(cift: bool = False) -> DinamikSonuc:
    sur = [Surucu.sabit_hiz("J", 0.0, math.degrees(OM_S))]
    return ters_dinamik(sarkac(cift), cubuk_kutle(), sur, T_S, g=G_VEK)


def test_k3_sarkac_sabit_hiz_tork_ve_radyal_tepki():
    res = sarkac_sabit()
    assert res.belirsiz is False
    th = np.radians(TH_S)
    olcek = M_S * G_S * L_S / 2
    yakin(res.tork["J"], olcek * np.sin(th), 1e-6, 1e-6 * olcek)  # θ̈ = 0
    # pim tepkisi (eklemin a çerçevesi = dünya: zemin özdeş, eksen z, sıfır yönü x)
    e_r = np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)])
    a_c = -(OM_S**2) * (L_S / 2) * e_r
    F_ref = M_S * a_c - M_S * np.array(G_VEK)  # çubuğa pimden etkiyen kuvvet: m a = F + m g
    F = res.eklem_kuvveti["J"]
    radyal = M_S * OM_S**2 * L_S / 2 + M_S * G_S * np.cos(th)  # F·(−e_r)
    olcek_F = M_S * (OM_S**2 * L_S / 2 + G_S)
    isaretli_esit(np.einsum("ij,ij->i", F, -e_r), radyal, 1e-6, 1e-6 * olcek_F)
    isaretli_esit(F, F_ref, 1e-6, 1e-6 * olcek_F)


def test_k3_sarkac_sinus_suruş():
    """θ = 30° sin(2πt): τ = I θ̈ + m g L/2 sin θ."""
    A = math.radians(30.0)
    w = 2 * math.pi
    sur = [Surucu("J", lambda t: 30.0 * math.sin(w * t))]
    t = np.linspace(0.0, 1.0, 41)
    res = ters_dinamik(sarkac(), cubuk_kutle(), sur, t, g=G_VEK)
    th = A * np.sin(w * t)
    thdd = -A * w * w * np.sin(w * t)
    tau = I_S * thdd + M_S * G_S * L_S / 2 * np.sin(th)
    yakin(res.tork["J"], tau, 1e-6, 1e-6 * np.max(np.abs(tau)))
    # güç dengesi (K4): τ θ̇ = d/dt(½ I θ̇²) + d/dt(−m g L/2 cos θ)
    thd = A * w * np.cos(w * t)
    P = (I_S * thdd + M_S * G_S * L_S / 2 * np.sin(th)) * thd
    yakin(res.guc, P, 1e-6, 1e-6 * np.max(np.abs(P)))


# ---------- K4 güç dengesi ----------


def test_k4_guc_dengesi_krank_biyel():
    """Kütlesiz krank / biyel: Σ τ q̇ = dE_k/dt = m ẋ ẍ; guc = τ ω."""
    _, res = kb_coz(g=SIFIR_G)
    P = M_P * OMEGA * dx_dtheta(THETA72) * OMEGA**2 * d2x_dtheta2(THETA72)
    olcek = 1e-6 * M_P * R_K**2 * OMEGA**3
    yakin(res.guc, P, 1e-6, olcek)
    yakin(res.tork["J_krank"] * OMEGA, P, 1e-6, olcek)


def test_k4_guc_dengesi_krank_biyel_kutleli_baglantilar():
    """Kütleli krank ve biyel, yerçekimi düzleme dik (iş yapmaz): guc = τ ω = dE_k/dt (referans: K4 genel)."""
    kut = {
        "krank": Kutle(0.0005, np.array([R_K / 2, 0.0, 0.0]), np.diag([1e-3, 0.1, 0.1])),
        "biyel": Kutle(0.001, np.array([L_B / 2, 0.0, 0.0]), np.diag([1e-3, 3.0, 3.0])),
        "piston": Kutle(M_P, np.zeros(3), M_P * np.eye(3)),
    }
    asm = krank_biyel(0.0)
    hiz = math.degrees(10.0)
    th = np.linspace(0.0, 330.0, 12)
    res = ters_dinamik(asm, kut, [Surucu.sabit_hiz("J_krank", 0.0, hiz)], th / hiz, g=(0.0, 0.0, -9810.0))
    P = guc_referans(asm, kut, "J_krank", th, hiz, (0.0, 0.0, -9810.0))
    yakin(res.guc, P, 0.0, 1e-6 * np.max(np.abs(P)))
    yakin(res.tork["J_krank"] * math.radians(hiz), P, 0.0, 1e-6 * np.max(np.abs(P)))


def test_k4_guc_dengesi_sarkac():
    res = sarkac_sabit()
    P = M_S * G_S * L_S / 2 * np.sin(np.radians(TH_S)) * OM_S  # dV/dt, E_k sabit
    yakin(res.guc, P, 1e-6, 1e-6 * M_S * G_S * L_S / 2 * OM_S)


def _vee(S: np.ndarray) -> np.ndarray:
    S = (S - S.T) / 2
    return np.array([S[2, 1], S[0, 2], S[1, 0]])


def _sur(asm: Assembly, surucu: str, deger: float) -> None:
    """SPEC 33 drive, önce sıkı tol; artık 1e-11 altına inmezse gevşek tol (referans gürültüsü yine ≪
    1e-6)."""
    for tol in (1e-11, 1e-10, 1e-9):
        try:
            drive(asm, {surucu: deger}, tol=tol).apply(asm)
            return
        except AssyError:
            if tol == 1e-9:
                raise


def guc_referans(asm, kutleler, surucu: str, theta, hiz: float, g) -> np.ndarray:
    """dE_k/dt + dV_g/dt bağımsız referans: SPEC 33 `drive` ile θ ± k·hiz·h konumları, 4. dereceden merkezi
    farkla
    v_c, a_c, ω, ω̇; d/dt(½ m v² + ½ ωᵀ J_w ω − m g·c) = Σ m v·a + ω·J_w ω̇ − m g·v
    (ω × J_w ω ⊥ ω olduğundan d/dt(½ωᵀJ_wω) = ω·J_w ω̇). Taban konum θ ızgarasında sırayla ilerler.
    Adım ω h = 0.02 rad: kesme hatası O((ωh)⁴), drive artığı (1e-11) gürültüsü / h² ile dengeli."""
    g = np.asarray(g, dtype=float)
    om = math.radians(hiz)
    h = 0.02 / om
    taban = copy.deepcopy(asm)
    out = []
    for th in theta:
        _sur(taban, surucu, float(th))
        poz = {}
        for k in (-2, -1, 0, 1, 2):
            w = copy.deepcopy(taban)
            _sur(w, surucu, float(th) + math.degrees(om * k * h))
            poz[k] = w
        P = 0.0
        for ad, K in kutleler.items():
            T = {k: poz[k].component(ad).T for k in poz}
            R = {k: T[k][:3, :3] for k in T}
            C = {k: R[k] @ K.c + T[k][:3, 3] for k in T}
            v = (-C[2] + 8 * C[1] - 8 * C[-1] + C[-2]) / (12 * h)
            a = (-C[2] + 16 * C[1] - 30 * C[0] + 16 * C[-1] - C[-2]) / (12 * h * h)
            Rd = (-R[2] + 8 * R[1] - 8 * R[-1] + R[-2]) / (12 * h)
            Rdd = (-R[2] + 16 * R[1] - 30 * R[0] + 16 * R[-1] - R[-2]) / (12 * h * h)
            w_ = _vee(Rd @ R[0].T)
            wd = _vee(Rdd @ R[0].T)  # R̈Rᵀ = [ω̇]× + [ω]×², antisimetrik kısmı [ω̇]×
            Jw = R[0] @ K.J @ R[0].T
            P += K.m * v @ a + w_ @ Jw @ wd - K.m * g @ v
        out.append(P)
    return np.array(out)


# Uzaysal RSCR: krank (R, zemin z), krank–biyel küresel, biyel–kol silindirik, kol (R, zemin y ekseni G'de).
# Kutzbach M = 6·3 − (5 + 3 + 4 + 5) = 1, fazla kısıt yok.
A_U, D_U, H_U, E_U = 20.0, 80.0, 20.0, 50.0


def rscr() -> Assembly:
    """θ = 0'da yaklaşık kurulur: kol ekseni u = (cos ψ, 0, sin ψ) G = (d, 0, h)'den; biyel ekseni u boyunca,
    küresel nokta biyelde (0, e, 0), krankta (a, 0, 0). ψ, A'nın kol doğrusuna uzaklığı e olacak biçimde
    (|A − G|² − ((A − G)·u)² = e²) seçildi; sonra drive ile tam oturtulur."""
    G = np.array([D_U, 0.0, H_U])
    A = np.array([A_U, 0.0, 0.0])
    AG = A - G
    phi = math.atan2(-AG[2], -AG[0])  # −AG·u = |AG_xz| cos(ψ − φ)
    psi = phi + math.acos(math.sqrt(AG @ AG - E_U**2) / math.hypot(AG[0], AG[2]))
    u = np.array([math.cos(psi), 0.0, math.sin(psi)])
    Q = G + (AG @ u) * u
    y = (A - Q) / np.linalg.norm(A - Q)
    Rc = np.column_stack([u, y, np.cross(u, y)])
    ey = np.array([0.0, 1.0, 0.0])
    Rr = np.column_stack([u, ey, np.cross(u, ey)])
    comps = [
        bilesen("zemin", fixed=True),
        bilesen("krank"),
        bilesen("biyel", T=transform(Rc, Q)),
        bilesen("kol", T=transform(Rr, G)),
    ]
    ex, ey_ = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    joints = [
        Joint("J0", REV, eksen("zemin"), eksen("krank")),
        Joint("S", SPH, nokta("krank", (A_U, 0, 0)), nokta("biyel", (0, E_U, 0))),
        Joint("C", CYL, eksen("kol", z=ex), eksen("biyel", z=ex)),
        Joint("J3", REV, eksen("zemin", tuple(G), ey_), eksen("kol", z=ey_)),
    ]
    asm = montaj(comps, joints)
    drive(asm, {"J0": 0.0}, tol=1e-11).apply(asm)
    return asm


RSCR_KUTLE = {
    "krank": Kutle(0.0005, np.array([A_U / 2, 0.0, 0.0]), np.diag([1e-3, 0.02, 0.02])),
    "biyel": Kutle(0.001, np.array([5.0, E_U / 2, 0.0]), np.diag([0.3, 0.1, 0.35])),
    "kol": Kutle(0.0008, np.array([30.0, 0.0, 0.0]), np.diag([0.01, 0.25, 0.25])),
}


def test_k4_guc_dengesi_uzaysal_kuresel_eklemli():
    asm = rscr()
    assert mobility(asm).dof == 1 and mobility(asm).redundant == 0  # kurgu denetimi
    hiz = math.degrees(2.0)
    th = np.linspace(10.0, 340.0, 12)
    g = (0.0, 0.0, -9810.0)
    res = ters_dinamik(asm, RSCR_KUTLE, [Surucu.sabit_hiz("J0", 0.0, hiz)], th / hiz, g=g)
    assert res.belirsiz is False
    P = guc_referans(asm, RSCR_KUTLE, "J0", th, hiz, g)
    olcek = 1e-6 * np.max(np.abs(P))
    yakin(res.guc, P, 0.0, olcek)
    yakin(res.tork["J0"] * math.radians(hiz), P, 0.0, olcek)
    for j in ("J0", "S", "C", "J3"):
        assert np.all(np.isfinite(res.eklem_kuvveti[j]))


# ---------- K5 fazla kısıt ----------


def test_k5_cift_mentese_belirsiz():
    tek = sarkac_sabit()
    cift = sarkac_sabit(cift=True)
    assert cift.belirsiz is True
    olcek = M_S * G_S * L_S / 2
    yakin(cift.tork["J"], tek.tork["J"], 1e-9, 1e-9 * olcek)
    # eksen (z) dışındaki kuvvet bileşenleri: iki eklemin toplamı = tek eklem (a çerçeveleri aynı yönde)
    toplam = cift.eklem_kuvveti["J"][:, :2] + cift.eklem_kuvveti["J2"][:, :2]
    olcek_F = M_S * (OM_S**2 * L_S / 2 + G_S)
    yakin(toplam, tek.eklem_kuvveti["J"][:, :2], 1e-9, 1e-9 * olcek_F)


# ---------- K6 sürücü sayısı ----------


@pytest.mark.parametrize(
    "tanim",
    [[], [("J_krank", 0.0, HIZ), ("J_kayar", 250.0, 0.0)]],
    ids=["sifir", "iki"],
)
def test_k6_surucu_sayisi_mobiliteye_esit_degil(tanim):
    asm = krank_biyel(0.0)
    suruculer = [Surucu.sabit_hiz(*d) for d in tanim]
    with pytest.raises(ModelError) as e:
        ters_dinamik(asm, kb_kutleler(), suruculer, T72[:5], g=SIFIR_G)
    assert re.search(r"(?<![\d.])1(?![\d.])", str(e.value)), "mesajda mobilite değeri (1) yok"


# ---------- en_kotu ----------


def test_en_kotu_tork_ve_eklem_kuvveti():
    _, res = kb_coz(g=SIFIR_G)
    tau = res.tork["J_krank"]
    k = int(np.argmax(np.abs(tau)))
    t_k, v_k = res.en_kotu("J_krank")
    assert t_k == pytest.approx(res.t[k], abs=0)
    assert v_k == pytest.approx(abs(tau[k]), rel=1e-12)
    F = np.linalg.norm(res.eklem_kuvveti["J_A"], axis=1)
    k = int(np.argmax(F))
    t_k, v_k = res.en_kotu("J_A")
    assert t_k == pytest.approx(res.t[k], abs=0)
    assert v_k == pytest.approx(F[k], rel=1e-12)
    with pytest.raises(ModelError):
        res.en_kotu("yok")


# ---------- K8 hatalar ----------


def test_k8_kutlesi_olmayan_hareketli_bilesen():
    kut = kb_kutleler()
    del kut["biyel"]
    with pytest.raises(ModelError):
        ters_dinamik(krank_biyel(0.0), kut, [Surucu.sabit_hiz("J_krank", 0.0, HIZ)], T72[:5], g=SIFIR_G)


@pytest.mark.parametrize(
    "kutle",
    [
        lambda: Kutle(0.001, np.zeros(3), np.diag([1.0, 1.0, -0.5])),  # negatif özdeğer
        lambda: Kutle(0.001, np.zeros(3), np.array([[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]])),
        lambda: Kutle(0.0, np.zeros(3), np.eye(3)),
        lambda: Kutle(-0.001, np.zeros(3), np.eye(3)),
    ],
    ids=["J_negatif", "J_belirsiz", "m_sifir", "m_negatif"],
)
def test_k8_gecersiz_kutle(kutle):
    with pytest.raises(ModelError):
        kut = kb_kutleler()
        kut["biyel"] = kutle()
        ters_dinamik(krank_biyel(0.0), kut, [Surucu.sabit_hiz("J_krank", 0.0, HIZ)], T72[:5], g=SIFIR_G)


@pytest.mark.parametrize("t", [[0.0, 0.002, 0.001], [0.0, 0.001, 0.001]], ids=["azalan", "esit"])
def test_k8_t_artan_degil(t):
    with pytest.raises(ModelError):
        ters_dinamik(krank_biyel(0.0), kb_kutleler(), [Surucu.sabit_hiz("J_krank", 0.0, HIZ)], t, g=SIFIR_G)


def test_k8_eklem_siniri_asimi_33_hatasi():
    """Sarkaç ekleminin sınırı (−45°, 45°); sürüş 60°'ye çıkar → SPEC 33'ün AssyError'ı aynen."""
    sur = [Surucu.sabit_hiz("J", 0.0, 60.0)]
    with pytest.raises(AssyError):
        ters_dinamik(sarkac(limits=(-45.0, 45.0)), cubuk_kutle(), sur, [0.0, 0.5, 1.0], g=G_VEK)


def test_k8_drive_yakinsamiyor_mesajda_eklem():
    """r = 50 > l = 30 krank–biyel θ = 0'da kurulur; θ = 90°'de r sin θ > l → ulaşılamaz konum."""
    asm = krank_biyel(0.0, r=50.0, l=30.0)
    sur = [Surucu.sabit_hiz("J_krank", 0.0, 90.0)]
    with pytest.raises((ModelError, AssyError)) as e:
        ters_dinamik(asm, kb_kutleler(), sur, [0.0, 0.5, 1.0], g=SIFIR_G)
    assert "J_krank" in str(e.value)


# ---------- K9 OCCT bağımsızlığı ----------


def test_k9_dinamik_occt_import_etmez():
    kod = (
        "import sys, assy.dinamik\n"
        "yasak = [m for m in sys.modules if m.split('.')[0] in ('OCP', 'OCC', 'build123d', 'geometry')]\n"
        "print(','.join(yasak))\n"
    )
    out = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
