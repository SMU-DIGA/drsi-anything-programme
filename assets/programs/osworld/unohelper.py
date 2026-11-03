# This file is sent as source code to the desktop VM and executed there, followed by a Calc skill.
# It (re)starts LibreOffice with a UNO socket and gives access to the open document.
import subprocess, time, os, re, sys, glob
os.environ.setdefault('DISPLAY', ':0')
try:
    import uno
except ImportError:
    sys.path.append('/usr/lib/python3/dist-packages')
    import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.table.CellContentType import EMPTY, VALUE, TEXT, FORMULA

PORT = 2002
CSV_OPTS = '44,34,76,1,,0,false,true,true,false,false'
FILTERS = {'.xlsx': 'Calc MS Excel 2007 XML', '.xls': 'MS Excel 97', '.ods': 'calc8',
           '.csv': 'Text - txt - csv (StarCalc)'}


def pv(n, v):
    p = PropertyValue()
    p.Name, p.Value = n, v
    return p


def doc_path_from_ps():
    """Path of the document LibreOffice was launched with (from its command line)."""
    out = subprocess.run(['ps', '-eo', 'comm,args'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in ('soffice.bin', 'oosplash', 'soffice'):
            m = re.search(r'(file://\S+)', parts[1])
            if m:
                return uno.fileUrlToSystemPath(m.group(1))
            for tok in parts[1].split()[1:]:
                if not tok.startswith('-') and os.path.exists(tok):
                    return os.path.abspath(tok)
    return None


def _resolve(timeout):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            return resolver.resolve('uno:socket,host=localhost,port=%d;urp;StarOffice.ComponentContext' % PORT)
        except Exception:
            time.sleep(0.5)
    return None


def start_office(path=None):
    """Kill LibreOffice (never `pkill -f soffice`: it would match this script) and relaunch with a socket."""
    for sig in ([], ['-9']):
        subprocess.run(['pkill'] + sig + ['-x', 'soffice.bin'])
        subprocess.run(['pkill'] + sig + ['-x', 'oosplash'])
        time.sleep(1.5 if not sig else 0.5)
    if path:
        d, b = os.path.split(path)
        for lk in glob.glob(os.path.join(d, '.~lock.' + b + '#')):
            try:
                os.remove(lk)
            except Exception:
                pass
    args = ['soffice', '--norestore', '--nologo', '--accept=socket,host=localhost,port=%d;urp;' % PORT,
            path or '--calc']
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def get_doc(path=None, timeout=40):
    """Return (doc, path). Restarts LibreOffice with a UNO socket if needed."""
    if path is None:
        path = doc_path_from_ps()
    ctx = _resolve(1)
    if ctx is None:
        start_office(path)
        ctx = _resolve(timeout)
    desktop = ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', ctx)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            comps = desktop.getComponents().createEnumeration()
            while comps.hasMoreElements():
                c = comps.nextElement()
                if hasattr(c, 'getSheets'):
                    if path is None or not c.getURL() or uno.fileUrlToSystemPath(c.getURL()) == path:
                        return c, path
        except Exception:
            pass
        time.sleep(0.5)
    if path:
        return desktop.loadComponentFromURL(uno.systemPathToFileUrl(path), '_default', 0, ()), path
    return desktop.getCurrentComponent(), path


def export(doc, path, flt, opts=None):
    props = [pv('FilterName', flt), pv('Overwrite', True)]
    if opts:
        props.append(pv('FilterOptions', opts))
    doc.storeToURL(uno.systemPathToFileUrl(path), tuple(props))
    print('EXPORTED', path)


def save(doc, path):
    """Store the document back in its own format."""
    ext = os.path.splitext(path)[1].lower()
    props = [pv('FilterName', FILTERS.get(ext, 'Calc MS Excel 2007 XML')), pv('Overwrite', True)]
    if ext == '.csv':
        props.append(pv('FilterOptions', CSV_OPTS))
    doc.storeAsURL(uno.systemPathToFileUrl(path), tuple(props))
    print('SAVED', path)


def col_idx(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def col_name(i):
    s = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def used_range(sheet):
    """(last column, last row) of the used area, 0-based."""
    cur = sheet.createCursor()
    cur.gotoEndOfUsedArea(False)
    a = cur.getRangeAddress()
    return a.EndColumn, a.EndRow


def find_header(sheet, name, max_rows=10):
    """(col, row) of the first cell in the top rows whose text equals name, else contains/is contained in it."""
    ec, er = used_range(sheet)
    nm = name.strip().lower()
    cells = [(c, r, sheet.getCellByPosition(c, r).getString().strip().lower())
             for r in range(min(er + 1, max_rows)) for c in range(ec + 1)]
    for c, r, t in cells:
        if t == nm:
            return c, r
    for c, r, t in cells:
        if t and (nm in t or t in nm):
            return c, r
    return None
