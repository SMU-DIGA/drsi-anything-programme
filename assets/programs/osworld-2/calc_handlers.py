"""Instruction + sheet dump -> UNO actions for Calc tasks.

Each handler h_*(instr, data) returns a list of (tag, code) actions or None; `plan` tries them in
priority order (HANDLERS) and returns the first match.
"""
import re

import vmcode

# Connect to the relaunched soffice (restarting it on DOC_URL if it died), bind doc/sheets/sh.
HEAD = vmcode.UNO_PRELUDE + r'''
try:
    ctx, desktop = _connect(40)
except Exception:
    # soffice died since the relaunch: start it again on the same document
    _launch([DOC_URL] if DOC_URL else [])
    ctx, desktop = _connect(60)
doc = _wait_doc(desktop)
sheets = doc.getSheets()
sh = doc.getCurrentController().getActiveSheet()
def colname(i):
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s
'''

TAIL = r'''
doc.store()
print('STORED', doc.getURL())
'''

DOC_URL = [""]


def uno(body, store=True):
    return "DOC_URL = %r\n" % DOC_URL[0] + HEAD + body + (TAIL if store else "")


# ---------------------------------------------------------------- helpers
def quoted(s):
    out = re.findall(r'"([^"]+)"|“([^”]+)”|‘([^’]+)’|(?<![A-Za-z])\'([^\']+)\'(?![A-Za-z])', s)
    return [next(g for g in t if g) for t in out]


def active_sheet(data):
    return data["sheets"][0] if data.get("sheets") else None


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def a1(ref):
    """'B12' -> (row 11, col 1)."""
    m = re.match(r'([A-Za-z]+)(\d+)', ref)
    c = 0
    for ch in m.group(1).upper():
        c = c * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, c - 1


def find_col(sheet, name, header_rows=3):
    """Return (header_row, col) for header text best matching name."""
    name_l = name.strip().lower()
    best = None
    for r, row in enumerate(sheet["rows"][:header_rows]):
        for c, v in enumerate(row):
            if isinstance(v, str) and v.strip():
                vl = v.strip().lower()
                if vl == name_l:
                    return r, c
                if best is None and (name_l in vl or vl in name_l) and len(vl) > 1:
                    best = (r, c)
    return best


def last_data_row(sheet, col, start):
    lr = sheet.get("lastrow")
    if lr and col < len(lr):
        return max(start, lr[col])
    last = start
    for r in range(start, len(sheet["rows"])):
        v = sheet["rows"][r][col] if col < len(sheet["rows"][r]) else ""
        if v not in ("", None):
            last = r
    return last


def mentioned_cols(instr, sheet):
    """Header columns mentioned in the instruction, in order of mention: [(pos, col, header)]."""
    low = instr.lower()
    out = []
    if not sheet["rows"]:
        return out
    for c, v in enumerate(sheet["rows"][0]):
        if isinstance(v, str) and len(v.strip()) > 1:
            m = re.search(r'(?<![a-z0-9])' + re.escape(v.strip().lower()) + r'(?![a-z0-9])', low)
            if m:
                out.append((m.start(), c, v.strip()))
    out.sort()
    # drop headers that are substrings of a longer mentioned header at the same spot
    return [(p, c, v) for p, c, v in out
            if not any(p2 <= p and p + len(v) <= p2 + len(v2) and v2 != v for p2, c2, v2 in out)]


def find_tables(rows):
    """Header-row tables: [{'hr': r, 'cols': [c...], 'rows': [r...]}], tables may sit side by side."""
    tables = []
    used = set()
    nr = len(rows)
    for r in range(nr):
        groups, cur = [], []
        for c, v in enumerate(rows[r]):
            if isinstance(v, str) and v.strip() and (r, c) not in used:
                cur.append(c)
            else:
                if cur:
                    groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        for g in groups:
            if len(g) < 2:
                continue
            blank = lambda rr: all(_empty(rows[rr][c]) for c in g if c < len(rows[rr]))
            drows = []
            rr = r + 1
            while rr < nr and not blank(rr):
                drows.append(rr)
                rr += 1
            if not drows:
                continue
            tables.append({"hr": r, "cols": g, "rows": drows})
            used.update((x, c) for x in drows for c in g)
    return tables


SET_CELLS = r'''
for r, v in %r:
    cell = sh.getCellByPosition(%d, r)
    if isinstance(v, str): cell.setString(v)
    else: cell.setValue(v)
'''


# ---------------------------------------------------------------- handlers
def h_validation(instr, data):
    """Dropdown list (data validation) on a column, options = quoted strings other than the header."""
    if not re.search(r'validation|drop[- ]?down|dropdown', instr.lower()):
        return None
    sheet = active_sheet(data)
    if sheet is None:
        return None
    q = quoted(instr)
    col = None
    for x in q:
        f = find_col(sheet, x)
        if f and str(sheet["rows"][f[0]][f[1]]).strip().lower() == x.strip().lower():
            col = f
            break
    if col is None:
        cols = mentioned_cols(instr, sheet)
        if not cols:
            return None
        col = (0, cols[0][1])
    hr, c = col
    hdr = str(sheet["rows"][hr][c]).strip().lower()
    opts = [x for x in q if x.strip().lower() != hdr]
    if not opts:
        return None
    # data rows: extent of the table (any non-empty cell in the row)
    last = hr
    for r in range(hr + 1, len(sheet["rows"])):
        if any(not _empty(v) for v in sheet["rows"][r]):
            last = r
    if sheet.get("truncated") and sheet.get("lastrow"):
        last = max(last, max(sheet["lastrow"]))
    formula = ";".join('"%s"' % o.replace('"', '""') for o in opts)
    body = r'''
from com.sun.star.sheet.ValidationType import LIST
rng = sh.getCellRangeByPosition(%d, %d, %d, %d)
v = rng.Validation
v.Type = LIST
v.setFormula1(%r)
v.ShowList = 1
v.IgnoreBlankCells = True
rng.Validation = v
''' % (c, hr + 1, c, last, formula)
    return [("validation", uno(body))]


def h_pivot(instr, data):
    """DataPilot: text columns mentioned -> row (or column) fields, first numeric one -> data field."""
    low = instr.lower()
    if "pivot" not in low and not re.search(r'summari[sz]e .* for each', low):
        return None
    sheet = active_sheet(data)
    if sheet is None:
        return None
    cols = mentioned_cols(instr, sheet)
    # fuzzy: also match header words (e.g. "promotion type" vs header "Promotion")
    found = {c for _, c, _ in cols}
    for c, v in enumerate(sheet["rows"][0] if sheet["rows"] else []):
        if c in found or not isinstance(v, str) or not v.strip():
            continue
        for w in [w for w in re.findall(r'[a-z]+', v.lower()) if len(w) > 3]:
            i = low.find(w)
            if i >= 0:
                cols.append((i, c, v))
                found.add(c)
                break
    cols.sort()
    if len(cols) < 2:
        return None
    numeric = lambda c: sum(isinstance(r[c], (int, float)) for r in sheet["rows"][1:] if c < len(r)) > 0.5 * max(1, len(sheet["rows"]) - 1)
    vals = [c for _, c, _ in cols if numeric(c)]
    groups = [c for _, c, _ in cols if not numeric(c)]
    if not vals or not groups:
        return None
    func = "SUM"
    for pat, f in [(r'average|mean', "AVERAGE"), (r'\bcount|number of', "COUNT"), (r'\bmax', "MAX"), (r'\bmin', "MIN")]:
        if re.search(pat, low):
            func = f
            break
    as_cols = bool(re.search(r'as (the )?column', low))
    m = re.search(r'new sheet\s*(?:\(|named\s*|called\s*)["“\']?([^"”\')]+)["”\')]?', instr, re.I)
    newsheet = m.group(1).strip() if m else ("Sheet2" if "new sheet" in low else None)
    body = r'''
from com.sun.star.table import CellRangeAddress, CellAddress
from com.sun.star.sheet.DataPilotFieldOrientation import ROW, COLUMN, DATA
from com.sun.star.sheet.GeneralFunction import %s as FUNC
srcidx = [sheets.getByIndex(i).getName() for i in range(sheets.getCount())].index(sh.getName())
src = CellRangeAddress(); src.Sheet = srcidx; src.StartColumn = 0; src.StartRow = 0; src.EndColumn = %d; src.EndRow = %d
newname = %r
if newname:
    if not sheets.hasByName(newname):
        sheets.insertNewByName(newname, sheets.getCount())
    tgt = sheets.getByName(newname)
else:
    tgt = sh
tidx = [sheets.getByIndex(i).getName() for i in range(sheets.getCount())].index(tgt.getName())
dest = CellAddress(); dest.Sheet = tidx; dest.Column = 0 if newname else %d; dest.Row = 0
dpt = tgt.getDataPilotTables()
desc = dpt.createDataPilotDescriptor()
desc.setSourceRange(src)
fields = desc.getDataPilotFields()
for g in %r:
    f = fields.getByIndex(g); f.Orientation = COLUMN if %r else ROW
for v in %r:
    f = fields.getByIndex(v); f.Orientation = DATA; f.Function = FUNC
dpt.insertNewByName('DataPilot1', dest, desc)
''' % (func, sheet["ncols"] - 1, sheet["nrows"] - 1, newsheet, sheet["ncols"] + 1, groups[:2], as_cols, vals[:1])
    return [("pivot", uno(body))]


def h_fill_blank(instr, data):
    """Fill empty cells of a range (A1:B9 or the whole sheet) with the value above or a given value."""
    low = instr.lower()
    if not ("blank" in low or "empty" in low) or "fill" not in low:
        return None
    m = re.search(r'\b([A-Z]+\d+)\s*:\s*([A-Z]+\d+)\b', instr)
    sheet = active_sheet(data)
    if m:
        r0, c0 = a1(m.group(1))
        r1, c1 = a1(m.group(2))
    elif sheet:
        r0, c0, r1, c1 = 1, 0, sheet["nrows"] - 1, sheet["ncols"] - 1
    else:
        return None
    if re.search(r'above|previous|preced|upper', low):
        body = r'''
for c in range(%d, %d):
    for r in range(max(%d, 1), %d):
        cell = sh.getCellByPosition(c, r)
        if cell.getType().value == 'EMPTY':
            up = sh.getCellByPosition(c, r - 1)
            t = up.getType().value
            if t == 'VALUE': cell.setValue(up.getValue())
            elif t == 'TEXT': cell.setString(up.getString())
            elif t == 'FORMULA': cell.setFormula(up.getFormula())
''' % (c0, c1 + 1, r0, r1 + 1)
        return [("fill_blank_above", uno(body))]
    m = re.search(r'(?:with|by)\s+["“\']?([^"”\'\s,.]+)', instr)
    if m:
        body = r'''
val = %r
for c in range(%d, %d):
    for r in range(%d, %d):
        cell = sh.getCellByPosition(c, r)
        if cell.getType().value == 'EMPTY':
            try: cell.setValue(float(val))
            except ValueError: cell.setString(val)
''' % (m.group(1), c0, c1 + 1, r0, r1 + 1)
        return [("fill_blank_value", uno(body))]
    return None


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10}


def h_pad_zeros(instr, data):
    """Copy the first quoted column into the second, left-padded with zeros to N digits."""
    low = instr.lower()
    if "pad" not in low or "zero" not in low:
        return None
    n = None
    for g in re.findall(r'\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\b[- ]digits?', low):
        n = int(g) if g.isdigit() else NUMBER_WORDS[g]
    q = quoted(instr)
    sheet = active_sheet(data)
    if n is None or len(q) < 2 or sheet is None:
        return None
    src = find_col(sheet, q[0])
    dst = find_col(sheet, q[1])
    if not src or not dst:
        return None
    hr, sc = src
    end = last_data_row(sheet, sc, hr + 1)
    body = r'''
for r in range(%d, %d):
    v = sh.getCellByPosition(%d, r)
    s = v.getString().strip()
    if not s: continue
    try:
        s = str(int(float(v.getValue())) if v.getType().value == 'VALUE' else int(s))
    except Exception:
        pass
    sh.getCellByPosition(%d, r).setString(s.zfill(%d))
''' % (hr + 1, end + 1, sc, dst[1], n)
    return [("pad_zeros", uno(body))]


EXPORT_FILTERS = {"csv": "Text - txt - csv (StarCalc)", "pdf": "calc_pdf_Export", "ods": "calc8",
                  "xlsx": "Calc MS Excel 2007 XML", "html": "HTML (StarCalc)"}


def h_export(instr, data):
    """Save a copy in another format (target = quoted path, else same name); 'fit to one page' for pdf."""
    low = instr.lower()
    # prefer csv/pdf/ods/html: "save as csv next to the original xlsx" must not overwrite the source
    m = re.search(r'\b(export|save|convert)\b.*?\b(csv|pdf|ods|html)\b', low) or \
        re.search(r'\b(export|save|convert)\b.*?\b(xlsx)\b', low)
    if not m or re.search(r'chart|pivot|formula|sort|calculat|fill', low):
        return None
    fmt = m.group(2)
    q = [x for x in quoted(instr) if "." in x or "/" in x]
    fit = bool(re.search(r'one page|single page|fit', low))
    body = r'''
FIT = %r
path = uno.fileUrlToSystemPath(doc.getURL())
target = %r
if target:
    if not target.startswith('/'):
        target = os.path.join(os.path.dirname(path), os.path.expanduser(target)) if not target.startswith('~') else os.path.expanduser(target)
    if not os.path.splitext(target)[1]:
        target += '.%s'
else:
    target = os.path.splitext(path)[0] + '.%s'
if FIT:
    pss = doc.getStyleFamilies().getByName('PageStyles')
    for i in range(sheets.getCount()):
        try:
            ps = pss.getByName(sheets.getByIndex(i).PageStyle)
            ps.ScaleToPagesX = 1; ps.ScaleToPagesY = 1
        except Exception as e:
            print('fit err', e)
args = (_pv('FilterName', %r),)
if %r == 'csv':
    args += (_pv('FilterOptions', '44,34,76,1,,0,false,true,true,false'),)
doc.storeToURL(uno.systemPathToFileUrl(target), args)
print('EXPORTED', target)
''' % (fit, q[0] if q else "", fmt, fmt, EXPORT_FILTERS[fmt], fmt)
    return [("export", uno(body, store=False))]


TOTALS_BODY = r'''
import re as _re
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
ra = cur.getRangeAddress(); R, C = ra.EndRow, ra.EndColumn
def T(r, c): return sh.getCellByPosition(c, r).getType().value
def isnum(r, c): return r >= 0 and c >= 0 and T(r, c) in ('VALUE', 'FORMULA')
def islabel(r, c):
    return T(r, c) == 'TEXT' and _re.match(r'^\s*(grand\s+)?(total|sum)s?\s*:?\s*$', sh.getCellByPosition(c, r).getString(), _re.I)
labels = [(r, c) for r in range(R + 1) for c in range(C + 1) if islabel(r, c)]
n = 0
# column of totals (label is a column header): sum the numbers to the left in each row below
for (r0, c) in labels:
    if c == 0: continue
    r = r0 + 1
    while r <= R:
        if all(T(r, k) == 'EMPTY' for k in range(C + 1)): break
        if islabel(r, c) or T(r, c) == 'TEXT': break
        if T(r, c) == 'EMPTY' and isnum(r, c - 1):
            cs = c - 1
            while isnum(r, cs - 1): cs -= 1
            sh.getCellByPosition(c, r).setFormula('=SUM(%s%d:%s%d)' % (colname(cs), r + 1, colname(c - 1), r + 1)); n += 1
        r += 1
# row of totals (label is a row header): sum the numbers above in each column to the right
for (r, c0) in labels:
    for c in range(c0 + 1, C + 1):
        if T(r, c) != 'EMPTY' or not isnum(r - 1, c): continue
        rs = r - 1
        while isnum(rs - 1, c): rs -= 1
        sh.getCellByPosition(c, r).setFormula('=SUM(%s%d:%s%d)' % (colname(c), rs + 1, colname(c), r)); n += 1
print('filled', n)
'''


def h_totals(instr, data):
    """Fill missing cells of rows/columns labelled Total/Sum with SUM formulas."""
    low = instr.lower()
    if not re.search(r'\btotals?\b|\bsums?\b', low) or not re.search(r'fill|missing|complete|empty|blank', low):
        return None
    if not re.search(r'(totals?|sums?|subtotals?)\s+(rows?|columns?|cells?|values?|lines?)|'
                     r'(rows?|columns?|cells?)\s+(which|that)\s+(show|contain|hold|display)s?\s+the\s+(total|sum)', low):
        return None
    return [("totals", uno(TOTALS_BODY))]


def h_sort(instr, data):
    """Sort the used area by up to 3 mentioned header columns (in order of mention)."""
    low = instr.lower()
    if not re.search(r'\bsort|\border\b.*\bby\b|\brank\b', low) or re.search(r'chart|pivot|new column|calculat', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    keys = sorted((low.find(v.strip().lower()), c) for c, v in enumerate(sheet["rows"][0])
                  if isinstance(v, str) and v.strip() and low.find(v.strip().lower()) >= 0)
    if not keys:
        return None
    desc = bool(re.search(r'descend|largest|highest|decreas|z to a|high to low|biggest|most', low))
    body = r'''
from com.sun.star.table import TableSortField
rng = sh.getCellRangeByPosition(0, 0, %d, %d)
fields = []
for c in %r:
    f = TableSortField(); f.Field = c; f.IsAscending = %s; f.IsCaseSensitive = False
    fields.append(f)
desc = (_pv('SortFields', uno.Any('[]com.sun.star.table.TableSortField', tuple(fields))), _pv('ContainsHeader', True))
uno.invoke(rng, 'sort', (uno.Any('[]com.sun.star.beans.PropertyValue', desc),))
''' % (sheet["ncols"] - 1, sheet["nrows"] - 1, [c for _, c in keys[:3]], not desc)
    return [("sort", uno(body))]


def h_hide_rows(instr, data):
    """Hide or delete rows containing a quoted value (e.g. "N/A"), or empty rows."""
    low = instr.lower()
    m = re.search(r'\b(hide|delete|remove)\b', low)
    if not m or "column" in low.split(m.group(1), 1)[1][:30]:
        return None
    vals = [x for x in quoted(instr) if len(x) < 30]
    empty = bool(re.search(r'empty rows|blank rows', low))
    if (not vals and not empty) or not re.search(r'row|them|record|entr|data', low) or active_sheet(data) is None:
        return None
    body = r'''
vals = %r
empty = %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
ra = cur.getRangeAddress()
rows = []
lv = [v.lower().strip('#') for v in vals]
for r in range(1, ra.EndRow + 1):
    row = [sh.getCellByPosition(c, r).getString().strip() for c in range(ra.EndColumn + 1)]
    if (vals and any(v.lower().strip('#') in lv for v in row if v)) or (empty and all(v == '' for v in row)):
        rows.append(r)
print('rows', rows)
if %r == 'hide':
    for r in rows:
        sh.getRows().getByIndex(r).IsVisible = False
else:
    for r in reversed(rows):
        sh.getRows().removeByIndex(r, 1)
''' % (vals, empty, 'hide' if m.group(1) == 'hide' else 'delete')
    return [("hide_rows", uno(body))]


CHART_TYPES = [  # (instruction word, diagram kind, horizontal bars)
    ("clustered column", "bar", False), ("column", "bar", False), ("bar", "bar", True),
    ("line", "line", False), ("pie", "pie", False), ("scatter", "xy", False), ("area", "area", False),
]


def h_chart(instr, data):
    """Chart of the header columns named in the instruction (first column = categories)."""
    low = instr.lower()
    if "chart" not in low:
        return None
    kind = next(((t, vert) for k, t, vert in CHART_TYPES if k in low), None)
    sheet = active_sheet(data)
    if kind is None or sheet is None:
        return None
    headers = [(c, v) for c, v in enumerate(sheet["rows"][0]) if isinstance(v, str) and v.strip()] if sheet["rows"] else []
    series = [c for c, v in headers if re.search(r'\b' + re.escape(v.strip().lower()) + r'\b', low)]
    if not series:
        return None
    cat = 0 if 0 not in series else None
    m = re.search(r'title (?:as|to|of)?\s*["“\']([^"”\']+)["”\']', instr, re.I)
    title = m.group(1) if m else None
    m = re.search(r'new sheet (?:named|called)\s*["“\']([^"”\']+)["”\']', instr, re.I)
    newsheet = m.group(1) if m else None
    cols = ([cat] if cat is not None else []) + series
    body = r'''
from com.sun.star.awt import Rectangle
from com.sun.star.table import CellRangeAddress
srcidx = [sheets.getByIndex(i).getName() for i in range(sheets.getCount())].index(sh.getName())
target = sh
newname = %r
if newname:
    if not sheets.hasByName(newname):
        sheets.insertNewByName(newname, sheets.getCount())
    target = sheets.getByName(newname)
ranges = []
for c in %r:
    a = CellRangeAddress(); a.Sheet = srcidx; a.StartColumn = c; a.EndColumn = c; a.StartRow = 0; a.EndRow = %d
    ranges.append(a)
rect = Rectangle(); rect.X = 1000; rect.Y = 1000; rect.Width = 16000; rect.Height = 9000
charts = target.getCharts()
name = 'Chart1'
while charts.hasByName(name): name += 'x'
charts.addNewByName(name, rect, tuple(ranges), True, %s)
cdoc = charts.getByName(name).getEmbeddedObject()
kind, vert = %r, %r
svc = {'bar': 'com.sun.star.chart.BarDiagram', 'line': 'com.sun.star.chart.LineDiagram', 'pie': 'com.sun.star.chart.PieDiagram', 'xy': 'com.sun.star.chart.XYDiagram', 'area': 'com.sun.star.chart.AreaDiagram'}[kind]
dia = cdoc.createInstance(svc)
cdoc.setDiagram(dia)
if kind == 'bar':
    dia.Vertical = vert
title = %r
if title:
    cdoc.HasMainTitle = True
    cdoc.getTitle().String = title
''' % (newsheet, cols, sheet["nrows"] - 1, cat is not None, kind[0], kind[1], title)
    return [("chart", uno(body))]


def h_lookup(instr, data):
    """Fill an empty column of one table from another table: exact key match, or threshold scale
    (largest key <= value) when keys are numeric with the same header."""
    low = instr.lower()
    if not re.search(r'lookup|look up|according|corresponding|match|based on|scale|table', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or len(sheet["rows"]) < 3:
        return None
    rows = sheet["rows"]
    tabs = find_tables(rows)
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    H = lambda r, c: str(rows[r][c]).strip().lower()
    for T in tabs:
        for t in T["cols"]:  # t: empty target column of table T
            if not all(_empty(rows[r][t]) for r in T["rows"]):
                continue
            for S in tabs:
                if S is T:
                    continue
                same = [s for s in S["cols"] if H(S["hr"], s) == H(T["hr"], t)]
                best = None  # (score, key col in T, key col in S, value col in S, mode)
                for k in T["cols"]:
                    if k == t:
                        continue
                    kv = [rows[r][k] for r in T["rows"] if not _empty(rows[r][k])]
                    if not kv:
                        continue
                    for k2 in S["cols"]:
                        svals = [s for s in (same or [c for c in S["cols"] if c != k2]) if s != k2]
                        if len(svals) != 1:
                            continue
                        sv = [rows[r][k2] for r in S["rows"]]
                        sc, mode = sum(v in sv for v in kv) / len(kv), "exact"
                        if sc < 0.6 and all(num(v) for v in kv) and all(num(v) for v in sv if not _empty(v)) \
                                and H(S["hr"], k2) == H(T["hr"], k):
                            sc, mode = 0.7, "approx"
                        if best is None or sc > best[0]:
                            best = (sc, k, k2, svals[0], mode)
                if not best or best[0] < 0.6:
                    continue
                _, k, k2, s, mode = best
                pairs = [(rows[r][k2], rows[r][s]) for r in S["rows"] if not _empty(rows[r][k2])]
                if mode == "approx":
                    pairs.sort(key=lambda p: p[0])
                fills = []
                for r in T["rows"]:
                    key = rows[r][k]
                    if _empty(key):
                        continue
                    if mode == "exact":
                        val = next((b for a, b in pairs if a == key), None)
                    else:
                        val = next((b for a, b in reversed(pairs) if a <= key), None)
                    if val is not None:
                        fills.append((r, val))
                if fills:
                    return [("lookup", uno(SET_CELLS % (fills, t)))]
    return None


def h_formula_expr(instr, data):
    """'<Target> = <expression over header names>' -> fill target column with row formulas."""
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    names = sorted([(str(v).strip(), c) for c, v in enumerate(sheet["rows"][0]) if isinstance(v, str) and v.strip()],
                   key=lambda x: -len(x[0]))
    for m in re.finditer(r'=', instr):
        right = re.split(r'[.;](?:\s|$)|,\s+(?:and|then)\b|\n', instr[m.end():])[0]
        # target: longest header name / quoted name at the end of the left side
        tl = instr[:m.start()].rstrip().rstrip('"\'”').lower()
        tgt = next(((n, c) for n, c in names if tl.endswith(n.lower())), None)
        if tgt is None:
            for mq in re.finditer(r'["“]([^"”]+)["”]|(?<![A-Za-z])\'([^\']+)\'(?![A-Za-z])', instr):
                qn = (mq.group(1) or mq.group(2)).strip()
                if tl.endswith(qn.lower()):
                    tgt = (qn, None)
                    break
        if tgt is None:
            continue
        out = right.strip().strip('"\'')
        used = []
        for n, c in names:
            if n == tgt[0]:
                continue
            pat = re.compile(r'(?<![\w])["\']?' + re.escape(n) + r'["\']?(?![\w])', re.I)
            if pat.search(out):
                out = pat.sub('\x00%d\x00' % c, out)
                used.append(c)
        out = out.replace('×', '*').replace('÷', '/')
        if not used or not re.fullmatch(r'[\s\d.+\-*/()%x]*', re.sub(r'\x00\d+\x00', '', out)):
            continue
        tcol = tgt[1] if tgt[1] is not None else sheet["ncols"]
        last = max(last_data_row(sheet, c, 1) for c in used)
        template = re.sub(r'\x00(\d+)\x00', lambda mm: '{%s}' % mm.group(1), out).strip()
        body = r'''
tmpl = %r
tc = %d
if %r:
    sh.getCellByPosition(tc, 0).setString(%r)
import re as _re
for r in range(1, %d):
    if all(sh.getCellByPosition(c, r).getType().value == 'EMPTY' for c in %r):
        continue
    f = '=' + _re.sub(r'\{(\d+)\}', lambda m: colname(int(m.group(1))) + str(r + 1), tmpl)
    sh.getCellByPosition(tc, r).setFormula(f)
''' % (template, tcol, tgt[1] is None, tgt[0], last + 1, used)
        return [("formula_expr", uno(body))]
    return None


def h_new_column_arith(instr, data):
    """New column "X" = two (or more, for sums) mentioned columns combined with -, /, * or +."""
    low = instr.lower()
    m = re.search(r'(?:new\s+)?column\s+(?:named|called|with (?:the )?(?:header|title|name))\s+["“\']([^"”\']+)["”\']', instr, re.I) \
        or re.search(r'["“\']([^"”\']+)["”\']\s+(?:new\s+)?column', instr, re.I)
    sheet = active_sheet(data)
    if not m or sheet is None or re.search(r'\baverage|\bmean\b|\bmedian\b', low):
        return None
    newname = m.group(1)
    cols = [x for x in mentioned_cols(instr, sheet) if x[2].lower() != newname.lower()]
    if len(cols) < 2:
        return None
    a, b = cols[0][1], cols[1][1]
    op = None
    mm = re.search(r'subtract\w*\s+(.+?)\s+from\s+(.+?)(?:[.,;]|$)', low)
    if mm:
        sub = [x for x in cols if x[2].lower() in mm.group(1)]
        frm = [x for x in cols if x[2].lower() in mm.group(2)]
        if sub and frm:
            a, b, op = frm[0][1], sub[0][1], '-'
    if op is None:
        for pat, o in [(r'minus|differen|subtract|less\b', '-'), (r'divid|ratio|\bper\b|rate|proportion|percentage of', '/'),
                       (r'multipl|product|times', '*'), (r'\bsum\b|\badd|plus|total', '+')]:
            if re.search(pat, low):
                op = o
                break
    if op is None:
        return None
    # target column: header cell named newname if it exists, else first empty column
    tgt = sheet["ncols"]
    for c, v in enumerate(sheet["rows"][0]):
        if isinstance(v, str) and v.strip().lower() == newname.lower():
            tgt = c
    last = max(last_data_row(sheet, a, 1), last_data_row(sheet, b, 1))
    terms = [x[1] for x in cols] if op == '+' and len(cols) > 2 else [a, b]
    body = r'''
sh.getCellByPosition(%d, 0).setString(%r)
terms = %r
for r in range(1, %d):
    f = '=' + %r.join('%%s%%d' %% (colname(c), r + 1) for c in terms)
    sh.getCellByPosition(%d, r).setFormula(f)
''' % (tgt, newname, terms, last + 1, op, tgt)
    return [("new_col_arith", uno(body))]


def h_rename_sheet(instr, data):
    low = instr.lower()
    if "rename" not in low or "sheet" not in low or "chart" in low:
        return None
    q = quoted(instr)
    names = [s["name"] for s in data.get("sheets", [])]
    m = re.search(r'rename\s+(?:the\s+)?(?:sheet\s+)?["“\']?([^"”\']+?)["”\']?\s+(?:sheet\s+)?(?:to|as|into)\s+["“\']?([^"”\']+?)["”\']?\s*(?:[.,;]|$)', instr, re.I)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
    elif len(q) >= 2:
        a, b = q[0], q[1]
    elif len(q) == 1 and len(names) == 1:
        a, b = names[0], q[0]
    else:
        return None
    if a not in names:
        cand = [n for n in names if n.lower() == a.lower().replace("sheet ", "sheet")]
        if not cand and len(names) == 1:
            cand = names
        if not cand:
            return None
        a = cand[0]
    return [("rename_sheet", uno("sheets.getByName(%r).setName(%r)\n" % (a, b)))]


def h_freeze(instr, data):
    """Freeze panes below/right of a range (A1:B2), or the first N rows/columns."""
    low = instr.lower()
    if "freeze" not in low:
        return None
    m = re.search(r'\b([A-Z]+)(\d+)\s*:\s*([A-Z]+)(\d+)\b', instr)
    col = row = 0
    if m:
        r1, c1 = a1(m.group(3) + m.group(4))
        col, row = c1 + 1, r1 + 1
    else:
        count = lambda g: int(g) if g and g.isdigit() else {"one": 1, "two": 2, "three": 3}.get(g, 1)
        rm = re.search(r'(?:first|top)\s+(\d+|one|two|three)?\s*rows?', low)
        cm = re.search(r'(?:first|left)\s+(\d+|one|two|three)?\s*colum', low)
        if rm:
            row = count(rm.group(1))
        if cm:
            col = count(cm.group(1))
        if not rm and not cm and "header" in low:
            row = 1
    if not row and not col:
        return None
    return [("freeze", uno("doc.getCurrentController().freezeAtPosition(%d, %d)\n" % (col, row)))]


# ---------------------------------------------------------------- generic fallbacks (g006c1)
# Tried only after every handler above declined (train routing unchanged).
def named_cols(instr, sheet):
    """Header columns named in quotes (exact header match), else mentioned bare: [(col, header)]."""
    hdr = {str(v).strip().lower(): c for c, v in enumerate(sheet["rows"][0])
           if isinstance(v, str) and v.strip()} if sheet["rows"] else {}
    out = [(hdr[x.strip().lower()], x.strip()) for x in quoted(instr) if x.strip().lower() in hdr]
    if not out:
        out = [(c, v) for _, c, v in mentioned_cols(instr, sheet)]
        # "column B" / "columns A and C"
        for m in re.finditer(r'\bcolumns?\s+([A-Z]{1,2})((?:\s*(?:,|and|&)\s*[A-Z]{1,2}\b)*)', instr):
            for L in re.findall(r'[A-Z]{1,2}', m.group(1) + m.group(2)):
                c = a1(L + "1")[1]
                if c < sheet["ncols"] and c not in [x[0] for x in out]:
                    out.append((c, L))
    seen, res = set(), []
    for c, v in out:
        if c not in seen:
            seen.add(c)
            res.append((c, v))
    return res


def _sheet_name_target(instr, default="Sheet2"):
    m = re.search(r'sheet\s+(?:named|called|titled)\s*["“\']([^"”\']+)["”\']', instr, re.I) or \
        re.search(r'["“\']([^"”\']+)["”\']\s+sheet', instr, re.I) or \
        re.search(r'(?:to|into|in)\s+(?:a\s+)?(?:new\s+)?sheet\s*["“\']([^"”\']+)["”\']', instr, re.I)
    return m.group(1) if m else default


def h_copy_to_sheet(instr, data):
    """Copy named columns (with header) to a new/named sheet, packed from column A."""
    low = instr.lower()
    if not re.search(r'\b(copy|move|extract|duplicate)\b', low) or 'sheet' not in low or 'column' not in low:
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    cols = named_cols(instr, sheet)
    if not cols:
        return None
    tgt = _sheet_name_target(instr)
    if tgt == sheet["name"]:
        return None
    move = bool(re.search(r'\bmove\b', low))
    body = r'''
cols = %r
tgt = %r
if not sheets.hasByName(tgt):
    sheets.insertNewByName(tgt, sheets.getCount())
T = sheets.getByName(tgt)
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
R = cur.getRangeAddress().EndRow
for i, c in enumerate(cols):
    src = sh.getCellRangeByPosition(c, 0, c, R)
    T.copyRange(T.getCellByPosition(i, 0).getCellAddress(), src.getRangeAddress())
if %r:
    for c in sorted(cols, reverse=True):
        sh.getColumns().removeByIndex(c, 1)
''' % ([c for c, _ in cols], tgt, move)
    return [("copy_to_sheet", uno(body))]


def h_reorder_cols(instr, data):
    """Reorder columns into the quoted header order (unnamed columns keep their relative order after)."""
    low = instr.lower()
    if not re.search(r'reorder|re-order|rearrange|order of (the )?columns|columns? (in|to be in) (the )?(following )?order', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    cols = [c for c, _ in named_cols(instr, sheet)]
    if len(cols) < 2:
        return None
    rest = [c for c in range(sheet["ncols"]) if c not in cols]
    order = cols + rest
    body = r'''
order = %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
ra = cur.getRangeAddress(); R, C = ra.EndRow, ra.EndColumn
rng = sh.getCellRangeByPosition(0, 0, C, R)
fa = rng.getFormulaArray()
new = tuple(tuple(row[c] if c < len(row) else '' for c in order) + tuple(row[len(order):]) for row in fa)
rng.setFormulaArray(new)
''' % order
    return [("reorder", uno(body))]


def h_number_format(instr, data):
    """Number format (decimal places / percent / currency / date) on the named columns' data cells."""
    low = instr.lower()
    m = re.search(r'(\d+|one|two|three|four|zero|no)\s+decimal', low)
    pct = bool(re.search(r'percent(age)?\s*(format|style|sign)?|as percentages?|%\s*format', low)) and \
        re.search(r'format|display|show|convert|change|make|turn', low)
    cur_ = bool(re.search(r'currency|dollar|\$\s*format|accounting', low)) and re.search(r'format|display|show|convert|change|make|turn', low)
    if not (m or pct or cur_):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    dec = 2
    if m:
        g = m.group(1)
        dec = int(g) if g.isdigit() else {"one": 1, "two": 2, "three": 3, "four": 4, "zero": 0, "no": 0}[g]
    frac = ("." + "0" * dec) if dec else ""
    code = ("0%s%%" % frac) if pct else ("[$$-409]#,##0%s" % frac if cur_ else "0%s" % frac)
    cols = [c for c, _ in named_cols(instr, sheet)]
    if not cols:
        # every mostly-numeric column
        num = lambda c: sum(isinstance(r[c], (int, float)) for r in sheet["rows"][1:] if c < len(r))
        cols = [c for c in range(sheet["ncols"]) if num(c) > 0.5 * max(1, len(sheet["rows"]) - 1)]
        if not cols or not re.search(r'all|every|each|whole|entire|numbers|values|data', low):
            return None
    body = r'''
from com.sun.star.lang import Locale
nf = doc.getNumberFormats(); loc = Locale()
code = %r
key = nf.queryKey(code, loc, False)
if key == -1: key = nf.addNew(code, loc)
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
R = cur.getRangeAddress().EndRow
for c in %r:
    sh.getCellRangeByPosition(c, 1, c, R).NumberFormat = key
print('format', code, key)
''' % (code, cols)
    return [("number_format", uno(body))]


def h_text_transform(instr, data):
    """Upper/lower/proper case or trim spaces of the named columns, in place."""
    low = instr.lower()
    op = None
    for pat, o in [(r'upper\s*-?case|all caps|capital letters', 'upper'), (r'lower\s*-?case', 'lower'),
                   (r'proper case|title case|capitali[sz]e (the )?(first|each)', 'title'),
                   (r'(leading|trailing|extra|redundant|unnecessary) (white)?spaces?|\btrim\b|whitespace', 'trim')]:
        if re.search(pat, low):
            op = o
            break
    sheet = active_sheet(data)
    if op is None or sheet is None or not sheet["rows"]:
        return None
    cols = [c for c, _ in named_cols(instr, sheet)]
    if not cols:
        if not re.search(r'all|every|each|whole|entire', low):
            return None
        cols = list(range(sheet["ncols"]))
    body = r'''
op = %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
R = cur.getRangeAddress().EndRow
for c in %r:
    for r in range(1, R + 1):
        cell = sh.getCellByPosition(c, r)
        if cell.getType().value != 'TEXT': continue
        s = cell.getString()
        t = {'upper': s.upper(), 'lower': s.lower(), 'title': s.title(), 'trim': ' '.join(s.split())}[op]
        if t != s: cell.setString(t)
''' % (op, cols)
    return [("text_" + op, uno(body))]


def h_merge(instr, data):
    """Merge a given range (optionally writing quoted text into it)."""
    low = instr.lower()
    m = re.search(r'\b([A-Z]+\d+)\s*:\s*([A-Z]+\d+)\b', instr)
    if 'merge' not in low or not m:
        return None
    r0, c0 = a1(m.group(1))
    r1, c1 = a1(m.group(2))
    q = [x for x in quoted(instr) if not re.fullmatch(r'[A-Z]+\d+(:[A-Z]+\d+)?', x)]
    txt = q[0] if q and re.search(r'write|text|header|title|enter|type|put|content', low) else None
    body = r'''
rng = sh.getCellRangeByPosition(%d, %d, %d, %d)
rng.merge(True)
txt = %r
if txt is not None:
    sh.getCellByPosition(%d, %d).setString(txt)
''' % (c0, r0, c1, r1, txt, c0, r0)
    return [("merge", uno(body))]


def h_delete_cols(instr, data):
    """Delete the named columns."""
    low = instr.lower()
    if not re.search(r'\b(delete|remove|drop)\b[^.]*\bcolumns?\b|\bcolumns?\b[^.]*\b(delete|remove)', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    cols = [c for c, _ in named_cols(instr, sheet)]
    if not cols:
        return None
    body = r'''
for c in %r:
    sh.getColumns().removeByIndex(c, 1)
''' % sorted(cols, reverse=True)
    return [("delete_cols", uno(body))]


def h_bold(instr, data):
    """Bold (and optionally centre) the header row or named columns."""
    low = instr.lower()
    if not re.search(r'\bbold\b', low):
        return None
    sheet = active_sheet(data)
    if sheet is None:
        return None
    if re.search(r'header|first row|top row|title row|column names', low):
        rng = (0, 0, max(0, sheet["ncols"] - 1), 0)
    else:
        cols = [c for c, _ in named_cols(instr, sheet)]
        if not cols:
            return None
        rng = (cols[0], 0, cols[-1], max(0, sheet["nrows"] - 1))
    body = r'''
from com.sun.star.awt.FontWeight import BOLD
rng = sh.getCellRangeByPosition(%d, %d, %d, %d)
rng.CharWeight = BOLD
''' % rng
    return [("bold", uno(body))]


AGG = [(r'\baverage|\bmean\b', 'AVERAGE', 'Average'), (r'\bsum\b|\btotal', 'SUM', 'Total'),
       (r'\bmax(imum)?\b|highest|largest', 'MAX', 'Max'), (r'\bmin(imum)?\b|lowest|smallest', 'MIN', 'Min'),
       (r'\bmedian\b', 'MEDIAN', 'Median'), (r'\bcount\b', 'COUNT', 'Count')]


def h_aggregate(instr, data):
    """Row-wise aggregate into a new/empty named column, or column-wise aggregate into a new row below."""
    low = instr.lower()
    f = next(((fn, lab) for pat, fn, lab in AGG if re.search(pat, low)), None)
    sheet = active_sheet(data)
    if f is None or sheet is None or not sheet["rows"] or len(sheet["rows"]) < 2:
        return None
    fn, lab = f
    rows = sheet["rows"]
    num = lambda c: sum(isinstance(r[c], (int, float)) and not isinstance(r[c], bool) for r in rows[1:] if c < len(r)) \
        > 0.5 * max(1, len(rows) - 1)
    numcols = [c for c in range(sheet["ncols"]) if num(c)]
    if not numcols:
        return None
    q = quoted(instr)
    hdr = {str(v).strip().lower(): c for c, v in enumerate(rows[0]) if isinstance(v, str) and v.strip()}
    if re.search(r'(new|a|the|last|bottom)\s+row|each column|every column|per column|below|bottom', low):
        label = next((x for x in q if x.strip().lower() not in hdr), lab)
        named = [c for c, _ in named_cols(instr, sheet) if c in numcols]
        cols = named or numcols
        last = max(sheet.get("lastrow") or [len(rows) - 1])
        body = r'''
R = %d
sh.getCellByPosition(0, R).setString(%r)
for c in %r:
    sh.getCellByPosition(c, R).setFormula('=%s(%%s2:%%s%%d)' %% (colname(c), colname(c), R))
''' % (last + 1, label, cols, fn)
        return [("agg_row", uno(body))]
    m = re.search(r'(?:new\s+)?column\s+(?:named|called|titled|with (?:the )?(?:header|title|name))\s+["“\']([^"”\']+)["”\']', instr, re.I) \
        or re.search(r'["“\']([^"”\']+)["”\']\s+(?:new\s+)?column', instr, re.I) \
        or re.search(r'(?:in|into|to)\s+(?:the\s+)?(?:column\s+)?["“\']([^"”\']+)["”\']', instr, re.I)
    if not m or not re.search(r'each (row|person|student|employee|item|product|record|line)|every row|per row|row-?wise|for each', low):
        return None
    name = m.group(1).strip()
    tgt = hdr.get(name.lower(), sheet["ncols"])
    named = [c for c, _ in named_cols(instr, sheet) if c in numcols and c != tgt]
    cols = named or [c for c in numcols if c != tgt]
    if not cols:
        return None
    last = max(last_data_row(sheet, c, 1) for c in cols)
    contiguous = cols == list(range(cols[0], cols[-1] + 1))
    body = r'''
tc = %d
sh.getCellByPosition(tc, 0).setString(%r)
cols = %r
for r in range(1, %d):
    if all(sh.getCellByPosition(c, r).getType().value == 'EMPTY' for c in cols): continue
    if %r:
        arg = '%%s%%d:%%s%%d' %% (colname(cols[0]), r + 1, colname(cols[-1]), r + 1)
    else:
        arg = ';'.join('%%s%%d' %% (colname(c), r + 1) for c in cols)
    sh.getCellByPosition(tc, r).setFormula('=%s(' + arg + ')')
''' % (tgt, name, cols, last + 1, contiguous, fn)
    return [("agg_col", uno(body))]


def _targets(instr, sheet, exclude):
    """Quoted names that are not the source headers -> (col, name): existing header col or new cols."""
    hdr = {str(v).strip().lower(): c for c, v in enumerate(sheet["rows"][0]) if isinstance(v, str) and v.strip()}
    out, nxt = [], sheet["ncols"]
    for x in quoted(instr):
        k = x.strip().lower()
        if k in hdr and hdr[k] in exclude:
            continue
        if len(x) <= 2 and not x.strip().isalnum():
            continue     # a delimiter like " " or ","
        if k in hdr:
            out.append((hdr[k], x.strip()))
        else:
            out.append((nxt, x.strip()))
            nxt += 1
    return out


def _delim(instr):
    low = instr.lower()
    for pat, d in [(r'comma', ','), (r'semicolon', ';'), (r'hyphen|dash', '-'), (r'underscore', '_'), (r'slash', '/')]:
        if re.search(pat, low):
            return d
    for x in re.findall(r'["“\']([^"”\'\w]{1,2})["”\']', instr):
        return x
    return ' '


def h_split(instr, data):
    """Split a named column into the quoted target columns (space or named delimiter)."""
    low = instr.lower()
    if not re.search(r'\bsplit|separate\b', low) or re.search(r'concatenat|combine|join', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    src = [c for c, _ in named_cols(instr, sheet)
           if any(isinstance(r[c], str) and r[c].strip() for r in sheet["rows"][1:] if c < len(r))]
    if not src:
        return None
    s = src[0]
    tg = [t for t in _targets(instr, sheet, {s}) if t[0] != s]
    if len(tg) < 2:
        return None
    d = _delim(instr)
    body = r'''
s, tg, d = %d, %r, %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
R = cur.getRangeAddress().EndRow
for c, n in tg:
    sh.getCellByPosition(c, 0).setString(n)
for r in range(1, R + 1):
    v = sh.getCellByPosition(s, r).getString().strip()
    if not v: continue
    parts = v.split(d) if d != ' ' else v.split()
    parts = [p.strip() for p in parts]
    if len(parts) > len(tg):
        parts = parts[:len(tg) - 1] + [(d if d != ' ' else ' ').join(parts[len(tg) - 1:])]
    for (c, n), p in zip(tg, parts):
        sh.getCellByPosition(c, r).setString(p)
''' % (s, tg, d)
    return [("split", uno(body))]


def h_concat(instr, data):
    """Concatenate named columns into a quoted target column (space or named delimiter)."""
    low = instr.lower()
    if not re.search(r'concatenat|combine|merge|join', low) or not re.search(r'column', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    srcs = [c for c, _ in named_cols(instr, sheet)
            if any(not _empty(r[c]) for r in sheet["rows"][1:] if c < len(r))]
    if len(srcs) < 2:
        return None
    tg = [t for t in _targets(instr, sheet, set(srcs)) if t[0] not in srcs]
    if not tg:
        return None
    d = _delim(instr) if re.search(r'space|comma|semicolon|hyphen|dash|underscore|slash|separat|delimit|["“\'][^"”\'\w]{1,2}["”\']', low) else ''
    body = r'''
srcs, (tc, tn), d = %r, %r, %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
R = cur.getRangeAddress().EndRow
sh.getCellByPosition(tc, 0).setString(tn)
for r in range(1, R + 1):
    vals = [sh.getCellByPosition(c, r).getString() for c in srcs]
    if not any(v.strip() for v in vals): continue
    sh.getCellByPosition(tc, r).setString(d.join(vals))
''' % (srcs, tg[0], d)
    return [("concat", uno(body))]


def h_dedup(instr, data):
    """Delete rows that repeat an earlier row (on the named columns, else on the whole row)."""
    low = instr.lower()
    if not re.search(r'duplicat', low) or not re.search(r'remove|delete|drop|eliminat|get rid|clean|unique', low) \
            or re.search(r'chart|pivot|highlight|colou?r|count', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    keys = [c for c, _ in named_cols(instr, sheet)]
    body = r'''
keys = %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
ra = cur.getRangeAddress(); R, C = ra.EndRow, ra.EndColumn
cols = keys or list(range(C + 1))
seen, dup = set(), []
for r in range(1, R + 1):
    k = tuple(sh.getCellByPosition(c, r).getString().strip() for c in cols)
    if not any(k): continue
    if k in seen: dup.append(r)
    else: seen.add(k)
print('dup rows', dup)
for r in reversed(dup):
    sh.getRows().removeByIndex(r, 1)
''' % keys
    return [("dedup", uno(body))]


def h_sequence(instr, data):
    """Fill a named (empty) column with 1..N, or with a quoted pattern like 'No. #'."""
    low = instr.lower()
    if not re.search(r'sequen|serial|\bnumber(ing)? (the|each|all)|\bauto-?number|incremental|consecutive|1, 2, 3', low):
        return None
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    cols = named_cols(instr, sheet)
    tgt = [c for c, _ in cols if all(_empty(r[c]) for r in sheet["rows"][1:] if c < len(r))]
    if not tgt:
        return None
    pat = next((x for x in quoted(instr) if '#' in x or re.search(r'\d', x) and not find_col(sheet, x)), None)
    prefix = suffix = ""
    start = 1
    if pat:
        m = re.search(r'#|\d+', pat)
        prefix, suffix = pat[:m.start()], pat[m.end():]
        if m.group(0) != '#':
            start = int(m.group(0))
    last = max(max(sheet.get("lastrow") or [0]), max(last_data_row(sheet, c, 1) for c in range(sheet["ncols"])))
    body = r'''
tc, pre, suf, start, last = %d, %r, %r, %d, %d
for i, r in enumerate(range(1, last + 1)):
    if all(sh.getCellByPosition(c, r).getType().value == 'EMPTY' for c in range(%d) if c != tc): continue
    if pre or suf: sh.getCellByPosition(tc, r).setString('%%s%%d%%s' %% (pre, start + i, suf))
    else: sh.getCellByPosition(tc, r).setValue(start + i)
''' % (tgt[0], prefix, suffix, start, last, sheet["ncols"])
    return [("sequence", uno(body))]


def h_layout(instr, data):
    """Autofit column widths / centre (left, right) alignment of the header or named columns."""
    low = instr.lower()
    sheet = active_sheet(data)
    if sheet is None or not sheet["rows"]:
        return None
    C = max(0, sheet["ncols"] - 1)
    if re.search(r'auto-?fit|optimal (column )?width|fit (the )?(column|content)|adjust (the )?column width', low):
        return [("autofit", uno("for c in range(%d):\n    sh.getColumns().getByIndex(c).OptimalWidth = True\n" % (C + 1)))]
    m = re.search(r'\b(cent(er|re)|left|right)[- ]?(align|justif)|align\w*\s+(?:\w+\s+){0,6}?(?:to (?:the )?)?(cent(?:er|re)|left|right)\b', low)
    if m:
        side = (m.group(1) or m.group(5) or 'center')
        val = 'CENTER' if side.startswith('cent') else side.upper()
        if re.search(r'header|first row|top row|title', low):
            rng = (0, 0, C, 0)
        else:
            cols = [c for c, _ in named_cols(instr, sheet)]
            rng = (cols[0], 0, cols[-1], max(0, sheet["nrows"] - 1)) if cols else (0, 0, C, max(0, sheet["nrows"] - 1))
        body = r'''
from com.sun.star.table.CellHoriJustify import %s as J
sh.getCellRangeByPosition(%d, %d, %d, %d).HoriJustify = J
''' % ((val,) + rng)
        return [("align", uno(body))]
    return None


COLORS = {"red": 0xFF0000, "green": 0x00FF00, "blue": 0x0000FF, "yellow": 0xFFFF00, "orange": 0xFFA500,
          "purple": 0x800080, "pink": 0xFFC0CB, "gray": 0x808080, "grey": 0x808080, "black": 0x000000}


def h_highlight(instr, data):
    """Colour (font or background) the cells of a named column that are max/min, >/< N, or equal a quoted value."""
    low = instr.lower()
    if not re.search(r'highlight|colou?r|mark|fill', low):
        return None
    m = re.search(r'#([0-9a-f]{6})\b', low)
    color = int(m.group(1), 16) if m else next((v for k, v in COLORS.items() if re.search(r'\b%s\b' % k, low)), None)
    sheet = active_sheet(data)
    if color is None or sheet is None or not sheet["rows"]:
        return None
    cond = None
    mm = re.search(r'(greater|more|higher|larger|above|over|exceed\w*|less|lower|smaller|below|under)\s+(?:than\s+)?(?:or equal to\s+)?\$?(-?\d+(?:\.\d+)?)', low)
    if mm:
        cond = ('gt' if re.match(r'greater|more|higher|larger|above|over|exceed', mm.group(1)) else 'lt', float(mm.group(2)))
    elif re.search(r'highest|largest|maximum|\bmax\b|biggest|top value', low):
        cond = ('max', 0)
    elif re.search(r'lowest|smallest|minimum|\bmin\b', low):
        cond = ('min', 0)
    cols = [c for c, _ in named_cols(instr, sheet)]
    hdrs = {str(v).strip().lower() for v in sheet["rows"][0] if isinstance(v, str)}
    if cond is None:
        vals = [x for x in quoted(instr) if x.strip().lower() not in hdrs and not x.startswith('#')]
        if not vals:
            return None
        cond = ('eq', vals[0])
    if not cols:
        return None
    font = bool(re.search(r'\bfont|\btext colou?r', low))
    body = r'''
cols, cond, color, font = %r, %r, %d, %r
cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
R = cur.getRangeAddress().EndRow
for c in cols:
    cells = [sh.getCellByPosition(c, r) for r in range(1, R + 1)]
    nums = [x.getValue() for x in cells if x.getType().value in ('VALUE', 'FORMULA') and x.getString().strip()]
    for x in cells:
        t = x.getType().value
        isn = t in ('VALUE', 'FORMULA') and x.getString().strip() != ''
        v = x.getValue()
        k, a = cond
        hit = (k == 'gt' and isn and v > a) or (k == 'lt' and isn and v < a) or \
              (k == 'max' and isn and nums and v == max(nums)) or (k == 'min' and isn and nums and v == min(nums)) or \
              (k == 'eq' and x.getString().strip().lower() == str(a).strip().lower())
        if hit:
            if font: x.CharColor = color
            else: x.CellBackColor = color
''' % (cols, cond, color, font)
    return [("highlight", uno(body))]


HANDLERS = [h_validation, h_pivot, h_fill_blank, h_pad_zeros, h_export, h_totals, h_sort, h_dedup, h_hide_rows, h_chart,
            h_lookup, h_formula_expr, h_new_column_arith, h_rename_sheet, h_freeze,
            h_copy_to_sheet, h_reorder_cols, h_split, h_concat, h_number_format, h_text_transform, h_merge,
            h_delete_cols, h_bold, h_aggregate, h_sequence, h_layout, h_highlight]


def clean(instr):
    """Drop boilerplate sentences ("don't touch irrelevant regions, even if they are blank")."""
    keep = [p for p in re.split(r'(?<=[.!?])\s+', instr) if not re.search(r'irrelevant|untouched', p, re.I)]
    return " ".join(keep) if keep else instr


def plan(instr, data):
    instr = clean(instr)
    DOC_URL[0] = data.get("url") or (data.get("files") or [""])[0] or ""
    for h in HANDLERS:
        try:
            acts = h(instr, data)
        except Exception as e:
            print("LOG handler error", h.__name__, e, flush=True)
            acts = None
        if acts:
            return acts
    return []
