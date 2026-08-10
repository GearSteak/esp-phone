"""Digivice joystick focus navigation for any app page."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QTextEdit,
    QWidget,
)

# Widgets the stick can land on
_FOCUS_TYPES = (
    QAbstractButton,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QListWidget,
    QComboBox,
    QCheckBox,
    QAbstractSpinBox,
    QSlider,
)


def _usable(w: QWidget) -> bool:
    if w is None or not isinstance(w, _FOCUS_TYPES):
        return False
    if not w.isVisible() or not w.isEnabled():
        return False
    if w.focusPolicy() == Qt.NoFocus:
        return False
    # Skip tiny chrome back if user prefers cycling content — keep it; Back key exists
    return True


def focusables(root: QWidget) -> List[QWidget]:
    """Visible focus targets under root, top-to-bottom then left-to-right."""
    found: List[QWidget] = []
    for w in root.findChildren(QWidget):
        if _usable(w):
            found.append(w)

    def key(w: QWidget) -> Tuple[int, int]:
        g = w.mapTo(root, w.rect().topLeft())
        return (g.y(), g.x())

    found.sort(key=key)
    # de-dupe while preserving order
    out: List[QWidget] = []
    seen = set()
    for w in found:
        i = id(w)
        if i not in seen:
            seen.add(i)
            out.append(w)
    return out


def _highlight(w: QWidget, on: bool) -> None:
    """High-contrast Digivice focus: style property + text marker (color-independent)."""
    w.setProperty("digiFocus", "1" if on else "0")
    # Shape/character cue works when color alone fails
    if isinstance(w, QAbstractButton):
        if on:
            base = w.property("digiFocusBase")
            if base is None:
                base = w.text()
                w.setProperty("digiFocusBase", base)
            else:
                base = str(base)
            label = str(base)
            if not label.startswith("▶ "):
                w.setText("▶ " + label)
        else:
            base = w.property("digiFocusBase")
            if base is not None:
                w.setText(str(base))
                # Keep base so re-focus is stable even if text was ▶ prefixed
            w.setProperty("digiFocusBase", None)
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def clear_highlights(root: QWidget) -> None:
    for w in root.findChildren(QWidget):
        if w.property("digiFocus") == "1":
            _highlight(w, False)


def digi_current(root: QWidget) -> Optional[QWidget]:
    """Highlighted digi target, even if Qt focus was stolen by shell/kiosk host."""
    items = focusables(root)
    if not items:
        return None
    for w in items:
        if w.property("digiFocus") == "1":
            return w
    cur = QApplication.focusWidget()
    if cur is not None:
        w: Optional[QWidget] = cur
        while w is not None:
            if w in items:
                return w
            w = w.parentWidget()
    return items[0]


def focus_index(items: List[QWidget], current: Optional[QWidget]) -> int:
    if not items:
        return -1
    if current in items:
        return items.index(current)
    # walk parents
    w = current
    while w is not None:
        if w in items:
            return items.index(w)
        w = w.parentWidget()
    return 0


def ensure_visible(w: Optional[QWidget]) -> None:
    """Scroll parent QScrollArea so focused control is on screen."""
    if w is None:
        return
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QScrollArea):
            p.ensureWidgetVisible(w, 8, 12)
            return
        # scroll area's viewport parent chain
        p = p.parentWidget()


def move_focus(root: QWidget, delta: int) -> bool:
    """Cycle focus among page controls. Returns True if handled."""
    items = focusables(root)
    if not items:
        return False
    cur = digi_current(root)
    idx = focus_index(items, cur)
    if idx < 0:
        idx = 0
    else:
        idx = (idx + delta) % len(items)
    clear_highlights(root)
    w = items[idx]
    w.setFocus(Qt.OtherFocusReason)
    _highlight(w, True)
    if isinstance(w, QListWidget) and w.count() > 0 and w.currentRow() < 0:
        w.setCurrentRow(0)
    ensure_visible(w)
    return True


def list_nudge(lst: QListWidget, delta: int) -> bool:
    """Move list selection; False if at edge (caller may leave list)."""
    if lst.count() == 0:
        return False
    row = lst.currentRow()
    if row < 0:
        lst.setCurrentRow(0)
        ensure_visible(lst)
        return True
    nxt = row + delta
    if 0 <= nxt < lst.count():
        lst.setCurrentRow(nxt)
        item = lst.item(nxt)
        if item is not None:
            lst.scrollToItem(item)
        ensure_visible(lst)
        return True
    return False


def activate_focused(w: Optional[QWidget], open_osk) -> bool:
    """Confirm on current widget. open_osk(widget) for text fields."""
    if w is None:
        return False
    if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
        open_osk(w)
        return True
    if isinstance(w, QListWidget):
        item = w.currentItem()
        if item is None and w.count() > 0:
            w.setCurrentRow(0)
            item = w.currentItem()
        if item is not None:
            w.itemClicked.emit(item)
            w.itemActivated.emit(item)
            return True
        return False
    if isinstance(w, QComboBox):
        # step or show popup — step is better for Digivice
        i = (w.currentIndex() + 1) % max(w.count(), 1)
        w.setCurrentIndex(i)
        return True
    if isinstance(w, QCheckBox):
        w.toggle()
        return True
    if isinstance(w, QAbstractButton):
        w.click()
        return True
    if isinstance(w, QAbstractSpinBox):
        w.stepUp()
        return True
    return False


def activate_page(root: QWidget, open_osk) -> bool:
    """Confirm the digi-highlighted control on a page (ignore stolen Qt focus)."""
    return activate_focused(digi_current(root), open_osk)


def ensure_page_focus(root: QWidget) -> None:
    """On entering an app page, land on first content control (skip back chrome if possible)."""
    items = focusables(root)
    if not items:
        return
    clear_highlights(root)
    # Prefer first non-Back control when chrome Back is first (sorted top-left)
    w = items[0]
    if len(items) > 1 and isinstance(w, QAbstractButton) and (w.text() or "") in ("←", "← ", "<"):
        w = items[1]
    w.setFocus(Qt.OtherFocusReason)
    _highlight(w, True)
    if isinstance(w, QListWidget) and w.count() > 0:
        w.setCurrentRow(0)
    ensure_visible(w)
