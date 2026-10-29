# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Uygulama: tek ornek, arka planda bekler; her cagri pencereyi ac/kapa yapar.

baslatici            ac / kapa (calisan ornege iletilir)
baslatici --daemon   arka planda baslat (oturum acilisinda), pencere gizli
baslatici --quit     arka plan ornegini kapat
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio  # noqa: E402

from . import theme  # noqa: E402

APP_ID = "io.github.nazms23.Baslatici"


class BaslaticiApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        theme.apply("baslatici.css")
        from .ui import LauncherWindow
        self.window = LauncherWindow(self)
        self.hold()  # pencere gizliyken de calismaya devam et

    def do_activate(self):
        self.window.toggle()

    def do_command_line(self, cmdline):
        args = cmdline.get_arguments()[1:]
        if "--quit" in args:
            self.quit()
        elif "--daemon" in args:
            pass
        elif "--hide" in args:
            self.window.hide_launcher()
        else:
            self.window.toggle()
        return 0


def main():
    return BaslaticiApp().run(sys.argv)
