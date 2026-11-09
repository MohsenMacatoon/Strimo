"""Put files in the same order File Explorer shows them.

Explorer hands a multi-selection to the player in its own internal order, not the order on
screen. So Strimo asks the open Explorer window for that folder how it is sorted
(Name, Date modified, Size, Type, ... ascending or descending) and sorts the same way.
Names are compared with Windows' own StrCmpLogicalW, exactly like Explorer.
If no Explorer window is found (or anything fails), it falls back to sorting by name.
"""
from __future__ import annotations

import os
import sys
import threading
from functools import cmp_to_key

from .util import natural_key

_IS_WIN = sys.platform == "win32"

if _IS_WIN:
    import ctypes

    try:
        _cmp_logical = ctypes.windll.shlwapi.StrCmpLogicalW
        _cmp_logical.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        _cmp_logical.restype = ctypes.c_int
    except Exception:  # noqa: BLE001
        _cmp_logical = None
else:
    _cmp_logical = None


def _name_cmp(a: str, b: str) -> int:
    if _cmp_logical is not None:
        return _cmp_logical(a, b)
    ka, kb = natural_key(a), natural_key(b)
    return (ka > kb) - (ka < kb)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _query_sort_columns(folder: str, result: list) -> None:
    """Runs in a helper thread: finds the Explorer window showing `folder`, reads SortColumns."""
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        try:
            shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
            windows = shell.Windows()
            want = _norm(folder)
            found = []
            for i in range(int(windows.Count)):
                try:
                    w = windows.Item(i)
                    doc = w.Document
                    path = str(doc.Folder.Self.Path)
                    if _norm(path) == want:
                        try:
                            group = str(doc.GroupBy)
                        except Exception:  # noqa: BLE001 - older Windows
                            group = ""
                        found.append((str(doc.SortColumns), group))
                except Exception:  # noqa: BLE001 - not a folder window (e.g. Internet Explorer), skip
                    continue
            if found:
                result.append(found[0])
        finally:
            comtypes.CoUninitialize()
    except Exception:  # noqa: BLE001
        pass


def explorer_view(folder: str, timeout: float = 1.5):
    """(group_by, [(property, descending), ...]) for the Explorer window showing `folder`."""
    if not _IS_WIN:
        return None, []
    result: list = []
    t = threading.Thread(target=_query_sort_columns, args=(folder, result), daemon=True)
    t.start()
    t.join(timeout)  # never let a busy Explorer freeze Strimo
    if not result:
        return None, []
    sort_text, group_text = result[0]
    return parse_group(group_text), parse_sort_columns(sort_text)


def parse_group(text: str):
    """Explorer's GroupBy ('System.Null' = no groups) -> (property, descending) or None."""
    cols = parse_sort_columns(text)
    if not cols or cols[0][0].lower() in ("system.null", ""):
        return None
    prop, desc = cols[0]
    raw = (text or "").strip()
    if raw.lower().startswith("prop:"):
        raw = raw[5:]
    if not raw.startswith(("-", "+")) and _is_date(prop):
        desc = True  # Explorer lists date groups newest first
    return prop, desc


def _is_date(prop: str) -> bool:
    return "date" in prop.lower()


def parse_sort_columns(text: str) -> list[tuple[str, bool]]:
    """'prop:-System.DateModified;System.ItemNameDisplay;' -> [('System.DateModified', True), ...]"""
    text = (text or "").strip()
    if text.lower().startswith("prop:"):
        text = text[5:]
    cols = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        desc = part.startswith("-")
        cols.append((part.lstrip("+-"), desc))
    return cols


def _stat(path: str):
    try:
        return os.stat(path)
    except OSError:
        return None


def _value(prop: str, path: str, st):
    """A sortable value for one Explorer column, or None if Strimo can't know it."""
    p = prop.lower()
    name = os.path.basename(path)
    if p in ("system.itemnamedisplay", "system.filename", "system.itemname", "system.itemnamesortoverride"):
        return ("name", name)
    if p in ("system.datemodified", "system.itemdate", "system.datecreated", "system.dateaccessed",
             "system.media.datemodified", "system.photo.datetaken"):
        if st is None:
            return 0.0
        if p == "system.datecreated":
            return getattr(st, "st_birthtime", None) or st.st_ctime
        if p == "system.dateaccessed":
            return st.st_atime
        return st.st_mtime
    if p in ("system.size", "system.totalfilesize"):
        return st.st_size if st else 0
    if p in ("system.itemtypetext", "system.itemtype", "system.filetype", "system.fileextension"):
        return ("name", os.path.splitext(name)[1])
    return None


def _group_value(prop: str, path: str, st, now=None):
    """Which Explorer group a file falls in (Today, Yesterday, ... / A - H / Small...)."""
    import datetime as dt

    value = _value(prop, path, st)
    if value is None:
        return None
    if isinstance(value, tuple):  # name or type
        text = value[1].lstrip(".")
        if prop.lower() in ("system.itemtypetext", "system.itemtype", "system.filetype", "system.fileextension"):
            return ("name", text.lower())
        c = text[:1].upper()
        if c.isdigit():
            return 0
        for i, (lo, hi) in enumerate((("A", "H"), ("I", "P"), ("Q", "Z")), start=1):
            if lo <= c <= hi:
                return i
        return 4
    if prop.lower() in ("system.size", "system.totalfilesize"):
        for i, limit in enumerate((0, 16 << 10, 1 << 20, 128 << 20, 1 << 30, 4 << 30)):
            if value <= limit:
                return i
        return 6
    # date groups; a bigger number = more recent
    now = now or dt.datetime.now()
    d = dt.datetime.fromtimestamp(value).date()
    today = now.date()
    week_start = today - dt.timedelta(days=(today.weekday() + 1) % 7)  # weeks start on Sunday
    month_start = today.replace(day=1)
    last_month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    if d > today:
        return 9
    if d == today:
        return 8
    if d == today - dt.timedelta(days=1):
        return 7
    if d >= week_start:
        return 6
    if d >= week_start - dt.timedelta(days=7):
        return 5
    if d >= month_start:
        return 4
    if d >= last_month_start:
        return 3
    if d.year == today.year:
        return 2
    return 1


def _cmp_values(a, b) -> int:
    if a is None or b is None:
        return 0
    if isinstance(a, tuple):
        return _name_cmp(a[1], b[1])
    return (a > b) - (a < b)


def sort_like_explorer(files: list[str], columns=None, group=None) -> list[str]:
    """Sort local files the way the Explorer window they came from shows them."""
    if len(files) < 2:
        return list(files)
    if columns is None:
        folders = {_norm(os.path.dirname(f)) for f in files}
        if len(folders) == 1:
            group, columns = explorer_view(os.path.dirname(files[0]))
        else:
            group, columns = None, []
    usable = [(prop, desc) for prop, desc in columns if _value(prop, "x", None) is not None]
    if group and _value(group[0], "x", None) is None:
        group = None
    stats = {f: _stat(f) for f in files} if (usable or group) else {}

    def cmp(a: str, b: str) -> int:
        if group:
            r = _cmp_values(_group_value(group[0], a, stats.get(a)), _group_value(group[0], b, stats.get(b)))
            if r:
                return -r if group[1] else r
        for prop, desc in usable:
            r = _cmp_values(_value(prop, a, stats.get(a)), _value(prop, b, stats.get(b)))
            if r:
                return -r if desc else r
        # Explorer's tie-breaker (and the default when the sort is unknown): name, A to Z
        return _name_cmp(os.path.basename(a), os.path.basename(b))

    return sorted(files, key=cmp_to_key(cmp))
