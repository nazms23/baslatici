# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Turkce karakter duyarsiz bulanik arama."""

import re

_TR = str.maketrans("ıİiIşŞğĞüÜöÖçÇâÂîÎûÛ", "iiiissgguuoocc" + "aaiiuu")


def norm(text):
    return text.translate(_TR).casefold()


def score(query, name, extra=""):
    """0 = eslesme yok. Ad > kelime basi > alt dize > harf sirasi (bulanik)."""
    q = norm(query).strip()
    if not q:
        return 0
    n = norm(name)
    if n == q:
        return 1000
    if n.startswith(q):
        return 800 - len(n)
    words = re.split(r"[\s\-_.()]+", n)
    if any(w.startswith(q) for w in words):
        return 600 - len(n)
    if q in n:
        return 400 - n.index(q)
    e = norm(extra)
    if e and (q in e):
        return 250
    # bulanik: sorgunun harfleri sirayla geciyor mu (ardisik harflere bonus)
    pos, run, best = -1, 0, 0
    for ch in q:
        nxt = n.find(ch, pos + 1)
        if nxt < 0:
            return 0
        run = run + 1 if nxt == pos + 1 else 0
        best += 2 + run
        pos = nxt
    return min(200, best * 4)


MATH_RE = re.compile(r"^[\d(√πe\-−][\d\s+\-−*/×÷^%,.()πe√]*$")


def looks_like_math(text):
    t = text.strip()
    return bool(MATH_RE.match(t)) and any(op in t for op in "+-−*/×÷^%√") and any(c.isdigit() for c in t)
