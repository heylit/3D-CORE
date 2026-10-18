"""
SPEC 47c — Analiz ekranının örnek işleri (uydurma geometri; gizlilik kuralı).

- `delikli_plaka`: 200×100×5 plaka [0,200]×[0,100]×[0,5], merkezde Ø10 delik (100, 50); çelik E = 210000,
  ν = 0.3, Re = 235. Kilitli örnek koşulları: x = 0 yüzü ux; x = 0 ∩ y = 50 düğümleri uy;
  x = 0 ∩ y = 50 ∩ z = 0 düğümü uz; x = 200 yüzüne t = (100, 0, 0) MPa çekme.
  Delik çevresinde `Refine` küresi.
  Analitik: Heywood Kt_g (d/W = 0.1) ve Kirsch σ_xx(y).
- `konsol_kiris`: 200×20×20 çubuk; x = 0 yüzü tam mesnet; x = 200 yüzüne t = (0, 0, −2.5) MPa (P = 1000 N).
  Analitik: δ = P·L³/(3·E·I) ve Timoshenko δ_T.

Rijit cisim kilidinin düzlemleri: ağda y = 50 çizgisinde düğüm olması garanti değildir (gmsh yüzü serbest
ağlar), bu yüzden y = 50 düzleminin toleransı ağ boyunun yarısıdır (`tol_h` = 0.5): x = 0 yüzünde
y = 50'ye en çok h/2 uzaklıktaki düğümler. Kilit yalnız rijit cisim hareketini tutar; yük yolunu değiştirmez.

Parçalar OCCT (build123d) ister; kurucular çağrılınca kurulur, import anında değil.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from core.model import Material
from mesh import Refine
from tezgah.ekranlar._analiz_kopru import (
    TOL_KUTU,
    Analitik,
    AnalizTanimi,
    Egri,
    Kosul,
    Secim,
    heywood_kt,
    kirsch_sxx,
    konsol_sehim,
    timoshenko_sehim,
)

CELIK = Material("celik", E=210_000.0, nu=0.3)


def _duzlem(nokta, normal, L: float) -> dict:
    return {"nokta": [float(v) for v in nokta], "normal": [float(v) for v in normal], "tol": TOL_KUTU * L}


def _kutu(a: float, b: float, c: float):
    import build123d as bd

    return bd.Box(a, b, c, align=(bd.Align.MIN,) * 3)


def delikli_plaka() -> AnalizTanimi:
    """Delikli plaka örneği (seçimler ve kilitli koşullar dahil)."""
    import build123d as bd

    from geometry.part import Part

    W, L_, t, d = 100.0, 200.0, 5.0, 10.0
    r = d / 2.0
    sekil = _kutu(L_, W, t) - bd.Pos(100.0, 50.0, t / 2.0) * bd.Cylinder(r, 2.0 * t)
    parca = Part(sekil, name="delikli_plaka")
    Lk = float(np.linalg.norm([L_, W, t]))
    sol = _duzlem((0, 0, 0), (-1, 0, 0), Lk)
    orta = {"nokta": [0.0, 50.0, 0.0], "normal": [0.0, 1.0, 0.0], "tol_h": 0.5}
    alt = _duzlem((0, 0, 0), (0, 0, -1), Lk)
    secimler = (
        Secim("s1", "duzlem", sol, kilitli=True),
        Secim("s2", "duzlem", {"duzlemler": [sol, orta]}, kilitli=True),
        Secim("s3", "duzlem", {"duzlemler": [sol, orta, alt]}, kilitli=True),
        Secim("s4", "duzlem", _duzlem((L_, 0, 0), (1, 0, 0), Lk), kilitli=True),
    )
    sigma = 100.0
    kosullar = (
        Kosul("k1", "s1", "mesnet", ("ux",), kilitli=True),
        Kosul("k2", "s2", "mesnet", ("uy",), kilitli=True),
        Kosul("k3", "s3", "mesnet", ("uz",), kilitli=True),
        Kosul("k4", "s4", "cekme", (sigma, 0.0, 0.0), kilitli=True),
    )
    analitik = (
        Analitik(
            "Kt_g (Heywood)",
            "(2 + (1 − d/W)³) / (1 − d/W), d/W = 0.1",
            heywood_kt(d / W),
            "",
            "sxx_max",
            sigma,
        ),
        Analitik("σ_xx delik kenarı (Kirsch, sonsuz plaka)", "3σ", float(kirsch_sxx(sigma, r, r)), "MPa"),
    )
    p0, p1 = (100.0, 50.0 + r, t / 2.0), (100.0, W, t / 2.0)
    y = np.linspace(50.0 + r, W, 91)
    egri = Egri(
        "Kirsch σ_xx (sonsuz plaka)",
        p0,
        p1,
        tuple(float(v) for v in y - (50.0 + r)),
        tuple(float(v) for v in kirsch_sxx(sigma, r, y - 50.0)),
    )
    return AnalizTanimi(
        ad="delikli_plaka",
        parca=parca,
        malzeme=CELIK,
        h=5.0,
        Re=235.0,
        refine=(Refine((100.0, 50.0, t / 2.0), 12.0, 1.25),),
        secimler=secimler,
        kosullar=kosullar,
        analitik=analitik,
        egriler=(egri,),
    )


def konsol_kiris() -> AnalizTanimi:
    """Konsol kiriş örneği (seçimler ve kilitli koşullar dahil)."""
    from geometry.part import Part

    L_, b, h = 200.0, 20.0, 20.0
    P = 1000.0
    parca = Part(_kutu(L_, b, h), name="konsol_kiris")
    Lk = float(np.linalg.norm([L_, b, h]))
    secimler = (
        Secim("s1", "duzlem", _duzlem((0, 0, 0), (-1, 0, 0), Lk), kilitli=True),
        Secim("s2", "duzlem", _duzlem((L_, 0, 0), (1, 0, 0), Lk), kilitli=True),
    )
    kosullar = (
        Kosul("k1", "s1", "mesnet", ("ux", "uy", "uz"), kilitli=True),
        Kosul("k2", "s2", "cekme", (0.0, 0.0, -P / (b * h)), kilitli=True),
    )
    E, nu = CELIK.E, CELIK.nu
    analitik = (
        Analitik(
            "Uç sehimi (Euler–Bernoulli)", "P·L³ / (3·E·I)", konsol_sehim(P, L_, E, b, h), "mm", "u_max"
        ),
        Analitik(
            "Uç sehimi (Timoshenko)",
            "P·L³ / (3·E·I) + P·L / (κ·G·A)",
            timoshenko_sehim(P, L_, E, nu, b, h),
            "mm",
            "u_max",
        ),
    )
    return AnalizTanimi(
        ad="konsol_kiris",
        parca=parca,
        malzeme=CELIK,
        h=5.0,
        secimler=secimler,
        kosullar=kosullar,
        analitik=analitik,
    )


# ad → kurucu; GET /api/ekran/analiz/ornekler bu sırayla listeler
ORNEKLER: dict[str, Callable[[], AnalizTanimi]] = {
    "delikli_plaka": delikli_plaka,
    "konsol_kiris": konsol_kiris,
}
