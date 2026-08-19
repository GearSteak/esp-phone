"""Shadowdark companion — one list per section, pad-first. Personal use of core tables."""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from esp_handset import store
from esp_handset.pages import page_chrome
from esp_handset.shadowdark_data import (
    ADVENTURE_1,
    ADVENTURE_2,
    ADVENTURE_3,
    ALIGN,
    ANCESTRY,
    ARMOR,
    CAVE_ENC,
    GEAR,
    KLASS,
    LOOT_0_3,
    NAMES,
    NPC_DOES,
    NPC_JOB,
    NPC_LOOK,
    NPC_SECRET,
    RULES,
    SITE,
    STATS,
    WEAPONS,
    XP_NEXT,
    book_candidates,
    load_spells,
)

_CHARS = "shadowdark_chars.json"
_TORCH = "shadowdark_torch.json"
_SET = "shadowdark_settings.json"
_HOUR = 3600.0
_MAX = 5

_BW = "background:#000; color:#fff;"
_LIST = (
    "QListWidget { background:#000; color:#fff; border:none; font-size:13px; outline:none; }"
    "QListWidget::item { padding:6px 4px; }"
    "QListWidget::item:selected { background:#fff; color:#000; }"
)
_READ = "QTextEdit { background:#000; color:#fff; border:none; font-size:12px; }"
_TABS = ("CHARS", "REF", "TOOLS", "SET")

_DICE = (
    ("d4", 4, None),
    ("d6", 6, None),
    ("d8", 8, None),
    ("d10", 10, None),
    ("d12", 12, None),
    ("d20", 20, None),
    ("d100", 100, None),
    ("Adv", 20, "adv"),
    ("Dis", 20, "dis"),
)


def _torch_state() -> dict:
    data = store.load(_TORCH, {}) or {}
    if not isinstance(data, dict):
        return {"end": 0.0, "warned": True}
    return {"end": float(data.get("end") or 0), "warned": bool(data.get("warned", True))}


def _save_torch(end: float, warned: bool) -> None:
    store.save(_TORCH, {"end": float(end), "warned": bool(warned)})


def check_torch_tick() -> Optional[str]:
    st = _torch_state()
    end = st["end"]
    if end <= 0 or st["warned"]:
        return None
    if time.time() < end:
        return None
    _save_torch(0.0, True)
    return "Your torch burns out"


def _chars() -> List[dict]:
    rows = store.load(_CHARS, [])
    return list(rows) if isinstance(rows, list) else []


def _save_chars(rows: List[dict]) -> None:
    store.save(_CHARS, rows[:_MAX])


def _blank() -> dict:
    return {
        "name": "Unnamed",
        "ancestry": "Human",
        "klass": "Fighter",
        "level": 1,
        "xp": 0,
        "align": "Neutral",
        "STR": 10,
        "DEX": 10,
        "CON": 10,
        "INT": 10,
        "WIS": 10,
        "CHA": 10,
        "hp": 8,
        "hp_max": 8,
        "ac": 11,
        "gear": ["Torch", "Rations"],
        "spells": [],
        "notes": "",
    }


def _mod(score: int) -> int:
    return (int(score) - 10) // 2


def _add(lst: QListWidget, label: str, kind: str, payload=None) -> None:
    it = QListWidgetItem(label)
    it.setData(Qt.UserRole, (kind, payload))
    lst.addItem(it)


def make_shadowdark_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet(_BW)
    outer = QVBoxLayout(body)
    outer.setContentsMargins(2, 2, 2, 2)
    outer.setSpacing(2)

    tabs_lab = QLabel("")
    tabs_lab.setStyleSheet("font-size:11px; font-weight:700;")
    banner = QLabel("")
    banner.setStyleSheet("font-size:11px; color:#ccc;")
    banner.setWordWrap(True)
    outer.addWidget(tabs_lab)
    outer.addWidget(banner)

    stack = QStackedWidget()
    outer.addWidget(stack, 1)

    menu = QListWidget()
    menu.setStyleSheet(_LIST)
    menu.setFocusPolicy(Qt.StrongFocus)
    menu.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    sheet_page = QWidget()
    shl = QVBoxLayout(sheet_page)
    shl.setContentsMargins(0, 0, 0, 0)
    shl.setSpacing(2)
    sheet_meta = QLabel("")
    sheet_meta.setWordWrap(True)
    sheet_meta.setStyleSheet("font-size:11px; color:#ddd;")
    sheet_list = QListWidget()
    sheet_list.setStyleSheet(_LIST)
    sheet_list.setFocusPolicy(Qt.StrongFocus)
    sheet_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    shl.addWidget(sheet_meta)
    shl.addWidget(sheet_list, 1)

    read = QTextEdit()
    read.setReadOnly(True)
    read.setStyleSheet(_READ)
    read.setFocusPolicy(Qt.StrongFocus)

    stack.addWidget(menu)
    stack.addWidget(sheet_page)
    stack.addWidget(read)

    state = {
        "tab": 0,
        "idx": 0,
        "round": 1,
        "dice": "",
        "spells": load_spells(),
        "view": "menu",  # menu | sheet | read
        "ref": "root",  # root | rules | spells | armor | weapons | gear
        "after_read": "menu",
    }

    def paint_tabs() -> None:
        bits = []
        for i, name in enumerate(_TABS):
            bits.append(f"[{name}]" if i == state["tab"] else name)
        tabs_lab.setText("  ".join(bits))

    def torch_line() -> str:
        st = _torch_state()
        left = int(st["end"] - time.time()) if st["end"] > 0 else 0
        if left <= 0:
            t = "torch out"
        else:
            mm, ss = divmod(left, 60)
            hh, mm = divmod(mm, 60)
            t = f"torch {hh}:{mm:02d}:{ss:02d}" if hh else f"torch {mm}:{ss:02d}"
        return t

    def paint_banner() -> None:
        dice = state["dice"] or "—"
        banner.setText(f"{dice}  ·  {torch_line()}  ·  round {state['round']}")

    def focus_menu() -> None:
        stack.setCurrentWidget(menu)
        state["view"] = "menu"
        menu.setFocus(Qt.OtherFocusReason)

    def show_read(text: str, *, back: str = "menu") -> None:
        state["view"] = "read"
        state["after_read"] = back
        read.setPlainText(text)
        stack.setCurrentWidget(read)
        read.setFocus(Qt.OtherFocusReason)

    def sheet_text(c: dict) -> str:
        mods = "  ".join(f"{s} {c.get(s, 10)}({_mod(int(c.get(s, 10))):+d})" for s in STATS)
        nxt = XP_NEXT.get(int(c.get("level") or 1), 10 * (int(c.get("level") or 1) + 1))
        gear = ", ".join(c.get("gear") or []) or "—"
        spells = ", ".join(c.get("spells") or []) or "—"
        return (
            f"{c.get('name')}  {c.get('ancestry')} {c.get('klass')}  "
            f"Lv {c.get('level')} {c.get('align')}\n"
            f"{mods}\n"
            f"AC {c.get('ac')}  HP {c.get('hp')}/{c.get('hp_max')}  "
            f"XP {c.get('xp')}/{nxt}\n"
            f"Gear: {gear}\nSpells: {spells}"
        )

    def fill_chars() -> None:
        menu.clear()
        rows = _chars()
        _add(menu, "New character", "new")
        if not rows:
            _add(menu, "(none yet)", "noop")
        else:
            for i, c in enumerate(rows):
                _add(
                    menu,
                    f"{c.get('name', '?')}  {c.get('klass', '')} "
                    f"Lv{c.get('level', 1)}  HP {c.get('hp')}/{c.get('hp_max')}",
                    "char",
                    i,
                )
        menu.setCurrentRow(0)

    def fill_ref_root() -> None:
        menu.clear()
        state["ref"] = "root"
        for lab, kind in (
            ("Rules", "cat_rules"),
            ("Spells", "cat_spells"),
            ("Armor", "cat_armor"),
            ("Weapons", "cat_weapons"),
            ("Gear", "cat_gear"),
            ("Names", "names"),
        ):
            _add(menu, lab, kind)
        menu.setCurrentRow(0)

    def fill_ref_rules() -> None:
        menu.clear()
        state["ref"] = "rules"
        for i, (title, _body) in enumerate(RULES):
            _add(menu, title, "rule", i)
        menu.setCurrentRow(0)

    def fill_ref_spells() -> None:
        menu.clear()
        state["ref"] = "spells"
        spells = state["spells"]
        if not spells:
            _add(menu, "(missing spells.json)", "noop")
        else:
            for i, sp in enumerate(spells):
                _add(
                    menu,
                    f"{sp.get('name')}  T{sp.get('tier')} {sp.get('class')}",
                    "spell",
                    i,
                )
        menu.setCurrentRow(0)

    def fill_named(ref: str, item_kind: str, rows: list, key: str) -> None:
        menu.clear()
        state["ref"] = ref
        for i, row in enumerate(rows):
            _add(menu, str(row.get(key, "?")), item_kind, i)
        menu.setCurrentRow(0)

    def fill_tools() -> None:
        menu.clear()
        for i, (lab, _s, _m) in enumerate(_DICE):
            _add(menu, f"Roll {lab}", "dice", i)
        _add(menu, "Light torch (1h)", "torch_on")
        _add(menu, "Snuff torch", "torch_off")
        _add(menu, "Round −", "rnd", -1)
        _add(menu, "Round +", "rnd", 1)
        _add(menu, "Reset round", "rnd", 0)
        _add(menu, "Encounter", "enc")
        _add(menu, "Loot 0–3", "loot")
        _add(menu, "NPC", "npc")
        _add(menu, "Hook", "hook")
        menu.setCurrentRow(0)

    def fill_set() -> None:
        menu.clear()
        _add(menu, "Open core book", "book")
        _add(menu, "About", "about")
        menu.setCurrentRow(0)

    def fill_menu() -> None:
        paint_tabs()
        paint_banner()
        t = state["tab"]
        if t == 0:
            fill_chars()
        elif t == 1:
            fill_ref_root()
        elif t == 2:
            fill_tools()
        else:
            fill_set()
        focus_menu()

    def goto_tab(i: int) -> None:
        state["tab"] = i % 4
        state["ref"] = "root"
        fill_menu()

    def show_sheet(i: int) -> None:
        rows = _chars()
        if i < 0 or i >= len(rows):
            return
        state["idx"] = i
        state["view"] = "sheet"
        c = rows[i]
        sheet_meta.setText(sheet_text(c))
        sheet_list.clear()
        for lab, kind, payload in (
            ("Hurt −1 HP", "hp", -1),
            ("Heal +1 HP", "hp", 1),
            ("−1 XP", "xp", -1),
            ("+1 XP", "xp", 1),
            ("Rename (random)", "rename", None),
            ("Delete", "delete", None),
            ("Back to list", "back", None),
        ):
            _add(sheet_list, lab, kind, payload)
        sheet_list.setCurrentRow(0)
        stack.setCurrentWidget(sheet_page)
        sheet_list.setFocus(Qt.OtherFocusReason)

    def bump_hp(delta: int) -> None:
        rows = _chars()
        i = state["idx"]
        if i >= len(rows):
            return
        c = rows[i]
        mx = int(c.get("hp_max") or 1)
        c["hp"] = max(0, min(mx, int(c.get("hp") or 0) + delta))
        _save_chars(rows)
        show_sheet(i)

    def bump_xp(delta: int) -> None:
        rows = _chars()
        i = state["idx"]
        if i >= len(rows):
            return
        c = rows[i]
        c["xp"] = max(0, int(c.get("xp") or 0) + delta)
        lv = int(c.get("level") or 1)
        need = XP_NEXT.get(lv, 10 * (lv + 1))
        if delta > 0 and c["xp"] >= need:
            c["level"] = lv + 1
            c["xp"] = c["xp"] - need
        _save_chars(rows)
        show_sheet(i)

    def do_new() -> None:
        rows = _chars()
        if len(rows) >= _MAX:
            return
        c = _blank()
        anc = random.choice(ANCESTRY)
        c["ancestry"] = anc
        c["klass"] = random.choice(KLASS)
        c["align"] = random.choice(ALIGN)
        c["name"] = random.choice(NAMES.get(anc, NAMES["Human"]))
        for s in STATS:
            c[s] = sum(sorted(random.randint(1, 6) for _ in range(4))[1:])
        c["hp_max"] = max(1, 8 + _mod(int(c["CON"])))
        c["hp"] = c["hp_max"]
        c["ac"] = 10 + _mod(int(c["DEX"]))
        rows.append(c)
        _save_chars(rows)
        show_sheet(len(rows) - 1)

    def do_rename() -> None:
        rows = _chars()
        i = state["idx"]
        if i >= len(rows):
            return
        anc = str(rows[i].get("ancestry") or "Human")
        rows[i]["name"] = random.choice(NAMES.get(anc, NAMES["Human"]))
        _save_chars(rows)
        show_sheet(i)

    def do_delete() -> None:
        rows = _chars()
        i = state["idx"]
        if i < 0 or i >= len(rows):
            return
        rows.pop(i)
        _save_chars(rows)
        goto_tab(0)

    def roll(idx: int) -> None:
        lab, sides, mode = _DICE[idx]
        if mode == "adv":
            a, b = random.randint(1, 20), random.randint(1, 20)
            keep = max(a, b)
            state["dice"] = f"Adv {keep}  ({a}/{b})"
        elif mode == "dis":
            a, b = random.randint(1, 20), random.randint(1, 20)
            keep = min(a, b)
            state["dice"] = f"Dis {keep}  ({a}/{b})"
        else:
            n = random.randint(1, sides)
            extra = ""
            if sides == 20 and n == 20:
                extra = " crit"
            elif sides == 20 and n == 1:
                extra = " fail"
            state["dice"] = f"{lab} {n}{extra}"
        paint_banner()

    def names_text() -> str:
        return "\n".join(f"{k}: {', '.join(v)}" for k, v in NAMES.items())

    def about_text() -> str:
        books = book_candidates()
        lines = [
            "Shadowdark companion · personal use, not for resale.",
            "← → switch Chars / Ref / Tools / Set",
            "↑ ↓ move in the list   Confirm open   Back close",
            "Dice stay on the Tools list; result is the line under the tabs.",
            "",
            "Put the core PDF in ~/Books (filename containing shadowdark).",
            "",
        ]
        if books:
            lines.append("Found:")
            lines.extend(str(p) for p in books[:4])
        else:
            lines.append("No book found yet.")
        return "\n".join(lines)

    def open_book() -> None:
        books = book_candidates()
        cfg = store.load(_SET, {}) or {}
        path = cfg.get("book") if isinstance(cfg, dict) else None
        p = Path(path) if path else (books[0] if books else None)
        if p is None or not Path(p).is_file():
            p = books[0] if books else None
        if p is None:
            show_read("No PDF in ~/Books with “shadowdark” in the name.")
            return
        store.save(_SET, {"book": str(p)})
        try:
            from PyQt5.QtWidgets import QApplication

            win = QApplication.activeWindow()
            pages = getattr(win, "pages", None) if win is not None else None
            if isinstance(pages, dict) and "files" in pages:
                fp = pages["files"]
                fn = getattr(fp, "open_path", None)
                go = getattr(win, "go", None)
                if callable(fn) and callable(go):
                    go("files")
                    fn(str(p))
                    return
        except Exception:
            pass
        from esp_handset.files_ui import _pdf_page

        n, txt = _pdf_page(Path(p), 1)
        show_read(f"{p}\n1/{n}\n\n{txt}")

    def gen_npc() -> str:
        anc = random.choice(ANCESTRY)
        name = random.choice(NAMES.get(anc, NAMES["Human"]))
        return (
            f"{name}  {anc} {random.choice(ALIGN)}\n"
            f"{random.choice(NPC_LOOK)}, {random.choice(NPC_JOB)}\n"
            f"{random.choice(NPC_DOES)}\nSecret: {random.choice(NPC_SECRET)}"
        )

    def gen_loot() -> str:
        n = random.randint(1, 100)
        item = LOOT_0_3[-1][1]
        for mx, it in LOOT_0_3:
            if n <= mx:
                item = it
                break
        return f"Treasure 0–3  d100={n}\n{item}"

    def gen_hook() -> str:
        a = random.choice(ADVENTURE_1)
        b = random.choice(ADVENTURE_2)
        c = random.choice(ADVENTURE_3)
        return f"{a} the {b} {c}\nSite: {random.choice(SITE)}"

    def on_menu(_item=None) -> None:
        it = menu.currentItem()
        if it is None:
            return
        kind, payload = it.data(Qt.UserRole)
        if kind == "noop":
            return
        if kind == "new":
            do_new()
            return
        if kind == "char":
            show_sheet(int(payload))
            return
        if kind == "cat_rules":
            fill_ref_rules()
            focus_menu()
            return
        if kind == "cat_spells":
            fill_ref_spells()
            focus_menu()
            return
        if kind == "cat_armor":
            fill_named("armor", "armor_item", ARMOR, "name")
            focus_menu()
            return
        if kind == "cat_weapons":
            fill_named("weapons", "weapon_item", WEAPONS, "name")
            focus_menu()
            return
        if kind == "cat_gear":
            fill_named("gear", "gear_item", GEAR, "name")
            focus_menu()
            return
        if kind == "names":
            show_read(names_text())
            return
        if kind == "rule":
            title, body_txt = RULES[int(payload)]
            show_read(f"{title}\n\n{body_txt}", back="ref_sub")
            return
        if kind == "spell":
            sp = state["spells"][int(payload)]
            show_read(
                f"{sp.get('name')}  T{sp.get('tier')} {sp.get('class')}\n"
                f"{sp.get('duration')} · {sp.get('range')}\n\n{sp.get('text')}",
                back="ref_sub",
            )
            return
        if kind == "armor_item":
            a = ARMOR[int(payload)]
            show_read(
                f"{a['name']}\n{a['cost']}  AC {a['ac']}\n{a['notes']}",
                back="ref_sub",
            )
            return
        if kind == "weapon_item":
            w = WEAPONS[int(payload)]
            show_read(
                f"{w['name']}\n{w['cost']}  {w['dmg']}\n{w['notes']}",
                back="ref_sub",
            )
            return
        if kind == "gear_item":
            g = GEAR[int(payload)]
            show_read(
                f"{g['name']}\n{g['cost']}  slot {g['slots']}",
                back="ref_sub",
            )
            return
        if kind == "dice":
            roll(int(payload))
            return
        if kind == "torch_on":
            _save_torch(time.time() + _HOUR, False)
            paint_banner()
            return
        if kind == "torch_off":
            _save_torch(0.0, True)
            paint_banner()
            return
        if kind == "rnd":
            d = int(payload)
            if d == 0:
                state["round"] = 1
            else:
                state["round"] = max(1, state["round"] + d)
            paint_banner()
            return
        if kind == "enc":
            show_read(f"Cave d20:\n{random.choice(CAVE_ENC)}")
            return
        if kind == "loot":
            show_read(gen_loot())
            return
        if kind == "npc":
            show_read(gen_npc())
            return
        if kind == "hook":
            show_read(gen_hook())
            return
        if kind == "book":
            open_book()
            return
        if kind == "about":
            show_read(about_text())

    def on_sheet(_item=None) -> None:
        it = sheet_list.currentItem()
        if it is None:
            return
        kind, payload = it.data(Qt.UserRole)
        if kind == "hp":
            bump_hp(int(payload))
        elif kind == "xp":
            bump_xp(int(payload))
        elif kind == "rename":
            do_rename()
        elif kind == "delete":
            do_delete()
        elif kind == "back":
            goto_tab(0)

    def leave_read() -> bool:
        if state["view"] != "read":
            return False
        if state["after_read"] == "ref_sub":
            # stay in the current ref sublist
            state["view"] = "menu"
            focus_menu()
            return True
        fill_menu()
        return True

    def leave_sheet() -> bool:
        if state["view"] != "sheet":
            return False
        goto_tab(0)
        return True

    def leave_ref_sub() -> bool:
        if state["view"] != "menu" or state["tab"] != 1 or state["ref"] == "root":
            return False
        fill_ref_root()
        focus_menu()
        return True

    menu.itemActivated.connect(on_menu)
    sheet_list.itemActivated.connect(on_sheet)

    tick = QTimer(body)
    tick.setInterval(500)
    tick.timeout.connect(paint_banner)
    tick.start()
    goto_tab(0)

    chrome = page_chrome("Shadowdark", body, on_back, scroll=False)

    def on_hardware_back() -> bool:
        if leave_read():
            return True
        if leave_sheet():
            return True
        if leave_ref_sub():
            return True
        return False

    def digi_move_h(delta: int) -> bool:
        # Swallow left/right so they never hunt buttons. Change tabs only on the menu.
        if state["view"] != "menu":
            return True
        if state["tab"] == 1 and state["ref"] != "root":
            return True
        goto_tab(state["tab"] + (1 if delta > 0 else -1))
        return True

    def digi_move_v(delta: int) -> bool:
        if state["view"] == "read":
            bar = read.verticalScrollBar()
            bar.setValue(bar.value() + int(delta) * 28)
            return True
        return False

    def digi_pad_active() -> bool:
        return True

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    chrome.digi_move_h = digi_move_h  # type: ignore[attr-defined]
    chrome.digi_move_v = digi_move_v  # type: ignore[attr-defined]
    chrome.digi_pad_active = digi_pad_active  # type: ignore[attr-defined]
    return chrome
