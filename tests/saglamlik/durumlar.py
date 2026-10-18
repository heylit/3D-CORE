"""SPEC 54 §4 — bozuk girdi koleksiyonu: her durum bir üretici + beklenti.

Testler yalnız specs/54-saglamlik.md'den ve iskelet imzalarından yazıldı; SPEC 54 kodu okunmadı.
Bütün girdiler uydurmadır (gizlilik kuralı): bloklar, silindirler, sahte adlar.

Her durum `calistir(tmp_path)` ile beklenen hatayı **yakalayıp döndürür**; hiç hata çıkmazsa `None` döner.
Bir üretici çalışırken NotImplementedError çıkarsa (SPEC 54 kodu ya da bağımlı modül henüz yok) yeniden
fırlatılır: test "uygulanmamış" sayılır (kök conftest), yanlış sınıf diye kırmızı olmaz.

Varsayımlar (SPEC'in açık bıraktığı yerler):
- Durum 6: montaj STEP'teki tek parçanın (`govde`, iki oluşum) katı tanımı (`MANIFOLD_SOLID_BREP`) silinir;
  mesaj o bileşenin / parçanın adını (`govde`) içerir.
- Durum 9: kısıtların adı yoktur (`assy.model.Mate`); mesajdaki kısıt adı sıra numarasıyla verilir
  (bugünkü `kısıt <i>` biçimi): iki çelişen kısıtın ikisi de (`kısıt 0`, `kısıt 1`) mesajda geçer.
- Durum 10: üçgende üç kenar (30, 40, 50) + üç açı (60°) çelişir; mesajda en az bir açı kısıtı
  (`angle` türü ya da `açı`) geçer.
- Durum 11 ve 11b'nin mesajı `cam/model.py`'de doğar (Karar 4): K2 ayrı arayüz PR'ına kadar xfail.
"""

from __future__ import annotations

import math
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from tests.conftest import make_bar

BOZUK = Path(__file__).resolve().parent / "bozuk"


@dataclass(frozen=True)
class Durum:
    """Bir bozuk girdi durumu. `nesne`: mesajda geçmesi gereken metinler; `oneri_icerir`: öneride geçmeli."""

    kimlik: str
    aciklama: str
    sinif: str  # beklenen hata sınıfının adı
    uret: Callable[[Path], None]  # hatayı fırlatan işlem
    nesne: tuple[str, ...] = ()
    oneri_icerir: tuple[str, ...] = ()  # öneride geçmesi gereken kelimeler (büyük/küçük harf duyarsız)
    oneri_sayi: bool = False  # öneride bir sınır sayısı olmalı
    occt: bool = False
    model_py: bool = False  # mesaj */model.py'de doğar (Karar 4)
    ek: tuple[str, ...] = field(default=())  # ek düzenli ifadeler (mesajda, IGNORECASE)


def calistir(d: Durum, tmp_path: Path) -> BaseException | None:
    """Durumu çalıştırır, çıkan istisnayı döndürür. NotImplementedError yeniden fırlatılır."""
    try:
        d.uret(tmp_path)
    except NotImplementedError:
        raise
    except BaseException as e:  # noqa: BLE001 — sınıfı test denetler
        return e
    return None


# ---------------------------------------------------------------- OCCT yardımcıları


def _bd():
    import build123d as bd

    return bd


def _blok(ad: str = "blok"):
    from geometry.part import Part

    bd = _bd()
    return Part(bd.Box(20.0, 20.0, 10.0), name=ad)


def _parca_oku():
    from fileio.parca_oku import parca_oku

    return parca_oku


def _blok_step(tmp_path: Path) -> Path:
    yol = tmp_path / "_blok_kaynak.step"
    _blok().to_step(yol)
    return yol


# ---------------------------------------------------------------- 1–5 dosyadan parça (Karar 3)


def _d1_bos(tmp_path: Path) -> None:
    yol = tmp_path / "bos.step"
    yol.write_bytes((BOZUK / "bos.step").read_bytes())
    assert yol.stat().st_size == 0
    _parca_oku()(yol)


def _d2_kesik(tmp_path: Path) -> None:
    veri = _blok_step(tmp_path).read_bytes()
    yol = tmp_path / "kesik.step"
    yol.write_bytes(veri[: int(len(veri) * 0.6)])
    _parca_oku()(yol)


def _d3_sozdizimi(tmp_path: Path) -> None:
    metin = _blok_step(tmp_path).read_text(encoding="utf-8", errors="replace")
    assert "ENDSEC;" in metin
    yol = tmp_path / "sozdizimi.step"
    yol.write_text(metin.replace("ENDSEC;", ""), encoding="utf-8")
    _parca_oku()(yol)


def _d3b_sozdizimi_elle(tmp_path: Path) -> None:
    yol = tmp_path / "sozdizimi.step"
    yol.write_bytes((BOZUK / "sozdizimi.step").read_bytes())
    _parca_oku()(yol)


def _d4_katisiz(tmp_path: Path) -> None:
    bd = _bd()
    yuz = bd.Face.make_rect(20.0, 20.0)
    yol = tmp_path / "katisiz.step"
    bd.export_step(bd.Shell([yuz]) if hasattr(bd, "Shell") else yuz, str(yol))
    assert yol.stat().st_size > 0
    _parca_oku()(yol)


def _stl_ucgen_sil(kaynak: Path, hedef: Path) -> None:
    """STL'den bir üçgen siler (ASCII ya da ikili)."""
    veri = kaynak.read_bytes()
    if veri[:5].lower() == b"solid" and b"facet" in veri[:400]:
        metin = veri.decode("ascii", errors="replace")
        bas = metin.index("facet")
        son = metin.index("endfacet", bas) + len("endfacet")
        hedef.write_text(metin[:bas] + metin[son:].lstrip("\r\n "), encoding="ascii")
        return
    n = int.from_bytes(veri[80:84], "little")
    assert len(veri) == 84 + 50 * n, "beklenmeyen ikili STL boyu"
    hedef.write_bytes(veri[:80] + (n - 1).to_bytes(4, "little") + veri[84 + 50 :])


def _d5_acik_stl(tmp_path: Path) -> None:
    kaynak = tmp_path / "_blok.stl"
    _blok().to_stl(kaynak)
    yol = tmp_path / "acik.stl"
    _stl_ucgen_sil(kaynak, yol)
    _parca_oku()(yol)


# ---------------------------------------------------------------- 6 bozuk montaj STEP


def _d6_bozuk_montaj(tmp_path: Path) -> None:
    from assy.model import Node, transform
    from fileio.step_montaj import read_step, write_step
    from geometry.part import Part

    bd = _bd()
    kok = Node(
        "grup",
        T=np.eye(4),
        children=[
            Node("govde_1", T=transform(None, (0.0, 0.0, 0.0)), part="govde"),
            Node("govde_2", T=transform(None, (50.0, 0.0, 0.0)), part="govde"),
        ],
    )
    yol = tmp_path / "montaj.step"
    write_step(yol, kok, {"govde": Part(bd.Box(30.0, 20.0, 10.0), name="govde")})
    metin = yol.read_text(encoding="utf-8", errors="replace")
    satirlar = metin.splitlines(keepends=True)
    breps = [i for i, s in enumerate(satirlar) if re.search(r"=\s*MANIFOLD_SOLID_BREP\s*\(", s)]
    assert len(breps) == 1, f"tek katı tanımı bekleniyordu: {len(breps)}"
    # Varlık birden çok satıra yayılabilir: ';' gelene kadar sil
    i = breps[0]
    j = i
    while not satirlar[j].rstrip().endswith(";"):
        j += 1
    yol.write_text("".join(satirlar[:i] + satirlar[j + 1 :]), encoding="utf-8")
    read_step(yol)


# ---------------------------------------------------------------- 7–8 OCCT işlemleri


def _d7_buyuk_fillet(tmp_path: Path) -> None:
    from geometry.fillet import fillet_vertical

    # 10 mm kalınlıkta blok (x yönünde 10 mm), dikey kenarlarda r = 8: iki komşu fillet çakışır
    from geometry.part import Part

    bd = _bd()
    fillet_vertical(Part(bd.Box(10.0, 40.0, 30.0), name="ince_blok"), 8.0)


def _d8_bos_boolean(tmp_path: Path) -> None:
    from geometry.boolean import cut

    a = _blok("kup")
    sonuc = cut(a, a)
    hacim = float(sonuc.volume)
    raise AssertionError(f"boş boolean sonucu döndü (hacim = {hacim})")


# ---------------------------------------------------------------- 9 çelişkili kısıtlar


def _d9_celiskili_kisit(tmp_path: Path) -> None:
    from assy.model import Assembly, Component, Mate, MateKind, Ref, RefKind
    from assy.solver import solve

    eksen_a = Ref("yatak", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    eksen_b = Ref("mil", RefKind.AXIS, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    m = Assembly(
        "yatak_grubu",
        components=[
            Component("yatak", "yatak.step", fixed=True),
            Component("mil", "mil.step", T=_donme_x(10.0)),
        ],
        mates=[
            Mate(MateKind.CONCENTRIC, eksen_a, eksen_b),
            Mate(MateKind.ANGLE, eksen_a, eksen_b, value=30.0),
        ],
    )
    solve(m)


def _donme_x(derece: float) -> np.ndarray:
    a = math.radians(derece)
    T = np.eye(4)
    T[1:3, 1:3] = [[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]]
    return T


# ---------------------------------------------------------------- 10 aşırı kısıtlı kroki


def _d10_asiri_kisitli(tmp_path: Path) -> None:
    from sketch.model import Constraint, ConstraintType, Line, Point, Sketch

    try:
        from sketch.solver import solve
    except ImportError as e:  # SPEC 17 çözücüsü bu dalda yoksa: uygulanmamış
        raise NotImplementedError("sketch.solver bu dalda yok (SPEC 17, main'de)") from e

    s = Sketch(
        points={
            "a": Point(0.0, 0.0, fixed=True),
            "b": Point(31.0, 1.0),
            "c": Point(29.0, 41.0),
        },
        entities={"ab": Line("a", "b"), "bc": Line("b", "c"), "ca": Line("c", "a")},
        constraints=[
            Constraint(ConstraintType.HORIZONTAL, ("ab",)),
            Constraint(ConstraintType.LENGTH, ("ab",), 30.0),
            Constraint(ConstraintType.LENGTH, ("bc",), 40.0),
            Constraint(ConstraintType.LENGTH, ("ca",), 50.0),
            Constraint(ConstraintType.ANGLE, ("ab", "bc"), 60.0),
            Constraint(ConstraintType.ANGLE, ("bc", "ca"), 60.0),
            Constraint(ConstraintType.ANGLE, ("ca", "ab"), 60.0),
        ],
    )
    solve(s)


# ---------------------------------------------------------------- 11 sıfır boy (cam/model.py, Karar 4)


def _d11_sifir_takim(tmp_path: Path) -> None:
    from cam.model import Tool, ToolKind

    Tool(id=1, name="T1 sifir", kind=ToolKind.FLAT, D=0.0, flute_length=20.0)


def _d11b_sifir_yay(tmp_path: Path) -> None:
    from cam.model import Move, MoveType, Tool, ToolKind, Toolpath

    t = Tool(id=1, name="T1 freze", kind=ToolKind.FLAT, D=10.0, flute_length=20.0)
    yol = Toolpath(
        "cep_1",
        t,
        start=(10.0, 0.0, 5.0),
        moves=[Move(MoveType.ARC_CW, end=(10.0, 0.0, 5.0), feed=500.0, center=(10.0, 0.0))],
        rpm=8000.0,
    )
    yol.validate()


# ---------------------------------------------------------------- 13 tekil FEM


def _d13_tekil_fem(tmp_path: Path) -> None:
    from core.solver import solve

    solve(make_bar(n_elem=3, fix_left=False))


# ---------------------------------------------------------------- 14 bozuk .3dc


def _gecerli_3dc(tmp_path: Path, ad: str = "yatak") -> Path:
    from fileio.proje import bos_proje, kaydet, uygula

    p = bos_proje(ad)
    p = uygula(p, "parça ekle", "modelleme", {"parca": {"sema": 1, "L": 40.0}})
    yol = tmp_path / f"{ad}.3dc"
    kaydet(p, yol)
    return yol


def _zip_yeniden(kaynak: Path, hedef: Path, degistir: Callable[[str, bytes], bytes]) -> None:
    with zipfile.ZipFile(kaynak) as z, zipfile.ZipFile(hedef, "w") as w:
        for bilgi in z.infolist():
            w.writestr(bilgi, degistir(bilgi.filename, z.read(bilgi.filename)))


def _d14a_ozet(tmp_path: Path) -> None:
    from fileio.proje import ac

    kaynak = _gecerli_3dc(tmp_path, "_kaynak")
    yol = tmp_path / "yatak.3dc"

    def bolumu_boz(ad: str, veri: bytes) -> bytes:
        return veri.replace(b"40.0", b"41.0").replace(b"40", b"41") if ad == "bolumler/parca.json" else veri

    _zip_yeniden(kaynak, yol, bolumu_boz)
    ac(yol)


def _d14b_kesik(tmp_path: Path) -> None:
    from fileio.proje import ac

    veri = _gecerli_3dc(tmp_path, "_kaynak").read_bytes()
    yol = tmp_path / "yatak.3dc"
    yol.write_bytes(veri[: len(veri) // 2])
    ac(yol)


def _d14c_sema(tmp_path: Path) -> None:
    import json

    from fileio.proje import ac

    kaynak = _gecerli_3dc(tmp_path, "_kaynak")
    yol = tmp_path / "yatak.3dc"

    def semayi_artir(ad: str, veri: bytes) -> bytes:
        if ad != "proje.json":
            return veri
        b = json.loads(veri)
        b["sema"] = int(b["sema"]) + 1
        return json.dumps(b, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()

    _zip_yeniden(kaynak, yol, semayi_artir)
    ac(yol)


# ---------------------------------------------------------------- koleksiyon

DURUMLAR: tuple[Durum, ...] = (
    Durum("1", "boş STEP (0 bayt)", "GeometryError", _d1_bos, nesne=("bos.step",), occt=True),
    Durum("2", "yarıda kesilmiş STEP (%60)", "GeometryError", _d2_kesik, nesne=("kesik.step",), occt=True),
    Durum("3", "ENDSEC; silinmiş STEP", "GeometryError", _d3_sozdizimi, nesne=("sozdizimi.step",), occt=True),
    Durum(
        "3b",
        "elle yazılmış ENDSEC'siz STEP",
        "GeometryError",
        _d3b_sozdizimi_elle,
        nesne=("sozdizimi.step",),
        occt=True,
    ),
    Durum(
        "4",
        "katısız STEP (tek yüz)",
        "GeometryError",
        _d4_katisiz,
        nesne=("katisiz.step",),
        oneri_icerir=("katı",),
        occt=True,
    ),
    Durum("5", "kapalı olmayan STL", "GeometryError", _d5_acik_stl, nesne=("acik.stl",), occt=True),
    Durum("6", "bozuk montaj STEP", "GeometryError", _d6_bozuk_montaj, nesne=("govde",), occt=True),
    Durum(
        "7",
        "fillet çok büyük (10 mm kalınlık, r = 8)",
        "GeometryError",
        _d7_buyuk_fillet,
        nesne=("ince_blok",),
        oneri_sayi=True,
        occt=True,
    ),
    Durum("8", "boş boolean sonucu cut(a, a)", "GeometryError", _d8_bos_boolean, occt=True),
    Durum(
        "9",
        "çelişkili kısıtlar (eş eksen + 30° açı)",
        "AssyError",
        _d9_celiskili_kisit,
        ek=(r"kısıt\s*0\b", r"kısıt\s*1\b"),
    ),
    Durum(
        "10", "aşırı kısıtlı üçgen (3 kenar + 3 açı)", "SketchError", _d10_asiri_kisitli, ek=(r"angle|açı",)
    ),
    Durum("11", "D = 0 takım", "CamError", _d11_sifir_takim, nesne=("T1 sifir",), model_py=True),
    Durum("11b", "sıfır boy yay", "CamError", _d11b_sifir_yay, nesne=("cep_1",), model_py=True),
    Durum("13", "tekil FEM (mesnetsiz çubuk)", "ModelError", _d13_tekil_fem, oneri_icerir=("mesnet",)),
    Durum("14a", ".3dc bölüm özeti tutmuyor", "ProjeError", _d14a_ozet, nesne=("yatak.3dc", "parca")),
    Durum("14b", ".3dc kesik zip", "ProjeError", _d14b_kesik, nesne=("yatak.3dc",)),
    Durum("14c", ".3dc şeması yeni", "ProjeError", _d14c_sema, nesne=("yatak.3dc",)),
)


# Bugünkü kodda (SPEC 54 kodu yazılmadan önce) gerçekten kırmızı olan, NotImplementedError'a varmayan
# satırlar. Yerel kapı kırmızı testi kabul etmediği için xfail(strict=True) işaretlidir; SPEC 54 kodu
# bunları düzeltince XPASS kırmızıya döner ve işaret ayrı bir test commit'iyle kaldırılır.
BEKLIYOR: dict[str, frozenset[str]] = {
    "core_error": frozenset({"7", "9", "14a", "14c"}),
    "format": frozenset({"6", "7", "8", "9", "13", "14a", "14b", "14c"}),
    "suggestion": frozenset({"7", "13"}),
    "cause": frozenset({"13", "14b"}),
}


def isaretler(d: Durum, test: str) -> list:
    """Parametre işaretleri: occt, Karar 4 (yalnız biçim testleri) ve BEKLIYOR."""
    import pytest

    out = [pytest.mark.occt] if d.occt else []
    if d.model_py and test in ("format", "suggestion"):
        out.append(pytest.mark.xfail(strict=True, reason="model.py mesajı: arayüz PR'ı"))
    elif d.kimlik in BEKLIYOR.get(test, frozenset()):
        out.append(
            pytest.mark.xfail(strict=True, reason="SPEC 54 Karar 1: bugünkü mesaj / sınıf; kod düzeltir")
        )
    return out


def param(d: Durum, test: str):
    import pytest

    return pytest.param(d, id=d.kimlik, marks=isaretler(d, test))
