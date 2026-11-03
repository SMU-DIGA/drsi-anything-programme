"""Collect the lower-corridor treasures and complete the level."""

from alt_policy import Alt
from base_policy import advance, WAIT, LEFT, RIGHT, JUMP, JUMP_LEFT, JUMP_RIGHT


class Extended(Alt):
    """Spend the retained keys, revisit room 20, and reach room 15."""

    def reset(self):
        super().reset()
        self.visit = 0
        self.visit_skull = None
        self.visit_skull_still = 0
        self.entered15 = False
        self.visit_retry = False

    def act(self, obs, info):
        room, x, y, skull, mv, timer = map(int, obs[[3, 42, 43, 47, 53, 83]])
        if self.wait_after_laser_death(obs, info):
            return WAIT
        if self.visit == 0 and self.extra_phase == 112:
            self.visit = 1
        st = self.visit
        # Lives lost outside a room 18 crossing refresh the baseline only.
        lost = self.life_lost('visit', int(info['lives']))
        if room == 18 and (3 <= st <= 7 or st == 10 or 24 <= st <= 28):
            if lost:
                self.visit_retry = True
            if self.visit_retry:
                if st == 10 and x <= 10 and y == 235 and mv in (8, 18):
                    self.visit = 9
                    self.visit_skull = None
                    self.visit_skull_still = 0
                    self.visit_retry = False
                elif (st != 10 and x >= 140 and y == 235
                      and mv in (8, 18)):
                    self.visit = 23 if st >= 24 else 2
                    self.visit_retry = False
                return WAIT
        if st == 0:
            return super().act(obs, info)
        if st in (2, 23):
            # Approach from the safe right ledge on either room 18 crossing.
            if room == 18 and x <= 131:
                return RIGHT
            if room == 18 and 132 <= x <= 135:
                self.visit = st + 1
                self.visit_skull = None
                self.visit_skull_still = 0
                return WAIT
            return LEFT
        if st in (3, 24):
            if x < 132:
                return RIGHT
            if x > 135:
                return LEFT
            if mv != 8:
                return WAIT
            self.visit_skull_still = (self.visit_skull_still + 1
                                      if skull == self.visit_skull else 0)
            gone = self.visit_skull_still >= 8
            skull_min, skull_max = ((84, 102) if self.second_level
                                    else (88, 98))
            go = (8 < timer <= 12 and (gone or (skull_min <= skull <= skull_max
                  and self.visit_skull is not None and skull > self.visit_skull)))
            self.visit_skull = skull
            if go:
                self.visit = st + 1
                return LEFT
            return WAIT
        if st == 9:
            # Return across room 18 after opening both room 17 doors.
            if room == 18 and 25 <= x <= 40:
                self.visit = 10
                self.visit_skull = None
                self.visit_skull_still = 0
                return WAIT
            return RIGHT
        if st == 10:
            # The skull turns at x 34, close enough to kill a player waiting
            # at x 27-28. Step back while it is at that end of its patrol and
            # return to the same spot (walking is 4 px per step).
            self.visit_skull_still = (self.visit_skull_still + 1
                                      if skull == self.visit_skull else 0)
            gone = self.visit_skull_still >= 8
            if skull <= 44 and not gone:
                self.visit_skull = skull
                return LEFT if x > 14 else WAIT
            if x < 25:
                self.visit_skull = skull
                return RIGHT
            # The bridge returns two steps after the countdown is at most 8
            # (the countdown's residue mod 4 depends on the start frame).
            # Probed on every residue: any leftward skull in 45..114 is
            # jumped safely, whereas a narrow 55..65 window can never
            # coincide with the bridge on some start frames.
            go = (0 < timer <= 4 and (gone or (45 <= skull <= 85
                  and self.visit_skull is not None and skull < self.visit_skull)))
            self.visit_skull = skull
            if go:
                self.visit = 11
                return RIGHT
            return WAIT
        if st == 14:
            if room == 19:
                self.visit = 16
                self.extra_phase = 113
                return RIGHT
            return JUMP_RIGHT
        if st == 16:
            # The ordinary room 20 treasure route handles its own retries.
            if self.extra_phase >= 118:
                self.visit = 17
                return WAIT
            return super().act(obs, info)
        if st == 29:
            # The room number may update before the x coordinate wraps.
            if room == 15 and x > 100:
                self.entered15 = True
            if self.entered15 and room == 15 and x <= 17:
                self.visit = 30
                return JUMP
            return LEFT

        # The second leftward crossing repeats stages 4--7 as stages 25--28.
        stage = st - 21 if 25 <= st <= 28 else st
        transitions = {
            1: (y == 235 and mv == 8, WAIT, LEFT),
            4: (x - skull <= 16, LEFT, JUMP_LEFT),
            5: (y == 235 and x < 100, JUMP_LEFT, LEFT),
            6: (x <= 48, LEFT, JUMP_LEFT),
            7: (room == 17, JUMP_LEFT, LEFT),
            8: (room == 17 and x <= 20, LEFT, RIGHT),
            11: (skull - x <= 16, RIGHT, JUMP_RIGHT),
            12: (y == 235 and x > 55, JUMP_RIGHT, RIGHT),
            13: (x >= 103, RIGHT, JUMP_RIGHT),
            17: (y == 235 and mv == 8, WAIT, LEFT),
            18: (x <= 132, LEFT, WAIT),
            19: (0 < timer <= 4, WAIT, JUMP_LEFT),
            20: (y == 235 and x <= 110, JUMP_LEFT, LEFT),
            21: (x <= 47, LEFT, JUMP_LEFT),
            22: (room == 19, JUMP_LEFT, LEFT),
        }
        if stage in transitions:
            self.visit, action = advance(st, transitions[stage])
            return action
        return WAIT
