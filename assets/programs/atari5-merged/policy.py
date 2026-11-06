"""One program for five Atari games that tells the game from the screen alone.

At the first non-blank frame of an episode (NOOP until then) the screen (downsampled to 21 x 16 RGB cells) is matched to the nearest of five
reference screens (game_signatures.npy, mean first frame over train seeds 0-15 of each game); the matching game's
program, unchanged, then plays the episode. The environment uses the full 18-action set, so the action count says
nothing about the game; each game's program still picks from its own minimal action set, mapped to the full set here.
"""
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# (sub-program, the spec it was written for, its minimal action set as indices into ALE's full 18 actions)
GAMES = [
    ("battle_zone", "BattleZone-v5", list(range(18))),
    ("double_dunk", "DoubleDunk-v5", list(range(18))),
    ("name_this_game", "NameThisGame-v5", [0, 1, 3, 4, 11, 12]),  # NOOP FIRE RIGHT LEFT RIGHTFIRE LEFTFIRE
    ("phoenix", "Phoenix-v5", [0, 1, 3, 4, 5, 11, 12, 13]),       # + DOWN, DOWNFIRE
    ("qbert", "Qbert-v5", [0, 1, 2, 3, 4, 5]),                    # NOOP FIRE UP RIGHT LEFT DOWN
]
SIGNATURES = np.load(os.path.join(HERE, "game_signatures.npy"))


def signature(frame):
    return np.asarray(frame, dtype=float).reshape(21, 10, 16, 10, 3).mean((1, 3)).ravel()


class Policy:
    def __init__(self, spec):
        self.spec, self.cache, self.game = spec, {}, None

    def _load(self, k):
        if k not in self.cache:
            name, env_id, actions = GAMES[k]
            path = os.path.join(HERE, name)
            os.chdir(path)  # each program may read its own files relative to its directory
            if path not in sys.path:
                sys.path.insert(0, path)
            spec = importlib.util.spec_from_file_location("game_" + name, os.path.join(path, "policy.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sub_spec = {**self.spec, "env_id": env_id, "action": {"type": "discrete", "n": len(actions)}}
            self.cache[k] = (module.Policy(sub_spec), actions)
        return self.cache[k]

    def reset(self):
        self.game = None  # decided again from the next first frame

    def act(self, obs, info):
        if self.game is None:
            if np.ptp(np.asarray(obs).reshape(-1, 3), axis=0).max() < 8:
                return 0  # a blank screen (some episodes start on one) says nothing about the game: wait
            k = int(np.argmin(np.linalg.norm(SIGNATURES - signature(obs), axis=1)))
            self.game = self._load(k)
            self.game[0].reset()
        policy, actions = self.game
        return actions[int(policy.act(obs, info))]
