"""
Doğrusal statik çözücü:  K u = F

Uygulanacak: specs/01-bar.md
"""

from __future__ import annotations

from core.model import Model, Result


def solve(model: Model) -> Result:
    """
    1. model.validate()
    2. K, F birleştir
    3. DOF'ları serbest (f) / tutulu (c) diye ayır, tutulu DOF'lara BC değerini yaz
    4. K_ff u_f = F_f - K_fc u_c   çöz
    5. Tepkiler: R = K u - F  (sadece tutulu DOF'larda, diğerleri 0)
    6. Eleman kuvvet ve gerilmelerini post.py ile hesapla
    Mekanizma (tekil K_ff) -> ModelError
    """
    raise NotImplementedError("specs/01-bar.md uygulanacak")
