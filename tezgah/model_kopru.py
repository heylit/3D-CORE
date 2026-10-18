"""
SPEC 26 — modelleme köprüsü: SolveResult / Rapor / Part → JSON ve ikili dizi; "Tezgah'a gönder" → SPEC 24 Is.

Saf fonksiyonlar, FastAPI'siz test edilir. Her JSON yanıtında "sema": SEMA.

SolveResult JSON: {sema, points: {kimlik: [x, y]}, radii, sides: {"k": ±1}, iterations, residual, dof,
                   freedom, directions: {kimlik: [x, y]}, redundant: [k]}
Ağ ikilisi (SPEC 24 ikili blok biçimi): başlık uint32 sema, n, m; float32 köşeler (n, 3), int32 üçgenler
(m, 3), int32 yüz index (m,). Bloklar 8 baytın katına sıfırla tamamlanır.
Segment JSON: {"tur": "dogru", "p0", "p1"} | {"tur": "yay", "merkez", "r", "bas", "son", "ccw"} (uv, mm).
"""

from __future__ import annotations

import dataclasses
import struct

import numpy as np

from cam.gcode import FANUC, DrillOp
from cam.model import Setup, Stock, Tool, ToolKind, Wcs
from cam.ops2d import Cut, contour, face, pocket
from cam.profile import Arc, Line, Profile, Region
from geometry.part import GeometryError, Part
from sketch.model import Plane, SegArc, SegLine, Sketch, SketchError, SketchRegion
from sketch.solver import SolveResult, drag, solve
from tezgah import SEMA
from tezgah.ifade import IfadeError, degerlendir, parametreleri_coz
from tezgah.kopru import Islem, IsTanimi, _blok, _oku

# "Tezgah'a gönder" varsayılanları (SPEC 24 örnek işiyle aynı kesme değerleri)
PAY_XY, PAY_UST = 2.0, 1.0  # mm, stok payı (alt 0)
Z_GUVENLI_PAY = 5.0  # mm, stok üstünden güvenli Z
YUZEY = {"D": 20.0, "ap": 1.0, "F": 1200.0, "rpm": 9000.0}
CEP = {"D": 10.0, "ap": 1.5, "F": 800.0, "rpm": 11000.0, "stepover": 4.0}
KONTUR = {"D": 10.0, "ap": 2.0, "F": 900.0, "rpm": 10000.0}
DELIK = {"F": 250.0, "rpm": 4500.0}
DUSEY_TOL = 1e-9  # normal / eksen +Z'ye paralellik
KESIT_PAY = 1e-3  # mm: en alt kesit taban yüzünün biraz üstünden alınır


# --- Eskiz çözümü -------------------------------------------------------------------------------------


def _xy(p) -> list[float]:
    return [float(p[0]), float(p[1])]


def cozum_json(res: SolveResult) -> dict:
    """SolveResult → JSON sözlüğü (float kayıpsız)."""
    return {
        "sema": SEMA,
        "points": {k: _xy(p) for k, p in res.points.items()},
        "radii": {k: float(r) for k, r in res.radii.items()},
        "sides": {str(k): int(v) for k, v in res.sides.items()},
        "iterations": int(res.iterations),
        "residual": float(res.residual),
        "dof": int(res.dof),
        "freedom": {k: int(v) for k, v in res.freedom.items()},
        "directions": {k: _xy(v) for k, v in res.directions.items()},
        "redundant": [int(i) for i in res.redundant],
    }


def _eskiz(eskiz: dict, olculer: dict | None = None, parametreler: dict | None = None) -> Sketch:
    """Eskiz sözlüğü → Sketch; olculer {kısıt sırası: ifade} verilirse değerler parametrelerle hesaplanır."""
    try:
        sk = Sketch.from_dict(eskiz)
    except SketchError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise SketchError(f"Bozuk eskiz: {e}") from None
    if olculer:
        try:
            P = parametreleri_coz(dict(parametreler or {}))
            for k, ifade in olculer.items():
                i = int(k)
                if not 0 <= i < len(sk.constraints):
                    raise SketchError(f"Ölçü: {i} numaralı kısıt yok")
                sk.constraints[i].value = degerlendir(ifade, P)
        except IfadeError as e:
            raise SketchError(f"Ölçü ifadesi: {e}") from None
    return sk


def eskiz_coz(eskiz: dict, olculer: dict | None = None, parametreler: dict | None = None) -> dict:
    """Sketch.to_dict() → sketch.solver.solve → cozum_json. Çelişki SketchError olarak yükselir.

    olculer / parametreler (isteğe bağlı): model adımındaki gibi ölçü ifadeleri ("=genislik").
    """
    return cozum_json(solve(_eskiz(eskiz, olculer, parametreler)))


def eskiz_surukle(
    eskiz: dict, nokta: str, hedef, olculer: dict | None = None, parametreler: dict | None = None
) -> dict:
    """Sketch.to_dict() → sketch.solver.drag → cozum_json. Sabit nokta SketchError olarak yükselir."""
    sk = _eskiz(eskiz, olculer, parametreler)
    if nokta not in sk.points:
        raise SketchError(f"Bilinmeyen nokta: {nokta!r}")
    return cozum_json(drag(sk, nokta, (float(hedef[0]), float(hedef[1]))))


# --- Rapor --------------------------------------------------------------------------------------------


def rapor_json(rapor) -> dict:
    """modelleme.Rapor → JSON sözlüğü: {sema, adimlar: [AdimRaporu alanları], kontroller, hata}."""
    adimlar = []
    for a in rapor.adimlar:
        d = dataclasses.asdict(a)
        d["celiski"] = [int(i) for i in a.celiski]
        d["alanlar"] = [float(x) for x in a.alanlar]
        d["freedom"] = {k: int(v) for k, v in a.freedom.items()}
        d["dV"] = None if a.dV is None else float(a.dV)
        adimlar.append(d)
    h = rapor.hata
    return {
        "sema": SEMA,
        "adimlar": adimlar,
        "kontroller": [dict(k) for k in rapor.kontroller],
        "hata": None if h is None else {"kimlik": h.kimlik, "hata": h.hata, "celiski": list(h.celiski)},
    }


# --- Ağ -----------------------------------------------------------------------------------------------


def _yuz_agi(yuz) -> tuple[np.ndarray, np.ndarray]:
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(yuz, loc)
    if tri is None:
        raise GeometryError("Yüz üçgenlenemedi")
    trsf = loc.Transformation()
    P = np.array([tri.Node(i).Transformed(trsf).Coord() for i in range(1, tri.NbNodes() + 1)], float)
    T = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], np.int64) - 1
    if yuz.Orientation() == TopAbs_REVERSED:
        T = T[:, ::-1]  # normal dışa baksın
    return P.reshape(-1, 3), T.reshape(-1, 3)


def ag_ikili(part: Part, tol: float = 0.01) -> bytes:
    """Parçanın üçgen ağı: float32 köşe, int32 üçgen, int32 yüz index (part.shape.faces() sırası).

    Köşeler yüz başına ayrıdır (yüz seçimi ve düz gölgeleme için); ağ kapalı ve dışa yönlüdür.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    kopya = BRepBuilderAPI_Copy(part.shape.wrapped).Shape()  # girdinin üçgenlemesi değişmesin
    BRepMesh_IncrementalMesh(kopya, tol, False, 0.5, False)
    yuzler = type(part.shape)(kopya).faces()  # part.shape.faces() ile aynı sıra
    V, T, Y, n = [], [], [], 0
    for i, f in enumerate(yuzler):
        P, t = _yuz_agi(f.wrapped)
        V.append(P)
        T.append(t + n)
        Y.append(np.full(len(t), i))
        n += len(P)
    if len(yuzler) != len(part.shape.faces()):
        raise GeometryError("Ağ yüz sırası parçanınkiyle tutmuyor")
    V = np.concatenate(V).astype(np.float32)
    T = np.concatenate(T).astype(np.int32)
    Y = np.concatenate(Y).astype(np.int32)
    return b"".join(
        [struct.pack("<III", SEMA, len(V), len(T)) + bytes(4), _blok(V.ravel()), _blok(T.ravel()), _blok(Y)]
    )


def ag_coz(veri: bytes) -> dict[str, np.ndarray]:
    """ag_ikili'nin tersi: {"kose": (n, 3), "ucgen": (m, 3), "yuz": (m,)}."""
    sema, n, m = struct.unpack_from("<III", veri, 0)
    if sema != SEMA:
        raise GeometryError(f"Ağ dizisi sürümü {sema}, beklenen {SEMA}")
    V, ofs = _oku(veri, 16, "f4", 3 * n)
    T, ofs = _oku(veri, ofs, "i4", 3 * m)
    Y, ofs = _oku(veri, ofs, "i4", m)
    if ofs != len(veri):
        raise GeometryError(f"Ağ dizisi boyu tutmuyor ({len(veri)} bayt, beklenen {ofs})")
    return {"kose": V.reshape(n, 3), "ucgen": T.reshape(m, 3), "yuz": Y}


# --- Yüz ----------------------------------------------------------------------------------------------


def seg_json(s: SegLine | SegArc) -> dict:
    if isinstance(s, SegLine):
        return {"tur": "dogru", "p0": _xy(s.p0), "p1": _xy(s.p1)}
    return {
        "tur": "yay",
        "merkez": _xy(s.center),
        "r": float(s.r),
        "bas": _xy(s.start),
        "son": _xy(s.end),
        "ccw": bool(s.ccw),
    }


def yuz_json(part: Part, index: int) -> dict:
    """{sema, plane: Plane.to_dict(), outline: [[seg JSON]]} (face_plane, face_outline)."""
    from geometry.extrude import face_outline, face_plane

    plane = face_plane(part, index)
    return {
        "sema": SEMA,
        "plane": plane.to_dict(),
        "outline": [[seg_json(s) for s in dongu] for dongu in face_outline(part, index)],
    }


# --- Tezgah'a gönder ----------------------------------------------------------------------------------


def _uyari(kimlik: str, baslik: str, aciklama: str, spec: str = "SPEC 26") -> dict:
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "deger": None,
        "birim": "",
        "durum": "uyari",
        "aciklama": aciklama,
        "spec": spec,
    }


def _takim(T: int, ad: str, D: float, boy: float, tur: ToolKind = ToolKind.FLAT) -> Tool:
    return Tool(id=T, name=f"{ad} Ø{D:g}", kind=tur, D=D, flute_length=max(30.0, boy + 5.0), flutes=3)


def _kes(p: dict, z_top: float, z_bottom: float, z_safe: float, stepover: float | None = None) -> Cut:
    return Cut(
        z_top=z_top,
        z_bottom=z_bottom,
        a_p=p["ap"],
        feed=p["F"],
        plunge_feed=p["F"] / 3,
        rpm=p["rpm"],
        z_safe=z_safe,
        stepover=stepover,
    )


def _xy_noktasi(plane: Plane, uv) -> np.ndarray:
    return (plane.origin + float(uv[0]) * plane.xdir + float(uv[1]) * plane.ydir)[:2]


def _profil(dongu, plane: Plane) -> Profile:
    """uv döngüsü → XY profili (+Z normalli düzlemde; yön düzlemin el kuralıyla korunur)."""
    out = []
    for s in dongu:
        if isinstance(s, SegLine):
            out.append(Line(_xy_noktasi(plane, s.p0), _xy_noktasi(plane, s.p1)))
        else:
            # uv → XY dönüşü dönüş (det = +1, normal +Z): ccw korunur
            out.append(
                Arc(
                    _xy_noktasi(plane, s.start),
                    _xy_noktasi(plane, s.end),
                    _xy_noktasi(plane, s.center),
                    s.ccw,
                )
            )
    return Profile(out)


def _bolge(r: SketchRegion, plane: Plane) -> Region:
    return Region(_profil(r.outer, plane), [_profil(h, plane) for h in r.holes])


def _dusey(v) -> bool:
    v = np.asarray(v, float)
    return abs(abs(v[2]) - 1.0) <= DUSEY_TOL and float(np.hypot(v[0], v[1])) <= 1e-6


def _gonder(model: dict) -> tuple[IsTanimi, list[dict]]:
    """tezgaha_gonder + atlanan işlemlerin uyarı kontrolleri."""
    from tezgah.modelleme import insa

    p, rapor = insa(model)
    if rapor.hata is not None:
        raise GeometryError(f"Model kurulamadı: adım '{rapor.hata.kimlik}': {rapor.hata.hata}")
    if p is None:
        raise GeometryError("Modelde katı yok; Tezgah'a gönderilecek parça yok")
    b0, b1 = (np.asarray(b, float) for b in p.bbox)
    stok = Stock(b0[0] - PAY_XY, b0[1] - PAY_XY, b0[2], b1[0] + PAY_XY, b1[1] + PAY_XY, b1[2] + PAY_UST)
    z_safe = stok.zmax + Z_GUVENLI_PAY
    yukseklik = float(b1[2] - b0[2])
    uyarilar: list[dict] = []
    islemler: list[Islem] = []
    T = iter(range(1, 1000))

    y = face(
        stok,
        _takim(next(T), "Alın frezesi", YUZEY["D"], 0.0),
        _kes(YUZEY, stok.zmax, b1[2], z_safe, 0.7 * YUZEY["D"]),
    )
    islemler.append(Islem("yuzey", "Alın frezeleme", y, dict(YUZEY)))

    ceplar, icler = [], []
    for k in rapor.kesimler:
        if k.plane.normal[2] < 1.0 - DUSEY_TOL:
            uyarilar.append(
                _uyari(
                    f"atlandi_{k.kimlik}",
                    "İşlenmeyen kesim",
                    f"'{k.kimlik}' kesimi +Z yönünde değil; bu bağlamada işlenmedi",
                )
            )
            continue
        z = float(k.plane.origin[2])
        for j, r in enumerate(k.bolgeler):
            bolge = _bolge(r, k.plane)
            if k.derinlik is not None:
                tk = _takim(next(T), "Parmak freze", CEP["D"], k.derinlik)
                op = pocket(bolge, tk, _kes(CEP, z, z - k.derinlik, z_safe, CEP["stepover"]))
                ceplar.append(Islem("cep", f"Cep {k.kimlik}" + (f" #{j + 1}" if j else ""), op, dict(CEP)))
            else:
                tk = _takim(next(T), "Parmak freze", KONTUR["D"], z - b0[2])
                op = contour(bolge.outer, tk, _kes(KONTUR, z, b0[2], z_safe), "ic")
                icler.append(
                    Islem("kontur", f"İç kontur {k.kimlik}" + (f" #{j + 1}" if j else ""), op, dict(KONTUR))
                )
    islemler += ceplar + icler

    for r in p.section_z(b0[2] + KESIT_PAY):
        tk = _takim(next(T), "Parmak freze", KONTUR["D"], yukseklik)
        op = contour(Profile.polygon(r.outer), tk, _kes(KONTUR, b1[2], b0[2], z_safe), "dis")
        islemler.append(Islem("kontur", "Dış kontur", op, dict(KONTUR)))

    gruplar: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for h in p.holes:
        if not (_dusey(h.axis) and h.axis[2] < 0):
            uyarilar.append(
                _uyari(
                    f"atlandi_delik_{len(uyarilar)}",
                    "İşlenmeyen delik",
                    f"({h.origin[0]:g}, {h.origin[1]:g}, {h.origin[2]:g}) deliği düşey değil; "
                    "bu bağlamada işlenmedi",
                )
            )
            continue
        z_dip = float(h.origin[2] - h.depth)
        gruplar.setdefault((float(h.d), z_dip, float(h.origin[2])), []).append(
            (float(h.origin[0]), float(h.origin[1]))
        )
    for (d, z_dip, z_giris), delikler in gruplar.items():
        derin = z_giris - z_dip
        tur = "G83" if derin > 3 * d else "G81"
        op = DrillOp(
            name="delik",
            tool=_takim(next(T), "Matkap", d, derin, ToolKind.DRILL),
            rpm=DELIK["rpm"],
            start=(*delikler[0], z_safe),
            holes=delikler,
            z=z_dip,
            r=z_giris + 1.0,
            feed=DELIK["F"],
            kind=tur,
            q=d if tur == "G83" else None,
        )
        islemler.append(Islem("delik", f"Delik Ø{d:g} {tur}", op, {"D": d, **DELIK}))

    tanim = IsTanimi(
        ad=str(model.get("ad", "model")),
        kurulum=Setup(name="Üst bağlama", wcs=Wcs("G54"), stock=stok),
        malzeme="AlMg3",
        islemler=islemler,
        dialect=FANUC,
        safe_z=z_safe,
        parca_ag=p.mesh(),
    )
    for isl in islemler:
        isl.op.validate()
    return tanim, uyarilar


def tezgaha_gonder(model: dict) -> IsTanimi:
    """Modelin geçmişinden freze işi: stok = sınır kutusu + pay (XY 2 mm, üst 1 mm, alt 0); yüz alma;
    +Z kör kesim → cep; boydan boya iç bölge → iç kontur; en alt kesit dış sınırı → dış kontur;
    düşey Part.holes → delme. +Z dışı kesim / delik Kontrol(durum="uyari") ile atlanır (gonder_uyarilari)."""
    return _gonder(model)[0]


def gonder_uyarilari(model: dict) -> tuple[IsTanimi, list[dict]]:
    """tezgaha_gonder ile aynı iş ve atlanan +Z dışı kesim / deliklerin uyarı kontrolleri."""
    return _gonder(model)
