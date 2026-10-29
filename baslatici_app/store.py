# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Favori duzeni (uygulamalar + klasorler) ve kullanim istatistigi (sik kullanilanlar).

duzen.json: {"favorites": [{"app": "kitty.desktop"}, {"folder": "Oyunlar", "apps": [...]}]}
kullanim.json: {"kitty.desktop": [son acilis zamanlari, ...]}
"""

import json
import os
import time

CONFIG_DIR = os.path.expanduser("~/.config/baslatici")
DATA_DIR = os.path.expanduser("~/.local/share/baslatici")
LAYOUT_FILE = os.path.join(CONFIG_DIR, "duzen.json")
USAGE_FILE = os.path.join(DATA_DIR, "kullanim.json")

# Ilk acilista bu sirayla (kuruluysa) favorilere eklenir
DEFAULT_FAVORITES = [
    "google-chrome.desktop", "firefox.desktop", "brave-browser.desktop", "kitty.desktop",
    "org.kde.dolphin.desktop", "discord.desktop", "spotify-launcher.desktop", "steam.desktop",
    "hesap-makinesi.desktop", "code.desktop", "nvim.desktop",
]


def _read(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    # Yerinde yaz (symlink'li dosyalar kirilmasin)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Layout:
    def __init__(self, installed_ids):
        data = _read(LAYOUT_FILE, None)
        if data is None:
            favs = [{"app": a} for a in DEFAULT_FAVORITES if a in installed_ids][:8]
            data = {"favorites": favs}
            _write(LAYOUT_FILE, data)
        self.favorites = data.get("favorites", [])

    def save(self):
        _write(LAYOUT_FILE, {"favorites": self.favorites})

    # ── sorgular ──
    def is_favorite(self, app_id):
        return any(e.get("app") == app_id or app_id in e.get("apps", []) for e in self.favorites)

    def visible(self, apps):
        """Kaldirilmis uygulamalari gizle (duzende kalir, tekrar kurulunca geri gelir)."""
        out = []
        for i, e in enumerate(self.favorites):
            if "app" in e and e["app"] in apps:
                out.append((i, e))
            elif "folder" in e:
                members = [a for a in e["apps"] if a in apps]
                if members:
                    out.append((i, {"folder": e["folder"], "apps": members}))
        return out

    # ── ust seviye ──
    def add(self, app_id, index=None):
        if self.is_favorite(app_id):
            self.remove_app(app_id)
        entry = {"app": app_id}
        if index is None or index > len(self.favorites):
            self.favorites.append(entry)
        else:
            self.favorites.insert(index, entry)

    def remove_index(self, index):
        del self.favorites[index]

    def remove_app(self, app_id):
        """Uygulamayi nerede olursa olsun (ust seviye / klasor) favorilerden cikar."""
        new = []
        for e in self.favorites:
            if e.get("app") == app_id:
                continue
            if "folder" in e:
                e = {"folder": e["folder"], "apps": [a for a in e["apps"] if a != app_id]}
                if not e["apps"]:
                    continue
                if len(e["apps"]) == 1:
                    e = {"app": e["apps"][0]}
            new.append(e)
        self.favorites = new

    def move(self, src, dst):
        """src indeksindeki ogeyi dst konumuna (ekleme noktasi) tasi."""
        if src == dst or src + 1 == dst:
            return
        item = self.favorites.pop(src)
        if dst > src:
            dst -= 1
        self.favorites.insert(dst, item)

    def merge(self, src, dst, name_hint="Yeni klasör"):
        """src ogesini dst'nin ustune birak: klasor olustur ya da klasore ekle."""
        if src == dst:
            return
        a, b = self.favorites[src], self.favorites[dst]
        src_apps = [a["app"]] if "app" in a else list(a["apps"])
        if "folder" in b:
            b["apps"].extend(x for x in src_apps if x not in b["apps"])
        else:
            self.favorites[dst] = {"folder": name_hint, "apps": [b["app"]] + src_apps}
        del self.favorites[src]

    def insert_app_at(self, app_id, index, merge=False, name_hint="Yeni klasör"):
        """Disaridan (Tumu listesinden / klasorden) gelen uygulamayi yerlestir."""
        self.remove_app(app_id)
        index = min(index, len(self.favorites))
        if merge and index < len(self.favorites):
            target = self.favorites[index]
            if "folder" in target:
                target["apps"].append(app_id)
            else:
                self.favorites[index] = {"folder": name_hint, "apps": [target["app"], app_id]}
        else:
            self.favorites.insert(index, {"app": app_id})

    # ── klasor ──
    def rename_folder(self, index, name):
        if "folder" in self.favorites[index]:
            self.favorites[index]["folder"] = name.strip() or "Klasör"

    def folder_move(self, index, src, dst):
        apps = self.favorites[index]["apps"]
        if src == dst or src + 1 == dst:
            return
        item = apps.pop(src)
        if dst > src:
            dst -= 1
        apps.insert(dst, item)

    def take_out_of_folder(self, index, app_id):
        """Klasordeki uygulamayi klasorun hemen sonrasina ust seviyeye cikar."""
        folder = self.favorites[index]
        folder["apps"].remove(app_id)
        self.favorites.insert(index + 1, {"app": app_id})
        if len(folder["apps"]) == 1:
            self.favorites[index] = {"app": folder["apps"][0]}
        elif not folder["apps"]:
            del self.favorites[index]

    def dissolve_folder(self, index):
        apps = self.favorites[index]["apps"]
        self.favorites[index:index + 1] = [{"app": a} for a in apps]


class Usage:
    """Frecency: son acilislar ne kadar yeniyse o kadar agirlikli."""

    KEEP = 30

    def __init__(self):
        self.data = _read(USAGE_FILE, {})

    def record(self, app_id):
        stamps = self.data.setdefault(app_id, [])
        stamps.append(int(time.time()))
        del stamps[:-self.KEEP]
        _write(USAGE_FILE, self.data)

    def score(self, app_id):
        now = time.time()
        total = 0.0
        for t in self.data.get(app_id, []):
            age = now - t
            total += 4 if age < 3600 else 2 if age < 86400 else 1 if age < 7 * 86400 else 0.5
        return total
