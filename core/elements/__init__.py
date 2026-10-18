"""
Eleman kütüphanesi.

Her eleman modülü şu fonksiyonları sağlar (sözleşme):

    ke(element, model) -> np.ndarray
        Global koordinatlarda eleman rijitlik matrisi (n x n, simetrik).

    dofs(element, model) -> list[int]
        ke satır/sütunlarının karşılık geldiği global DOF numaraları.

    axial_force(element, model, u) -> float          (sadece çubuk tipi elemanlar)
        Global yer değiştirme vektörü u'dan eleman iç kuvveti [N] (+ çekme).

    stress(element, model, u) -> np.ndarray (6,)     (sadece katı elemanlar)
        Gerilme tensörü [MPa], Voigt: xx, yy, zz, xy, xz, yz (specs/11-tet4.md).

    volume(element, model) -> float                  (sadece katı elemanlar)
        Eleman hacmi [mm³]; düğüm gerilmesinin hacim ağırlığı (specs/13-calculix.md).

    me(element, model, lumped=False) -> np.ndarray   (isteğe bağlı; modal analiz için)
        Kütle matrisi [t], ke ile aynı boyut ve DOF sırası; tutarlı veya toplanmış (specs/45-modal.md).
        Sağlamayan eleman tipi core.modal'da ModelError verir.

ke ve dofs her elemanda zorunludur.

Yeni eleman eklemek = bu klasöre bir dosya + aşağıdaki sözlüğe bir satır.
assembly.py ve solver.py'ye DOKUNULMAZ.
"""

from core.elements import bar1d, tet4, tet10

ELEMENTS = {
    "bar1d": bar1d,
    "tet4": tet4,
    "tet10": tet10,
}


def get(element_type: str):
    from core.model import ModelError

    try:
        return ELEMENTS[element_type]
    except KeyError:
        raise ModelError(f"Bilinmeyen eleman tipi: {element_type}") from None
