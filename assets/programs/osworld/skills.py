"""Instruction-pattern skills: each takes the instruction and returns VM-side code, or None if it does not apply.

Calc skills run after unohelper.py (get_doc, save, export, used_range, find_header, col_idx, col_name and the
CellContentType constants EMPTY/VALUE/TEXT/FORMULA). Most start with SHEET, which binds doc, path and the
active sheet `sh`. OS skills start with OS_HELPER, whose `sh(cmd)` runs a shell command.
The order of CALC_SKILLS / OS_SKILLS matters: the first skill that returns code wins.
"""
import re

WORDNUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7,
           'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12}
CELL_RANGE = re.compile(r'\b([A-Z]{1,3})(\d+)\s*:\s*([A-Z]{1,3})(\d+)\b')
EXPORT_VERB = re.compile(r'\b(export|save|convert)\b')

SHEET = '''
doc, path = get_doc()
sh = doc.getCurrentController().getActiveSheet()
ec, er = used_range(sh)
'''


def _num(tok):
    tok = tok.lower()
    return int(tok) if tok.isdigit() else WORDNUM.get(tok)


def _quoted(ins, q='"\'“”'):
    """Strings quoted with any of the characters in q."""
    return re.findall('[{0}]([^{0}]+)[{0}]'.format(q), ins)


def _col_number(letters):
    """1-based column number of column letters (A -> 1)."""
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


# ---------------------------------------------------------------- Calc


def fill_blank_above(ins):
    il = ins.lower()
    if not re.search(r'(blank|empty)\s+cells?', il) or not re.search(r'above|previous|preceding', il):
        return None
    m = CELL_RANGE.search(ins)
    rng = m and (m.group(1), int(m.group(2)), m.group(3), int(m.group(4)))
    return SHEET + '''
rng = %r
if rng:
    c0, r0, c1, r1 = col_idx(rng[0]), rng[1] - 1, col_idx(rng[2]), rng[3] - 1
else:
    c0, r0, c1, r1 = 0, 0, ec, er
n = 0
for c in range(c0, c1 + 1):
    last = None
    for r in range(0, r1 + 1):
        cell = sh.getCellByPosition(c, r)
        t = cell.getType()
        if t == EMPTY or (t == TEXT and cell.getString().strip() == ''):
            if r >= r0 and last is not None:
                if last[0] == 'v': cell.setValue(last[1])
                else: cell.setString(last[1])
                n += 1
        elif t == TEXT or (t == FORMULA and cell.getValue() == 0 and cell.getString() != '0'):
            last = ('s', cell.getString())
        else:
            last = ('v', cell.getValue())
print('filled', n)
save(doc, path)
''' % (rng,)


def export_csv(ins):
    il = ins.lower()
    if not EXPORT_VERB.search(il) or 'csv' not in il:
        return None
    return '''
doc, path = get_doc()
export(doc, os.path.splitext(path)[0] + '.csv', 'Text - txt - csv (StarCalc)', CSV_OPTS)
'''


def export_pdf(ins):
    il = ins.lower()
    if 'pdf' not in il or not EXPORT_VERB.search(il):
        return None
    onepage = bool(re.search(r'one page|single page|1 page', il))
    home = bool(re.search(r'home dir|home folder|/home/user', il))
    return '''
doc, path = get_doc()
if %r:
    styles = doc.getStyleFamilies().getByName('PageStyles')
    for i in range(doc.getSheets().getCount()):
        ps = styles.getByName(doc.getSheets().getByIndex(i).PageStyle)
        ps.ScaleToPagesX = 1
        ps.ScaleToPagesY = 1
    save(doc, path)
base = os.path.splitext(os.path.basename(path))[0] + '.pdf'
export(doc, os.path.join(os.path.expanduser('~') if %r else os.path.dirname(path), base), 'calc_pdf_Export')
''' % (onepage, home)


def pad_zeros(ins):
    il = ins.lower()
    if 'pad' not in il or 'zero' not in il:
        return None
    m = re.search(r'(\w+)[\s-]+digits?', il)
    n = _num(m.group(1)) if m else None
    names = _quoted(ins)
    if not n or len(names) < 2:
        return None
    return SHEET + '''
src = find_header(sh, %r); dst = find_header(sh, %r)
print('hdr', src, dst)
for r in range(src[1] + 1, er + 1):
    cell = sh.getCellByPosition(src[0], r)
    if cell.getType() == EMPTY: continue
    s = cell.getString().strip()
    v = cell.getValue()
    if v == int(v) and s.replace('.', '').isdigit():
        s = str(int(v))
    sh.getCellByPosition(dst[0], r).setString(s.zfill(%d))
save(doc, path)
''' % (names[0], names[1], n)


def hide_rows_value(ins):
    if 'hide' not in ins.lower():
        return None
    names = _quoted(ins)
    if not names:
        return None
    val = names[0].lstrip('#').lower()
    return SHEET + '''
val = %r
rows = sh.getRows(); n = 0
for r in range(er + 1):
    for c in range(ec + 1):
        x = sh.getCellByPosition(c, r)
        if (x.getString().strip().lstrip('#').lower() == val
                or (x.getType() == FORMULA and x.getError() != 0 and 'n/a' in val)):
            rows.getByIndex(r).IsVisible = False; n += 1
            break
print('hidden', n)
save(doc, path)
''' % val


def rename_sheet(ins):
    m = re.search(r"rename\s+(?:the\s+)?(?:sheet\s+)?[\"']?([^\"']+?)[\"']?\s+(?:sheet\s+)?(?:to|as|into)\s+[\"']([^\"']+)[\"']", ins, re.I)
    if not m:
        return None
    return '''
doc, path = get_doc()
sheets = doc.getSheets()
names = list(sheets.getElementNames())
old = %r.lower()
cand = ([n for n in names if n.lower() == old] or [n for n in names if old in n.lower()]
        or [doc.getCurrentController().getActiveSheet().getName()])
sheets.getByName(cand[0]).setName(%r)
save(doc, path)
''' % (m.group(1).strip(), m.group(2))


def freeze_panes(ins):
    il = ins.lower()
    if 'freeze' not in il:
        return None
    rows = cols = 0
    m = CELL_RANGE.search(ins)
    if m:
        # freeze everything above/left of the cell after the range end
        cols, rows = _col_number(m.group(3)), int(m.group(4))
    else:
        mr = re.search(r'(?:first|top)\s+(\w+)?\s*rows?', il)
        mc = re.search(r'(?:first|left(?:most)?)\s+(\w+)?\s*columns?', il)
        if mr:
            rows = _num(mr.group(1) or 'one') or 1
        if mc:
            cols = _num(mc.group(1) or 'one') or 1
        if not rows and not cols:
            rows = int('header' in il or 'row' in il)
            cols = int('column' in il)
    if not rows and not cols:
        return None
    return '''
doc, path = get_doc()
doc.getCurrentController().freezeAtPosition(%d, %d)
save(doc, path)
''' % (cols, rows)


def data_validation_list(ins):
    il = ins.lower()
    if ('validation' not in il and 'drop' not in il) or not re.search(r'drop[\s-]*down|list', il):
        return None
    quoted = _quoted(ins, '"“”')
    if len(quoted) < 2:
        return None
    return SHEET + '''
h = find_header(sh, %r)
print('hdr', h)
from com.sun.star.sheet.ValidationType import LIST
rg = sh.getCellRangeByPosition(h[0], h[1] + 1, h[0], max(er, h[1] + 1))
v = rg.Validation
v.Type = LIST
v.Formula1 = ';'.join('"%%s"' %% o for o in %r)
v.ShowList = 1
v.IgnoreBlankCells = True
rg.Validation = v
save(doc, path)
''' % (quoted[0], quoted[1:])


def fill_totals(ins):
    """Fill empty cells of a 'Total' row (column sums) and/or 'Total' column (row sums) with SUM formulas."""
    il = ins.lower()
    if 'total' not in il or not re.search(r'\b(fill|missing|calculate|compute|sum)', il):
        return None
    if re.search(r'pivot|chart|revenue for each|hour', il):
        return None
    new_row = bool(re.search(r'(underneath|below|bottom|new)\s+row', il))
    return SHEET + '''
def isnum(c, r):
    x = sh.getCellByPosition(c, r)
    if x.getType() == VALUE: return True
    if x.getType() == FORMULA:
        try: float(x.getString().replace(',', '')); return True
        except Exception: return False
    return False
def empty(c, r):
    return sh.getCellByPosition(c, r).getType() == EMPTY
def istot(c, r):
    return sh.getCellByPosition(c, r).getString().strip().lower() in ('total', 'totals', 'sum', 'grand total')
hr = 0  # header row: first of the top rows with >= 2 filled cells
for r in range(min(6, er + 1)):
    if sum(1 for c in range(ec + 1) if not empty(c, r)) >= 2:
        hr = r; break
trow = next(((c, r) for r in range(hr + 1, er + 1) for c in range(min(3, ec + 1)) if istot(c, r)), None)
if trow is None and %r:
    trow = (0, er + 1); sh.getCellByPosition(0, er + 1).setString('Total')
tcol = next((c for c in range(ec + 1) if istot(c, hr)), None)
n = 0
lastr = (trow[1] - 1) if trow else er
if tcol is not None:
    for r in range(hr + 1, lastr + 1):
        if not empty(tcol, r): continue
        cs = [c for c in range(tcol) if isnum(c, r)]
        if not cs: continue
        sh.getCellByPosition(tcol, r).setFormula('=SUM(%%s%%d:%%s%%d)' %% (col_name(cs[0]), r + 1, col_name(tcol - 1), r + 1)); n += 1
if trow is not None:
    for c in range(trow[0] + 1, ec + 1):
        if not empty(c, trow[1]): continue
        if not any(isnum(c, r) for r in range(hr + 1, trow[1])): continue
        sh.getCellByPosition(c, trow[1]).setFormula('=SUM(%%s%%d:%%s%%d)' %% (col_name(c), hr + 2, col_name(c), trow[1])); n += 1
print('totals filled', n, 'trow', trow, 'tcol', tcol)
save(doc, path)
''' % new_row


def sort_table(ins):
    il = ins.lower()
    if not re.search(r'\bsort\b', il) or re.search(r'chart|pivot|filter', il):
        return None
    names = _quoted(ins)
    if not names:
        m = re.search(r'by (?:the )?(\w[\w ]*?) column', ins, re.I) or re.search(r'by (?:the |their )?(\w+)', ins, re.I)
        if not m:
            return None
        names = [m.group(1)]
    desc = bool(re.search(r'descend|largest to smallest|highest to lowest|z to a|decreas', il))
    return SHEET + '''
h = find_header(sh, %r)
print('hdr', h)
from com.sun.star.table import TableSortField
rg = sh.getCellRangeByPosition(0, h[1], ec, er)
f = TableSortField(); f.Field = h[0]; f.IsAscending = %r; f.IsCaseSensitive = False
desc = rg.createSortDescriptor()
for p in desc:
    if p.Name == 'SortFields': p.Value = uno.Any('[]com.sun.star.table.TableSortField', (f,))
    if p.Name == 'ContainsHeader': p.Value = True
uno.invoke(rg, 'sort', (tuple(desc),))
save(doc, path)
''' % (names[0], not desc)


def lookup_fill(ins):
    """Fill an empty column from a lookup table elsewhere on the sheet (exact match, or numeric range lookup)."""
    il = ins.lower()
    if not re.search(r'lookup|look up|scale table|according to (the )?(\w+ )?table|table shown', il):
        return None
    return SHEET + '''
G = [[sh.getCellByPosition(c, r) for c in range(ec + 1)] for r in range(er + 1)]
S = [[x.getString().strip() for x in row] for row in G]
E = [[x.getType() == EMPTY for x in row] for row in G]
# target column: header cell with the longest run (>= 2) of empty cells below while neighbours have data
best = None
for r in range(er):
    for c in range(ec + 1):
        if E[r][c] or not S[r][c]: continue
        n = 0; rr = r + 1
        while rr <= er and E[rr][c] and any(not E[rr][k] for k in range(max(0, c - 3), min(ec, c + 3) + 1) if k != c):
            n += 1; rr += 1
        if n >= 2 and (best is None or n > best[2]):
            best = (c, r, n)
print('target', best)
tc, tr, tn = best
trows = list(range(tr + 1, tr + 1 + tn))
# target block: contiguous filled header cells around the target header
blk = {tc}
c = tc - 1
while c >= 0 and not E[tr][c]: blk.add(c); c -= 1
c = tc + 1
while c <= ec and not E[tr][c]: blk.add(c); c += 1
tcols = sorted(blk - {tc})
print('target block', sorted(blk))
def rows_below(c, r):
    out = []; rr = r + 1
    while rr <= er and not E[rr][c]:
        out.append(rr); rr += 1
    return out
def in_target(c, r):
    return c in blk and (r == tr or r in trows)
# lookup table: key column kc (matched against query column qc of the target block), value column vc
bestm = None
for r in range(er + 1):
    for kc in range(ec + 1):
        if E[r][kc] or in_target(kc, r): continue
        kr = rows_below(kc, r)
        if len(kr) < 2: continue
        keys = {S[x][kc].lower() for x in kr}
        ckeys = {S[x][kc] for x in kr}
        for qc in tcols:
            hit = sum(1 for x in trows if S[x][qc] in ckeys) + 0.3 * sum(1 for x in trows if S[x][qc].lower() in keys)
            approx = False
            if all(G[x][kc].getType() == VALUE for x in kr) and all(G[x][qc].getType() == VALUE for x in trows):
                if 0.8 * len(trows) > hit:
                    approx = True; hit = 0.8 * len(trows)
            if hit == 0: continue
            for vc in range(ec + 1):
                if vc == kc or E[r][vc] and E[kr[0]][vc]: continue
                if any(E[x][vc] for x in kr) or in_target(vc, r): continue
                hv, ht = S[r][vc].lower(), S[tr][tc].lower()
                score = hit * 10 + (5 if hv and (hv in ht or ht in hv) else 0) - abs(vc - kc)
                if bestm is None or score > bestm[0]:
                    bestm = (score, r, kc, vc, qc, kr, approx)
print('lookup', bestm and bestm[:5], bestm and bestm[6])
score, lr, kc, vc, qc, kr, approx = bestm
table = {S[x][kc].lower(): G[x][vc] for x in kr}
steps = sorted((G[x][kc].getValue(), G[x][vc]) for x in kr) if approx else []
n = 0
for x in trows:
    if approx:
        v = G[x][qc].getValue(); src = None
        for k, cell in steps:
            if k <= v: src = cell
    else:
        src = table.get(S[x][qc].lower())
    if src is None: continue
    dst = sh.getCellByPosition(tc, x)
    if src.getType() == VALUE: dst.setValue(src.getValue())
    else: dst.setString(src.getString())
    n += 1
print('filled', n)
save(doc, path)
'''


def age_from_birthday(ins):
    il = ins.lower()
    if 'age' not in il or 'birth' not in il:
        return None
    m = re.search(r'(/[\w./-]+\.\w+)', ins)
    reffile = m.group(1).rstrip('.') if m else None
    return SHEET + '''
import datetime
reff = %r
ref = datetime.date.today()
if reff and os.path.exists(reff):
    txt = open(reff).read(); print('ref text', txt[:200])
    mm = re.search(r'(\\d{4})-(\\d{1,2})-(\\d{1,2})', txt)
    if mm:
        ref = datetime.date(int(mm.group(1)), int(mm.group(2)), int(mm.group(3)))
    else:
        mm = re.search(r'(\\d{1,2})/(\\d{1,2})/(\\d{4})', txt)
        if mm: ref = datetime.date(int(mm.group(3)), int(mm.group(1)), int(mm.group(2)))
print('ref', ref)
bh = None; ah = None
for r in range(min(6, er + 1)):
    for c in range(ec + 1):
        t = sh.getCellByPosition(c, r).getString().strip().lower()
        if 'birth' in t and bh is None: bh = (c, r)
        if t.startswith('age'): ah = (c, r)
print('hdr', bh, ah)
if ah is None:
    ah = (ec + 1, bh[1]); sh.getCellByPosition(ec + 1, bh[1]).setString('Age')
base = datetime.date(1899, 12, 30)
n = 0
for r in range(bh[1] + 1, er + 1):
    cell = sh.getCellByPosition(bh[0], r)
    if cell.getType() == EMPTY: continue
    d = None
    if cell.getType() == VALUE:
        d = base + datetime.timedelta(days=int(cell.getValue()))
    else:
        s = cell.getString().strip()
        for fmt in ('%%Y-%%m-%%d', '%%m/%%d/%%Y', '%%d/%%m/%%Y', '%%Y/%%m/%%d', '%%d.%%m.%%Y', '%%B %%d, %%Y', '%%d %%B %%Y'):
            try: d = datetime.datetime.strptime(s, fmt).date(); break
            except Exception: pass
    if d is None: continue
    age = ref.year - d.year - ((ref.month, ref.day) < (d.month, d.day))
    sh.getCellByPosition(ah[0], r).setValue(age); n += 1
print('ages', n)
save(doc, path)
''' % reffile


# ---------------------------------------------------------------- OS

OS_HELPER = r'''
import subprocess, os, shlex
os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/run/user/%d/bus' % os.getuid())
def sh(cmd, sudo=False):
    if sudo:
        cmd = "echo password | sudo -S bash -c %s" % shlex.quote(cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=90)
    print('$', cmd[:200]); print(r.stdout[-3000:]); print(r.stderr[-1000:])
    return r
def resolve(name):
    """Find a file/dir by name: as given, under home or ~/Desktop, then by `find` under home, then /."""
    home = os.path.expanduser('~')
    for c in (name, os.path.join(home, name), os.path.join(home, 'Desktop', name)):
        if os.path.exists(c):
            return os.path.abspath(c)
    for root, depth, extra in ((home, '4', []), ('/', '5', ['-xdev'])):
        out = subprocess.run(['find', root] + extra + ['-maxdepth', depth, '-name', name],
                             capture_output=True, text=True).stdout
        hits = [h for h in out.splitlines() if h and '/proc/' not in h]
        if hits:
            return sorted(hits, key=len)[0]
    return None
'''


def os_text_size(ins):
    il = ins.lower()
    if not re.search(r'(enlarge|bigger|larger|increase|zoom|magnif)', il):
        return None
    if not re.search(r'\btext|font|screen', il) or 'calc' in il or 'cell' in il:
        return None
    return OS_HELPER + '''
sh("gsettings set org.gnome.desktop.interface text-scaling-factor 1.25")
sh("gsettings get org.gnome.desktop.interface text-scaling-factor")
'''


def os_copy_hierarchy(ins):
    il = ins.lower()
    if not re.search(r'cop(y|ies)\s+(the\s+)?(directory|folder)\s+(hierarchy|structure|tree)', il):
        return None
    q = _quoted(ins)
    if len(q) < 2:
        m = re.search(r'from\s+(\S+)\s+to\s+(\S+)', ins)
        if not m:
            return None
        q = [m.group(1), m.group(2).rstrip('.')]
    src, dst = q[0], q[1]
    if src.startswith(('$', '<')) or dst.startswith('$'):
        return None  # unresolved placeholders -> infeasible, let policy FAIL
    return OS_HELPER + '''
src = resolve(%r)
dst = resolve(%r) or os.path.join(os.path.dirname(src) if src else os.getcwd(), %r)
print('src', src, 'dst', dst)
os.makedirs(dst, exist_ok=True)
for root, dirs, files in os.walk(src):
    os.makedirs(os.path.join(dst, os.path.relpath(root, src)), exist_ok=True)
sh('find %%s -type d | head -50' %% shlex.quote(dst))
''' % (src, dst, dst)


def os_dnd(ins):
    il = ins.lower()
    if not re.search(r'do not disturb|do-not-disturb|dnd|(turn off|disable|stop|mute|silence).{0,20}notification', il):
        return None
    on = not re.search(r'(turn off|disable|exit|leave)\s+(the\s+)?.?do not disturb', il)
    return OS_HELPER + '''
sh("gsettings set org.gnome.desktop.notifications show-banners %s")
sh("gsettings get org.gnome.desktop.notifications show-banners")
''' % ('false' if on else 'true')


def os_count_lines_terminal(ins):
    il = ins.lower()
    if 'terminal' not in il or 'count' not in il or 'line' not in il:
        return None
    m = re.search(r'\b(\w+)\s+files', il)
    ext = m.group(1) if m else None
    if not ext or ext in ('all', 'the', 'these', 'text'):
        mm = re.search(r'\*?\.(\w+)', ins)
        ext = mm.group(1) if mm else None
    if not ext:
        return None
    cmd = 'find . -type f -name "*.%s" -exec cat {} + | wc -l' % ext
    return '''
import pyautogui, time, subprocess
out = subprocess.run(['wmctrl', '-l'], capture_output=True, text=True).stdout
print(out)
term = [line for line in out.splitlines() if 'Terminal' in line or 'user@' in line]
if term:
    subprocess.run(['wmctrl', '-i', '-a', term[0].split()[0]]); time.sleep(1)
else:
    pyautogui.hotkey('ctrl', 'alt', 't'); time.sleep(3)
pyautogui.write(%r, interval=0.02)
pyautogui.press('enter')
''' % cmd


def os_create_user(ins):
    il = ins.lower()
    if 'user' not in il or not re.search(r'\b(create|add|make)\b', il):
        return None
    m = re.search(r'user(?:\s+named|\s+called|name)?\s+["\']([^"\']+)["\']', ins, re.I)
    if not m:
        return None
    p = re.search(r'password\s+["\']([^"\']+)["\']', ins, re.I)
    f = re.search(r'(?:only|restrict\w*).{0,40}?(?:folder|directory)\s+["\']?(/[^"\'\s]+)', ins, re.I)
    return OS_HELPER + '''
user, pw, folder = %r, %r, %r
q = shlex.quote
if folder:  # chroot sftp-only user confined to folder
    sh('mkdir -p %%s' %% q(folder), sudo=True)
    sh('useradd -M -d %%s -s /bin/bash %%s' %% (q(folder), q(user)), sudo=True)
else:
    sh('useradd -m -s /bin/bash %%s' %% q(user), sudo=True)
if pw:
    sh('echo %%s | chpasswd' %% q(user + ':' + pw), sudo=True)
if folder:
    sh('chown root:root %%s; chmod 755 %%s' %% (q(folder), q(folder)), sudo=True)
    block = '\\nMatch User %%s\\n    ChrootDirectory %%s\\n    ForceCommand internal-sftp\\n    AllowTcpForwarding no\\n    X11Forwarding no\\n' %% (user, folder)
    sh('printf %%s %%s >> /etc/ssh/sshd_config' %% ('%%s', q(block)), sudo=True)
    sh('systemctl restart ssh || systemctl restart sshd || service ssh restart', sudo=True)
sh('id %%s' %% q(user))
''' % (m.group(1), p and p.group(1), f and f.group(1).rstrip('.'))


OS_SKILLS = [os_text_size, os_copy_hierarchy, os_dnd, os_count_lines_terminal, os_create_user]
CALC_SKILLS = [data_validation_list, fill_blank_above, pad_zeros, export_pdf, export_csv, hide_rows_value,
               rename_sheet, freeze_panes, fill_totals, sort_table, lookup_fill, age_from_birthday]
