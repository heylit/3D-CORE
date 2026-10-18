"""SPEC 26 testleri için elle kurulmuş, uydurma model geçmişleri (gizlilik kuralı: gerçek parça yok).

Biçim SPEC 26 "Model geçmişi" bölümündendir. Sayılar elle seçilmiştir; hiçbiri `tezgah` kodundan
türetilmez. Eskizler `sketch.model` ile kurulur; `olculer` anahtarı kısıt sırasıdır (JSON'da metin).
"""

from __future__ import annotations

import copy

from sketch.model import Circle, Constraint, ConstraintType, Line, Plane, Point, Sketch

CT = ConstraintType

# Dikdörtgen eskizinde kısıt sıraları (dikdortgen_eskiz): 0–3 H/V, 4 alt kenar boyu, 5 sağ kenar boyu.
I_GENISLIK, I_BOY = 4, 5


def duzlem_xy(z: float = 0.0) -> Plane:
    return Plane((0.0, 0.0, z), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))


def dikdortgen_eskiz(
    x0: float, y0: float, w: float, h: float, plane: Plane | None = None, tam: bool = True
) -> Sketch:
    """Sol alt köşesi (x0, y0)'da sabit dikdörtgen: H, V, H, V, LENGTH(alt) = w, LENGTH(sağ) = h.

    tam=False → sağ kenar boyu yok: dof = 1 (üst kenar düşey kayabilir).
    """
    pts = {
        "a": Point(x0, y0, fixed=True),
        "b": Point(x0 + w, y0),
        "c": Point(x0 + w, y0 + h),
        "d": Point(x0, y0 + h),
    }
    ents = {"alt": Line("a", "b"), "sag": Line("b", "c"), "ust": Line("c", "d"), "sol": Line("d", "a")}
    cs = [
        Constraint(CT.HORIZONTAL, ("alt",)),
        Constraint(CT.VERTICAL, ("sag",)),
        Constraint(CT.HORIZONTAL, ("ust",)),
        Constraint(CT.VERTICAL, ("sol",)),
        Constraint(CT.LENGTH, ("alt",), w),
    ]
    if tam:
        cs.append(Constraint(CT.LENGTH, ("sag",), h))
    return Sketch(plane=plane or Plane.XY(), points=pts, entities=ents, constraints=cs)


def daire_eskiz(cx: float, cy: float, r: float, plane: Plane | None = None) -> Sketch:
    """Merkezi sabit, RADIUS kısıtlı daire (kısıt 0)."""
    return Sketch(
        plane=plane or Plane.XY(),
        points={"m": Point(cx, cy, fixed=True)},
        entities={"o": Circle("m", r)},
        constraints=[Constraint(CT.RADIUS, ("o",), r)],
    )


def nokta_eskiz(noktalar: dict[str, tuple[float, float]], plane: Plane | None = None) -> Sketch:
    """Yalnız sabit noktalar (delik merkezleri); öğe ve kısıt yok, dof = 0."""
    return Sketch(
        plane=plane or Plane.XY(),
        points={k: Point(u, v, fixed=True) for k, (u, v) in noktalar.items()},
        entities={},
        constraints=[],
    )


def eskiz_adimi(kimlik: str, sk: Sketch, duzlem: dict, olculer: dict | None = None) -> dict:
    return {
        "kimlik": kimlik,
        "tur": "eskiz",
        "duzlem": duzlem,
        "eskiz": sk.to_dict(),
        "olculer": {str(k): v for k, v in (olculer or {}).items()},
    }


def ekstruzyon_adimi(
    kimlik: str,
    eskiz: str,
    mesafe,
    islem: str = "yeni",
    bitis: str = "mesafe",
    yon: str = "ileri",
    bolgeler="hepsi",
) -> dict:
    return {
        "kimlik": kimlik,
        "tur": "ekstruzyon",
        "eskiz": eskiz,
        "bolgeler": bolgeler,
        "mesafe": mesafe,
        "yon": yon,
        "islem": islem,
        "bitis": bitis,
    }


def delik_adimi(kimlik: str, eskiz: str, noktalar: list[str], cesit: str, d, derinlik, **ek) -> dict:
    return {
        "kimlik": kimlik,
        "tur": "delik",
        "eskiz": eskiz,
        "noktalar": list(noktalar),
        "cesit": cesit,
        "d": d,
        "derinlik": derinlik,
        **ek,
    }


def model(adimlar: list[dict], parametreler: dict | None = None, ad: str = "deneme") -> dict:
    return {"sema": 1, "ad": ad, "parametreler": dict(parametreler or {}), "adimlar": adimlar}


def kopya(m: dict) -> dict:
    return copy.deepcopy(m)


# --- Hazır modeller -------------------------------------------------------------------------------------


def plaka(
    genislik="=genislik", boy="=boy", kalinlik="=kalinlik", parametreler=None, tam: bool = True
) -> dict:
    """XY'de 40 × 30 (parametreli) dikdörtgen, ekstrüzyon "yeni" kalinlik = 10: V = 12000 mm³.

    Adımlar: e1 (eskiz), x1 (ekstrüzyon).
    """
    P = {"genislik": "40", "boy": "30", "kalinlik": "10"} if parametreler is None else parametreler
    olc = {I_GENISLIK: genislik}
    if tam:
        olc[I_BOY] = boy
    return model(
        [
            eskiz_adimi(
                "e1", dikdortgen_eskiz(0.0, 0.0, 40.0, 30.0, tam=tam), {"tur": "XY", "ofset": 0}, olc
            ),
            ekstruzyon_adimi("x1", "e1", kalinlik),
        ],
        P,
        ad="plaka",
    )


# Flanş (test tarafının kendi örneği; `ornek_model("flans")`'tan bağımsız):
# 120 × 80 × 15 plaka; ortada 40 × 30 kör cep (x ∈ [40, 80], y ∈ [25, 55]) 8 mm; 4 adet Ø8 boydan boya delik.
FL_A, FL_B, FL_C = 120.0, 80.0, 15.0
FL_CEP = (40.0, 25.0, 40.0, 30.0)  # x0, y0, w, h
FL_CEP_DERINLIK = 8.0
FL_DELIKLER = {"d1": (15.0, 15.0), "d2": (105.0, 15.0), "d3": (105.0, 65.0), "d4": (15.0, 65.0)}
FL_D = 8.0


def flans() -> dict:
    """V = 120·80·15 − 40·30·8 − 4·π·4²·15."""
    ust = {"tur": "XY", "ofset": FL_C}
    return model(
        [
            eskiz_adimi("e1", dikdortgen_eskiz(0.0, 0.0, FL_A, FL_B), {"tur": "XY", "ofset": 0}),
            ekstruzyon_adimi("x1", "e1", FL_C),
            eskiz_adimi("e2", dikdortgen_eskiz(*FL_CEP, plane=duzlem_xy(FL_C)), ust),
            ekstruzyon_adimi("cep", "e2", FL_CEP_DERINLIK, islem="kes"),
            eskiz_adimi("e3", nokta_eskiz(FL_DELIKLER, plane=duzlem_xy(FL_C)), ust),
            delik_adimi("delikler", "e3", list(FL_DELIKLER), "duz", FL_D, None),
        ],
        ad="flans-test",
    )


def flans_hacmi() -> float:
    import math

    return FL_A * FL_B * FL_C - FL_CEP[2] * FL_CEP[3] * FL_CEP_DERINLIK - 4 * math.pi * (FL_D / 2) ** 2 * FL_C
