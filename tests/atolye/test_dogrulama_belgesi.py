"""SPEC 38 K9 — işe özel doğrulama maddeleri (§7) ve docs/tezgah-dogrulama.md eşlemesi.

Ek A elle: §2 G55 kaydı (−250, −190, −80), §3 GRBL ΔL = 0 / 15 (referans T1),
§4 z_tepe = max(0, 10) = 10 → h = max(50, ⌈10 − (−20)⌉ + 10) = max(50, 40) = 50,
§5 k = ölçüm kalemi sayısı.
Testler yalnız SPEC 38 metninden yazıldı; `atolye` uygulama kodu okunmadı.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from atolye import CheckItem, build_job_sheet
from cam.gcode import FANUC
from cam.model import Move, MoveType, Setup, Stock, Toolpath, Wcs
from tests.atolye import ek_a

BELGE = Path(__file__).resolve().parents[2] / "docs" / "tezgah-dogrulama.md"


def job_ek_a(**kw):
    args = dict(machine=ek_a.machine())
    args.update(kw)
    setups = args.pop("setups", [ek_a.setup()])
    ops = args.pop("ops", [ek_a.ops()])
    return build_job_sheet("Ek A", setups, ops, ek_a.lib(), ek_a.MATERIAL, **args)


def test_ek_a_grbl_maddeleri():
    job = job_ek_a()
    k = len(job.inspection)
    assert k >= 1
    assert list(job.checks) == [
        CheckItem(2, "G55 kaydına X-250,000 Y-190,000 Z-80,000 girildi"),
        CheckItem(2, "Sıfır: X0 sol kenar, Y0 ön kenar, Z0 üst yüz"),
        CheckItem(3, "T1: G43.1 Z0,000 (referans T1)"),
        CheckItem(3, "T2: G43.1 Z15,000 (referans T1)"),
        CheckItem(4, "Kuru çalıştırma: G55 Z'si +50 mm kaydırıldı"),
        CheckItem(5, f"İlk parça ölçüm listesindeki {k} kalem ölçüldü ve kaydedildi"),
    ]


def test_n_max_maddesi_basta():
    job = job_ek_a(n_max=12000)
    assert job.checks[0] == CheckItem(1, "En yüksek devir S10000 ≤ tezgâh sınırı 12000")
    assert list(job.checks[1:]) == list(job_ek_a().checks)


def test_fanuc_ve_bilinmeyen_boy():
    job = job_ek_a(dialect=FANUC)
    bolum3 = [c.text for c in job.checks if c.section == 3]
    assert len(bolum3) == 2
    # "T<n>: H<n> = <L>"; L = 90 / 105 (sayı biçimi dialect.decimals ya da format_value)
    assert re.fullmatch(r"T1: H1 = 90(,000)?", bolum3[0]), bolum3[0]
    assert re.fullmatch(r"T2: H2 = 105(,000)?", bolum3[1]), bolum3[1]

    t2 = ek_a.T2(holder=None)
    lib = ek_a.lib(t2=t2)
    job = build_job_sheet(
        "Ek A", [ek_a.setup()], [[ek_a.tp1(), ek_a.tp2(t2)]], lib, "al", machine=ek_a.machine()
    )
    bolum3 = [c.text for c in job.checks if c.section == 3]
    assert bolum3 == ["T1: ölçü boyu tezgâhta ölçülecek", "T2: ölçü boyu tezgâhta ölçülecek"]


def test_kuru_calistirma_h():
    """Bağlama elemanı yok, Stock(0, 0, −100, 50, 40, 0): h = max(50, ⌈0 + 100⌉ + 10) = 110."""
    s = Setup("derin", Wcs("G54", (0, 0, 0)), Stock(0, 0, -100, 50, 40, 0))
    tp = Toolpath(
        "cep", ek_a.T1(), start=(5, 5, 15), moves=[Move(MoveType.LINEAR, (5, 5, -1), 100)], rpm=10000
    )
    job = job_ek_a(setups=[s], ops=[[tp]])
    bolum4 = [c.text for c in job.checks if c.section == 4]
    assert bolum4 == ["Kuru çalıştırma: G54 Z'si +110 mm kaydırıldı"]


def test_olcum_yoksa_bolum5_yok():
    """k = 0 → §5 maddesi yok. Ölçüm kalemi vermeyen iş: kesme derinliği ≤ 0 (havada)."""
    tp = Toolpath(
        "hava", ek_a.T1(), start=(5, 5, 15), moves=[Move(MoveType.LINEAR, (5, 5, 1), 100)], rpm=10000
    )
    job = job_ek_a(ops=[[tp]])
    assert job.inspection == ()
    assert not [c for c in job.checks if c.section == 5]


def _belge() -> str:
    """Belge metni. "## 6." bölümü kod commit'inde eklenir; o zamana dek test "uygulanmamış" sayılır
    (NotImplementedError: yerelde TDD için atlanır, CI'da `--uygulanmamis-hata` ile kırmızı)."""
    metin = BELGE.read_text(encoding="utf-8")
    if "\n## 6." not in metin:
        raise NotImplementedError("SPEC 38: docs/tezgah-dogrulama.md '## 6. İş föyü' bölümü henüz yok")
    return metin


def _basliklar() -> list[str]:
    return [s for s in _belge().splitlines() if s.startswith("## ")]


def test_belge_basliklari():
    basliklar = _basliklar()
    for n in range(1, 7):
        assert any(b.startswith(f"## {n}.") for b in basliklar), f"'## {n}.' başlığı yok"
    assert any(b.startswith("## 6. İş föyü") for b in basliklar)


@pytest.mark.parametrize("n_max", [None, 12000])
def test_her_madde_bolumu_belgede(n_max):
    basliklar = _basliklar()
    for c in job_ek_a(n_max=n_max).checks:
        assert 1 <= c.section <= 5
        assert any(b.startswith(f"## {c.section}.") for b in basliklar)


def test_bolum6_write_job_sheet():
    metin = _belge()
    i = metin.index("\n## 6.")
    bolum6 = metin[i:]
    j = bolum6.find("\n## ", 1)
    if j > 0:
        bolum6 = bolum6[:j]
    assert "write_job_sheet" in bolum6
