"""
Eleman kütüphanesi.

Her eleman modülü şu üç fonksiyonu sağlar (sözleşme):

    ke(element, model) -> np.ndarray
        Global koordinatlarda eleman rijitlik matrisi (n x n, simetrik).

    dofs(element, model) -> list[int]
        ke satır/sütunlarının karşılık geldiği global DOF numaraları.

    axial_force(element, model, u) -> float
        Global yer değiştirme vektörü u'dan eleman iç kuvveti [N] (+ çekme).

Yeni eleman eklemek = bu klasöre bir dosya + aşağıdaki sözlüğe bir satır.
assembly.py ve solver.py'ye DOKUNULMAZ.
"""

from core.elements import bar1d, tet4

ELEMENTS = {
    "bar1d": bar1d,
    "tet4": tet4,
}


def get(element_type: str):
    from core.model import ModelError

    try:
        return ELEMENTS[element_type]
    except KeyError:
        raise ModelError(f"Bilinmeyen eleman tipi: {element_type}") from None
