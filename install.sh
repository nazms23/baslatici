#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
# Baslatici kurulum
#   ./install.sh              kur (~/.local/bin/baslatici)
#   ./install.sh --uninstall  kaldir (favori duzeni ~/.config/baslatici korunur)
#
# Kurulum repo klasorune symlink verir: repoyu silme/tasima, guncellemek icin `git pull` yeterli.

set -e

APP="baslatici"
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BIN="$HOME/.local/bin"

if [ "$1" = "--uninstall" ]; then
    "$BIN/$APP" --quit 2>/dev/null || true
    rm -f "$BIN/$APP"
    echo "Başlatıcı kaldırıldı. (Favori düzeni korunuyor: ~/.config/baslatici/duzen.json)"
    exit 0
fi

missing=0
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw' 2>/dev/null || missing=1
python3 -c 'import gi; gi.require_version("Gtk4LayerShell", "1.0"); from gi.repository import Gtk4LayerShell' 2>/dev/null || missing=1
if [ "$missing" = 1 ]; then
    echo "Eksik bağımlılık: GTK4, libadwaita, gtk4-layer-shell ve Python bağları."
    echo "  Arch:          sudo pacman -S --needed python-gobject gtk4 libadwaita gtk4-layer-shell"
    echo "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtk4layershell-1.0"
    echo "  Fedora:        sudo dnf install python3-gobject gtk4 libadwaita gtk4-layer-shell"
    exit 1
fi

mkdir -p "$BIN"
ln -sf "$DIR/$APP" "$BIN/$APP"

echo "Başlatıcı kuruldu: $BIN/$APP"
echo
echo "Hyprland (Lua) için:"
echo "  hl.on(\"hyprland.start\", function() hl.exec_cmd(\"$BIN/$APP --daemon\") end)"
echo "  hl.bind(\"SUPER + R\", hl.dsp.exec_cmd(\"$BIN/$APP\"))"
echo "  hl.layer_rule({ match = { namespace = \"^baslatici\$\" }, blur = true, ignore_alpha = 0.5 })"
