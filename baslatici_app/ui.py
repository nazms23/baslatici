# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nazms23
"""Baslatici penceresi: favoriler (surukle-birak, klasorler), kategoriler, arama, hesap, komut."""

import json
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Gio, GLib, GObject, Graphene, Gtk  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402
except (ValueError, ImportError):
    LayerShell = None

from . import apps as A  # noqa: E402
from . import calc  # noqa: E402
from . import search as S  # noqa: E402
from .store import Layout, Usage  # noqa: E402

COLS = 7
FAV_ICON = 52
GRID_ICON = 44


def _payload(text):
    return Gdk.ContentProvider.new_for_value(GObject.Value(GObject.TYPE_STRING, text))


def _focused_monitor_name():
    try:
        out = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=1).stdout
        return next((m["name"] for m in json.loads(out) if m.get("focused")), None)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class LauncherWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title="Başlatıcı", css_classes=["baslatici"])
        self.catalog = A.load_apps()
        self.layout = Layout(set(self.catalog))
        self.usage = Usage()
        self.category = None  # None = Tumu
        self.folder_index = None
        self.nav = []          # [(flowbox, [children])] klavye gezintisi icin
        self.sel = (0, 0)      # (bolum, indeks)
        self.mode = "home"     # home | results | folder
        self.calc_value = None

        self._setup_layer()
        self._build()
        self._install_actions()

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        Gio.AppInfoMonitor.get().connect("changed", lambda *_: self._reload_catalog())
        self.prebuilt = False
        GLib.idle_add(self._prebuild)

    # ───────────── Pencere / layer-shell ─────────────
    def _setup_layer(self):
        self.layered = bool(LayerShell and LayerShell.is_supported())
        if self.layered:
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_namespace(self, "baslatici")
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
                LayerShell.set_anchor(self, edge, True)
            LayerShell.set_exclusive_zone(self, -1)
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
        else:
            self.set_default_size(820, 640)
            self.set_decorated(False)

    def _place_on_focused_monitor(self):
        if not self.layered:
            return
        name = _focused_monitor_name()
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            m = monitors.get_item(i)
            if m.get_connector() == name:
                LayerShell.set_monitor(self, m)
                return

    def toggle(self):
        if self.get_visible():
            self.hide_launcher()
        else:
            self.show_launcher()

    def show_launcher(self):
        self._place_on_focused_monitor()
        self.entry.set_text("")
        self._show_home(rebuild=not self.prebuilt)
        self.present()
        self.entry.grab_focus()

    def hide_launcher(self):
        self.set_visible(False)
        # Bir sonraki acilis aninda olsun: izgaralari simdi (gizliyken) hazirla
        self.prebuilt = False
        GLib.idle_add(self._prebuild)

    def _prebuild(self):
        if not self.get_visible():
            self.category = None
            self.tab_buttons[0][1].set_active(True)
            self._refresh_favorites()
            self._refresh_all()
            self.prebuilt = True
        return False

    # ───────────── Yapi ─────────────
    def _build(self):
        root = Gtk.Box(css_classes=["baslatici-dim"] if self.layered else [], hexpand=True, vexpand=True)
        click = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_root_click)
        root.add_controller(click)
        self.root = root

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["bas-panel"],
                             halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=True, vexpand=True,
                             width_request=800, height_request=620)
        root.append(self.panel)

        self.entry = Gtk.SearchEntry(placeholder_text="Ara…   = hesap   > komut", css_classes=["search"],
                                     hexpand=True)
        self.entry.connect("search-changed", self._on_search)
        self.entry.connect("activate", lambda *_: self._activate_selected())
        self.panel.append(self.entry)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120,
                               vexpand=True)
        self.stack.add_named(self._build_home(), "home")
        self.stack.add_named(self._build_results(), "results")
        self.stack.add_named(self._build_folder(), "folder")
        self.panel.append(self.stack)

        self.footer = Gtk.Label(css_classes=["footer"], xalign=0)
        self.panel.append(self.footer)
        self.set_child(root)
        self._built = True

    def _build_home(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label="Favoriler", css_classes=["section-title"], xalign=0))
        head.append(Gtk.Label(label="sürükle: sırala · başka bir uygulamanın üstüne bırak: klasör",
                              css_classes=["hint"], xalign=1, hexpand=True))
        box.append(head)

        self.fav_box = self._flowbox(self._on_fav_activated)
        self.fav_box.add_css_class("fav-grid")
        self._add_drop(self.fav_box, self._drop_on_fav_area)
        self.fav_empty = Gtk.Label(label="Bir uygulamayı buraya sürükle ya da sağ tık → Favorilere ekle",
                                   css_classes=["hint", "fav-empty"], visible=False)
        box.append(self.fav_box)
        box.append(self.fav_empty)

        self.tabs = Gtk.Box(spacing=4, css_classes=["tabs"], margin_top=4)
        box.append(self.tabs)

        self.all_box = self._flowbox(self._on_app_activated)
        self.all_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                             css_classes=["all-scroll"])
        self.all_scroll.set_child(self.all_box)
        self._add_drop(self.all_scroll, self._drop_on_all_area, motion=self._motion_all_area)
        box.append(self.all_scroll)
        self._build_tabs()  # ilk sekme secilince all_box doldurulur; o yuzden sonra
        return box

    def _build_results(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["card"], visible=False)
        self.card_title = Gtk.Label(xalign=0, css_classes=["card-title"], selectable=False, wrap=True)
        self.card_sub = Gtk.Label(xalign=0, css_classes=["card-sub"])
        self.card.append(self.card_title)
        self.card.append(self.card_sub)
        box.append(self.card)
        self.res_box = self._flowbox(self._on_app_activated)
        self.res_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.res_scroll.set_child(self.res_box)
        box.append(self.res_scroll)
        self.res_empty = Gtk.Label(label="Eşleşen uygulama yok", css_classes=["hint"], visible=False,
                                   margin_top=24)
        box.append(self.res_empty)
        return box

    def _build_folder(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        head = Gtk.Box(spacing=10)
        back = Gtk.Button(css_classes=["back-btn"], tooltip_text="Favorilere dön (Esc) · uygulamayı buraya "
                                                                 "bırakırsan klasörden çıkar")
        back_box = Gtk.Box(spacing=6)
        back_box.append(Gtk.Image(icon_name="go-previous-symbolic"))
        back_box.append(Gtk.Label(label="Favoriler"))
        back.set_child(back_box)
        back.connect("clicked", lambda *_: self._show_home())
        self._add_drop(back, self._drop_on_back)
        head.append(back)
        self.folder_name = Gtk.EditableLabel(css_classes=["folder-name"], hexpand=True,
                                             tooltip_text="Adı değiştirmek için tıkla")
        self.folder_name.connect("notify::editing", self._on_folder_rename)
        head.append(self.folder_name)
        head.append(Gtk.Label(label="sürükle: sırala · Geri'ye bırak: klasörden çıkar", css_classes=["hint"]))
        box.append(head)
        self.folder_box = self._flowbox(self._on_app_activated)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.folder_box)
        box.append(scroll)
        return box

    def _flowbox(self, on_activate):
        fb = Gtk.FlowBox(max_children_per_line=COLS, min_children_per_line=COLS, homogeneous=True,
                         selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=True,
                         row_spacing=4, column_spacing=4, valign=Gtk.Align.START)
        fb.connect("child-activated", lambda _fb, child: on_activate(child))
        return fb

    def _build_tabs(self):
        child = self.tabs.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.tabs.remove(child)
            child = nxt
        self.tab_buttons = []
        first = None
        for name, icon in [("Tümü", "view-app-grid-symbolic")] + A.categories_present(self.catalog):
            btn = Gtk.ToggleButton(css_classes=["tab"], focusable=False)
            inner = Gtk.Box(spacing=6)
            inner.append(Gtk.Image(icon_name=icon))
            inner.append(Gtk.Label(label=name))
            btn.set_child(inner)
            if first:
                btn.set_group(first)
            else:
                first = btn
            cat = None if name == "Tümü" else name
            btn.connect("toggled", lambda b, c=cat: b.get_active() and self._set_category(c))
            self.tabs.append(btn)
            self.tab_buttons.append((cat, btn))
        first.set_active(True)

    # ───────────── Ogeler ─────────────
    def _tile(self, label, icon_widget, extra_classes=()):
        child = Gtk.FlowBoxChild(css_classes=["tile", *extra_classes], focusable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
        box.append(icon_widget)
        box.append(Gtk.Label(label=label, ellipsize=3, max_width_chars=11, css_classes=["tile-label"],
                             justify=Gtk.Justification.CENTER, wrap=True, wrap_mode=2, lines=2))
        child.set_child(box)
        child.icon_widget = icon_widget
        return child

    def _app_tile(self, app, size, payload=None):
        img = Gtk.Image(gicon=app.icon, pixel_size=size)
        child = self._tile(app.name, img)
        child.kind, child.app_id = "app", app.id
        child.set_tooltip_text(f"{app.name}\n{app.description}" if app.description else app.name)
        self._add_menu(child)
        if payload:
            self._add_drag(child, payload)
        return child

    def _folder_tile(self, index, entry):
        grid = Gtk.Grid(row_spacing=3, column_spacing=3, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                        css_classes=["folder-icon"], width_request=FAV_ICON + 8, height_request=FAV_ICON + 8)
        for n, app_id in enumerate(entry["apps"][:4]):
            grid.attach(Gtk.Image(gicon=self.catalog[app_id].icon, pixel_size=22), n % 2, n // 2, 1, 1)
        child = self._tile(entry["folder"], grid, ("folder",))
        child.kind, child.fav_index = "folder", index
        child.set_tooltip_text(f"{entry['folder']} ({len(entry['apps'])} uygulama)")
        self._add_menu(child)
        return child

    # ───────────── Doldurma ─────────────
    def _refresh_favorites(self):
        self.fav_box.remove_all()
        visible = self.layout.visible(self.catalog)
        for index, entry in visible:
            if "app" in entry:
                child = self._app_tile(self.catalog[entry["app"]], FAV_ICON, payload=f"fav:{index}")
            else:
                child = self._folder_tile(index, entry)
                self._add_drag(child, f"fav:{index}")
            child.fav_index = index
            self._add_drop(child, self._drop_on_fav_tile, motion=self._motion_fav_tile)
            self.fav_box.append(child)
        self.fav_empty.set_visible(not visible)

    def _sorted(self, apps):
        return sorted(apps, key=lambda a: (-self.usage.score(a.id), S.norm(a.name)))

    def _refresh_all(self):
        self.all_box.remove_all()
        apps = [a for a in self.catalog.values() if self.category is None or a.category == self.category]
        for app in self._sorted(apps):
            self.all_box.append(self._app_tile(app, GRID_ICON, payload=f"app:{app.id}"))

    def _refresh_folder(self):
        self.folder_box.remove_all()
        entry = self.layout.favorites[self.folder_index]
        self.folder_name.set_text(entry["folder"])
        for n, app_id in enumerate(a for a in entry["apps"] if a in self.catalog):
            child = self._app_tile(self.catalog[app_id], FAV_ICON, payload=f"fld:{self.folder_index}:{app_id}")
            child.folder_pos = n
            self._add_drop(child, self._drop_on_folder_tile, motion=self._motion_folder_tile)
            self.folder_box.append(child)

    def _reload_catalog(self):
        self.catalog = A.load_apps()
        self._build_tabs()
        if self.get_visible() and self.mode == "home":
            self._show_home()

    # ───────────── Gorunumler ─────────────
    def _show_home(self, rebuild=True):
        self.mode = "home"
        self.folder_index = None
        if rebuild:
            self._refresh_favorites()
            self._refresh_all()
        self.stack.set_visible_child_name("home")
        self._set_nav([self.fav_box, self.all_box])
        self._footer("Enter: aç · Shift+Enter: NVIDIA ile aç · Ctrl+1…9: favori · Tab: kategori · Esc: kapat")

    def _show_folder(self, index):
        self.mode = "folder"
        self.folder_index = index
        self._refresh_folder()
        self.stack.set_visible_child_name("folder")
        self._set_nav([self.folder_box])
        self._footer("Enter: aç · Esc: favorilere dön · adı değiştirmek için ada tıkla")

    def _set_category(self, cat):
        self.category = cat
        if getattr(self, "_built", False) and self.mode == "home":
            self._refresh_all()
            self._set_nav([self.fav_box, self.all_box], keep_section=True)

    def _footer(self, text):
        self.footer.set_label(text)

    # ───────────── Arama / hesap / komut ─────────────
    def _on_search(self, entry):
        text = entry.get_text()
        if not text.strip():
            if self.mode == "results":
                self._show_home()
            return
        self.mode = "results"
        self.stack.set_visible_child_name("results")
        self.res_box.remove_all()
        self.calc_value = None
        self.command = None

        if text.startswith(">"):
            cmd = text[1:].strip()
            self.command = cmd or None
            self._card(f"  {cmd or 'komut yaz…'}", "Enter: arka planda çalıştır · Ctrl+Enter: terminalde")
            self.res_empty.set_visible(False)
            self._set_nav([])
            self._footer("> komut modu")
            return

        expr = text[1:] if text.startswith("=") else text
        if text.startswith("=") or S.looks_like_math(text):
            self._try_calc(expr)
        else:
            self.card.set_visible(False)

        if text.startswith("="):
            self.res_empty.set_visible(False)
            self._set_nav([])
            self._footer("Enter: sonucu kopyala")
            return

        scored = []
        for app in self.catalog.values():
            s = S.score(text, app.name, app.search_text)
            if s > 0:
                scored.append((s + (15 * self.usage.score(app.id) if s >= 250 else 0), app))
        # Guclu eslesme (ad/kelime/alt dize) varsa harf-sirasi (bulanik) gurultusunu gizle
        if any(sc >= 250 for sc, _a in scored):
            scored = [(sc, a) for sc, a in scored if sc >= 250]
        scored.sort(key=lambda x: (-x[0], S.norm(x[1].name)))
        for _s, app in scored[:28]:
            self.res_box.append(self._app_tile(app, GRID_ICON))
        self.res_empty.set_visible(not scored and not self.card.get_visible())
        self._set_nav([self.res_box])
        if self.calc_value is not None and scored:
            self._footer("Enter: uygulamayı aç · Ctrl+C: hesap sonucunu kopyala")
        elif self.calc_value is not None:
            self._footer("Enter: sonucu kopyala")
        else:
            self._footer("Enter: aç · Shift+Enter: NVIDIA ile aç · Esc: aramayı temizle")

    def _try_calc(self, expr):
        try:
            value = calc.fmt(calc.evaluate(expr.replace("*", "×").replace("/", "÷").replace("-", "−")))
        except calc.CalcError as e:
            if expr.strip():
                self._card(f"= …", str(e))
            return
        self.calc_value = value
        self._card(f"= {value}", "Enter / Ctrl+C: panoya kopyala")

    def _card(self, title, sub):
        self.card_title.set_label(title)
        self.card_sub.set_label(sub)
        self.card.set_visible(True)

    def _copy(self, text):
        Gdk.Display.get_default().get_clipboard().set(text)
        self.card_sub.set_label("Kopyalandı ✓")
        GLib.timeout_add(350, lambda: (self.hide_launcher(), False)[1])

    # ───────────── Klavye gezintisi ─────────────
    def _set_nav(self, boxes, keep_section=False):
        self.nav = []
        for fb in boxes:
            kids = []
            c = fb.get_first_child()
            while c:
                kids.append(c)
                c = c.get_next_sibling()
            if kids:
                self.nav.append((fb, kids))
        for fb in (self.fav_box, self.all_box, self.res_box, self.folder_box):
            fb.unselect_all()
        if keep_section and self.sel[0] < len(self.nav):
            self._select(self.sel[0], 0)
        else:
            self._select(0, 0)

    def _select(self, s, i):
        if not self.nav:
            self.sel = (0, 0)
            return
        s = max(0, min(s, len(self.nav) - 1))
        fb, kids = self.nav[s]
        i = max(0, min(i, len(kids) - 1))
        for other, _ in self.nav:
            if other is not fb:
                other.unselect_all()
        fb.select_child(kids[i])
        self.sel = (s, i)
        vp = fb.get_parent()
        if isinstance(vp, Gtk.Viewport):
            vp.scroll_to(kids[i], None)

    def _move(self, dx, dy):
        if not self.nav:
            return
        s, i = self.sel
        kids = self.nav[s][1]
        if dx:
            i += dx
            if i >= len(kids) and s + 1 < len(self.nav):
                s, i = s + 1, 0
            elif i < 0 and s > 0:
                s, i = s - 1, len(self.nav[s - 1][1]) - 1
        elif dy > 0:
            if i + COLS < len(kids):
                i += COLS
            elif (i // COLS) < (len(kids) - 1) // COLS:
                i = len(kids) - 1
            elif s + 1 < len(self.nav):
                s, i = s + 1, i % COLS
        elif dy < 0:
            if i - COLS >= 0:
                i -= COLS
            elif s > 0:
                prev = self.nav[s - 1][1]
                last_row = (len(prev) - 1) // COLS
                s, i = s - 1, min(last_row * COLS + i % COLS, len(prev) - 1)
        self._select(s, i)

    def _selected_child(self):
        if not self.nav:
            return None
        s, i = self.sel
        kids = self.nav[s][1]
        return kids[i] if i < len(kids) else None

    def _activate_selected(self, nvidia=False, terminal=False):
        if self.mode == "results" and self.command is not None:
            A.run_command(self.command, in_terminal=terminal)
            self.hide_launcher()
            return
        child = self._selected_child()
        if child is None:
            if self.calc_value is not None:
                self._copy(self.calc_value)
            return
        if child.kind == "folder":
            self._show_folder(child.fav_index)
        else:
            self._launch(child.app_id, nvidia)

    def _on_key(self, _ctl, keyval, _code, state):
        name = Gdk.keyval_name(keyval) or ""
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if self.folder_name.get_editing():
            return False
        if name == "Escape":
            if self.entry.get_text():
                self.entry.set_text("")
            elif self.mode == "folder":
                self._show_home()
            else:
                self.hide_launcher()
            return True
        if name in ("Return", "KP_Enter"):
            self._activate_selected(nvidia=shift, terminal=ctrl)
            return True
        if name in ("Left", "Right", "Up", "Down"):
            self._move({"Left": -1, "Right": 1}.get(name, 0), {"Up": -1, "Down": 1}.get(name, 0))
            return True
        if name in ("Tab", "ISO_Left_Tab") and self.mode == "home":
            self._cycle_tab(-1 if (shift or name == "ISO_Left_Tab") else 1)
            return True
        if ctrl and name in ("c", "C") and self.calc_value is not None:
            self._copy(self.calc_value)
            return True
        if ctrl and name.isdigit() and name != "0" and self.mode == "home":
            kids = self.nav[0][1] if self.nav and self.nav[0][0] is self.fav_box else []
            n = int(name) - 1
            if n < len(kids):
                self.sel = (0, n)
                self._activate_selected()
            return True
        if name == "BackSpace" and not self.entry.get_text() and self.mode == "folder":
            self._show_home()
            return True
        return False

    def _cycle_tab(self, step):
        idx = next((n for n, (c, _b) in enumerate(self.tab_buttons) if c == self.category), 0)
        self.tab_buttons[(idx + step) % len(self.tab_buttons)][1].set_active(True)

    # ───────────── Etkinlestirme ─────────────
    def _on_fav_activated(self, child):
        self.sel = (0, child.get_index())
        if child.kind == "folder":
            self._show_folder(child.fav_index)
        else:
            self._launch(child.app_id)

    def _on_app_activated(self, child):
        self._launch(child.app_id)

    def _launch(self, app_id, nvidia=False):
        app = self.catalog.get(app_id)
        if not app:
            return
        A.launch(app, nvidia=nvidia)
        self.usage.record(app_id)
        self.hide_launcher()

    def _on_root_click(self, gesture, _n, x, y):
        ok, rect = self.panel.compute_bounds(self.root)
        if ok and not rect.contains_point(Graphene.Point().init(x, y)):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.hide_launcher()

    # ───────────── Sag tik menusu ─────────────
    def _install_actions(self):
        def add(name, cb, vtype="s"):
            act = Gio.SimpleAction.new(name, GLib.VariantType.new(vtype))
            act.connect("activate", lambda _a, v: cb(v.unpack()))
            self.add_action(act)
        add("launch", lambda a: self._launch(a))
        add("launch-nvidia", lambda a: self._launch(a, nvidia=True))
        add("fav-add", self._menu_fav_add)
        add("fav-remove", self._menu_fav_remove)
        add("folder-out", self._menu_folder_out)
        add("folder-open", lambda i: self._show_folder(i), "i")
        add("folder-dissolve", self._menu_folder_dissolve, "i")

    def _add_menu(self, child):
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", lambda g, _n, x, y: self._popup_menu(child, x, y))
        child.add_controller(click)

    def _popup_menu(self, child, x, y):
        menu = Gio.Menu()

        def item(label, action, target):
            it = Gio.MenuItem.new(label, None)
            it.set_action_and_target_value(action, target)
            menu.append_item(it)

        if child.kind == "folder":
            i = GLib.Variant.new_int32(child.fav_index)
            item("Klasörü aç", "win.folder-open", i)
            item("Klasörü dağıt", "win.folder-dissolve", i)
        else:
            a = GLib.Variant.new_string(child.app_id)
            item("Aç", "win.launch", a)
            item("NVIDIA ile aç", "win.launch-nvidia", a)
            if self.mode == "folder":
                item("Klasörden çıkar", "win.folder-out", a)
            if self.layout.is_favorite(child.app_id):
                item("Favorilerden çıkar", "win.fav-remove", a)
            else:
                item("Favorilere ekle", "win.fav-add", a)
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(child)
        pop.set_has_arrow(False)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _after_change(self):
        self.layout.save()
        GLib.idle_add(self._rerender)

    def _rerender(self):
        if self.mode == "folder" and self.folder_index is not None:
            entry = (self.layout.favorites[self.folder_index]
                     if self.folder_index < len(self.layout.favorites) else {})
            if "folder" in entry:
                self._show_folder(self.folder_index)
            else:
                self._show_home()
        elif self.mode == "home":
            sel = self.sel
            self._show_home()
            self._select(*sel)
        else:
            self._on_search(self.entry)
        return False

    def _menu_fav_add(self, app_id):
        self.layout.add(app_id)
        self._after_change()

    def _menu_fav_remove(self, app_id):
        self.layout.remove_app(app_id)
        self._after_change()

    def _menu_folder_out(self, app_id):
        self.layout.take_out_of_folder(self.folder_index, app_id)
        self._after_change()

    def _menu_folder_dissolve(self, index):
        self.layout.dissolve_folder(index)
        self._after_change()

    def _on_folder_rename(self, label, _pspec):
        if not label.get_editing() and self.folder_index is not None:
            self.layout.rename_folder(self.folder_index, label.get_text())
            self.layout.save()

    # ───────────── Surukle-birak ─────────────
    def _add_drag(self, child, payload):
        src = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        src.connect("prepare", lambda *_: _payload(payload))
        src.connect("drag-begin", lambda s, _d: self._drag_begin(s, child, payload))
        src.connect("drag-end", lambda *_: self.all_scroll.remove_css_class("drop-remove"))
        child.add_controller(src)

    def _drag_begin(self, source, child, payload):
        source.set_icon(Gtk.WidgetPaintable.new(child.icon_widget), FAV_ICON // 2, FAV_ICON // 2)
        self.dragging = payload

    def _add_drop(self, widget, on_drop, motion=None):
        tgt = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        if motion:
            tgt.connect("motion", lambda t, x, y: motion(widget, x, y))
            tgt.connect("enter", lambda t, x, y: motion(widget, x, y))
        tgt.connect("leave", lambda *_: self._clear_drop_marks(widget))
        tgt.connect("drop", lambda t, value, x, y: self._handle_drop(widget, on_drop, value, x, y))
        widget.add_controller(tgt)

    def _handle_drop(self, widget, on_drop, value, x, y):
        self._clear_drop_marks(widget)
        handled = on_drop(widget, value, x, y)
        if handled:
            self._after_change()
        return bool(handled)

    @staticmethod
    def _clear_drop_marks(widget):
        for c in ("drop-before", "drop-after", "drop-merge", "drop-remove"):
            widget.remove_css_class(c)

    @staticmethod
    def _zone(widget, x, allow_merge=True):
        w = max(1, widget.get_width())
        if allow_merge:
            return "before" if x < w * 0.28 else "after" if x > w * 0.72 else "merge"
        return "before" if x < w / 2 else "after"

    def _mark(self, widget, zone):
        self._clear_drop_marks(widget)
        widget.add_css_class(f"drop-{zone}")
        return Gdk.DragAction.MOVE

    def _motion_fav_tile(self, child, x, _y):
        drag = getattr(self, "dragging", "")
        allow_merge = not (drag.startswith("fav:") and int(drag[4:]) == child.fav_index)
        if child.kind == "folder" and drag.startswith("fav:"):
            src = self.layout.favorites[int(drag[4:])]
            allow_merge = allow_merge and "app" in src
        return self._mark(child, self._zone(child, x, allow_merge))

    def _name_hint(self, *app_ids):
        cats = {self.catalog[a].category for a in app_ids if a in self.catalog}
        return cats.pop() if len(cats) == 1 and "Diğer" not in cats else "Yeni klasör"

    def _drop_on_fav_tile(self, child, value, x, _y):
        idx = child.fav_index
        target = self.layout.favorites[idx]
        if value.startswith("fav:"):
            src = int(value[4:])
            source = self.layout.favorites[src]
            zone = self._zone(child, x, src != idx and not ("folder" in target and "folder" in source))
            if zone == "merge":
                ids = ([source["app"]] if "app" in source else []) + ([target["app"]] if "app" in target else [])
                self.layout.merge(src, idx, self._name_hint(*ids))
            else:
                self.layout.move(src, idx if zone == "before" else idx + 1)
            return True
        if value.startswith("app:"):
            app_id = value[4:]
            zone = self._zone(child, x)
            hint = self._name_hint(app_id, target["app"]) if "app" in target else ""
            self.layout.insert_app_at(app_id, idx if zone == "before" else idx + 1 if zone == "after" else idx,
                                      merge=(zone == "merge"), name_hint=hint or "Yeni klasör")
            return True
        return False

    def _drop_on_fav_area(self, _widget, value, _x, _y):
        if value.startswith("fav:"):
            self.layout.move(int(value[4:]), len(self.layout.favorites))
            return True
        if value.startswith("app:"):
            self.layout.add(value[4:])
            return True
        return False

    def _motion_all_area(self, widget, _x, _y):
        drag = getattr(self, "dragging", "")
        if drag.startswith("fav:") and "app" in self.layout.favorites[int(drag[4:])]:
            widget.add_css_class("drop-remove")
            return Gdk.DragAction.MOVE
        return 0

    def _drop_on_all_area(self, _widget, value, _x, _y):
        if value.startswith("fav:"):
            idx = int(value[4:])
            if "app" in self.layout.favorites[idx]:
                self.layout.remove_index(idx)
                return True
        return False

    def _motion_folder_tile(self, child, x, _y):
        return self._mark(child, self._zone(child, x, allow_merge=False))

    def _drop_on_folder_tile(self, child, value, x, _y):
        if not value.startswith("fld:"):
            return False
        _p, _fi, app_id = value.split(":", 2)
        apps = self.layout.favorites[self.folder_index]["apps"]
        if app_id not in apps:
            return False
        src = apps.index(app_id)
        dst = child.folder_pos if self._zone(child, x, False) == "before" else child.folder_pos + 1
        self.layout.folder_move(self.folder_index, src, dst)
        return True

    def _drop_on_back(self, _widget, value, _x, _y):
        if value.startswith("fld:"):
            _p, _fi, app_id = value.split(":", 2)
            self.layout.take_out_of_folder(self.folder_index, app_id)
            return True
        return False
