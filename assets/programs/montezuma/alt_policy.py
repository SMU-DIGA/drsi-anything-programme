"""Reach the right-hand rooms while retaining the starting-room key."""

from base_policy import Policy, WAIT, UP, DOWN, RIGHT, LEFT, JUMP, JUMP_RIGHT

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

    def act(self, o, i):
        (room, x, y, spider, timer) = map(int, o[[3, 42, 43, 44, 83]])
        if self.alt == 0 and self.extra_phase == 32 and (x <= 76):
            self.alt = 1
            self.at = 0
        if self.alt == 1:
            # Cross the room 10 bridge, the two snakes, and room 12 lasers.
            a = WAIT
            # Each row gives the completion test and the actions before and
            # after it. The snake jumps use the shared seven-step hold below.
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
            }
            if self.at in crossings:
                complete, a, on_complete = crossings[self.at]
                if complete:
                    if self.at in (6, 8):
                        self.altsteps = 1
                    self.at += 1
                    a = on_complete
            elif self.at in (7, 9):
                a = JUMP_RIGHT
                self.altsteps += 1
                if self.altsteps >= 7:
                    self.at += 1
            elif 11 <= self.at <= 21:
                if self.at % 2 == 1:
                    a = WAIT
                    if timer >= 32:
                        self.at += 1
                        a = RIGHT
                else:
                    a = RIGHT
                    target = {12: 25, 14: 53, 16: 77, 18: 101, 20: 129}[self.at]
                    if x >= target:
                        self.at += 1
                        a = WAIT
            elif self.at == 22:
                a = RIGHT
                if room == 13:
                    self.at = 23
                    self.sp = spider
                    a = WAIT
            elif self.at == 23:
                # Re-enter if the approaching spider has already passed the
                # safe starting point. A vanished spider leaves a fixed RAM x.
                if not self.alt13_ready:
                    if room == 12:
                        return RIGHT
                    if x > 100:
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
                a = RIGHT
                if spider - x <= 19:
                    self.at = 24
                    a = JUMP_RIGHT
            elif self.at == 24:
                a = JUMP_RIGHT
                if x >= 75:
                    self.at = 25
                    a = UP
            elif self.at == 25:
                if y == 235 and (spider <= 55 or self.alt13_gone):
                    self.at = 26
                    a = LEFT
            elif self.at == 26:
                a = LEFT
                if x <= 79:
                    self.at = 27
                    a = UP
            elif self.at == 27:
                a = UP
                if room == 7 and y >= 230:
                    self.alt = 2
                    self.extra_phase = 54
                    return super().act(o, i)
            return a
        if self.alt == 2 and self.extra_phase == 60:
            self.alt = 3
            self.at = 0
        if self.alt == 3:
            # Go left through the lasers for the room 6 sword, then return.
            if self.at == 0:
                if x <= 55:
                    self.at = 1
                    return WAIT
                return LEFT
            if self.at == 1:
                if timer >= 32:
                    self.at = 2
                    return LEFT
                return WAIT
            if self.at == 2:
                if x <= 27:
                    self.at = 3
                    return WAIT
                return LEFT
            if self.at == 3:
                if timer >= 32:
                    self.at = 4
                    return LEFT
                return WAIT
            if self.at == 4:
                if room == 6 and x > 100:
                    self.at = 5
                return LEFT
            if self.at == 5:
                if x <= 9:
                    self.alt = 4
                    self.extra_phase = 48
                    return JUMP
                return LEFT
        if self.alt == 4 and self.extra_phase == 54 and (x >= 75):
            self.alt = 5
            self.extra_phase = 61
            return DOWN
        if self.alt == 5 and self.extra_phase == 86:
            # Save the left-hand room 5 door's key for the lower corridor.
            self.extra_phase = 87
        return super().act(o, i)
