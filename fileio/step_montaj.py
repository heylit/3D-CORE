"""
Montaj STEP'i yazma / okuma (SPEC 07), OCCT XCAF ile (STEPCAFControl_Writer / Reader).

Her parça kimliği ve alt montaj tanımı (kök dahil) bir PRODUCT, her ağaç düğümü bir
NEXT_ASSEMBLY_USAGE_OCCURRENCE olur; aynı parça kaç kez kullanılırsa kullanılsın şekli bir kez yazılır.
build123d'nin export_step / import_step'i paylaşılan şeklin ikinci oluşumunun adını korumadığı için
XCAF belgesi doğrudan kurulur.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np

from assy.model import AssyError, Node
from assy.tree import validate
from geometry.part import GeometryError, Part

try:
    import build123d as bd
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.collections import Sequence_TDF_Label
    from OCP.gp import gp_Trsf
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_Tool
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Compound
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
except ImportError:  # pragma: no cover - kurulum yoksa _require_occt anlamlı hata verir
    bd = None


# ---------------------------------------------------------------- yardımcılar


def _require_occt() -> None:
    if bd is None:
        raise GeometryError('build123d kurulu değil: pip install -e ".[cad]"')


def _yeni_belge():
    belge = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    st = XCAFDoc_DocumentTool.ShapeTool_s(belge.Main())
    return belge, st


def _ad_yaz(etiket, ad: str) -> None:
    TDataStd_Name.Set_s(etiket, TCollection_ExtendedString(ad))


def _ad_oku(etiket) -> str:
    a = TDataStd_Name()
    if etiket.FindAttribute(TDataStd_Name.GetID_s(), a):
        return a.Get().ToExtString()
    return ""


def _konum(T: np.ndarray):
    tr = gp_Trsf()
    tr.SetValues(*T[:3, :4].ravel())
    return TopLoc_Location(tr)


def _matris(konum) -> np.ndarray:
    tr = konum.Transformation()
    T = np.eye(4)
    for i in range(3):
        for j in range(4):
            T[i, j] = tr.Value(i + 1, j + 1)
    return T


def _konumsuz(sekil):
    """Şeklin kendi konumunu geometriye işler: ürün şekli birim konumla yazılır."""
    if sekil.Location().IsIdentity():
        return sekil
    return BRepBuilderAPI_Transform(
        sekil.Located(TopLoc_Location()), sekil.Location().Transformation(), True
    ).Shape()


# ---------------------------------------------------------------- yazma


def write_step(path: str | Path, root: Node, parts: Mapping[str, Part]) -> None:
    """Ağacı ürün / oluşum yapısıyla STEP'e yazar. Kökün T'si çocuklarına katlanır."""
    _require_occt()
    validate(root)
    eksik = sorted({n.part for n in _yapraklar(root)} - set(parts))
    if eksik:
        raise AssyError(f"parts içinde olmayan parça kimlikleri: {eksik}")

    belge, st = _yeni_belge()
    st.SetAutoNaming_s(False)
    tanimlar: dict[str, object] = {}  # tanım adı -> XCAF etiketi

    def tanim(n: Node):
        if n.definition in tanimlar:
            return tanimlar[n.definition]
        if n.part is not None:
            etiket = st.AddShape(_konumsuz(parts[n.part].shape.wrapped), False)
        else:
            bilesik = TopoDS_Compound()
            BRep_Builder().MakeCompound(bilesik)
            etiket = st.AddShape(bilesik, True)
        _ad_yaz(etiket, n.definition)
        tanimlar[n.definition] = etiket
        for c in n.children:
            T = root.T @ c.T if n is root else c.T
            _ad_yaz(st.AddComponent(etiket, tanim(c), _konum(T)), c.name)
        return etiket

    if root.part is not None:  # tek yapraklı kök: kendisi bir montaj tanımı değil
        raise AssyError(f"Kök '{root.name}' bir alt montaj olmalı")
    tanim(root)
    st.UpdateAssemblies()

    yazici = STEPCAFControl_Writer()
    yazici.SetNameMode(True)
    Interface_Static.SetIVal_s("write.step.assembly", 1)
    if not yazici.Transfer(belge, STEPControl_AsIs) or yazici.Write(str(path)) != IFSelect_RetDone:
        raise GeometryError(f"Montaj STEP'i yazılamadı: {path}")


def _yapraklar(root: Node) -> list[Node]:
    out, yigin = [], [root]
    while yigin:
        n = yigin.pop()
        if n.part is not None:
            out.append(n)
        yigin.extend(n.children)
    return out


# ---------------------------------------------------------------- okuma


def read_step(path: str | Path) -> tuple[Node, dict[str, Part]]:
    """STEP'i ağaç ve parça sözlüğü olarak okur (kök T = birim)."""
    _require_occt()
    path = Path(path)
    if not path.is_file():
        raise GeometryError(f"STEP dosyası yok: {path}")
    belge, st = _yeni_belge()
    okuyucu = STEPCAFControl_Reader()
    okuyucu.SetNameMode(True)
    if okuyucu.ReadFile(str(path)) != IFSelect_RetDone or not okuyucu.Transfer(belge):
        raise GeometryError(
            f"{path.name}: STEP okunamadı — dosyayı CAD programınızda STEP AP214 olarak yeniden dışa aktarın"
        )

    parts: dict[str, Part] = {}
    parca_etiketi: dict[str, str] = {}  # kimlik -> XCAF etiket girdisi (aynı adlı farklı ürün kontrolü)

    def parca(etiket) -> str:
        kimlik = _ad_oku(etiket) or path.stem
        giris = TCollection_AsciiString()
        TDF_Tool.Entry_s(etiket, giris)
        giris = giris.ToCString()
        if kimlik not in parts:
            try:
                parts[kimlik] = Part(bd.Shape.cast(st.GetShape_s(etiket)), name=kimlik)
            except GeometryError as e:
                raise GeometryError(
                    f"{path.name} / {kimlik}: bileşenin katı şekli okunamadı — dosyayı CAD programınızda "
                    "bileşenler katı olacak biçimde STEP AP214 olarak yeniden dışa aktarın"
                ) from e
            parca_etiketi[kimlik] = giris
        elif parca_etiketi[kimlik] != giris:
            raise AssyError(f"STEP'te aynı adlı iki farklı parça ürünü: '{kimlik}'")
        return kimlik

    def cocuk_adlari(adlar: list[str]) -> list[str]:
        """Kardeşlerde yinelenen ada ikinciden başlayarak '#2', '#3'… eklenir."""
        sayac: dict[str, int] = {}
        out = []
        for a in adlar:
            sayac[a] = sayac.get(a, 0) + 1
            out.append(a if sayac[a] == 1 else f"{a}#{sayac[a]}")
        return out

    def dugum(etiket, ad: str, T: np.ndarray) -> Node:
        if not st.IsAssembly_s(etiket):
            return Node(name=ad, T=T, part=parca(etiket))
        bilesenler = Sequence_TDF_Label()
        st.GetComponents_s(etiket, bilesenler, False)
        cocuklar, adlar = [], []
        for i in range(1, bilesenler.Length() + 1):
            b = bilesenler.Value(i)
            hedef = TDF_Label()
            st.GetReferredShape_s(b, hedef)
            adlar.append(_ad_oku(b) or _ad_oku(hedef) or path.stem)
            cocuklar.append((hedef, _matris(st.GetLocation_s(b))))
        nodes = [dugum(h, a, Tc) for (h, Tc), a in zip(cocuklar, cocuk_adlari(adlar), strict=True)]
        tanim = _ad_oku(etiket) or ad
        return Node(name=ad, T=T, children=nodes, ref=tanim if tanim != ad else None)

    serbest = Sequence_TDF_Label()
    st.GetFreeShapes(serbest)
    etiketler = [serbest.Value(i) for i in range(1, serbest.Length() + 1)]
    if not etiketler:
        raise GeometryError(f"{path.name}: STEP'te şekil yok — dışa aktarırken en az bir parça seçin")
    if len(etiketler) == 1 and st.IsAssembly_s(etiketler[0]):
        kok = dugum(etiketler[0], _ad_oku(etiketler[0]) or path.stem, np.eye(4))
        kok.ref = None
    else:
        adlar = cocuk_adlari([_ad_oku(e) or path.stem for e in etiketler])
        kok = Node(
            name=path.stem, children=[dugum(e, a, np.eye(4)) for e, a in zip(etiketler, adlar, strict=True)]
        )
    validate(kok)
    return kok, parts
