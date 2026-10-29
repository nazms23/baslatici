# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Tema yukleyici (hesap-makinesi ile ayni): base.css + uygulamanin kendi css'i + canli accent.

Accent dosyasi (~/.config/accent/colors.css) varsa okunur (or. wallpaper'dan renk ureten bir script yazar);
dosya degisince yeniden yuklenir, wallpaper degisince acik uygulamalar da renk degistirir.
"""

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
ACCENT_CSS = os.path.expanduser("~/.config/accent/colors.css")

_providers = []
_monitor = None


def _add_provider(priority):
    provider = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, priority)
    _providers.append(provider)
    return provider


def _load_accent(provider):
    if os.path.exists(ACCENT_CSS):
        provider.load_from_path(ACCENT_CSS)


def apply(app_css=None):
    """Adw.Application 'startup' sinyalinden sonra cagrilmali."""
    global _monitor
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    base = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    _add_provider(base).load_from_path(os.path.join(HERE, "base.css"))
    if app_css:
        _add_provider(base + 1).load_from_path(os.path.join(HERE, app_css))

    accent = _add_provider(base + 2)
    _load_accent(accent)

    os.makedirs(os.path.dirname(ACCENT_CSS), exist_ok=True)
    _monitor = Gio.File.new_for_path(ACCENT_CSS).monitor_file(Gio.FileMonitorFlags.NONE, None)

    def on_changed(_mon, _file, _other, event):
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED):
            _load_accent(accent)

    _monitor.connect("changed", on_changed)
