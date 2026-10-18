"""
Test bağımsızlığı kapısı (CLAUDE.md "Test bağımsızlığı").

Bir PR'daki merge olmayan commit'leri tarar. Commit mesajındaki `Claude-Session:` izi commit'i yazan
Claude oturumunu verir; cherry-pick bu izi korur. Kural:

1. Tek bir Claude commit'i hem test hem kod dosyasını değiştiremez.
2. Aynı Claude oturumu PR'da hem test değiştiren hem kod değiştiren commit'lere sahip olamaz.

Dosya sınıfları:
- test: `tests/` altındaki her dosya ve her `conftest.py`
- kod:  diğer `.py` dosyaları; `scripts/`, `.github/`, `.claude/`, `_kurulum/`, `docs/` hariç
  (bunlar araçtır, ürün kodu değil)
- nötr: geri kalan her şey (belgeler, SPEC'ler, durum, örnek JSON, pyproject, ci.ps1 ...)

İz taşımayan commit'ler (insan commit'leri) ve merge commit'leri denetlenmez.

İstisna: PR'a `bagimsizlik-istisnasi` etiketi depo sahibi tarafından GitHub arayüzünden (bir GitHub
App üzerinden değil) eklenmişse, etiketlendiği anda PR'da bulunan ihlaller kabul edilir. Etiketten
sonra gelen yeni bir ihlal commit'i kapıyı yeniden kırmızı yapar.

Kullanım (CI):  python scripts/bagimsizlik_kapisi.py --taban <base_sha> --uc <head_sha>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

ETIKET = "bagimsizlik-istisnasi"
ARAC_KLASORLERI = ("scripts/", ".github/", ".claude/", "_kurulum/", "docs/")
_OTURUM = re.compile(r"^Claude-Session:.*?(session_[A-Za-z0-9]+)", re.MULTILINE)


@dataclass
class Commit:
    sha: str
    oturum: str | None  # None = iz yok (insan commit'i)
    dosyalar: list[str]
    tarih: datetime | None = None  # committer tarihi (istisna penceresi için)
    test: bool = field(init=False)
    kod: bool = field(init=False)

    def __post_init__(self) -> None:
        siniflar = {sinif(d) for d in self.dosyalar}
        self.test = "test" in siniflar
        self.kod = "kod" in siniflar


@dataclass
class Ihlal:
    mesaj: str
    shalar: list[str]


def sinif(yol: str) -> str:
    """Dosya yolunu 'test', 'kod' veya 'notr' olarak sınıflandırır."""
    if yol.startswith("tests/") or yol.rsplit("/", 1)[-1] == "conftest.py":
        return "test"
    if yol.endswith(".py") and not yol.startswith(ARAC_KLASORLERI):
        return "kod"
    return "notr"


def oturum_bul(mesaj: str) -> str | None:
    """Commit mesajındaki son `Claude-Session:` satırından oturum kimliğini (session_...) döndürür."""
    bulunan = _OTURUM.findall(mesaj)
    return bulunan[-1] if bulunan else None


def denetle(commitler: list[Commit]) -> list[Ihlal]:
    """Kurala aykırı commit'leri döndürür. Boş liste = kapı yeşil."""
    ihlaller: list[Ihlal] = []
    for c in commitler:
        if c.oturum and c.test and c.kod:
            ihlaller.append(
                Ihlal(f"{c.sha[:8]} tek commit'te hem test hem kod değiştiriyor ({c.oturum})", [c.sha])
            )
    oturumlar = sorted({c.oturum for c in commitler if c.oturum})
    for s in oturumlar:
        testler = [c.sha for c in commitler if c.oturum == s and c.test]
        kodlar = [c.sha for c in commitler if c.oturum == s and c.kod]
        if testler and kodlar and set(testler) != set(kodlar):
            kisa = ", ".join
            ihlaller.append(
                Ihlal(
                    f"{s} oturumu hem testleri ({kisa(x[:8] for x in testler)}) "
                    f"hem kodu ({kisa(x[:8] for x in kodlar)}) değiştiriyor",
                    sorted(set(testler) | set(kodlar)),
                )
            )
    return ihlaller


def istisna_gecerli(olaylar: list[dict], sahip: str, ihlaller: list[Ihlal], commitler: list[Commit]) -> bool:
    """
    `olaylar`: GitHub issue events listesi (eskiden yeniye). Etiket şu an PR'da olmalı, son ekleyen
    depo sahibi olmalı, ekleme bir GitHub App (ör. Claude) üzerinden yapılmamış olmalı ve
    her ihlal commit'i etiketten önce yazılmış olmalı.
    """
    son = None
    for o in olaylar:
        if (o.get("label") or {}).get("name") != ETIKET:
            continue
        if o.get("event") == "labeled":
            son = o
        elif o.get("event") == "unlabeled":
            son = None
    if son is None or son.get("performed_via_github_app"):
        return False
    if (son.get("actor") or {}).get("login") != sahip:
        return False
    an = _tarih(son["created_at"])
    tarihler = {c.sha: c.tarih for c in commitler}
    for i in ihlaller:
        for sha in i.shalar:
            t = tarihler.get(sha)
            if t is None or t > an:
                return False
    return True


def _tarih(metin: str) -> datetime:
    return datetime.fromisoformat(metin.replace("Z", "+00:00"))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def commitleri_oku(taban: str, uc: str) -> list[Commit]:
    """`taban..uc` aralığındaki merge olmayan commit'leri eskiden yeniye okur."""
    shalar = _git("rev-list", "--no-merges", "--reverse", f"{taban}..{uc}").split()
    commitler = []
    for sha in shalar:
        mesaj = _git("show", "-s", "--format=%B", sha)
        tarih = _tarih(_git("show", "-s", "--format=%cI", sha).strip())
        dosyalar = _git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).split("\n")
        commitler.append(Commit(sha, oturum_bul(mesaj), [d for d in dosyalar if d], tarih))
    return commitler


def _olaylari_getir(depo: str, pr: str, token: str) -> list[dict]:
    olaylar: list[dict] = []
    sayfa = 1
    while True:
        url = f"https://api.github.com/repos/{depo}/issues/{pr}/events?per_page=100&page={sayfa}"
        istek = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(istek, timeout=30) as yanit:
            parca = json.load(yanit)
        olaylar += parca
        if len(parca) < 100:
            return olaylar
        sayfa += 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--taban", required=True, help="PR taban commit'i (base sha)")
    p.add_argument("--uc", required=True, help="PR uç commit'i (head sha)")
    a = p.parse_args(argv)

    commitler = commitleri_oku(_git("merge-base", a.taban, a.uc).strip(), a.uc)
    for c in commitler:
        taraf = "+".join(t for t, var in (("test", c.test), ("kod", c.kod)) if var) or "nötr"
        print(f"  {c.sha[:8]}  {c.oturum or 'iz yok':40}  {taraf}")

    ihlaller = denetle(commitler)
    if not ihlaller:
        print("Test bağımsızlığı: tamam.")
        return 0
    for i in ihlaller:
        print(f"::error::Test bağımsızlığı ihlali: {i.mesaj}")

    depo, pr, token = (os.environ.get(k) for k in ("GITHUB_REPOSITORY", "PR_NUMARASI", "GITHUB_TOKEN"))
    if depo and pr and token:
        sahip = depo.split("/")[0]
        if istisna_gecerli(_olaylari_getir(depo, pr, token), sahip, ihlaller, commitler):
            print(f"::warning::İhlaller '{ETIKET}' etiketiyle (depo sahibi, GitHub arayüzü) kabul edildi.")
            return 0
    print(
        f"Kapı kırmızı. Testler ve kod ayrı oturumlarda yazılmalı (CLAUDE.md). İstisna için depo sahibi "
        f"PR'a GitHub arayüzünden '{ETIKET}' etiketini ekler."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
