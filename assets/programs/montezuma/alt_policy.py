"""Reach the right-hand rooms while retaining the starting-room key."""

from base_policy import Policy, advance, WAIT, UP, DOWN, RIGHT, LEFT, JUMP, JUMP_RIGHT

# Room 12: the x reached on each walk between laser cycles.
LASER_TARGETS = {12: 25, 14: 49, 16: 77, 18: 101, 20: 129}


class Alt(Policy):
    """Return through rooms 10--13, collect the room 7 key and sword, and
    use the sword on the room 21 spider."""

    def reset(self):
        super().reset()
        self.alt = 0
        self.shortcut_lives = None
        self.room7_retry = False
        self.at = 0
        self.altsteps = 0
        self.sp = None
        self.alt13_ready = False
        self.alt13_still = 0
        self.alt13_gone = False
        self.cross_recovering = False
        self.third11_wait = 0
        self.sword_route = 0
        self.sword_spider = None

    def use_sword(self, obs):
        """Descend from room 13, defeat the room 21 spider, and climb back
        (alt 5, phase 61); then resume the base route at phase 63."""
        room, y, spider = map(int, obs[[3, 43, 44]])
        # With the room 13 spider gone there is nothing to wait for.
        if self.alt13_gone and self.detour_phase == 41:
            self.detour_phase = 42
        if (self.sword_route == 0 and self.alt == 5 and self.extra_phase == 61
                and room == 13 and y >= 240):
            self.sword_route = 1
            self.sword_spider = None
        stage = self.sword_route
        if stage in (1, 6):
            # Wait for the same spider motion before descending and returning.
            go = self.sword_spider is not None and spider <= 55 and spider < self.sword_spider
            self.sword_spider = spider
            if go or self.alt13_gone:
                self.sword_route += 1
                return DOWN if stage == 1 else UP
            return WAIT
        transitions = {
            2: (room == 21 and y >= 240, DOWN, WAIT),
            3: (70 <= spider <= 80, WAIT, DOWN),
            4: (not int(obs[65]) & 32, DOWN, UP),  # sword used on the spider
            5: (room == 13 and y >= 195, UP, WAIT),
            7: (y >= 232, UP, RIGHT),
        }
        if stage in transitions:
            self.sword_route, action = advance(stage, transitions[stage])
            if self.sword_route == 6:
                self.sword_spider = spider
            elif self.sword_route == 8:
                self.extra_phase = 63
            return action
        return None

    def act(self, obs, info):
        action = self.use_sword(obs)
        if action is not None:
            return action
        room, x, y, spider, timer = map(int, obs[[3, 42, 43, 44, 83]])
        if (self.alt == 0 and self.phase == 17 and self.laser_phase == 16
                and self.jump_steps >= 18 and self.extra_phase == 0):
            lives = int(info['lives'])
            if self.shortcut_lives is None:
                self.shortcut_lives = lives
            if lives < self.shortcut_lives:
                if room == 10 and x == 77 and y > 240:
                    self.alt = 1
                    self.at = 0
                return WAIT
            if room == 11 and x < 20:
                self.alt = 1
                self.at = 6
            return RIGHT
        if self.alt == 2 and room == 7 and 54 <= self.extra_phase <= 60:
            action = self.recover_room7_prize(obs, info)
            if action is not None:
                return action
        if self.alt == 4 and room == 7 and 50 <= self.extra_phase <= 54:
            if self.life_lost('room7', int(info['lives'])):
                self.room7_retry = True
            if self.room7_retry:
                if x <= 10 and y == 235 and int(obs[53]) in (8, 18):
                    self.extra_phase = 50
                    self.room7_retry = False
                return WAIT
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
            self.at, action = advance(self.at, stages[self.at])
            if self.at == 6:
                self.alt = 4
                self.extra_phase = 48
            return action
        if self.alt == 4 and self.extra_phase == 54 and x >= 75:
            self.alt = 5
            self.extra_phase = 61
            return DOWN
        return super().act(obs, info)

    def cross_to_room7(self, obs, info, room, x, y, spider, timer):
        """Cross the room 10 bridge, room 11 snakes, room 12 lasers and room 13."""
        if self.life_lost('cross', int(info['lives'])):
            self.cross_recovering = True
        if self.cross_recovering:
            movement = int(obs[53])
            if room == 10 and x == 77 and y > 240 and movement != 26:
                self.at = 0
            elif room in (11, 12, 13) and x < 10 and y == 235 and movement in (8, 18):
                self.at = {11: 6, 12: 11, 13: 22}[room]
                if room == 11:
                    self.third11_wait = 0
                self.alt13_ready = False
                self.alt13_still = 0
                self.alt13_gone = False
                self.sp = None
            else:
                return WAIT
            self.cross_recovering = False
        at = self.at
        if self.third_level and room == 11 and at in (6, 8):
            # Allow the jumping snakes' motion to advance before crossing.
            if x < 10 and self.third11_wait < 8:
                self.third11_wait += 1
                return WAIT
            if x >= 145:
                self.at = 10
            return RIGHT
        # Rows are (completion condition, action while waiting, action on
        # completion). The snake jumps (stages 7 and 9) use a shared seven-step hold.
        crossings = {
            0: (room == 10 and y >= 240, DOWN, WAIT),
            1: (0 < timer <= 12, WAIT, DOWN),
            2: (y <= 235, DOWN, JUMP_RIGHT),
            3: (x >= 99 and y == 235, JUMP_RIGHT, RIGHT),
            4: (x >= 119, RIGHT, JUMP_RIGHT),
            5: (x >= 145, JUMP_RIGHT, RIGHT),
            6: (room == 11 and x >= 33, RIGHT, JUMP_RIGHT),
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
        # The second snake is cleared only by jumps from x 97--99. Walking
        # moves 4 px per step, so a walk that reaches x 96 would next jump
        # from 100. Stop, hop in place, and walk on landing: the landing
        # step moves only part of a step, which shifts the position.
        if at == 8 and room == 11 and x == 96 and int(obs[53]) != 6:
            return WAIT if int(obs[53]) == 18 else JUMP
        if at in crossings:
            self.at, action = advance(at, crossings[at])
            if self.at != at:
                if at in (6, 8):
                    self.altsteps = 1
                elif at == 22:
                    self.sp = spider
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
            # The gap closes 5 px per step. A jump at gap 18 lands on the
            # spider; one at gap 15 clears it.
            if spider - x <= 16:
                self.at = 24
                return JUMP_RIGHT
            return RIGHT
        # at == 27: climb into room 7 and resume the ordinary route.
        if room == 7 and 230 <= y <= 240:
            self.alt = 2
            self.extra_phase = 54
            return super().act(obs, info)
        return UP
