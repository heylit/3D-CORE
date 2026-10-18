"""
SPEC 13 — `fileio.calculix` yazıcı biçimi testleri (K8). ccx gerektirmez.

.inp metni bu dosyadaki küçük ayrıştırıcıyla okunur (anahtar satırı `*` ile başlar, veri satırları virgülle
ayrılır, `**` yorumdur). Beklentiler SPEC 13 Teori / CalculiX eşlemesi tablosundan; uygulama kodu okunmadı.
Düğüm ve eleman id'lerinin .inp'ye olduğu gibi yazıldığı varsayılır (eşleme tablosu: `BC(node, ...)` →
`*BOUNDARY node, ...`).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from fileio.calculix import to_inp, write_inp
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri, yuzey_cekmesi
from tests.conftest import make_bar

# repr'i uzun, 20 karakteri aşan veya üssü büyük sayılar (ccx alanı en çok 20 karakter okur)
ZOR = [1e-16, -7.850462293417722e-16, 1e100, 0.1 + 0.2, -123456.78901234567, 2.0 / 3.0]


# --- küçük .inp ayrıştırıcısı ----------------------------------------------------------


def bloklar(inp: str) -> list[tuple[str, dict[str, str], list[list[str]]]]:
    """[(ANAHTAR, {PARAMETRE: değer}, [[alan, ...], ...]), ...]; anahtar ve parametre adları büyük harf."""
    sonuc: list[tuple[str, dict[str, str], list[list[str]]]] = []
    for satir in inp.splitlines():
        s = satir.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            parcalar = [p.strip() for p in s[1:].split(",")]
            params = {}
            for p in parcalar[1:]:
                if not p:
                    continue
                k, _, v = p.partition("=")
                params[k.strip().upper()] = v.strip()
            sonuc.append((parcalar[0].upper(), params, []))
        elif sonuc:
            sonuc[-1][2].append([f.strip() for f in s.split(",") if f.strip()])
    return sonuc


def veri(inp: str, anahtar: str, **kosul: str) -> list[list[str]]:
    """Anahtarı (ve verilen parametreleri) tutan bütün blokların veri satırları, art arda."""
    satirlar: list[list[str]] = []
    for k, params, data in bloklar(inp):
        if k == anahtar and all(params.get(p.upper(), "").upper() == v.upper() for p, v in kosul.items()):
            satirlar.extend(data)
    return satirlar


def dugum_kumeleri(inp: str) -> dict[str, set[int]]:
    """`*NODE, NSET=ad` ve `*NSET, NSET=ad` kümeleri (ad büyük harf). GENERATE desteklenmez."""
    kumeler: dict[str, set[int]] = {}
    for k, params, data in bloklar(inp):
        if k in ("NODE", "NSET") and "NSET" in params:
            hedef = kumeler.setdefault(params["NSET"].upper(), set())
            if k == "NODE":
                hedef.update(int(s[0]) for s in data)
            else:
                for s in data:
                    for a in s:
                        hedef.update(kumeler.get(a.upper(), set()) if not a.isdigit() else {int(a)})
    return kumeler


def sinir_kosullari(inp: str) -> dict[tuple[int, int], float]:
    """`*BOUNDARY` satırları → {(düğüm, serbestlik 1..3): değer}; küme adları düğümlere açılır."""
    kumeler = dugum_kumeleri(inp)
    sonuc: dict[tuple[int, int], float] = {}
    for s in veri(inp, "BOUNDARY"):
        dugumler = {int(s[0])} if s[0].isdigit() else kumeler[s[0].upper()]
        ilk = int(s[1])
        son = int(s[2]) if len(s) > 2 else ilk
        deger = float(s[3]) if len(s) > 3 else 0.0
        for n in dugumler:
            for k in range(ilk, son + 1):
                sonuc[(n, k)] = deger
    return sonuc


def sayi_mi(alan: str) -> bool:
    try:
        float(alan)
    except ValueError:
        return False
    return True


def yakin(okunan: float, gercek: float) -> bool:
    """Geri okuma: göreli hata ≤ 5e-13 (gerçek değer 0 ise okunan da 0)."""
    if gercek == 0.0:
        return okunan == 0.0
    return abs(okunan - gercek) <= 5e-13 * abs(gercek)


# --- modeller --------------------------------------------------------------------------


def iki_malzemeli_tet(kaydirma: float = 0.2) -> Model:
    """Yapılandırılmış ağ (iki düğüm sırasını da içerir); elemanların yarısı ikinci malzemede."""
    m = kutu_agi(12.0, 6.0, 4.0, 3, 2, 2, Material("celik", 210_000.0, 0.3), kaydirma=kaydirma, tohum=9)
    m.materials.append(Material("al", 70_000.0, 0.33))
    for e in m.elements[::2]:
        e.material = "al"
    for eksen in range(3):
        m.bcs.extend(BC(n, ("ux", "uy", "uz")[eksen], 0.0) for n in yuz_dugumleri(m, eksen, 0.0))
    m.loads = yuzey_cekmesi(m, 0, 12.0, (5.0, -1.0, 2.0))
    return m


def zor_sayili_tet() -> Model:
    """Koordinat, malzeme, mesnet ve yük değerlerinde ZOR sayılar."""
    X = [
        (ZOR[1], 0.0, ZOR[0]),
        (10.0 + ZOR[3], ZOR[1], 0.0),
        (ZOR[4] * 1e-5, 8.0 + ZOR[5], 0.0),
        (0.0, ZOR[0], 6.0 + ZOR[3]),
    ]
    return Model(
        dim=3,
        nodes=[Node(i + 1, *x) for i, x in enumerate(X)],
        elements=[Element(1, "tet4", [1, 2, 3, 4], "zor")],
        materials=[Material("zor", ZOR[2], 0.1 + 0.2)],
        bcs=[BC(1, "ux", ZOR[0]), BC(1, "uy", ZOR[1]), BC(1, "uz", 0.0), BC(2, "uz", ZOR[5])],
        loads=[Load(3, "ux", ZOR[4]), Load(4, "uz", ZOR[1]), Load(4, "uy", ZOR[2])],
    )


# --- K8: biçim ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", [iki_malzemeli_tet(), make_bar(n_elem=4)], ids=["tet4", "bar1d"])
def test_node_block_has_one_line_per_node(model):
    inp = to_inp(model)
    assert isinstance(inp, str)
    satirlar = veri(inp, "NODE")
    assert len(satirlar) == len(model.nodes)
    assert sorted(int(s[0]) for s in satirlar) == sorted(n.id for n in model.nodes)


@pytest.mark.parametrize("model", [iki_malzemeli_tet(), zor_sayili_tet(), make_bar(n_elem=4)])
def test_every_numeric_field_at_most_20_chars(model):
    inp = to_inp(model)
    for _, _, data in bloklar(inp):
        for satir in data:
            for alan in satir:
                if sayi_mi(alan):
                    assert len(alan) <= 20, f"ccx 20 karakterden uzun alanı okuyamaz: {alan!r}"


def test_hard_numbers_read_back_exactly():
    """1e-16, −7.85e-16, 1e+100 gibi değerler: alan ≤ 20 karakter ve geri okunca göreli hata ≤ 5e-13."""
    m = zor_sayili_tet()
    inp = to_inp(m)

    dugum = {int(s[0]): [float(v) for v in s[1:4]] for s in veri(inp, "NODE")}
    for n in m.nodes:
        for okunan, gercek in zip(dugum[n.id], (n.x, n.y, n.z), strict=True):
            assert yakin(okunan, gercek), (n.id, okunan, gercek)

    elastik = veri(inp, "ELASTIC")
    assert len(elastik) == 1
    assert yakin(float(elastik[0][0]), ZOR[2]) and yakin(float(elastik[0][1]), 0.1 + 0.2)

    sinir = sinir_kosullari(inp)
    for bc in m.bcs:
        k = ("ux", "uy", "uz").index(bc.dof) + 1
        assert (bc.node, k) in sinir
        assert yakin(sinir[(bc.node, k)], bc.value), (bc, sinir[(bc.node, k)])

    yuk: dict[tuple[int, int], float] = {}
    for s in veri(inp, "CLOAD"):
        anahtar = (int(s[0]), int(s[1]))
        yuk[anahtar] = yuk.get(anahtar, 0.0) + float(s[2])
    beklenen = {(ld.node, ("ux", "uy", "uz").index(ld.dof) + 1): ld.value for ld in m.loads}
    assert set(yuk) == set(beklenen)
    for anahtar, deger in beklenen.items():
        assert yakin(yuk[anahtar], deger), (anahtar, yuk[anahtar], deger)


def test_c3d4_elements_all_positive_volume():
    """Girdide negatif sıralı elemanlar olsa da her C3D4 satırı pozitif hacimli; id ve düğüm kümesi aynı."""
    m = iki_malzemeli_tet()
    X = {n.id: n.xyz for n in m.nodes}

    def det(nodes):
        P = [X[n] for n in nodes]
        return float(np.dot(np.cross(P[1] - P[0], P[2] - P[0]), P[3] - P[0]))

    assert any(det(e.nodes) < 0 for e in m.elements), "testin ağı negatif sıralı eleman içermeli"
    inp = to_inp(m)
    satirlar = veri(inp, "ELEMENT", type="C3D4")
    assert len(satirlar) == len(m.elements)
    giris = {e.id: set(e.nodes) for e in m.elements}
    for s in satirlar:
        eid, nodes = int(s[0]), [int(v) for v in s[1:5]]
        assert len(s) == 5
        assert set(nodes) == giris[eid]
        assert det(nodes) > 0, f"C3D4 eleman {eid} negatif hacimli yazıldı"
    assert sorted(int(s[0]) for s in satirlar) == sorted(giris)


def test_c3d4_has_solid_section_without_area():
    inp = to_inp(iki_malzemeli_tet())
    kesitler = [(p, d) for k, p, d in bloklar(inp) if k == "SOLID SECTION"]
    assert kesitler
    for params, data in kesitler:
        assert "ELSET" in params and "MATERIAL" in params
        assert all(not any(sayi_mi(a) for a in s) for s in data), "C3D4 kesitinde alan satırı olmamalı"
    assert not veri(inp, "ELEMENT", type="T3D2")


def test_each_material_once():
    """Her malzeme bir `*MATERIAL`; `*ELASTIC` değerleri modeldeki (E, ν) çiftleri."""
    m = iki_malzemeli_tet()
    inp = to_inp(m)
    adlar = [p.get("NAME", "").upper() for k, p, _ in bloklar(inp) if k == "MATERIAL"]
    assert len(adlar) == len(m.materials) and len(set(adlar)) == len(adlar)
    elastik = sorted((float(s[0]), float(s[1])) for s in veri(inp, "ELASTIC"))
    assert elastik == pytest.approx(sorted((mat.E, mat.nu) for mat in m.materials), rel=5e-13)


def test_bar_model_t3d2_with_area_and_lateral_fix():
    """1B: T3D2, `*SOLID SECTION` alan satırı A; bütün düğümlerde uy = uz = 0 (2. ve 3. serbestlik)."""
    m = make_bar(n_elem=3, A=123.25)
    inp = to_inp(m)
    satirlar = veri(inp, "ELEMENT", type="T3D2")
    assert len(satirlar) == 3 and not veri(inp, "ELEMENT", type="C3D4")
    kesit = veri(inp, "SOLID SECTION")
    assert any(sayi_mi(s[0]) and float(s[0]) == pytest.approx(123.25, rel=5e-13) for s in kesit)
    sinir = sinir_kosullari(inp)
    for n in m.nodes:
        for k in (2, 3):
            assert sinir.get((n.id, k)) == 0.0, f"düğüm {n.id}: {k}. serbestlik tutulmamış"
    assert sinir[(1, 1)] == 0.0


def test_output_requests():
    """Çıktı istekleri: *NODE PRINT (U, RF), *EL PRINT (S), *NODE FILE (U), *EL FILE (S); *STEP / *STATIC."""
    inp = to_inp(iki_malzemeli_tet())

    def degiskenler(anahtar):
        return {a.upper() for s in veri(inp, anahtar) for a in s}

    assert {"U", "RF"} <= degiskenler("NODE PRINT")
    assert "S" in degiskenler("EL PRINT")
    assert "U" in degiskenler("NODE FILE")
    assert "S" in degiskenler("EL FILE")
    anahtarlar = [k for k, _, _ in bloklar(inp)]
    assert "STEP" in anahtarlar and "STATIC" in anahtarlar and "END STEP" in anahtarlar
    assert anahtarlar.index("STEP") < anahtarlar.index("STATIC") < anahtarlar.index("END STEP")


def test_write_inp_writes_same_text(tmp_path):
    m = iki_malzemeli_tet()
    yol = tmp_path / "model.inp"
    assert write_inp(m, yol) is None
    assert yol.read_text() == to_inp(m)
    write_inp(m, str(tmp_path / "ikinci.inp"))
    assert (tmp_path / "ikinci.inp").read_text() == to_inp(m)


# --- K8: hatalar -------------------------------------------------------------------------


def _tet(dim: int = 3, tip: str = "tet4", section: str | None = None) -> Model:
    X = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    return Model(
        dim=dim,
        nodes=[Node(i + 1, *x) for i, x in enumerate(X)],
        elements=[Element(1, tip, [1, 2, 3, 4], "celik", section)],
        materials=[Material("celik", 210_000.0)],
        sections=[Section("s", 10.0)],
    )


def _validate_hatasi() -> Model:
    m = _tet()
    m.elements[0].nodes = [1, 2, 3, 99]  # bilinmeyen düğüm
    return m


def _bilinmeyen_tip() -> Model:
    return _tet(tip="hex8")


def _bar_3b() -> Model:
    m = _tet()
    m.elements = [Element(1, "bar1d", [1, 2], "celik", "s")]
    return m


def _tet_1b() -> Model:
    return Model(
        dim=1,
        nodes=[Node(i + 1, float(i)) for i in range(4)],
        elements=[Element(1, "tet4", [1, 2, 3, 4], "celik")],
        materials=[Material("celik", 210_000.0)],
    )


def _tet_2b() -> Model:
    m = _tet()
    m.dim = 2
    return m


def _karisik() -> Model:
    m = _tet()
    m.elements.append(Element(2, "bar1d", [1, 2], "celik", "s"))
    return m


def _karisik_1b() -> Model:
    m = make_bar(n_elem=3)
    m.elements.append(Element(9, "tet4", [1, 2, 3, 4], "celik"))
    return m


def _kesitsiz_bar() -> Model:
    m = make_bar(n_elem=2)
    m.elements[1].section = None
    return m


@pytest.mark.parametrize(
    "kur",
    [_validate_hatasi, _bilinmeyen_tip, _bar_3b, _tet_1b, _tet_2b, _karisik, _karisik_1b, _kesitsiz_bar],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_unsupported_models_raise(kur, tmp_path):
    m = kur()
    with pytest.raises(ModelError):
        to_inp(m)
    with pytest.raises(ModelError):
        write_inp(m, tmp_path / "x.inp")
