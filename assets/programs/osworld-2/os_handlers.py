"""Instruction -> shell commands for OS tasks."""
import re
import shlex

# Working directory a task means by "current directory": the cwd of an open terminal shell, else home.
CWD = ("CWD=$(for p in $(pgrep -u user -x bash); do readlink /proc/$p/cwd; done | grep -v '^/$' | tail -1); "
       "[ -z \"$CWD\" ] && CWD=/home/user; cd \"$CWD\"; ")


def sh(cmd, sudo=False):
    """Python snippet that runs a shell command in the VM and prints its output."""
    if sudo:
        cmd = "echo password | sudo -S bash -c %s" % shlex.quote(cmd)
    return ("import subprocess, os\n"
            "env = dict(os.environ)\n"
            "env.setdefault('DISPLAY', ':0')\n"
            "env.setdefault('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/run/user/%%d/bus' %% os.getuid())\n"
            "print('uid', os.getuid(), env.get('DBUS_SESSION_BUS_ADDRESS'))\n"
            "r = subprocess.run(%r, shell=True, executable='/bin/bash', capture_output=True, text=True, timeout=100, env=env)\n"
            "print(r.stdout[-3000:]); print(r.stderr[-1500:])\n" % cmd)


def Q(s):
    return shlex.quote(s)


def quoted(s):
    out = re.findall(r'"([^"]+)"|“([^”]+)”|(?<![A-Za-z])\'([^\']+)\'(?![A-Za-z])|`([^`]+)`', s)
    return [next(g for g in t if g) for t in out]


def gs(schema, key, value):
    return "gsettings set %s %s %s" % (schema, key, Q(value))


TYPE_IN_TERMINAL = r'''
import subprocess, time, pyautogui, os
env_cmd = %r
w = subprocess.run("wmctrl -l | grep -i -E 'terminal|user@' | head -1 | cut -d' ' -f1", shell=True, capture_output=True, text=True).stdout.strip()
if w:
    subprocess.run("wmctrl -i -a %%s" %% w, shell=True)
    time.sleep(1)
else:
    d = %r
    if d == '/home/user':
        # "current directory" = folder open in the file manager (window title)
        for line in subprocess.run("wmctrl -l", shell=True, capture_output=True, text=True).stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4 or parts[1] == '-1': continue
            title = parts[3].strip()
            if title.startswith('/') and os.path.isdir(title):
                d = title; break
            f = subprocess.run(["find", "/home/user", "-maxdepth", "4", "-type", "d", "-name", title], capture_output=True, text=True).stdout.split()
            if f:
                d = f[0]; break
    try:
        subprocess.Popen(['gnome-terminal', '--working-directory=' + d], env=dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':0')))
        time.sleep(4)
    except Exception:
        pyautogui.hotkey('ctrl', 'alt', 't'); time.sleep(3)
    pyautogui.typewrite('cd ' + d + '\n', interval=0.02); time.sleep(0.5)
pyautogui.typewrite(env_cmd + '\n', interval=0.02)
time.sleep(1.5)
'''


def terminal_cwd(probe):
    cwds = [l.split(' ', 1)[1].strip() for l in probe.splitlines() if l.startswith('CWD ') and len(l) > 5]
    cwds = [c for c in cwds if c != '/']
    return cwds[-1] if cwds else '/home/user'


def plan(instr, probe="", more=True):
    s = instr
    low = s.lower()
    q = quoted(s)

    def run(cmd, sudo=False, tag="sh"):
        return [(tag, sh(cmd, sudo)), ("done", "DONE")]

    # ---------------- count lines of files of an extension, shown in the terminal
    m = re.search(r'count\b.*\blines?\b.*?\.?\b([a-z0-9]{1,5}) files', low) or \
        re.search(r'lines? of (?:all |the )?(?:\*?\.)?([a-z0-9]{1,5}) files', low)
    if m and 'terminal' in low:
        depth = '-maxdepth 1 ' if re.search(r'not recursive|non-?recursive', low) else ''
        cmd = 'find . %s-type f -name "*.%s" -exec cat {} + | wc -l' % (depth, m.group(1))
        return [("type", TYPE_IN_TERMINAL % (cmd, terminal_cwd(probe))), ("done", "DONE")]

    # ---------------- settings
    if re.search(r'\b(volume)\b', low) and re.search(r'max|100|loud|highest', low):
        return run("pactl set-sink-mute @DEFAULT_SINK@ 0; pactl set-sink-volume @DEFAULT_SINK@ 100%; "
                   "amixer -D pulse sset Master 100% unmute || amixer sset Master 100% unmute")
    if re.search(r'\bmute\b', low) and 'volume' not in low:
        return run("pactl set-sink-mute @DEFAULT_SINK@ 1")
    if 'dark' in low and re.search(r'theme|mode', low):
        return run(gs("org.gnome.desktop.interface", "color-scheme", "prefer-dark") + "; " +
                   gs("org.gnome.desktop.interface", "gtk-theme", "Yaru-dark"))
    if re.search(r'(screen|display).*(lock|dim|blank|turn(s)? off|sleep)|(lock|dim).*screen', low):
        cmds = []
        if 'dim' in low:
            cmds.append("gsettings set org.gnome.settings-daemon.plugins.power idle-dim false")
        if re.search(r'never|disable|turn off|not|don\'t|stop', low) or 'lock' in low:
            if 'lock' in low:
                cmds.append("gsettings set org.gnome.desktop.screensaver lock-enabled false")
            if re.search(r'never|blank|turn(s)? off|sleep|idle', low) or not cmds:
                cmds.append("gsettings set org.gnome.desktop.session idle-delay 0")
        m = re.search(r'(\d+)\s*(minute|min|second|sec)', low)
        if m and not re.search(r'never', low):
            secs = int(m.group(1)) * (60 if m.group(2).startswith('min') else 1)
            cmds = ["gsettings set org.gnome.desktop.session idle-delay %d" % secs]
        if cmds:
            return run("; ".join(cmds))
    if 'timezone' in low or 'time zone' in low:
        m = re.search(r'utc\s*([+-]\s*\d+)?', low)
        tz = None
        if m:
            off = (m.group(1) or '+0').replace(' ', '')
            n = int(off)
            tz = 'UTC' if n == 0 else 'Etc/GMT%+d' % (-n)
        else:
            m = re.search(r'\b([A-Z][a-z]+/[A-Z][A-Za-z_]+)\b', s)
            if m:
                tz = m.group(1)
        if tz:
            return run("timedatectl set-timezone %s" % tz, sudo=True)
    if re.search(r'(text|font).*(size|scal|larger|bigger)|(larger|bigger|increase|enlarge|magnif).*(text|font)', low) \
            and not re.search(r'terminal|editor|libreoffice|document|cell', low):
        m = re.search(r'(\d+(?:\.\d+)?)\s*(%|x|times)?', low)
        f = 1.25
        if m:
            v = float(m.group(1))
            f = v / 100 if m.group(2) == '%' or v > 4 else v
        return run(gs("org.gnome.desktop.interface", "text-scaling-factor", str(f)))
    # hardware the VM may not have: check first; absent hardware => infeasible => FAIL
    if 'battery' in low:
        cmd = "ls /sys/class/power_supply/ | grep -qi bat || echo NOHW; "
        if 'percent' in low:
            cmd += gs("org.gnome.desktop.interface", "show-battery-percentage", "true")
        return [("hwcheck", sh(cmd)), ("done", "DONE")]
    if 'bluetooth' in low:
        cmd = "ls /sys/class/bluetooth 2>/dev/null | grep -q . || echo NOHW; "
        cmd += "rfkill %s bluetooth" % ("block" if re.search(r'\boff\b|disable', low) else "unblock")
        return [("hwcheck", sh(cmd)), ("done", "DONE")]
    if re.search(r'do not disturb|don\'t disturb|dnd', low) or ('notification' in low and re.search(r'turn off|disable|stop|silence|bother', low)):
        return run(gs("org.gnome.desktop.notifications", "show-banners", "false") +
                   "; gsettings get org.gnome.desktop.notifications show-banners")
    if re.search(r'auto[- ]?hide', low) and 'dock' in low:
        return run(gs("org.gnome.shell.extensions.dash-to-dock", "dock-fixed", "false") + "; " +
                   gs("org.gnome.shell.extensions.dash-to-dock", "autohide", "true"))

    if 'wallpaper' in low or 'background' in low and 'desktop' in low:
        paths = [x for x in q if '/' in x or '.' in x]
        m = re.search(r'(~?/[\w./-]+\.(?:png|jpe?g|svg|webp))', s)
        p = paths[0] if paths else (m.group(1) if m else None)
        if p:
            p = p.replace('~', '/home/user', 1) if p.startswith('~') else p
            cmd = ("P=%s; [ -f \"$P\" ] || P=$(find /home/user -name \"$(basename \"$P\")\" 2>/dev/null | head -1); "
                   "gsettings set org.gnome.desktop.background picture-uri \"file://$P\"; "
                   "gsettings set org.gnome.desktop.background picture-uri-dark \"file://$P\"" % Q(p))
            return run(cmd)
    m = re.search(r'\b(uninstall|remove)\b\s+(?:the\s+)?(?:package\s+|app(?:lication)?\s+)?["“\']?([a-z0-9][a-z0-9.+-]+)', low)
    if m and re.search(r'uninstall|package|from (my|the) (system|computer)|app', low) and not re.search(r'file|folder|director', low):
        pkg = m.group(2)
        return run("apt-get remove -y %s || snap remove %s; apt-get purge -y %s" % (pkg, pkg, pkg), sudo=True)
    if re.search(r'(?:symbolic|soft|sym)\s*link', low):
        if len(q) >= 2:
            a, b = q[0], q[1]
            if re.search(r'link\s+(?:named|called|at)\s', low) and low.find(b.lower()) < low.find(a.lower()):
                a, b = b, a
            a = a.replace('~', '/home/user', 1)
            b = b.replace('~', '/home/user', 1)
            return run("cd /home/user; ln -sf %s %s; ls -l %s" % (Q(a), Q(b), Q(b)))

    # ---------------- users
    m = re.search(r'(?:user|account)\s+(?:named|called)?\s*["“\']?([a-z_][a-z0-9_-]*)["”\']?', low)
    if m and re.search(r'\b(create|add|new)\b', low) and 'user' in low:
        name = m.group(1)
        pw = None
        mp = re.search(r'password\s*(?:is|of|as|to)?\s*["“\']([^"”\']+)["”\']', s, re.I)
        if mp:
            pw = mp.group(1)
        cmd = "id %s || useradd -m -s /bin/bash %s; " % (name, name)
        if pw:
            cmd += "echo %s | chpasswd; " % Q("%s:%s" % (name, pw))
        if 'sudo' in low or 'admin' in low:
            cmd += "usermod -aG sudo %s; " % name
        folder = [x for x in q if x.startswith('/')]
        if 'ssh' in low and folder and re.search(r'only|restrict|limit', low):
            f = folder[0]
            cmd += ("mkdir -p %s; chown root:root %s; chmod 755 %s; usermod -d %s %s; "
                    "printf '\\nMatch User %s\\n    ChrootDirectory %s\\n    ForceCommand internal-sftp\\n    AllowTcpForwarding no\\n    X11Forwarding no\\n' >> /etc/ssh/sshd_config; "
                    "systemctl restart ssh || systemctl restart sshd || service ssh restart; " % (Q(f), Q(f), Q(f), Q(f), name, name, f))
        return run(cmd, sudo=True)

    # ---------------- permissions
    m = re.search(r'permission[s]?\b.*\bto\s+([0-7]{3,4})\b', low)
    if m:
        mode = m.group(1)
        typ = ""
        if 'file' in low and not re.search(r'files and (sub)?director|director(y|ies) and files', low):
            typ = "-type f"
        elif re.search(r'director(y|ies)|folders', low) and 'file' not in low:
            typ = "-type d"
        rec = 'recurs' in low or 'tree' in low or 'subdir' in low
        cmd = CWD + "find . %s %s -exec chmod %s {} +" % ("" if rec else "-maxdepth 1", typ, mode)
        return run(cmd)

    # ---------------- rename
    m = re.search(r'\brename\b', low)
    if m and len(q) >= 2:
        a, b = q[0], q[1]
        cmd = ("P=$(find /home/user -maxdepth 4 -name %s 2>/dev/null | head -1); "
               "[ -n \"$P\" ] && mv \"$P\" \"$(dirname \"$P\")\"/%s; ls \"$(dirname \"$P\")\"" % (Q(a), Q(b)))
        return run(cmd)

    # ---------------- copy/move all files of a pattern from one dir to another
    m = re.search(r'\b(copy|move)\b', low)
    pat = re.search(r'(\*[\w.*-]*|\.[a-z0-9]{1,5}\b)\s*files', low) or re.search(r'(\*[\w.*-]+)', s)
    if m and pat:
        p = pat.group(1)
        glob = p if '*' in p else '*' + p
        dirs = [x for x in q if '*' not in x and not re.match(r'^\.[A-Za-z0-9]{1,5}$', x)]
        cwd = terminal_cwd(probe)
        if len(dirs) >= 2:
            src, dst = dirs[0], dirs[1]
        elif len(dirs) == 1:
            src, dst = '.', dirs[0]
        else:
            src = dst = None
        if dst:
            def absd(d):
                if d.startswith('/'):
                    return d
                if d.startswith('~'):
                    return '/home/user' + d[1:]
                return d
            op = 'cp' if m.group(1) == 'copy' else 'mv'
            pres = bool(re.search(r'hierarch|structure|preserv|keep(ing)? the (directory|folder)', low))
            pre = "cd %s; S=%s; [ -d \"$S\" ] || S=$(find /home/user -type d -name %s 2>/dev/null | head -1); " % (
                Q(cwd), Q(absd(src)), Q(src.rstrip('/').split('/')[-1]))
            pre += "D=%s; case \"$D\" in /*) ;; *) [ -d \"$D\" ] || { F=$(find /home/user -type d -name \"$D\" 2>/dev/null | head -1); [ -n \"$F\" ] && D=$F; } ;; esac; " % Q(absd(dst))
            pre += "case \"$D\" in /*) ;; *) D=$(pwd)/$D;; esac; mkdir -p \"$D\"; cd \"$S\"; "
            if pres:
                cmd = pre + "find . -type f -name %s -not -path \"$D/*\" -exec cp --parents {} \"$D\"/ \\; ; find \"$D\" | head -50" % Q(glob)
                if op == 'mv':
                    cmd += "; find . -type f -name %s -not -path \"$D/*\" -delete" % Q(glob)
            else:
                cmd = pre + "find . -type f -name %s -not -path \"$D/*\" -exec %s {} \"$D\"/ \\; ; ls \"$D\" | head -50" % (Q(glob), op)
            return run(cmd)

    # ---------------- copy/move a named file to a named dir (m: copy/move match from above)
    if m and len(q) >= 2 and not re.search(r'\*|recursive|hierarch|structure|all\b', low):
        op = 'cp -r' if m.group(1) == 'copy' else 'mv'
        a, b = q[0], q[1]
        cmd = ("cd /home/user; S=$(find /home/user -maxdepth 4 -name %s 2>/dev/null | head -1); "
               "D=%s; case \"$D\" in /*|~*) ;; *) F=$(find /home/user -maxdepth 4 -type d -name \"$D\" 2>/dev/null | head -1); "
               "[ -n \"$F\" ] && D=$F || D=/home/user/$D;; esac; D=${D/#\\~/\\/home\\/user}; mkdir -p \"$D\"; %s \"$S\" \"$D\"/; ls \"$D\""
               % (Q(a.split('/')[-1]), Q(b), op))
        return run(cmd)

    # ---------------- create dirs/files
    m = re.search(r'\b(create|make)\b.*\b(folder|directory)\b', low)
    if m and q and 'file' not in low:
        cmds = []
        for name in q:
            p = name if name.startswith('/') or name.startswith('~') else '/home/user/Desktop/' + name if 'desktop' in low else '/home/user/' + name
            cmds.append("mkdir -p %s" % (p if p.startswith('~') else Q(p)))
        return run("; ".join(cmds))
    try:
        return plan_more(s, low, q, probe) if more else []
    except Exception as e:
        print("LOG plan_more error", e, flush=True)
        return []


# ---------------------------------------------------------------- generic fallbacks (g006c1)
# Each is tried only when no family above matched. Commands that can tell whether they worked print
# NOHW on failure (tag "hwcheck"): the policy then answers FAIL (the task may be infeasible).
APPS = [  # (instruction words, process names)
    (r'writer|calc\b|impress|libreoffice|office', 'soffice.bin oosplash'),
    (r'chrome|chromium', 'chrome chromium chromium-browser'), (r'firefox', 'firefox'),
    (r'thunderbird', 'thunderbird'), (r'vs ?code|visual studio code', 'code'), (r'\bvlc\b', 'vlc'),
    (r'gimp', 'gimp-2.10 gimp'), (r'text editor|gedit', 'gedit gnome-text-editor'),
    (r'file manager|nautilus|files app', 'nautilus'), (r'terminal', 'gnome-terminal-server'),
]

TRASH_RESTORE = r'''
import os, glob, re, shutil
from urllib.parse import unquote
words = %r
base = os.path.expanduser('~/.local/share/Trash')
best = None
for info in glob.glob(base + '/info/*.trashinfo'):
    name = os.path.basename(info)[:-len('.trashinfo')]
    txt = open(info).read()
    m = re.search(r'^Path=(.*)$', txt, re.M)
    if not m: continue
    orig = unquote(m.group(1))
    low = (name + ' ' + orig).lower().replace('_', ' ').replace('-', ' ')
    sc = sum(w in low for w in words)
    print('trash', name, orig, sc)
    if best is None or sc > best[0]:
        best = (sc, name, orig, info)
if best is None or (words and best[0] == 0):
    print('NOHW nothing to restore')
else:
    sc, name, orig, info = best
    os.makedirs(os.path.dirname(orig), exist_ok=True)
    shutil.move(base + '/files/' + name, orig)
    os.remove(info)
    print('restored', orig, os.path.exists(orig))
'''

GSET = [  # (instruction pattern, schema, key, value when turning on, value when turning off)
    (r'night ?light', 'org.gnome.settings-daemon.plugins.color', 'night-light-enabled', 'true', 'false'),
    (r'(show|display).*seconds|seconds.*(clock|top bar)', 'org.gnome.desktop.interface', 'clock-show-seconds', 'true', 'false'),
    (r'(show|display).*week ?day|week ?day.*(clock|top bar)', 'org.gnome.desktop.interface', 'clock-show-weekday', 'true', 'false'),
    (r'24[- ]?h(ou)?r', 'org.gnome.desktop.interface', 'clock-format', '24h', '12h'),
    (r'12[- ]?h(ou)?r', 'org.gnome.desktop.interface', 'clock-format', '12h', '24h'),
    (r'animation', 'org.gnome.desktop.interface', 'enable-animations', 'true', 'false'),
    (r'natural scroll', 'org.gnome.desktop.peripherals.touchpad', 'natural-scroll', 'true', 'false'),
    (r'tap[- ]to[- ]click', 'org.gnome.desktop.peripherals.touchpad', 'tap-to-click', 'true', 'false'),
    (r'hot ?corner', 'org.gnome.desktop.interface', 'enable-hot-corners', 'true', 'false'),
    (r'automatic(ally)? suspend|auto[- ]?suspend', 'org.gnome.settings-daemon.plugins.power', 'sleep-inactive-ac-type', 'suspend', 'nothing'),
    (r'(show|display).*date.*(clock|top bar)', 'org.gnome.desktop.interface', 'clock-show-date', 'true', 'false'),
    (r'location services', 'org.gnome.system.location', 'enabled', 'true', 'false'),
    (r'(show|display).*desktop icons|desktop icons', 'org.gnome.shell.extensions.ding', 'show-home', 'true', 'false'),
    (r'high contrast', 'org.gnome.desktop.a11y.interface', 'high-contrast', 'true', 'false'),
    (r'screen reader', 'org.gnome.desktop.a11y.applications', 'screen-reader-enabled', 'true', 'false'),
    (r'on[- ]screen keyboard', 'org.gnome.desktop.a11y.applications', 'screen-keyboard-enabled', 'true', 'false'),
    (r'sticky keys', 'org.gnome.desktop.a11y.keyboard', 'stickykeys-enable', 'true', 'false'),
]

STOP = set("a an the my me i to of in on from and or please help can could you it its this that is be "
           "file files folder recover restore trash bin deleted delete wrongly accidentally back "
           "want would like put some which was were have has had ubuntu system computer".split())


def plan_more(s, low, q, probe):
    def run(cmd, sudo=False, tag="sh"):
        return [(tag, sh(cmd, sudo)), ("done", "DONE")]

    def check(cmd, sudo=False):
        return [("hwcheck", sh(cmd, sudo)), ("done", "DONE")]

    def home(p):
        return '/home/user' + p[1:] if p.startswith('~') else p

    # restore a file from the trash
    if 'trash' in low and re.search(r'recover|restore|undelete|bring back|get back|retrieve', low):
        words = [w for w in re.findall(r'[a-z0-9]+', " ".join(q).lower() if q else low) if w not in STOP and len(w) > 2]
        return [("hwcheck", TRASH_RESTORE % words), ("done", "DONE")]

    # force quit a frozen application
    if re.search(r'force[- ]?(quit|close|kill|stop)|\bkill\b|frozen|\bfroze\b|freezes|freezing|not responding|unresponsive|\bhangs?\b|\bhanging', low):
        for pat, procs in APPS:
            if re.search(pat, low):
                cmd = " ; ".join("pkill -9 -x %s" % p for p in procs.split())
                return run(cmd + "; sleep 1; ps -eo comm | grep -E '%s' || echo gone" % "|".join(procs.split()), tag="kill")

    # vim settings
    if re.search(r'\bvim\b', low) and re.search(r'line numbers?|numbering', low):
        return run("touch ~/.vimrc; grep -q '^set number' ~/.vimrc || echo 'set number' >> ~/.vimrc; cat ~/.vimrc")

    # install a package / application
    m = re.search(r'\binstall\s+(?:the\s+)?(?:latest\s+)?(?:package\s+|app(?:lication)?\s+)?["“\']?([A-Za-z0-9][A-Za-z0-9.+-]*)', s)
    if m and not re.search(r'uninstall|python\s*4', low):
        name = q[0] if q and re.fullmatch(r'[A-Za-z0-9.+ -]+', q[0]) else m.group(1)
        pkg = name.strip().lower().replace(' ', '-')
        if pkg in ('a', 'an', 'the', 'my', 'it', 'this', 'some', 'package', 'software', 'app'):
            pkg = None
        if pkg:
            snaps = {'spotify': 'spotify', 'vscode': 'code --classic', 'code': 'code --classic', 'slack': 'slack',
                     'discord': 'discord', 'zoom': 'zoom-client', 'telegram': 'telegram-desktop', 'postman': 'postman'}
            first = ("snap install %s" % snaps[pkg]) if pkg in snaps else ("DEBIAN_FRONTEND=noninteractive apt-get install -y %s" % Q(pkg))
            second = ("DEBIAN_FRONTEND=noninteractive apt-get install -y %s" % Q(pkg)) if pkg in snaps else ("snap install %s" % Q(pkg))
            verify = "dpkg -s %s >/dev/null 2>&1 || snap list %s >/dev/null 2>&1 || command -v %s || echo NOHW" % (
                Q(pkg), Q(pkg.split()[0]), Q(pkg))
            return check("%s || %s; %s" % (first, second, verify), sudo=True)

    # create a file with given content
    m = re.search(r'\b(create|make|write|new)\b.*\bfile\b', low)
    fn = [x for x in q if re.search(r'\.[A-Za-z0-9]{1,5}$', x) and ' ' not in x]
    if m and fn:
        content = None
        mc = re.search(r'(?:content|text|containing|contains|line|says|write)s?\s*(?:of|is|as|:)?\s*["“\']([^"”]*)["”\']', s, re.I)
        if mc and mc.group(1) not in fn:
            content = mc.group(1)
        p = home(fn[0])
        if not p.startswith('/'):
            d = '/home/user/Desktop' if 'desktop' in low else ('/home/user/Documents' if 'documents' in low else terminal_cwd(probe))
            dq = [home(x) for x in q if x not in fn and (x.startswith('/') or x.startswith('~'))]
            if dq:
                d = dq[0]
            p = d.rstrip('/') + '/' + p
        cmd = "mkdir -p %s; " % Q(p.rsplit('/', 1)[0])
        cmd += ("printf '%%s\\n' %s > %s; " % (Q(content), Q(p))) if content is not None else "touch %s; " % Q(p)
        return run(cmd + "ls -l %s; cat %s" % (Q(p), Q(p)))

    # compress a folder/file
    m = re.search(r'\b(compress|zip|archive|tar)\b', low)
    if m and q:
        arch = [x for x in q if re.search(r'\.(zip|tar|tar\.gz|tgz|tar\.bz2|tar\.xz)$', x)]
        srcs = [x for x in q if x not in arch]
        if srcs:
            src = home(srcs[0])
            fmt = 'zip' if ('zip' in low and 'gzip' not in low) else 'tar.gz'
            out = home(arch[0]) if arch else None
            if out:
                fmt = 'zip' if out.endswith('.zip') else 'tar'
            cmd = ("cd %s; S=%s; [ -e \"$S\" ] || S=$(find /home/user -maxdepth 4 -name %s 2>/dev/null | head -1); "
                   "[ -e \"$S\" ] || { echo NOHW; exit; }; cd \"$(dirname \"$S\")\"; B=$(basename \"$S\"); " % (
                       Q(terminal_cwd(probe)), Q(src), Q(src.rstrip('/').split('/')[-1])))
            o = Q(out) if out else ('"$B.zip"' if fmt == 'zip' else '"$B.tar.gz"')
            if fmt == 'zip':
                cmd += "(command -v zip >/dev/null && zip -r %s \"$B\") || python3 -c 'import shutil,sys,os; o=sys.argv[1]; shutil.make_archive(o[:-4], \"zip\", \".\", sys.argv[2])' %s \"$B\"; " % (o, o)
            else:
                cmd += "tar -czf %s \"$B\"; " % o
            return check(cmd + "ls -l; [ -s %s ] || echo NOHW" % o)

    # add an application to the dock favourites
    if re.search(r'favou?rite|dock|dash|pin', low) and re.search(r'\badd\b|\bpin\b|put', low):
        for pat, _ in APPS:
            mm = re.search(pat, low)
            if mm:
                key = mm.group(0).replace(' ', '')
                cmd = ("F=$(ls /usr/share/applications /var/lib/snapd/desktop/applications 2>/dev/null | grep -i %s | grep desktop$ | head -1); "
                       "[ -z \"$F\" ] && { echo NOHW; exit; }; "
                       "python3 - \"$F\" <<'EOF'\nimport subprocess, sys, ast\n"
                       "cur = ast.literal_eval(subprocess.run(['gsettings','get','org.gnome.shell','favorite-apps'],capture_output=True,text=True).stdout.strip().replace('@as ',''))\n"
                       "f = sys.argv[1]\nif f not in cur: cur.append(f)\n"
                       "subprocess.run(['gsettings','set','org.gnome.shell','favorite-apps',str(cur)])\nprint(cur)\nEOF" % Q(key))
                return check(cmd)

    # change a user's password
    m = re.search(r'password', low)
    if m and re.search(r'change|set|reset|update', low) and q:
        user = 'user'
        mu = re.search(r'(?:user|account)\s+["“\']?([a-z_][a-z0-9_-]*)', low)
        if mu and mu.group(1) not in ('password', 'to', 'named'):
            user = mu.group(1)
        pw = q[-1]
        return run("echo %s | chpasswd" % Q("%s:%s" % (user, pw)), sudo=True)

    # hostname
    m = re.search(r'host\s*name', low)
    if m and q:
        return run("hostnamectl set-hostname %s || echo %s > /etc/hostname" % (Q(q[-1]), Q(q[-1])), sudo=True)

    # simple desktop settings (on/off from the instruction's wording)
    off = bool(re.search(r'\b(turn off|switch off|disable|hide|stop|don\'t|do not|remove|no longer|without)\b', low))
    for pat, schema, key, onv, offv in GSET:
        if re.search(pat, low):
            v = offv if off else onv
            return run(gs(schema, key, v) + "; gsettings get %s %s" % (schema, key))
    m = re.search(r'\bdock\b.*\b(bottom|left|right|top)\b|\b(bottom|left|right|top)\b.*\bdock\b', low)
    if m and re.search(r'move|position|place|put|set', low):
        side = (m.group(1) or m.group(2)).upper()
        return run(gs("org.gnome.shell.extensions.dash-to-dock", "dock-position", side))
    m = re.search(r'cursor\b.*\bsize\b.*?(\d+)|(\d+)\D*cursor size', low)
    if m:
        return run(gs("org.gnome.desktop.interface", "cursor-size", m.group(1) or m.group(2)))

    # show hidden files in the file manager
    if 'hidden' in low and re.search(r'show|display|see|view', low) and re.search(r'file manager|nautilus|files', low):
        return run(gs("org.gtk.Settings.FileChooser", "show-hidden", "true") + "; " +
                   gs("org.gtk.gtk4.Settings.FileChooser", "show-hidden", "true") + " 2>/dev/null; "
                   "gsettings set org.gnome.nautilus.preferences show-hidden-files true 2>/dev/null; true")
    return []
