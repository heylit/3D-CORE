"""SPEC 64 K7 — tek yön ve veritabanı yok (AST taraması).

- Tüm repo (`tests/` hariç) PostgreSQL / ORM sürücüsü içe aktarmaz: psycopg, psycopg2, asyncpg, sqlalchemy,
  pg8000.
- `tezgah/mes/` ağ istemcisi içe aktarmaz: httpx, requests, urllib.request, socket (Tezgah MES'e istek atmaz).
`import x.y`, `from x import y`, `from x.y import z` ve `importlib.import_module("x")` / `__import__("x")`
biçimleri taranır; `from urllib import request` de `urllib.request` sayılır.
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
DB = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "pg8000"}
AG = {"httpx", "requests", "urllib.request", "socket"}
ATLA = {"tests", ".venv", "venv", ".git", "node_modules", "build", "dist", "yerel_parcalar", "__pycache__"}


def _modulleri(kod: str) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(ast.parse(kod)):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
        elif isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant):
            f = n.func
            ad = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if ad in ("import_module", "__import__") and isinstance(n.args[0].value, str):
                out.add(n.args[0].value)
    return out


def _yasak(moduller: set[str], yasak: set[str]) -> set[str]:
    return {m for m in moduller for y in yasak if m == y or m.startswith(y + ".")}


def _py(kok: Path):
    for p in kok.rglob("*.py"):
        if not set(p.relative_to(KOK).parts) & ATLA:
            yield p


def test_tarayici_kendini_dogrular():
    """Tarama biçimlerinin hepsi yakalanıyor (yanlış negatif olmasın)."""
    kod = (
        "import psycopg2.extras\nfrom sqlalchemy import create_engine\nimport socket\n"
        "from urllib import request\nimport importlib\nimportlib.import_module('asyncpg')\n"
        "x = __import__('httpx')\nimport urllib.parse\n"
    )
    m = _modulleri(kod)
    assert _yasak(m, DB) == {"psycopg2.extras", "sqlalchemy", "sqlalchemy.create_engine", "asyncpg"}
    assert _yasak(m, AG) == {"socket", "urllib.request", "httpx"}


def test_repo_db_surucusu_yok():
    ihlal = {}
    for p in _py(KOK):
        bul = _yasak(_modulleri(p.read_text(encoding="utf-8")), DB)
        if bul:
            ihlal[str(p.relative_to(KOK))] = sorted(bul)
    assert not ihlal, ihlal


def test_mes_ag_istemcisi_yok():
    mes = KOK / "tezgah" / "mes"
    dosyalar = list(mes.rglob("*.py"))
    assert dosyalar, "tezgah/mes/ yok"
    ihlal = {}
    for p in dosyalar:
        bul = _yasak(_modulleri(p.read_text(encoding="utf-8")), AG | DB)
        if bul:
            ihlal[str(p.relative_to(KOK))] = sorted(bul)
    assert not ihlal, ihlal
