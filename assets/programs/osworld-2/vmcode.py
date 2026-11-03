"""Python source snippets that run inside the VM."""

# Shared by RELAUNCH and every Calc handler: UNO connection, (re)starting soffice with a UNO socket,
# finding the open spreadsheet document.
UNO_PRELUDE = r'''
import os, sys, time, json, subprocess, re
from urllib.parse import unquote
sys.path.append('/usr/lib/python3/dist-packages')
sys.path.append('/usr/lib/libreoffice/program')
import uno
from com.sun.star.beans import PropertyValue

def _pv(n, v):
    p = PropertyValue(); p.Name = n; p.Value = v; return p

def _connect(tries=40):
    local = uno.getComponentContext()
    res = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    last = None
    for i in range(tries):
        try:
            ctx = res.resolve("uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
            return ctx, ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        except Exception as e:
            last = e
            time.sleep(0.5)
    raise last

def _launch(files):
    """Kill soffice (NEVER pkill -f soffice: it matches this python too), drop lock files, restart it
    with a UNO socket on the given documents."""
    subprocess.run("pkill -x soffice.bin; pkill -x oosplash; sleep 1.5; pkill -9 -x soffice.bin; rm -f /home/user/.~lock.* 2>/dev/null", shell=True)
    for f in files:
        p = unquote(f[7:] if f.startswith('file://') else f)
        try:
            os.remove(os.path.join(os.path.dirname(p), '.~lock.' + os.path.basename(p) + '#'))
        except Exception:
            pass
    time.sleep(1)
    args = ['soffice', '--accept=socket,host=localhost,port=2002;urp;', '--norestore', '--nologo']
    args += files if files else ['--calc']
    subprocess.Popen(args, env=dict(os.environ, DISPLAY=':0'), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)

def _wait_doc(desktop, tries=40):
    """First open spreadsheet document (None after ~20 s)."""
    for _ in range(tries):
        comps = desktop.getComponents().createEnumeration()
        while comps.hasMoreElements():
            c = comps.nextElement()
            if hasattr(c, 'getSheets'):
                return c
        time.sleep(0.5)
    return None
'''

# Step 1: list soffice processes, windows and terminal cwds. Waits for a still-loading Calc document
# (up to 45 s if soffice runs, else NOPROC_WAIT s, which the policy prepends). Prints SOFFICE_DOC lines.
PROBE = r'''
import subprocess, time
t0 = time.time()
while True:
    out = subprocess.run("ps -eo args | grep -E '^/usr/lib/libreoffice/program/soffice.bin|^soffice|^/usr/bin/soffice|^libreoffice' | grep -v grep; "
                         "wmctrl -l; for p in $(pgrep -u user -x bash); do echo CWD $(readlink /proc/$p/cwd); done",
                         shell=True, capture_output=True, text=True).stdout
    has_proc = 'soffice' in out or 'libreoffice' in out
    if 'LibreOffice' in out or time.time() - t0 > (45 if has_proc else NOPROC_WAIT):
        break
    time.sleep(2)
for line in out.splitlines():
    if ('soffice' in line and any(x in line for x in ('file://', '.xls', '.ods', '.csv'))) or 'LibreOffice Calc' in line:
        print('SOFFICE_DOC', line)
print(out[-2500:])
'''

# Relaunch the running Calc with a UNO socket (the GUI one has none) on the same document, then dump
# all sheets as JSON after the @@JSON@@ marker.
RELAUNCH = UNO_PRELUDE + r'''
def _doc_files():
    """Documents soffice was started with; else a '<name>.xlsx - LibreOffice' window; else the newest
    spreadsheet file in the home directory (the document never opened on a slow setup)."""
    out = subprocess.run("ps -eo args", shell=True, capture_output=True, text=True).stdout
    files = []
    for line in out.splitlines():
        if 'soffice' in line and 'accept=' not in line and 'python' not in line:
            for tok in line.split():
                if tok.startswith('file://') or (tok.startswith('/') and '.' in tok.split('/')[-1] and 'soffice' not in tok):
                    files.append(tok)
    if files:
        return files
    t = subprocess.run("wmctrl -l", shell=True, capture_output=True, text=True).stdout
    for line in t.splitlines():
        m = re.search(r'\s(\S+\.(xlsx|xls|csv|ods))\s+-\s+LibreOffice', line)
        if m:
            cand = subprocess.run("find /home/user -name '%s' 2>/dev/null | head -1" % m.group(1), shell=True, capture_output=True, text=True).stdout.strip()
            if cand: files.append(cand)
    if files:
        return files
    cand = subprocess.run("find /home/user -maxdepth 3 -not -path '*/.*' -type f \\( -name '*.xlsx' -o -name '*.xls' -o -name '*.ods' -o -name '*.csv' \\) -mmin -600 -printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-",
                          shell=True, capture_output=True, text=True).stdout.strip()
    return [cand] if cand else []

files = _doc_files()
try:
    ctx, desktop = _connect(1)
except Exception:
    _launch(files)
    ctx, desktop = _connect(60)
doc = _wait_doc(desktop)
info = {'files': files, 'url': doc.getURL() if doc else None, 'sheets': []}
if doc is not None:
    sheets = doc.getSheets()
    for si in range(sheets.getCount()):
        sh = sheets.getByIndex(si)
        cur = sh.createCursor(); cur.gotoEndOfUsedArea(False)
        ra = cur.getRangeAddress()
        nr, nc = ra.EndRow + 1, ra.EndColumn + 1
        rows = []
        if nr * nc <= 200000:
            rows = [list(r) for r in sh.getCellRangeByPosition(0, 0, nc - 1, min(nr, 2000) - 1).getDataArray()]
        # per column: index of the last non-empty row
        lastrow = [max([r for r in range(len(rows)) if c < len(rows[r]) and rows[r][c] not in ('', None)] or [0])
                   for c in range(nc)]
        info['sheets'].append({'name': sh.getName(), 'nrows': nr, 'ncols': nc, 'rows': rows, 'lastrow': lastrow})
# action output is cut to its last 8000 chars: shrink the dump to fit
s = json.dumps(info, default=str)
while len(s) > 7500:
    big = [x for x in info['sheets'] if len(x['rows']) > 3]
    if not big:
        for x in info['sheets'][1:]:
            x['rows'] = []
        s = json.dumps(info, default=str)
        break
    for x in big:
        x['rows'] = x['rows'][:max(3, len(x['rows']) * 2 // 3)]
        x['truncated'] = True
    s = json.dumps(info, default=str)
print('@@JSON@@' + s)
'''
