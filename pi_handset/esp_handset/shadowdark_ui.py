"""Shadowdark companion — B/W, pad-first, four tabs. Personal use of core tables."""
from __future__ import annotations

import random
import time
from typing import Callable, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
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

_BW = (
    "background:#000; color:#fff;"
)
_BTN = (
    "QPushButton { background:#000; color:#fff; border:1px solid #888; "
    "font-size:11px; font-weight:700; padding:4px; }"
    'QPushButton[digiFocus="1"] { border:2px solid #fff; background:#fff; color:#000; }'
)
_LIST = (
    "QListWidget { background:#000; color:#fff; border:1px solid #444; font-size:12px; }"
    "QListWidget::item:selected { background:#fff; color:#000; }"
    'QListWidget[digiFocus="1"] { border:2px solid #fff; }'
)
_TAB_OFF = (
    "QPushButton { background:#000; color:#aaa; border:1px solid #555; font-size:9px; }"
)
_TAB_ON = (
    "QPushButton { background:#fff; color:#000; border:1px solid #fff; font-size:9px; font-weight:700; }"
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


def make_shadowdark_page(on_back: Callable[[], None]) -> QWidget:
    body = QWidget()
    body.setStyleSheet(_BW)
    outer = QVBoxLayout(body)
    outer.setContentsMargins(2, 2, 2, 2)
    outer.setSpacing(2)

    status = QLabel("Characters")
    status.setStyleSheet("font-size:10px; color:#ccc;")
    outer.addWidget(status)

    stack = QStackedWidget()
    outer.addWidget(stack, 1)

    # ── Characters ────────────────────────────────────────────────────────
    ch_page = QWidget()
    chl = QVBoxLayout(ch_page)
    chl.setContentsMargins(0, 0, 0, 0)
    ch_list = QListWidget()
    ch_list.setStyleSheet(_LIST)
    ch_list.setFocusPolicy(Qt.StrongFocus)
    ch_btns = QHBoxLayout()
    b_new = QPushButton("New")
    b_open = QPushButton("Open")
    b_del = QPushButton("Del")
    for b in (b_new, b_open, b_del):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setMinimumHeight(26)
        ch_btns.addWidget(b)
    chl.addWidget(ch_list, 1)
    chl.addLayout(ch_btns)

    # ── Character sheet ───────────────────────────────────────────────────
    sh_page = QWidget()
    shl = QVBoxLayout(sh_page)
    shl.setContentsMargins(0, 0, 0, 0)
    name_ed = QLineEdit()
    name_ed.setStyleSheet("background:#000; color:#fff; border:1px solid #666; font-size:13px;")
    meta = QLabel("")
    meta.setWordWrap(True)
    meta.setStyleSheet("font-size:10px; color:#ddd;")
    hp_row = QHBoxLayout()
    hp_lab = QLabel("HP")
    hp_lab.setStyleSheet("font-size:11px;")
    hp_minus = QPushButton("-")
    hp_plus = QPushButton("+")
    xp_minus = QPushButton("XP-")
    xp_plus = QPushButton("XP+")
    for b in (hp_minus, hp_plus, xp_minus, xp_plus):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setFixedHeight(26)
    hp_row.addWidget(hp_lab)
    hp_row.addWidget(hp_minus)
    hp_row.addWidget(hp_plus)
    hp_row.addWidget(xp_minus)
    hp_row.addWidget(xp_plus)
    sheet_txt = QTextEdit()
    sheet_txt.setReadOnly(True)
    sheet_txt.setStyleSheet("QTextEdit { background:#000; color:#fff; border:none; font-size:11px; }")
    sh_nav = QHBoxLayout()
    b_edit = QPushButton("Edit")
    b_back_ch = QPushButton("List")
    for b in (b_edit, b_back_ch):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setMinimumHeight(26)
        sh_nav.addWidget(b)
    shl.addWidget(name_ed)
    shl.addWidget(meta)
    shl.addLayout(hp_row)
    shl.addWidget(sheet_txt, 1)
    shl.addLayout(sh_nav)

    # ── Reference ─────────────────────────────────────────────────────────
    ref_page = QWidget()
    rfl = QVBoxLayout(ref_page)
    rfl.setContentsMargins(0, 0, 0, 0)
    ref_list = QListWidget()
    ref_list.setStyleSheet(_LIST)
    ref_list.setFocusPolicy(Qt.StrongFocus)
    for title in ("Rules", "Spells", "Armor", "Weapons", "Gear", "Names"):
        ref_list.addItem(title)
    ref_body = QTextEdit()
    ref_body.setReadOnly(True)
    ref_body.setStyleSheet("QTextEdit { background:#000; color:#fff; border:1px solid #333; font-size:11px; }")
    rfl.addWidget(ref_list, 0)
    ref_list.setMaximumHeight(88)
    rfl.addWidget(ref_body, 1)

    # ── Tools ─────────────────────────────────────────────────────────────
    tools = QWidget()
    tl = QVBoxLayout(tools)
    tl.setContentsMargins(0, 0, 0, 0)
    dice_out = QLabel("—")
    dice_out.setAlignment(Qt.AlignCenter)
    dice_out.setStyleSheet("font-size:36px; font-weight:800;")
    dice_det = QLabel("Dice")
    dice_det.setAlignment(Qt.AlignCenter)
    dice_det.setStyleSheet("font-size:10px; color:#bbb;")
    grid = QGridLayout()
    dice_defs = (
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
    dice_btns = []
    for i, (lab, _s, _m) in enumerate(dice_defs):
        b = QPushButton(lab)
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setMinimumHeight(26)
        dice_btns.append(b)
        grid.addWidget(b, i // 3, i % 3)
    torch_lab = QLabel("Torch out")
    torch_lab.setAlignment(Qt.AlignCenter)
    torch_lab.setStyleSheet("font-size:14px;")
    trow = QHBoxLayout()
    light = QPushButton("Light 1h")
    snuff = QPushButton("Out")
    for b in (light, snuff):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setMinimumHeight(26)
        trow.addWidget(b)
    turn_lab = QLabel("Round 1")
    turn_lab.setAlignment(Qt.AlignCenter)
    tnav = QHBoxLayout()
    t_prev = QPushButton("Rnd-")
    t_next = QPushButton("Rnd+")
    t_reset = QPushButton("Reset")
    for b in (t_prev, t_next, t_reset):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setMinimumHeight(26)
        tnav.addWidget(b)
    gen_row = QHBoxLayout()
    g_enc = QPushButton("Encounter")
    g_loot = QPushButton("Loot 0-3")
    g_npc = QPushButton("NPC")
    g_adv = QPushButton("Hook")
    for b in (g_enc, g_loot, g_npc, g_adv):
        b.setFocusPolicy(Qt.StrongFocus)
        b.setStyleSheet(_BTN)
        b.setMinimumHeight(26)
        gen_row.addWidget(b)
    gen_out = QTextEdit()
    gen_out.setReadOnly(True)
    gen_out.setStyleSheet("QTextEdit { background:#000; color:#fff; border:1px solid #333; font-size:11px; }")
    tl.addWidget(dice_out)
    tl.addWidget(dice_det)
    tl.addLayout(grid)
    tl.addWidget(torch_lab)
    tl.addLayout(trow)
    tl.addWidget(turn_lab)
    tl.addLayout(tnav)
    tl.addLayout(gen_row)
    tl.addWidget(gen_out, 1)

    # ── Settings ──────────────────────────────────────────────────────────
    set_page = QWidget()
    sl = QVBoxLayout(set_page)
    sl.setContentsMargins(2, 2, 2, 2)
    set_info = QLabel("")
    set_info.setWordWrap(True)
    set_info.setStyleSheet("font-size:11px;")
    b_book = QPushButton("Open core book")
    b_book.setFocusPolicy(Qt.StrongFocus)
    b_book.setStyleSheet(_BTN)
    b_book.setMinimumHeight(30)
    sl.addWidget(set_info)
    sl.addWidget(b_book)
    sl.addStretch(1)

    stack.addWidget(ch_page)
    stack.addWidget(sh_page)
    stack.addWidget(ref_page)
    stack.addWidget(tools)
    stack.addWidget(set_page)

    tabs = QHBoxLayout()
    tab_btns = []
    for lab in ("Chars", "Ref", "Tools", "Set"):
        b = QPushButton(lab)
        b.setFocusPolicy(Qt.StrongFocus)
        b.setFixedHeight(24)
        tab_btns.append(b)
        tabs.addWidget(b)
    outer.addLayout(tabs)

    state = {"tab": 0, "idx": 0, "round": 1, "spells": load_spells()}

    def paint_tabs() -> None:
        names = ("Characters", "Reference", "Tools", "Settings")
        status.setText(names[state["tab"]])
        for i, b in enumerate(tab_btns):
            b.setStyleSheet(_TAB_ON if i == state["tab"] else _TAB_OFF)

    def goto_tab(i: int) -> None:
        state["tab"] = i
        paint_tabs()
        stack.setCurrentWidget((ch_page, ref_page, tools, set_page)[i])
        if i == 0:
            refresh_chars()
        elif i == 1:
            show_ref()
        elif i == 2:
            paint_torch()
        else:
            paint_settings()

    def refresh_chars() -> None:
        ch_list.clear()
        rows = _chars()
        if not rows:
            ch_list.addItem("(empty — New)")
            return
        for c in rows:
            ch_list.addItem(
                f"{c.get('name','?')}  {c.get('ancestry','')} {c.get('klass','')} "
                f"Lv{c.get('level',1)}  HP {c.get('hp')}/{c.get('hp_max')}"
            )
        ch_list.setCurrentRow(min(state["idx"], len(rows) - 1))

    def sheet_text(c: dict) -> str:
        mods = "  ".join(f"{s} {c.get(s,10)}({_mod(int(c.get(s,10))):+d})" for s in STATS)
        gear = ", ".join(c.get("gear") or []) or "—"
        spells = ", ".join(c.get("spells") or []) or "—"
        nxt = XP_NEXT.get(int(c.get("level") or 1), 10 * (int(c.get("level") or 1) + 1))
        return (
            f"{mods}\n"
            f"AC {c.get('ac')}  HP {c.get('hp')}/{c.get('hp_max')}  "
            f"XP {c.get('xp')}/{nxt}  {c.get('align')}\n"
            f"Gear: {gear}\nSpells: {spells}\n{c.get('notes') or ''}"
        )

    def show_sheet(i: int) -> None:
        rows = _chars()
        if i < 0 or i >= len(rows):
            return
        state["idx"] = i
        c = rows[i]
        name_ed.setText(str(c.get("name") or ""))
        meta.setText(f"{c.get('ancestry')} {c.get('klass')}  Lv {c.get('level')}")
        hp_lab.setText(f"HP {c.get('hp')}/{c.get('hp_max')}")
        sheet_txt.setPlainText(sheet_text(c))
        stack.setCurrentWidget(sh_page)
        name_ed.setFocus(Qt.OtherFocusReason)

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
        refresh_chars()
        show_sheet(len(rows) - 1)

    def do_del() -> None:
        rows = _chars()
        i = ch_list.currentRow()
        if i < 0 or i >= len(rows):
            return
        rows.pop(i)
        _save_chars(rows)
        refresh_chars()

    def do_open() -> None:
        rows = _chars()
        i = ch_list.currentRow()
        if 0 <= i < len(rows):
            show_sheet(i)

    def save_name() -> None:
        rows = _chars()
        i = state["idx"]
        if i >= len(rows):
            return
        rows[i]["name"] = name_ed.text().strip() or rows[i].get("name")
        _save_chars(rows)

    def show_ref() -> None:
        title = ref_list.currentItem().text() if ref_list.currentItem() else "Rules"
        if title == "Rules":
            ref_body.setPlainText("\n\n".join(f"{t}\n{b}" for t, b in RULES))
        elif title == "Spells":
            lines = []
            for sp in state["spells"]:
                lines.append(
                    f"{sp.get('name')}  T{sp.get('tier')} {sp.get('class')}\n"
                    f"{sp.get('duration')} · {sp.get('range')}\n{sp.get('text')}\n"
                )
            ref_body.setPlainText("\n".join(lines) or "Missing data/shadowdark/spells.json")
        elif title == "Armor":
            ref_body.setPlainText(
                "\n".join(f"{a['name']}  {a['cost']}  AC {a['ac']}  {a['notes']}" for a in ARMOR)
            )
        elif title == "Weapons":
            ref_body.setPlainText(
                "\n".join(f"{w['name']}  {w['cost']}  {w['dmg']}  {w['notes']}" for w in WEAPONS)
            )
        elif title == "Gear":
            ref_body.setPlainText("\n".join(f"{g['name']}  {g['cost']}  slot {g['slots']}" for g in GEAR))
        elif title == "Names":
            bits = [f"{k}: {', '.join(v[:8])}…" for k, v in NAMES.items()]
            ref_body.setPlainText("\n".join(bits))

    def roll(idx: int) -> None:
        lab, sides, mode = dice_defs[idx]
        if mode == "adv":
            a, b = random.randint(1, 20), random.randint(1, 20)
            keep = max(a, b)
            dice_out.setText(str(keep))
            dice_det.setText(f"Adv {a}/{b}")
            return
        if mode == "dis":
            a, b = random.randint(1, 20), random.randint(1, 20)
            keep = min(a, b)
            dice_out.setText(str(keep))
            dice_det.setText(f"Dis {a}/{b}")
            return
        n = random.randint(1, sides)
        extra = ""
        if sides == 20 and n == 20:
            extra = " crit"
        elif sides == 20 and n == 1:
            extra = " fail"
        dice_out.setText(str(n))
        dice_det.setText(f"{lab}{extra}")

    def paint_torch() -> None:
        st = _torch_state()
        left = int(st["end"] - time.time()) if st["end"] > 0 else 0
        if left <= 0:
            torch_lab.setText("Torch out")
            return
        mm, ss = divmod(left, 60)
        hh, mm = divmod(mm, 60)
        torch_lab.setText(f"Torch {hh}:{mm:02d}:{ss:02d}" if hh else f"Torch {mm}:{ss:02d}")

    def paint_settings() -> None:
        books = book_candidates()
        lines = [
            "Shadowdark companion · personal use",
            "Put the core PDF in ~/Books (name containing shadowdark).",
            "Open book uses the in-app reader — no Linux file dialog.",
            "",
        ]
        if books:
            lines.append("Found:")
            lines.extend(str(p) for p in books[:4])
        else:
            lines.append("No book found yet.")
        set_info.setText("\n".join(lines))

    def open_book() -> None:
        books = book_candidates()
        cfg = store.load(_SET, {}) or {}
        path = cfg.get("book") if isinstance(cfg, dict) else None
        from pathlib import Path

        p = Path(path) if path else (books[0] if books else None)
        if p is None or not Path(p).is_file():
            if books:
                p = books[0]
            else:
                gen_out.setPlainText("No PDF in ~/Books")
                goto_tab(2)
                return
        store.save(_SET, {"book": str(p)})
        page = body.window()
        opener = getattr(page, "open_files_path", None)
        # Prefer in-app Files page if the shell registered it
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
        del opener
        # Fallback: show first PDF page in tools output
        from esp_handset.files_ui import _pdf_page

        n, txt = _pdf_page(Path(p), 1)
        gen_out.setPlainText(f"{p}\n1/{n}\n\n{txt}")
        goto_tab(2)

    def gen_npc() -> None:
        anc = random.choice(ANCESTRY)
        name = random.choice(NAMES.get(anc, NAMES["Human"]))
        gen_out.setPlainText(
            f"{name}  {anc} {random.choice(ALIGN)}\n"
            f"{random.choice(NPC_LOOK)}, {random.choice(NPC_JOB)}\n"
            f"{random.choice(NPC_DOES)}\nSecret: {random.choice(NPC_SECRET)}"
        )

    def gen_enc() -> None:
        gen_out.setPlainText(f"Cave d20: {random.choice(CAVE_ENC)}")

    def gen_loot() -> None:
        n = random.randint(1, 100)
        item = LOOT_0_3[-1][1]
        for mx, it in LOOT_0_3:
            if n <= mx:
                item = it
                break
        gen_out.setPlainText(f"Treasure 0-3  d100={n}\n{item}")

    def gen_hook() -> None:
        a = random.choice(ADVENTURE_1)
        b = random.choice(ADVENTURE_2)
        c = random.choice(ADVENTURE_3)
        gen_out.setPlainText(f"{a} the {b} {c}\nSite: {random.choice(SITE)}")

    b_new.clicked.connect(do_new)
    b_open.clicked.connect(do_open)
    b_del.clicked.connect(do_del)
    ch_list.itemActivated.connect(lambda _=None: do_open())
    name_ed.editingFinished.connect(save_name)
    hp_minus.clicked.connect(lambda: bump_hp(-1))
    hp_plus.clicked.connect(lambda: bump_hp(1))
    xp_minus.clicked.connect(lambda: bump_xp(-1))
    xp_plus.clicked.connect(lambda: bump_xp(1))
    b_back_ch.clicked.connect(lambda: goto_tab(0))
    ref_list.currentRowChanged.connect(lambda _i: show_ref())
    for i, b in enumerate(dice_btns):
        b.clicked.connect(lambda _=False, k=i: roll(k))
    light.clicked.connect(lambda: (_save_torch(time.time() + _HOUR, False), paint_torch()))
    snuff.clicked.connect(lambda: (_save_torch(0.0, True), paint_torch()))
    t_prev.clicked.connect(lambda: (state.__setitem__("round", max(1, state["round"] - 1)), turn_lab.setText(f"Round {state['round']}")))
    t_next.clicked.connect(lambda: (state.__setitem__("round", state["round"] + 1), turn_lab.setText(f"Round {state['round']}")))
    t_reset.clicked.connect(lambda: (state.__setitem__("round", 1), turn_lab.setText("Round 1")))
    g_enc.clicked.connect(gen_enc)
    g_loot.clicked.connect(gen_loot)
    g_npc.clicked.connect(gen_npc)
    g_adv.clicked.connect(gen_hook)
    b_book.clicked.connect(open_book)
    for i, b in enumerate(tab_btns):
        b.clicked.connect(lambda _=False, k=i: goto_tab(k))

    tick = QTimer(body)
    tick.setInterval(500)
    tick.timeout.connect(paint_torch)
    tick.start()
    goto_tab(0)

    chrome = page_chrome("Shadowdark", body, on_back, scroll=False)

    def on_hardware_back() -> bool:
        if stack.currentWidget() is sh_page:
            goto_tab(0)
            return True
        return False

    chrome.on_hardware_back = on_hardware_back  # type: ignore[attr-defined]
    return chrome
