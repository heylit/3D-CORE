"""SPEC 57 §5 — cam/plan2/sira.py testleri (K7, K8). OCCT gerektirmez.

Testler yalnızca SPEC 57 metninden ve iskeletteki imzalardan yazıldı; gövdeler okunmadı.
Maliyet: J = c_tc·N_tc + c_rot·N_rot; N_tc = ardışık farklı takım geçişi + ilk takım (SPEC 29
`tool_changes`), N_rot = ardışık farklı yönelim geçişi.

Arayüz netleştirmesi (kodlayıcı, durum/57 madde 1–2, 21cac89): yönelim `PlannedOp.setup`'tan okunur
(bağlama içi yönelim indeksi). `kind`'ler SPEC 29'dakiler artı "punta", "kilavuz", "havsa".
Aynı setup içinde yuz_alma → her şey; {acik_bolge, cep, cep_kalan} → {punta, delik, kilavuz, havsa,
lamba}; aynı adreste cep → cep_kalan; indeks kümesi kesişen `holes[…]` adresleri aynı delik:
punta → delik → {kilavuz, havsa, lamba}. Setup'lar arası öncelik yok; `precedence` her indeksi
(öncülsüzü boş kümeyle) içerir.

El hesapları (K7):
(a) A(T1)→B(T2), C(T1)→D(T2): özgün sıra A,B,C,D → N_tc = 4; en iyi A,C,B,D → 2 (alt sınır).
(b) A(T1)→B(T2)→C(T1): tek topolojik sıra → N_tc = 3.
(c) 3 delik × punta(T3)→matkap(T4)→kılavuz(T5): özgün sıra 9, en iyi 3 (önce bütün puntalar,
    sonra matkaplar, sonra kılavuzlar).
(d) iki yönelimde aynı takım: N_tc = 1, N_rot = 1.
"""

from __future__ import annotations

import itertools
import random

import pytest

from cam.cutting import SpindleFeed
from cam.model import CamError, Tool, ToolKind, Toolpath
from cam.plan import PlannedOp
from cam.plan2.sira import order_ops, precedence


def _op(i: int, tool_id: int, kind: str = "cep", feature: str | None = None, setup: int = 0) -> PlannedOp:
    T = Tool(id=tool_id, name=f"T{tool_id}", kind=ToolKind.FLAT, D=6.0, flute_length=20.0, flutes=2)
    tp = Toolpath(name=f"op{i}", tool=T, start=(0.0, 0.0, 10.0), rpm=1000.0)
    return PlannedOp(
        name=f"{i + 1:02d}-{kind}-T{tool_id}",
        kind=kind,
        setup=setup,
        feature=feature if feature is not None else f"pockets[{i}]",
        tool_id=tool_id,
        op=tp,
        spindle=SpindleFeed(n=1000, F=100.0, Vc=18.85, f=0.05),
        a_p=None,
        stepover=None,
    )


def _sayim(ops: list[PlannedOp], sira: list[int]) -> tuple[int, int]:
    """N_tc (ilk takım dahil) ve N_rot."""
    tc = rot = 0
    for k, i in enumerate(sira):
        if k == 0 or ops[i].tool_id != ops[sira[k - 1]].tool_id:
            tc += 1
        if k > 0 and ops[i].setup != ops[sira[k - 1]].setup:
            rot += 1
    return tc, rot


def _topolojik(sira: list[int], prec: dict[int, set[int]], n: int) -> bool:
    if sorted(sira) != list(range(n)):
        return False
    yer = {i: k for k, i in enumerate(sira)}
    return all(yer[p] < yer[i] for i, ps in prec.items() for p in ps)


def _kapanis(prec: dict[int, set[int]], n: int) -> dict[int, set[int]]:
    """Geçişli kapanış: i → bütün (dolaylı) öncülleri."""
    out = {i: set(prec.get(i, set())) for i in range(n)}
    degisti = True
    while degisti:
        degisti = False
        for i in range(n):
            ek = set().union(*(out[p] for p in out[i])) - out[i] if out[i] else set()
            if ek:
                out[i] |= ek
                degisti = True
    return out


def _J(ops, sira, c_tc=1.0, c_rot=0.1) -> float:
    tc, rot = _sayim(ops, sira)
    return c_tc * tc + c_rot * rot


# ---------------------------------------------------------------- K7


def test_iki_zincir_alt_sinir():
    ops = [_op(0, 1), _op(1, 2), _op(2, 1), _op(3, 2)]
    prec = {1: {0}, 3: {2}}
    assert _sayim(ops, [0, 1, 2, 3]) == (4, 0)
    sira, n_tc, n_rot = order_ops(ops, prec)
    assert list(sira) == [0, 2, 1, 3]  # eşitlikte özgün (29) sıraya en yakın
    assert (n_tc, n_rot) == (2, 0)
    assert _sayim(ops, list(sira)) == (n_tc, n_rot)


def test_zorunlu_gecis():
    ops = [_op(0, 1), _op(1, 2), _op(2, 1)]
    sira, n_tc, n_rot = order_ops(ops, {1: {0}, 2: {1}})
    assert list(sira) == [0, 1, 2]
    assert n_tc == 3 and n_rot == 0


def _delik_islemleri() -> list[PlannedOp]:
    ops = []
    for h in range(3):
        for kind, T in (("punta", 3), ("delik", 4), ("kilavuz", 5)):
            ops.append(_op(len(ops), T, kind=kind, feature=f"holes[{h}]"))
    return ops


def test_punta_matkap_kilavuz():
    ops = _delik_islemleri()
    prec = {3 * h + 1: {3 * h} for h in range(3)} | {3 * h + 2: {3 * h + 1} for h in range(3)}
    assert _sayim(ops, list(range(9)))[0] == 9
    sira, n_tc, _ = order_ops(ops, prec)
    assert n_tc == 3
    assert list(sira) == [0, 3, 6, 1, 4, 7, 2, 5, 8]
    assert _topolojik(list(sira), prec, 9)


def test_oncelik_delik_zinciri():
    """precedence(): aynı delikte punta → matkap → kılavuz (SPEC 29 kurallarından açıkça)."""
    ops = _delik_islemleri()
    prec = precedence(ops)
    kapanis = _kapanis(prec, 9)
    for h in range(3):
        p, m, k = 3 * h, 3 * h + 1, 3 * h + 2
        assert p in kapanis[m] and m in kapanis[k]
        for g in range(3):  # farklı deliklerin işlemleri birbirine bağlı değil
            if g != h:
                assert not (kapanis[k] & {3 * g, 3 * g + 1, 3 * g + 2})
    sira, n_tc, _ = order_ops(ops, prec)
    assert n_tc == 3 and _topolojik(list(sira), prec, 9)


def test_oncelik_yuz_alma_once():
    """Yüz alma aynı yöndeki (aynı yönelim) her işlemden önce."""
    ops = [_op(0, 2, kind="cep", feature="pockets[0]"), _op(1, 1, kind="yuz_alma", feature="faces[0]")]
    prec = precedence(ops)
    assert 1 in prec.get(0, set())
    sira, _, _ = order_ops(ops, prec)
    assert list(sira) == [1, 0]


def test_oncelik_tam_sozluk():
    ops = [_op(0, 1), _op(1, 2, kind="delik", feature="holes[0]"), _op(2, 3)]
    prec = precedence(ops)
    assert set(prec) == {0, 1, 2}
    assert all(isinstance(v, set) for v in prec.values())


def test_oncelik_cep_delikten_once():
    ops = [
        _op(0, 11, kind="delik", feature="holes[0,1]"),
        _op(1, 2, kind="cep", feature="pockets[0]"),
        _op(2, 3, kind="cep_kalan", feature="pockets[0]"),
        _op(3, 1, kind="acik_bolge", feature="opens[0]"),
    ]
    kapanis = _kapanis(precedence(ops), 4)
    assert {1, 2, 3} <= kapanis[0]
    assert 1 in kapanis[2]  # aynı adreste cep → cep_kalan
    assert not kapanis[1] & {0, 2} and not kapanis[3] & {0, 1, 2}


def test_oncelik_delik_grubu_kesisimi():
    # holes[0,1] matkap, holes[1] kılavuz ve havşa: indeks 1 ortak → aynı delik
    ops = [
        _op(0, 5, kind="kilavuz", feature="holes[1]"),
        _op(1, 6, kind="havsa", feature="holes[1]"),
        _op(2, 4, kind="delik", feature="holes[0,1]"),
        _op(3, 3, kind="punta", feature="holes[0,1]"),
        _op(4, 4, kind="delik", feature="holes[2]"),
    ]
    kapanis = _kapanis(precedence(ops), 5)
    assert 3 in kapanis[2] and {2, 3} <= kapanis[0] and {2, 3} <= kapanis[1]
    assert not kapanis[4]  # holes[2] ayrık
    assert 0 not in kapanis[1] and 1 not in kapanis[0]


def test_oncelik_setuplar_arasi_yok():
    ops = [_op(0, 1, kind="yuz_alma", feature="faces[0]", setup=0), _op(1, 2, kind="cep", setup=1)]
    prec = precedence(ops)
    assert prec == {0: set(), 1: set()}


def test_iki_yonelim_ayni_takim():
    ops = [_op(0, 1, setup=0), _op(1, 1, setup=1)]
    sira, n_tc, n_rot = order_ops(ops, {})
    assert (n_tc, n_rot) == (1, 1)
    assert sorted(sira) == [0, 1]


def test_yonelim_maliyeti_takimdan_ucuz():
    # A(T1, y0), B(T2, y0), C(T1, y1): A,C,B → N_tc 2, N_rot 2 (J = 2.2); A,B,C → 3, 1 (3.1)
    ops = [_op(0, 1, setup=0), _op(1, 2, setup=0), _op(2, 1, setup=1)]
    # C,A,B: N_tc 2, N_rot 1 → J = 2.1 (en iyi); A,C,B → 2.2; A,B,C → 3.1
    sira, n_tc, n_rot = order_ops(ops, {})
    assert (n_tc, n_rot) == (2, 1)
    assert _J(ops, list(sira)) == pytest.approx(2.1)
    # yönelim pahalıysa (c_rot = 5) yönelim değişimi en aza iner
    _, n_tc5, n_rot5 = order_ops(ops, {}, c_tc=1.0, c_rot=5.0)
    assert n_rot5 == 1 and n_tc5 == 2


# ---------------------------------------------------------------- K8


def _rastgele(n: int, rng: random.Random) -> tuple[list[PlannedOp], dict[int, set[int]]]:
    ops = [_op(i, rng.randint(1, 3), setup=rng.randint(0, 1)) for i in range(n)]
    prec: dict[int, set[int]] = {}
    for j in range(n):
        for i in range(j):
            if rng.random() < 0.25:
                prec.setdefault(j, set()).add(i)
    return ops, prec


def _en_iyi(ops, prec, c_tc=1.0, c_rot=0.1) -> float:
    n = len(ops)
    best = None
    for perm in itertools.permutations(range(n)):
        if _topolojik(list(perm), prec, n):
            J = _J(ops, list(perm), c_tc, c_rot)
            best = J if best is None else min(best, J)
    return best


@pytest.mark.parametrize("seed", range(12))
def test_dp_kaba_kuvvete_esit(seed):
    rng = random.Random(5700 + seed)
    n = rng.randint(3, 7)
    ops, prec = _rastgele(n, rng)
    sira, n_tc, n_rot = order_ops(ops, prec)
    sira = list(sira)
    assert _topolojik(sira, prec, n)
    assert _sayim(ops, sira) == (n_tc, n_rot)
    assert n_tc >= len({o.tool_id for o in ops})  # alt sınır
    assert _J(ops, sira) == pytest.approx(_en_iyi(ops, prec))


@pytest.mark.parametrize("seed", range(12))
def test_sezgisel_kotulesmez(seed):
    rng = random.Random(5800 + seed)
    n = rng.randint(4, 10)
    ops, prec = _rastgele(n, rng)
    sira, n_tc, n_rot = order_ops(ops, prec, exact_max=0)  # n > exact_max → sezgisel
    sira = list(sira)
    assert _topolojik(sira, prec, n)
    assert _sayim(ops, sira) == (n_tc, n_rot)
    assert _J(ops, sira) <= _J(ops, list(range(n))) + 1e-12  # özgün (29) sıradan kötü değil


def test_buyuk_n_sezgisel():
    rng = random.Random(57)
    ops, prec = _rastgele(30, rng)
    sira, n_tc, n_rot = order_ops(ops, prec)
    assert _topolojik(list(sira), prec, 30)
    assert _J(ops, list(sira)) <= _J(ops, list(range(30))) + 1e-12


def test_donguli_dag():
    ops = [_op(0, 1), _op(1, 2), _op(2, 1)]
    with pytest.raises(CamError):
        order_ops(ops, {0: {2}, 1: {0}, 2: {1}})
    with pytest.raises(CamError):
        order_ops(ops, {0: {0}})
