"""Reach the right-hand rooms while retaining the starting-room key."""

from base_policy import Policy, WAIT, UP, DOWN, RIGHT, LEFT, JUMP, JUMP_RIGHT

# Room 12: the x reached on each walk between laser cycles.
LASER_TARGETS = {12: 25, 14: 53, 16: 77, 18: 101, 20: 129}


class Alt(Policy):
    """Return through rooms 10--13 and collect the room 7 key and sword."""

    def reset(self):
        super().reset()
        self.alt = 0
        self.at = 0
        self.altsteps = 0
        self.sp = None
        self.alt13_ready = False
        self.alt13_still = 0
        self.alt13_gone = False

    def act(self, obs, info):
        room, x, y, spider, timer = map(int, obs[[3, 42, 43, 44, 83]])
        if self.alt == 0 and self.extra_phase == 32 and x <= 76:
            self.alt = 1
            self.at = 0
        if self.alt == 1:
            return self.cross_to_room7(obs, info, room, x, y, spider, timer)
        if self.alt == 2 and self.extra_phase == 60:
            self.alt = 3
            self.at = 0
        if self.alt == 3:
            # Go left through the room 7 lasers for the room 6 sword; the
            # ordinary route (phase 48) then brings us back.
            stages = {
                0: (x <= 55, LEFT, WAIT),
                1: (timer >= 32, WAIT, LEFT),
                2: (x <= 27, LEFT, WAIT),
                3: (timer >= 32, WAIT, LEFT),
                4: (room == 6 and x > 100, LEFT, LEFT),
                5: (x <= 9, LEFT, JUMP),
            }
            complete, action, on_complete = stages[self.at]
            if complete:
                self.at += 1
                if self.at == 6:
                    self.alt = 4
                    self.extra_phase = 48
                return on_complete
            return action
        if self.alt == 4 and self.extra_phase == 54 and x >= 75:
            self.alt = 5
            self.extra_phase = 61
            return DOWN
        if self.alt == 5 and self.extra_phase == 86:
            # Save the left-hand room 5 door's key for the lower corridor.
            self.extra_phase = 87
        return super().act(obs, info)

    def cross_to_room7(self, obs, info, room, x, y, spider, timer):
        """Cross the room 10 bridge, room 11 snakes, room 12 lasers and room 13."""
        at = self.at
        # Rows are (completion condition, action while waiting, action on
        # completion). The snake jumps (stages 7 and 9) use a shared seven-step hold.
        crossings = {
            0: (room == 10 and y >= 240, DOWN, WAIT),
            1: (0 < timer <= 12, WAIT, DOWN),
            2: (y <= 235, DOWN, JUMP_RIGHT),
            3: (x >= 99 and y == 235, JUMP_RIGHT, RIGHT),
            4: (x >= 119, RIGHT, JUMP_RIGHT),
            5: (x >= 145, JUMP_RIGHT, RIGHT),
            6: (room == 11 and x >= 35, RIGHT, JUMP_RIGHT),
            8: (x >= 97, RIGHT, JUMP_RIGHT),
            10: (room == 12, RIGHT, WAIT),
            # Room 12 lasers: wait for them to switch off, then walk on.
            **{s: (timer >= 32, WAIT, RIGHT) for s in (11, 13, 15, 17, 19, 21)},
            **{s: (x >= t, RIGHT, WAIT) for s, t in LASER_TARGETS.items()},
            22: (room == 13, RIGHT, WAIT),
            24: (x >= 75, JUMP_RIGHT, UP),
            25: (y == 235 and (spider <= 55 or self.alt13_gone), WAIT, LEFT),
            26: (x <= 79, LEFT, UP),
        }
        if at in crossings:
            complete, action, on_complete = crossings[at]
            if complete:
                if at in (6, 8):
                    self.altsteps = 1
                elif at == 22:
                    self.sp = spider
                self.at += 1
                return on_complete
            return action
        if at in (7, 9):
            self.altsteps += 1
            if self.altsteps >= 7:
                self.at += 1
            return JUMP_RIGHT
        if at == 23:
            # Re-enter if the approaching spider has already passed the
            # safe starting point. A vanished spider leaves a fixed RAM x.
            if not self.alt13_ready:
                if room == 12 or x > 100:
                    return RIGHT
                moving_left = self.sp is not None and spider < self.sp
                self.alt13_still = self.alt13_still + 1 if spider == self.sp else 0
                self.sp = spider
                if self.alt13_still >= 8:
                    self.alt13_gone = True
                    self.alt13_ready = True
                elif 96 <= spider <= 102 and moving_left:
                    self.alt13_ready = True
                elif spider < 96 or spider > 102:
                    return LEFT
                else:
                    return WAIT
            if spider - x <= 19:
                self.at = 24
                return JUMP_RIGHT
            return RIGHT
        # at == 27: climb into room 7 and resume the ordinary route.
        if room == 7 and y >= 230:
            self.alt = 2
            self.extra_phase = 54
            return super().act(obs, info)
        return UP
