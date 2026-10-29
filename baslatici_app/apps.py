# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Kurulu uygulamalar: .desktop dosyalarini okur, kategorilere ayirir, calistirir."""

import os
import re
import shlex
from dataclasses import dataclass, field

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib  # noqa: E402

# (ad, ikon, eslesen .desktop kategorileri) - siralama onemli: ilk eslesen kazanir
CATEGORIES = [
    ("Oyunlar", "applications-games-symbolic", {"Game"}),
    ("İnternet", "network-workgroup-symbolic", {"Network", "WebBrowser", "Chat", "InstantMessaging", "Email"}),
    ("Medya", "applications-multimedia-symbolic", {"AudioVideo", "Audio", "Video", "Player", "Music"}),
    ("Grafik", "applications-graphics-symbolic", {"Graphics", "Photography", "Viewer"}),
    ("Geliştirme", "applications-engineering-symbolic", {"Development", "IDE", "TextEditor"}),
    ("Ofis", "x-office-document-symbolic", {"Office"}),
    ("Sistem", "applications-system-symbolic",
     {"System", "Settings", "Monitor", "TerminalEmulator", "FileManager", "HardwareSettings"}),
    ("Araçlar", "applications-utilities-symbolic", {"Utility", "Accessories", "Calculator"}),
]

# Baslaticinin kendi ortami (layer-shell LD_PRELOAD'u) acilan uygulamalara sizmasin
_STRIP_ENV = ("LD_PRELOAD",)

NVIDIA_ENV = {
    "__NV_PRIME_RENDER_OFFLOAD": "1",
    "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
    "__VK_LAYER_NV_optimus": "NVIDIA_only",
}

TERMINAL = os.environ.get("BASLATICI_TERMINAL", "kitty")


@dataclass
class App:
    id: str
    name: str
    info: Gio.DesktopAppInfo
    category: str
    search_text: str = ""
    keywords: list = field(default_factory=list)

    @property
    def icon(self):
        return self.info.get_icon() or Gio.ThemedIcon.new("application-x-executable")

    @property
    def description(self):
        return self.info.get_generic_name() or self.info.get_description() or ""


def _category_of(info):
    cats = set(filter(None, (info.get_categories() or "").split(";")))
    for name, _icon, keys in CATEGORIES:
        if cats & keys:
            return name
    return "Diğer"


def load_apps():
    apps = {}
    for info in Gio.AppInfo.get_all():
        if not isinstance(info, Gio.DesktopAppInfo) or not info.should_show():
            continue
        app_id = info.get_id()
        if not app_id or app_id in apps:
            continue
        keywords = list(info.get_keywords() or [])
        exe = os.path.basename((info.get_executable() or "").split()[0]) if info.get_executable() else ""
        search = " ".join(filter(None, [info.get_display_name(), info.get_generic_name(), exe] + keywords))
        apps[app_id] = App(id=app_id, name=info.get_display_name() or app_id, info=info,
                           category=_category_of(info), search_text=search, keywords=keywords)
    return apps


def categories_present(apps):
    present = {a.category for a in apps.values()}
    out = [(n, i) for n, i, _ in CATEGORIES if n in present]
    if "Diğer" in present:
        out.append(("Diğer", "view-more-symbolic"))
    return out


def _clean_exec(info):
    """Exec satirindan %f %U gibi alan kodlarini temizle."""
    cmd = info.get_commandline() or ""
    cmd = re.sub(r"%[fFuUdDnNickvm]", "", cmd)
    return cmd.replace("%%", "%").strip()


def launch(app, nvidia=False):
    env = dict(NVIDIA_ENV) if nvidia else {}
    if app.info.get_boolean("Terminal"):
        _spawn([TERMINAL, "-e", "sh", "-c", _clean_exec(app.info)], env)
        return
    display = Gdk.Display.get_default()
    ctx = display.get_app_launch_context() if display else Gio.AppLaunchContext()
    for k in _STRIP_ENV:
        ctx.unsetenv(k)
    for k, v in env.items():
        ctx.setenv(k, v)
    try:
        app.info.launch([], ctx)
    except GLib.Error:
        _spawn(["sh", "-c", _clean_exec(app.info)], env)


def run_command(cmd, in_terminal=False):
    """'>' modu: komutu arka planda (veya terminalde, bitince acik kalir) calistir."""
    if in_terminal:
        _spawn([TERMINAL, "--hold", "sh", "-c", cmd], {})
    else:
        _spawn(["sh", "-c", cmd], {})


def _spawn(argv, env):
    launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
    for k in _STRIP_ENV:
        launcher.unsetenv(k)
    for k, v in env.items():
        launcher.setenv(k, v, True)
    launcher.set_cwd(os.path.expanduser("~"))
    try:
        launcher.spawnv(argv)
    except GLib.Error as e:
        print(f"baslatici: calistirilamadi {shlex.join(argv)}: {e.message}")
