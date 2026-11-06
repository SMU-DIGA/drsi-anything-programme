"""Play the opening, capitalize on an early steal, and recover if behind."""

import numpy as np


ATTACK_ACTIONS = tuple(range(18)) + (2, 6, 7, 10, 14, 15)
HOLD_FIRE = 10
SCORE_REGIONS = (np.s_[9:16, 44:52], np.s_[9:16, 108:116])


class Policy:
    def __init__(self, spec: dict):
        self.reset()

    def _start_attack(self, t: int) -> None:
        # Restart the fixed attack sequence for every new possession so a
        # recovery uses the same opening-tuned actions instead of the tail
        # left over from a previous failed attack.
        self.state = "attack"
        self.attack_start = t
        self.rng = np.random.default_rng(0)

    def reset(self) -> None:
        self.t = 0
        self.initial_score = self.last_score = None
        self.score_change_time = 0
        self.recovery_used = False
        self._start_attack(0)

    def act(self, obs, info: dict) -> int:
        t = self.t
        self.t += 1
        scores = tuple(obs[region].tobytes() for region in SCORE_REGIONS)
        if self.initial_score is None:
            self.initial_score = self.last_score = scores
        score_changed = scores != self.last_score
        if score_changed:
            self.score_change_time = t
            self.last_score = scores

        defense = bool(np.any(obs[182, 36] > 40))
        if self.state == "attack" and (defense or score_changed or
                                       t - self.attack_start >= 200):
            self.state = "hold"

        # An early switch from DEF to OFF is a live steal, not a stoppage.
        if (self.state == "hold" and t < 30 and
                scores == self.initial_score and obs[182, 37, 1] > 40 and
                obs[182, 36, 1] < 40):
            self._start_attack(t)

        if self.state == "hold":
            behind = (scores[0] == self.initial_score[0] and
                      scores[1] != self.initial_score[1])
            if (not self.recovery_used and behind and not defense and
                    t - self.score_change_time >= 24):
                self.recovery_used = True
                self.state = "press"
                return 0  # release the held button before starting the possession
            # Start by contesting the ball in place before moving up court.
            return 1 if t < 6 and defense else HOLD_FIRE

        if self.state == "press":
            self._start_attack(t + 1)
            return 1

        return ATTACK_ACTIONS[int(self.rng.integers(len(ATTACK_ACTIONS)))]
