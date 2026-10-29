# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Hesap motoru (hesap-makinesi projesinden): arama kutusunda "=240*15%" icin.

eval yok, ifade ast ile cozulur; Decimal hassasiyet; Turkce sayi bicimi.
"""

import ast
import math
import re
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext

getcontext().prec = 34


# ───────────────────────── Hesaplama motoru ─────────────────────────

class CalcError(Exception):
    pass


def _d(x):
    """float -> Decimal (kisa temsil, 0.1 -> Decimal('0.1'))."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        raise CalcError("Tanımsız")
    return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)


def _clean(x):
    """Trigonometrideki 1e-17 gibi kalintilari sifirla."""
    return Decimal(0) if abs(x) < Decimal("1e-15") else x


def _sqrt(x):
    if x < 0:
        raise CalcError("Negatif sayının karekökü yok")
    return x.sqrt()


def _log(x, fn):
    if x <= 0:
        raise CalcError("Logaritma için sayı pozitif olmalı")
    return _d(fn(float(x)))


FUNCS = {
    "sqrt": _sqrt,
    "sin": lambda x: _clean(_d(math.sin(math.radians(float(x))))),
    "cos": lambda x: _clean(_d(math.cos(math.radians(float(x))))),
    "tan": lambda x: _tan(x),
    "ln": lambda x: _log(x, math.log),
    "log": lambda x: _log(x, math.log10),
    "abs": abs,
}

CONSTS = {"pi": _d(math.pi), "e": _d(math.e)}


def _tan(x):
    if float(x) % 180 == 90:
        raise CalcError("tan(90°) tanımsız")
    return _clean(_d(math.tan(math.radians(float(x)))))


def to_python(expr):
    """Ekrandaki ifadeyi (× ÷ − ^ √ π , %) Python ifadesine cevirir."""
    s = expr
    for a, b in (("×", "*"), ("÷", "/"), ("−", "-"), ("^", "**"), ("π", "(pi)"), (",", "."), ("√", "sqrt")):
        s = s.replace(a, b)
    s = s.replace("%", "/100")
    # Ortulu carpma: 2π, 2(3), )(, 3sin(30)
    # ("e" sabiti harf olmayan komsularla ayirt edilir; \b rakam-harf arasinda calismaz)
    E = r"(?<![a-z])e(?![a-z])"
    for _ in range(2):  # ust uste binen eslesmeler icin (2eπ)
        s = re.sub(rf"(\d|\)|pi|{E})\s*(\(|pi|{E}|sqrt|sin|cos|tan|ln|log|abs)", r"\1*\2", s)
    # Kapanmamis parantezleri tamamla (onizleme ve "=" icin)
    s += ")" * max(0, s.count("(") - s.count(")"))
    return s


_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _d(node.value)
    if isinstance(node, ast.Name) and node.id in CONSTS:
        return CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINOPS):
        a, b = _eval(node.left), _eval(node.right)
        op = node.op
        try:
            if isinstance(op, ast.Add):
                return a + b
            if isinstance(op, ast.Sub):
                return a - b
            if isinstance(op, ast.Mult):
                return a * b
            if isinstance(op, ast.Div):
                if b == 0:
                    raise CalcError("Sıfıra bölünemez")
                return a / b
            if isinstance(op, ast.Mod):
                if b == 0:
                    raise CalcError("Sıfıra bölünemez")
                return a % b
            if isinstance(op, ast.Pow):
                if b == b.to_integral_value() and abs(b) <= 10000:
                    if a == 0 and b < 0:
                        raise CalcError("Sıfıra bölünemez")
                    return a ** int(b)
                if a < 0:
                    raise CalcError("Negatif sayının kesirli kuvveti yok")
                return _d(float(a) ** float(b))
        except (InvalidOperation, DivisionByZero, OverflowError):
            raise CalcError("Sonuç çok büyük")
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in FUNCS and len(node.args) == 1 and not node.keywords):
        return FUNCS[node.func.id](_eval(node.args[0]))
    raise CalcError("Geçersiz ifade")


def evaluate(expr):
    src = to_python(expr).strip()
    if not src:
        raise CalcError("Boş")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        raise CalcError("Geçersiz ifade")
    return _eval(tree)


def fmt(x):
    """Decimal -> Turkce bicim: 1.234.567,89 ; cok buyuk/kucukte bilimsel."""
    if x.is_nan() or x.is_infinite():
        raise CalcError("Tanımsız")
    if x == 0:
        return "0"
    ax = abs(x)
    if ax >= Decimal("1e15") or ax < Decimal("1e-9"):
        mant, _, exp = f"{x:.10e}".partition("e")
        mant = mant.rstrip("0").rstrip(".")
        return mant.replace(".", ",") + "×10^" + str(int(exp))
    q = x.quantize(Decimal("1e-12")).normalize()
    sign = "-" if q < 0 else ""
    ip, _, fp = f"{abs(q):f}".partition(".")
    ip = f"{int(ip):,}".replace(",", ".")
    return sign + ip + ("," + fp if fp else "")


def raw(x):
    """Sonucu yeniden hesaplanabilir girdi olarak (binlik ayraci yok)."""
    s = fmt(x)
    if "×10^" in s:
        mant, exp = s.split("×10^")
        return f"{mant}×10^{exp}"
    return s.replace(".", "")
