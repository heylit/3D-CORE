"""
SPEC 26 — güvenli ifade değerlendirici (ölçüler ve parametreler).

Dil: sayılar, + − * / **, parantez, tekli eksi, parametre adları, pi, sqrt, sin, cos, tan (derece),
abs, min, max. Python eval kullanılmaz; ast ağacı beyaz listeyle yürünür. Başka her düğüm, bilinmeyen ad,
sıfıra bölme, sonsuz / nan sonuç ve parametreler arası döngü → IfadeError (adlarla).
"""

from __future__ import annotations

import ast
import math
import operator

SABITLER = {"pi": math.pi}
FONKSIYONLAR = {
    "sqrt": (math.sqrt, 1, 1),
    "sin": (lambda x: math.sin(math.radians(x)), 1, 1),
    "cos": (lambda x: math.cos(math.radians(x)), 1, 1),
    "tan": (lambda x: math.tan(math.radians(x)), 1, 1),
    "abs": (abs, 1, 1),
    "min": (min, 1, None),
    "max": (max, 1, None),
}
IKILI = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


class IfadeError(ValueError):
    """Geçersiz ya da değerlendirilemeyen ifade."""


def _sonlu(v, ne: str) -> float:
    if isinstance(v, complex) or not isinstance(v, (int, float)) or isinstance(v, bool):
        raise IfadeError(f"{ne}: sonuç gerçel sayı değil ({v!r})")
    v = float(v)
    if not math.isfinite(v):
        raise IfadeError(f"{ne}: sonuç sonlu değil ({v})")
    return v


def _agac(metin: str) -> ast.expr:
    """'=' önekini atar ve ifadeyi ayrıştırır."""
    s = metin.strip()
    if s.startswith("="):
        s = s[1:].strip()
    if not s:
        raise IfadeError(f"Boş ifade: {metin!r}")
    try:
        return ast.parse(s, mode="eval").body
    except SyntaxError as e:
        raise IfadeError(f"Sözdizimi hatası: {metin!r} ({e.msg})") from None


def _yuru(n: ast.AST, ortam: dict[str, float]) -> float:
    if isinstance(n, ast.Constant):
        if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
            raise IfadeError(f"Sayı olmayan sabit: {n.value!r}")
        return _sonlu(n.value, "sabit")
    if isinstance(n, ast.Name):
        if n.id in ortam:
            return _sonlu(ortam[n.id], f"parametre {n.id}")
        if n.id in SABITLER:
            return SABITLER[n.id]
        raise IfadeError(f"Bilinmeyen ad: {n.id}")
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = _yuru(n.operand, ortam)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.BinOp) and (type(n.op) in IKILI or isinstance(n.op, ast.Pow)):
        a, b = _yuru(n.left, ortam), _yuru(n.right, ortam)
        try:
            v = a**b if isinstance(n.op, ast.Pow) else IKILI[type(n.op)](a, b)
        except ZeroDivisionError:
            raise IfadeError("Sıfıra bölme") from None
        except OverflowError:
            raise IfadeError("Taşma: sonuç sonlu değil") from None
        return _sonlu(v, "işlem")
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FONKSIYONLAR:
        if n.keywords or any(isinstance(a, ast.Starred) for a in n.args):
            raise IfadeError(f"{n.func.id}: yalnız konumlu argüman")
        f, en_az, en_cok = FONKSIYONLAR[n.func.id]
        k = len(n.args)
        if k < en_az or (en_cok is not None and k > en_cok):
            raise IfadeError(f"{n.func.id}: argüman sayısı yanlış ({k})")
        args = [_yuru(a, ortam) for a in n.args]
        try:
            v = f(*args)
        except (ValueError, OverflowError) as e:
            raise IfadeError(f"{n.func.id}{tuple(args)}: {e}") from None
        return _sonlu(v, n.func.id)
    raise IfadeError(f"İzin verilmeyen ifade öğesi: {type(n).__name__}")


def degerlendir(ifade: str | float, ortam: dict[str, float] | None = None) -> float:
    """İfadeyi ortamdaki parametre değerleriyle değerlendirir.

    ifade: sayı, "40" ya da "=genislik/2" (baştaki "=" isteğe bağlı).
    """
    if isinstance(ifade, bool):
        raise IfadeError(f"Sayı olmayan değer: {ifade!r}")
    if isinstance(ifade, (int, float)):
        return _sonlu(ifade, "sayı")
    if not isinstance(ifade, str):
        raise IfadeError(f"İfade metin ya da sayı olmalı: {ifade!r}")
    return _yuru(_agac(ifade), dict(ortam or {}))


def _adlar(ifade: str | float) -> set[str]:
    """İfadedeki parametre adları (fonksiyon adları ve sabitler hariç)."""
    if not isinstance(ifade, str):
        return set()
    agac = _agac(ifade)
    cagri = {id(c.func) for c in ast.walk(agac) if isinstance(c, ast.Call)}
    return {n.id for n in ast.walk(agac) if isinstance(n, ast.Name) and id(n) not in cagri} - set(SABITLER)


def parametreleri_coz(parametreler: dict[str, str | float]) -> dict[str, float]:
    """Parametre tablosunu bağımlılık grafiğinin topolojik sırasıyla değerlendirir.
    Döngü (a = b, b = a) → IfadeError (döngüdeki adlarla)."""
    bag = {ad: _adlar(v) & set(parametreler) for ad, v in parametreler.items()}
    sonuc: dict[str, float] = {}
    yol: list[str] = []

    def coz(ad: str) -> None:
        if ad in sonuc:
            return
        if ad in yol:
            dongu = yol[yol.index(ad) :] + [ad]
            raise IfadeError(f"Parametre döngüsü: {' → '.join(dongu)}")
        yol.append(ad)
        for b in sorted(bag[ad]):
            coz(b)
        yol.pop()
        try:
            sonuc[ad] = degerlendir(parametreler[ad], sonuc)
        except IfadeError as e:
            raise IfadeError(f"Parametre {ad}: {e}") from None

    for ad in parametreler:
        coz(ad)
    return {ad: sonuc[ad] for ad in sorted(sonuc, key=list(parametreler).index)}
