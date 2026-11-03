"""Rule-based OSWorld agent for libreoffice_calc and os tasks.

Step 1 probes the desktop (vmcode.PROBE) to decide calc vs os.
Calc: relaunch the open document with a UNO socket and dump its sheets (vmcode.RELAUNCH), pick a
handler from the instruction (calc_handlers.plan), run its UNO code that edits and stores the document.
OS: map the instruction to shell commands run inside the VM (os_handlers.plan).
Anything unrecognised or failing => FAIL: feasible tasks score 0 either way, infeasible ones score 1.
"""
import json
import re
import traceback

import vmcode
import calc_handlers
import os_handlers

# a slow VM may not show the Calc document yet: wait longer when the task reads like a spreadsheet task
SHEETY = re.compile(r'\b(cells?|columns?|rows?|sheets?|spreadsheet|table|xlsx|csv|chart|pivot|formula|'
                    r'calc|libreoffice|workbook|header)\b', re.I)


def log(*a):
    print("LOG", *a, flush=True)


class Policy:
    def __init__(self, spec):
        self.spec = spec
        self.reset()

    def reset(self):
        self.step = 0
        self.queue = []          # pending (tag, code) actions
        self.mode = None         # "calc" | "os"
        self.instr = ""
        self.last_tag = None     # tag of the action whose result `info` carries
        self.last_code = None
        self.retries = 0         # re-sent probe/relaunch actions after "no response from the desktop"

    def act(self, obs, info):
        try:
            return self._act(obs, info)
        except Exception:
            log("ERROR", traceback.format_exc())
            return "DONE"

    def _emit(self, tag, code):
        self.last_tag = tag
        self.last_code = code
        return code

    def _act(self, obs, info):
        self.step += 1
        if self.step == 1:
            self.instr = obs.get("instruction", "")
            print("INSTRUCTION:", self.instr, flush=True)
            wait = 45 if SHEETY.search(self.instr) else 10
            return self._emit("probe", "NOPROC_WAIT = %d\n" % wait + vmcode.PROBE)

        res = info.get("action_result") or {}
        out = res.get("output", "")
        log("result", json.dumps(res)[:1500])
        # a busy VM sometimes drops an action's result: probe and relaunch are idempotent, re-send them
        if "no response" in str(res.get("error", "")) and not out and self.last_tag in ("probe", "relaunch") \
                and self.retries < 3 and self.step < 20:
            self.retries += 1
            log("no response -> retry", self.last_tag, self.retries)
            return self._emit(self.last_tag, self.last_code)

        if self.last_tag == "probe":
            sheety = bool(SHEETY.search(self.instr))
            # calc vs os decided with the original OS families only (fallbacks must not steal Calc tasks)
            base = os_handlers.plan(self.instr, out, more=False)
            os_acts = base or os_handlers.plan(self.instr, out)
            self.mode = "calc" if "SOFFICE_DOC" in out or (sheety and not base) else "os"
            if os_acts and os_acts[0][0] == "kill":   # force-quit a frozen app (maybe LibreOffice itself)
                self.mode = "os"
            log("mode", self.mode)
            if self.mode == "os":
                log("os plan", [a[0] for a in os_acts])
                self.queue = os_acts
                if not os_acts:
                    return self._emit("fail", "FAIL")
            else:
                return self._emit("relaunch", vmcode.RELAUNCH)

        elif self.last_tag == "relaunch":
            if "@@JSON@@" not in out:
                log("relaunch failed")
                return self._emit("fail", "FAIL")
            data = json.loads(out.split("@@JSON@@", 1)[1].strip())
            print("DATA " + json.dumps(data, default=str)[:200000], flush=True)
            for sh in data.get("sheets", []):
                log("sheet", sh["name"], sh["nrows"], sh["ncols"], json.dumps(sh["rows"][:4], default=str)[:600])
            self.queue = calc_handlers.plan(self.instr, data)
            log("calc plan", [a[0] for a in self.queue])
            if not self.queue:
                return self._emit("fail", "FAIL")

        elif self.mode == "calc" and str(res.get("returncode", "0")) not in ("0", "") \
                and "STORED" not in out and "EXPORTED" not in out:
            log("handler failed -> FAIL")
            return self._emit("fail", "FAIL")

        elif self.last_tag == "hwcheck" and "NOHW" in out:
            log("required hardware absent -> FAIL")
            return self._emit("fail", "FAIL")

        if self.queue:
            return self._emit(*self.queue.pop(0))
        return self._emit("done", "DONE")
