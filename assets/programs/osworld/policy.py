"""Rule-based policy.

Step 1: match the instruction against the regex skills in skills.py and send the generated code as a
single action (Calc skills are prefixed with unohelper.py, which connects to LibreOffice over UNO).
Step 2: DONE, or FAIL if that code errored. No matching skill -> FAIL (correct for infeasible tasks).
"""
import os
import re
import traceback

import skills

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unohelper.py')) as f:
    UNO_HELPER = f.read()

PLACEHOLDER = re.compile(r'["\']\$\{?[A-Za-z_]\w*\}?["\']')   # e.g. "$sourceDir": task is infeasible


def calc_is_open(tree):
    return 'LibreOffice Calc' in tree or 'name="soffice"' in tree or '.xlsx' in tree


def make_action(ins, calc_open):
    """Code for the first skill that matches the instruction, or None."""
    if PLACEHOLDER.search(ins):
        print('UNRESOLVED PLACEHOLDER', flush=True)
        return None
    groups = [(skills.CALC_SKILLS, UNO_HELPER + '\n'), (skills.OS_SKILLS, '')]
    if not calc_open:
        groups.reverse()
    for fns, prefix in groups:
        for fn in fns:
            try:
                code = fn(ins)
            except Exception:
                traceback.print_exc()
                continue
            if code:
                print('SKILL', fn.__name__, flush=True)
                return prefix + code
    return None


class Policy:
    def __init__(self, spec):
        self.spec = spec

    def reset(self):
        self.step = 0
        self.failed = False

    def act(self, obs, info):
        self.step += 1
        if self.step == 1:
            ins = obs['instruction']
            calc_open = calc_is_open(obs.get('accessibility_tree') or '')
            print('INSTRUCTION:', ins, '\nCALC_OPEN', calc_open, flush=True)
            action = make_action(ins, calc_open)
            if action is None:
                print('NO SKILL -> FAIL', flush=True)
                return 'FAIL'
            return action
        ar = info.get('action_result') or {}
        print('ACTION_RESULT:', str(ar)[:4000], flush=True)
        if str(ar.get('returncode', '0')) not in ('0', '') or 'Traceback' in str(ar.get('error', '')):
            self.failed = True
        return 'FAIL' if self.failed else 'DONE'
