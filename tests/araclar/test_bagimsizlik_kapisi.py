"""scripts/bagimsizlik_kapisi.py: test bağımsızlığı CI kapısı."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_YOL = Path(__file__).resolve().parents[2] / "scripts" / "bagimsizlik_kapisi.py"
_spec = importlib.util.spec_from_file_location("bagimsizlik_kapisi", _YOL)
kapi = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = kapi  # dataclass modülü sys.modules'te arar
_spec.loader.exec_module(kapi)

A = "session_01AAAAAAAAAAAAAAAAAAAAAA"
B = "session_01BBBBBBBBBBBBBBBBBBBBBB"
SAHIP = "heylit"


def _c(sha, oturum, *dosyalar, saat=10):
    return kapi.Commit(sha, oturum, list(dosyalar), datetime(2026, 10, 18, saat, tzinfo=UTC))


@pytest.mark.parametrize(
    "yol, beklenen",
    [
        ("tests/cam/test_model.py", "test"),
        ("tests/benchmarks/tet_ag.py", "test"),
        ("tests/fixtures/parca.json", "test"),
        ("conftest.py", "test"),
        ("cam/model.py", "kod"),
        ("core/elements/tet4.py", "kod"),
        ("viz/__main__.py", "kod"),
        ("scripts/bagimsizlik_kapisi.py", "notr"),
        (".github/workflows/test.yml", "notr"),
        ("durum/15-goruntuleyici.md", "notr"),
        ("specs/11-tet4.md", "notr"),
        ("examples/11_tet4_cekme.json", "notr"),
        ("pyproject.toml", "notr"),
    ],
)
def test_sinif(yol, beklenen):
    assert kapi.sinif(yol) == beklenen


def test_oturum_bul_iz_satirindan():
    mesaj = (
        "SPEC 11: tests\n\n"
        "https://claude.ai/code/session_01XXXXXXXXXXXXXXXXXXXXXX gövdede geçse de sayılmaz\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
        f"Claude-Session: https://claude.ai/code/{A}\n"
    )
    assert kapi.oturum_bul(mesaj) == A


def test_oturum_bul_iz_yoksa_none():
    assert kapi.oturum_bul("insan commit'i\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n") is None


def test_ayri_oturumlar_yesil():
    # Kodcu iskeleti, test oturumu testleri, kodcu kodu yazar (cherry-pick izi korur).
    commitler = [
        _c("1" * 40, A, "cam/islem.py"),
        _c("2" * 40, B, "tests/cam/test_islem.py"),
        _c("3" * 40, A, "cam/islem.py", "durum/03-cam.md"),
    ]
    assert kapi.denetle(commitler) == []


def test_tek_commit_hem_test_hem_kod_kirmizi():
    ihlaller = kapi.denetle([_c("1" * 40, A, "cam/islem.py", "tests/cam/test_islem.py")])
    assert len(ihlaller) == 1
    assert ihlaller[0].shalar == ["1" * 40]


def test_ayni_oturum_iki_tarafa_dokununca_kirmizi():
    ihlaller = kapi.denetle([_c("1" * 40, A, "tests/cam/test_islem.py"), _c("2" * 40, A, "cam/islem.py")])
    assert len(ihlaller) == 1
    assert set(ihlaller[0].shalar) == {"1" * 40, "2" * 40}


def test_iz_tasimayan_commitler_denetlenmez():
    assert kapi.denetle([_c("1" * 40, None, "cam/islem.py", "tests/cam/test_islem.py")]) == []


def test_sadece_belge_ve_nötr_yesil():
    assert kapi.denetle([_c("1" * 40, A, "README.md", "scripts/x.py", "tests/cam/test_islem.py")]) == []


def _olay(olay, saat, app=None, aktor=SAHIP, etiket=kapi.ETIKET):
    return {
        "event": olay,
        "label": {"name": etiket},
        "actor": {"login": aktor},
        "performed_via_github_app": app,
        "created_at": f"2026-10-18T{saat:02d}:00:00Z",
    }


def _ihlalli():
    commitler = [_c("1" * 40, A, "cam/islem.py", "tests/cam/test_islem.py", saat=10)]
    return commitler, kapi.denetle(commitler)


def test_istisna_sahip_arayuzden_etiketlerse_gecerli():
    commitler, ihlaller = _ihlalli()
    assert kapi.istisna_gecerli([_olay("labeled", 11)], SAHIP, ihlaller, commitler)


def test_istisna_github_app_ile_eklenirse_gecersiz():
    commitler, ihlaller = _ihlalli()
    olaylar = [_olay("labeled", 11, app={"slug": "claude"})]
    assert not kapi.istisna_gecerli(olaylar, SAHIP, ihlaller, commitler)


def test_istisna_baskasi_eklerse_gecersiz():
    commitler, ihlaller = _ihlalli()
    assert not kapi.istisna_gecerli([_olay("labeled", 11, aktor="biri")], SAHIP, ihlaller, commitler)


def test_istisna_etiketten_sonraki_ihlali_kapsamaz():
    commitler, ihlaller = _ihlalli()
    assert not kapi.istisna_gecerli([_olay("labeled", 9)], SAHIP, ihlaller, commitler)


def test_istisna_etiket_kaldirilinca_gecersiz():
    commitler, ihlaller = _ihlalli()
    olaylar = [_olay("labeled", 11), _olay("unlabeled", 12)]
    assert not kapi.istisna_gecerli(olaylar, SAHIP, ihlaller, commitler)


def test_istisna_baska_etiket_sayilmaz():
    commitler, ihlaller = _ihlalli()
    assert not kapi.istisna_gecerli([_olay("labeled", 11, etiket="hata")], SAHIP, ihlaller, commitler)


@pytest.mark.skipif(shutil.which("git") is None, reason="git yok")
def test_git_deposundan_okuma(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    def commit(dosya, mesaj):
        (tmp_path / dosya).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / dosya).write_text(mesaj)
        git("add", ".")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", mesaj)

    git("init", "-q", "-b", "main")
    commit("README.md", "ilk")
    taban = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    commit("tests/test_x.py", f"testler\n\nClaude-Session: https://claude.ai/code/{B}")
    commit("pkg/x.py", f"kod\n\nClaude-Session: https://claude.ai/code/{A}")
    monkeypatch.chdir(tmp_path)
    commitler = kapi.commitleri_oku(taban, "HEAD")
    assert [(c.oturum, c.test, c.kod) for c in commitler] == [(B, True, False), (A, False, True)]
    assert kapi.main(["--taban", taban, "--uc", "HEAD"]) == 0
    commit("tests/test_y.py", f"aynı oturum test\n\nClaude-Session: https://claude.ai/code/{A}")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert kapi.main(["--taban", taban, "--uc", "HEAD"]) == 1
