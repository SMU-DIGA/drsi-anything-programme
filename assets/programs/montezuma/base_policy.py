"""Explicit RAM-based route through the first level of Montezuma's Revenge."""

# Atari actions, held for four game frames.
WAIT, JUMP, UP, RIGHT, LEFT, DOWN = 0, 1, 2, 3, 4, 5
JUMP_RIGHT, JUMP_LEFT = 11, 12

# Action held during each navigate_lasers stage (WAIT when absent).
LASER_ACTIONS = {1: LEFT, 3: LEFT, 4: LEFT, 6: LEFT, 15: LEFT,
                 9: RIGHT, 10: RIGHT, 11: DOWN, 13: DOWN, 14: DOWN}

# explore_lower_rooms timed phases: (total steps including the step that
# entered the phase, action, action on the last step).
TIMED = {
    6: (10, WAIT, LEFT),
    8: (7, JUMP_LEFT, JUMP_LEFT),
    13: (7, JUMP_LEFT, JUMP_LEFT),
    57: (9, WAIT, WAIT),
    83: (7, JUMP_LEFT, JUMP_LEFT),
}


# RAM[53] movement states during a death or fall.
FALLING = (22, 26, 30)


def advance(stage, transition):
    """Apply a sequential route row: condition, action, action on completion."""
    complete, action, on_complete = transition
    return (stage + 1, on_complete) if complete else (stage, action)


def standing_jump(x, lo, hi, movement, rightward):
    """Step into lo <= x <= hi, then jump from standing; None unless standing.

    A sticky repeat only delays a standing jump in place, whereas it can
    shift a running jump's take-off by a step.
    """
    if movement == 18:  # still settling after a landing
        return WAIT
    if movement != 8:
        return None
    if lo <= x <= hi:
        return JUMP_RIGHT if rightward else JUMP_LEFT
    if rightward:
        return RIGHT if x < lo else LEFT
    return LEFT if x > hi else RIGHT


def climb_from_respawn(x, y, movement):
    """WAIT while dying, then climb a central ladder to its floor; else None."""
    if movement in FALLING:
        return WAIT
    if x == 77 and y != 235:
        return UP if y < 235 else DOWN
    return None


class Policy:
    # Level-specific timings; set on later-level controllers and their helpers.
    second_level = False
    third_level = False

    # Phases 0--5 use position checks; a zero duration below also waits for
    # the corresponding observation check in act().
    ROUTE = {
        6: (LEFT, 0), 7: (JUMP_LEFT, 7), 8: (LEFT, 0),
        9: (UP, 10), 10: (LEFT, 3), 11: (JUMP, 8),
        12: (RIGHT, 0), 13: (WAIT, 0), 14: (LEFT, 2),
        15: (JUMP_LEFT, 10), 16: (LEFT, 2),
    }

    def __init__(self, spec: dict):
        self.reset()

    def reset(self):
        self.phase = 0
        self.elapsed = 0
        self.lives = None
        self.laser_entered = False
        self.laser_phase = 0
        self.jump_steps = 0
        self.prev_spider = None
        self.extra_phase = 0
        self.extra_steps = 0
        self.detour_phase = 0
        self.detour_steps = 0
        self.detour_retry = False
        self.detour_out_retry = False
        self.room13_realign = False
        self.room20_recovery = 0
        self.room20_lives = None
        self.room20_jumping = False
        self.first_skull = None
        self.first_skull_staged = False
        self.opening_recover = False
        self.opening_retry = False
        self.opening_last_skull = None
        self.opening_still = 0
        self.prize_retry = False
        self.laser_retry = set()
        self.life_baselines = {}

    def life_lost(self, section, lives):
        """Update the life count seen in a route section; True if it fell."""
        previous = self.life_baselines.get(section)
        self.life_baselines[section] = lives
        return previous is not None and lives < previous

    def act(self, obs, info: dict):
        # Align with the first rope using observed position instead of elapsed
        # steps: sticky inputs can delay both leaving the ladder and jumping.
        x, y, movement = (int(obs[j]) for j in (42, 43, 53))
        if self.phase <= 11 and int(obs[3]) == 1:
            if self.life_lost('opening', int(info['lives'])):
                self.opening_recover = True
            if self.opening_recover:
                if x == 77 and y == 235 and movement in (8, 18):
                    self.phase = 0
                    self.elapsed = 0
                    self.first_skull = None
                    self.first_skull_staged = False
                    self.opening_recover = False
                    self.opening_retry = True
                else:
                    return WAIT
        opening = {
            # Down the start ladder, then jump onto the rope.
            0: (y <= 199, DOWN, DOWN),
            1: (x >= 92 and y == 192, RIGHT, JUMP_RIGHT),
            2: (movement == 4, JUMP_RIGHT, WAIT),
            # Jump to the right ledge and climb down its ladder.
            4: (x >= 130 and y <= 205, JUMP_RIGHT, DOWN),
            5: (y <= 148 and x >= 120, DOWN, DOWN),
        }
        if self.phase in opening:
            self.phase, action = advance(self.phase, opening[self.phase])
            self.elapsed = 0
            return action
        if self.phase == 3:
            # Ensure the jump button is released before jumping from the rope.
            self.elapsed += 1
            if self.elapsed >= 3:
                self.phase = 4
                return JUMP_RIGHT
            return WAIT
        if self.phase == 12:
            # After the key, walk right until a life is lost: the quickest
            # way back. Phase 13 waits for the respawn at x 77.
            if self.lives is None:
                self.lives = int(info['lives'])
            if int(info['lives']) < self.lives:
                self.phase = 13
                self.elapsed = 0
        if self.phase == 13 and x == 77 and y == 235:
            self.phase = 14
            self.elapsed = 0
        if self.phase == 6:
            if self.opening_skull_vanished(obs):
                self.phase = 8
                return LEFT
            skull = int(obs[47])
            if not self.first_skull_staged:
                moving_right = self.first_skull is not None and skull > self.first_skull
                self.first_skull = skull
                if moving_right and 34 <= skull <= 36:
                    self.first_skull_staged = True
                else:
                    return WAIT
            # Walking closes the gap 5 px per step, so the jump gap used to
            # depend on the start frame (49 or 44 are each fatal on some
            # start frames). Stand still while the skull closes 1 px per step
            # so the jump always starts at a gap of exactly 48.
            gap = x - skull
            if gap <= 48:
                self.phase += 1
                self.elapsed = 0
            elif gap <= 52:
                return WAIT
        if self.phase == 8 and x <= 21:
            self.phase += 1
            self.elapsed = 0
        if self.phase >= 17:
            return self.navigate_lasers(obs, info)
        action, duration = self.ROUTE[self.phase]
        self.elapsed += 1
        if duration and self.elapsed >= duration:
            self.phase += 1
            self.elapsed = 0
        return action

    def opening_skull_vanished(self, obs):
        """After an opening death, the skull may disappear and freeze in RAM."""
        if not self.opening_retry:
            return False
        skull = int(obs[47])
        self.opening_still = self.opening_still + 1 if skull == self.opening_last_skull else 0
        self.opening_last_skull = skull
        return self.opening_still >= 8

    def recover_room7_prize(self, obs, info):
        """After a prize-trip death, return from the room 7 ladder."""
        x, y, movement = (int(obs[j]) for j in (42, 43, 53))
        if self.life_lost('prize', int(info['lives'])):
            self.prize_retry = True
        if not self.prize_retry:
            return None
        action = climb_from_respawn(x, y, movement)
        if action is not None:
            return action
        if 74 <= x <= 80 and y == 235:
            self.extra_phase = 54
            self.prize_retry = False
            return RIGHT
        return WAIT

    def wait_after_laser_death(self, obs, info, room0=True):
        """True while waiting for the right-edge respawn after a death in the
        room 0 (if room0) or room 12 return lasers; then restart the crossing."""
        room, x, y, movement = (int(obs[j]) for j in (3, 42, 43, 53))
        if room0 and room == 0 and self.phase >= 17 and self.laser_phase <= 6:
            section = 'first_laser'
        elif room == 12 and 71 <= self.extra_phase <= 81:
            section = 'return_laser'
        else:
            return False
        if self.life_lost(section, int(info['lives'])):
            self.laser_retry.add(section)
        if section not in self.laser_retry:
            return False
        if x >= 140 and y == 235 and movement in (8, 18):
            self.laser_retry.discard(section)
            if section == 'first_laser':
                self.laser_phase = 0
                self.laser_entered = False
            else:
                self.extra_phase = 71
        return True

    def navigate_lasers(self, obs, info):
        """Room 0 lasers and treasure, then the room 4 spider and room 10 treasure."""
        room, x, y, spider, timer = (int(obs[j]) for j in (3, 42, 43, 44, 83))
        if not self.laser_entered:
            if room != 0 or x < 140:
                return LEFT
            self.laser_entered = True
        # Completion test of each stage; several stages may end on one step.
        ends = {0: timer >= 32, 1: x <= 130, 2: timer >= 32, 3: x <= 102,
                4: x <= 54, 5: timer >= 32, 6: x <= 26, 8: timer >= 32,
                9: x >= 54, 10: x >= 74, 11: room == 4 and y >= 240,
                13: room == 10 and y >= 240, 14: y <= 235, 15: x <= 15}
        while True:
            stage = self.laser_phase
            if stage in (7, 16):
                # Hold JUMP for the treasure: steps 1-8 in room 0, then
                # (with the same counter) steps 10-18 in room 10.
                self.jump_steps += 1
                if self.jump_steps <= (8 if stage == 7 else 18):
                    return JUMP
                if stage == 16:
                    return self.explore_lower_rooms(obs, info)
                done = True
            elif stage == 12:
                # Descend the room 4 ladder once the spider moves away left.
                done = (spider <= 55 and self.prev_spider is not None
                        and spider < self.prev_spider)
                self.prev_spider = spider
            else:
                done = ends[stage]
            if not done:
                return LASER_ACTIONS.get(stage, WAIT)
            self.laser_phase += 1

    def explore_lower_rooms(self, obs, info):
        room, x, y, spider = (int(obs[j]) for j in (3, 42, 43, 44))
        phase = self.extra_phase
        if phase == 64 and room == 13 and x == 77:
            if y < 235:
                return UP
            if y > 235:
                return DOWN
        if phase == 71 and room == 13:
            if x == 77 and y > 235:
                self.room13_realign = True
            if self.room13_realign and x == 77:
                return DOWN if y > 235 else (UP if y < 235 else LEFT)
            self.room13_realign = False
        if phase == 85:
            # Keep both keys for the exit doors and descend through room 5.
            if room == 5 and 155 <= y <= 165:
                self.extra_phase = 110
                return DOWN
            # A repeated LEFT can carry us past the room 11 ladder.
            if room == 11 and y == 235 and int(obs[53]) != 6:
                if x < 74:
                    return RIGHT
                if x > 80:
                    return LEFT
            return UP
        if phase >= 110:
            return self.collect_lower_treasures(obs, info)

        if self.detour_phase:
            return self.room23_detour(obs, info)
        if phase == 68:
            if x >= 80 and int(obs[53]) == 4:
                self.detour_phase = 28
                self.detour_steps = 0
                return self.room23_detour(obs, info)
            return WAIT

        # A row is (completion condition, action while waiting, action on
        # completion). The completing step counts as step 1 of a TIMED phase.
        movement, timer = int(obs[53]), int(obs[83])
        # A sticky RIGHT can consume the key jump entirely. Retry from the
        # ledge while the room's key flag remains set.
        if phase == 58 and room == 7 and int(obs[66]) & 1:
            return JUMP
        # Phases 0--4 are never used: after the room 10 treasure the first
        # level takes the Alt shortcut and later levels set phase 5 on
        # returning across the room 10 bridge (policy.SecondLevel).
        transitions = {
            # Descend from room 4 toward room 8.
            5: (room == 3 and x > 100, LEFT, WAIT),
            7: (x <= 125, LEFT, JUMP_LEFT),
            9: (x <= 79, LEFT, DOWN),
            10: (room == 9 and y > 240, DOWN, DOWN),
            11: (y <= 235, DOWN, LEFT),
            12: (x <= 61, LEFT, JUMP_LEFT),
            14: (x <= 31, LEFT, JUMP_LEFT),
            15: (room == 8 and x > 100, JUMP_LEFT, DOWN),
            # Active controllers bypass phases 16--47 and resume here for
            # the sword and keys in rooms 7 and 14.
            48: (y == 235, WAIT, RIGHT),
            49: (room == 7 and x < 20, RIGHT, WAIT),
            50: (timer >= 32, WAIT, RIGHT),
            51: (x >= 27, RIGHT, WAIT),
            52: (timer >= 32, WAIT, RIGHT),
            53: (x >= 55, RIGHT, RIGHT),
            54: (x >= 103, RIGHT, WAIT),
            55: (timer >= 32, WAIT, RIGHT),
            56: (x >= 127, RIGHT, JUMP),
            58: (timer >= 32, WAIT, LEFT),
            59: (x <= 103, LEFT, LEFT),
            60: (x <= 75, LEFT, DOWN),
            63: (y <= 237, DOWN, RIGHT),
            64: (room == 14 and x < 20, RIGHT, RIGHT),
            65: (x >= 30, RIGHT, JUMP_RIGHT),
            66: (movement == 4, JUMP_RIGHT, DOWN),
            # Return from the room 23 detour to the room 12 lasers.
            71: (room == 12 and x > 100, LEFT, WAIT),
            # Cross room 12 and climb to room 5.
            72: (x <= 131, LEFT, WAIT),
            **{p: (timer >= 32, WAIT, LEFT) for p in (73, 75, 77, 79)},
            **{p: (x <= t, LEFT, WAIT)
               for p, t in ((74, 103), (76, 79), (78, 51), (80, 27))},
            81: (room == 11 and x > 120, LEFT, LEFT),
            82: (x <= (122 if ((int(info['lives']) == 3 and spider < 60)
                               or (int(info['lives']) <= 2 and spider >= 100))
                    else 120), LEFT, JUMP_LEFT),
            84: (x <= 78, LEFT, UP),
        }
        if phase in transitions:
            self.extra_phase, action = advance(phase, transitions[phase])
            self.extra_steps = 1
            return action

        # The first rope can be caught at different heights when a jump is
        # delayed. Align before transferring to the right-hand rope.
        if phase == 67:
            if y < 185:
                return UP
            if y > 189:
                return DOWN
            self.extra_phase = 68
            return JUMP_RIGHT

        # Timed pauses and jump holds, counting the step that entered them:
        # (total steps, action, last action).
        if phase in TIMED:
            duration, action, last_action = TIMED[phase]
            self.extra_steps += 1
            if self.extra_steps >= duration:
                self.extra_phase += 1
                self.extra_steps = 1
                return last_action
            return action

        if phase == 61:
            # Descend into room 13; alt_policy.Alt.use_sword takes over there
            # and resumes this route at phase 63.
            return DOWN
        return WAIT

    def collect_lower_treasures(self, obs, info):
        """Collect the room 19 torch and room 20 treasures."""
        room, x, y, movement = (int(obs[j]) for j in (3, 42, 43, 53))
        phase = self.extra_phase
        # A fall can occur after the first jump as well as on the approach.
        # Retry from the left ledge whenever a crossing costs a life.
        if 113 <= phase <= 117 and room == 20:
            lives = int(info['lives'])
            lost = self.room20_lives is not None and lives < self.room20_lives
            # A treasure may award an extra life during the crossing.
            self.room20_lives = lives
            if lost:
                self.room20_recovery = 1
                self.room20_jumping = False
                self.extra_phase = 113
                return WAIT
        # A repeated RIGHT can delay a jump by a whole call. Wait until we
        # have observed the player airborne before accepting a landing.
        if phase in (114, 116):
            if movement == 6 and y > 235:
                self.room20_jumping = True
            if self.room20_jumping and y == 235 and movement != 6:
                self.room20_jumping = False
                self.extra_phase += 1
                return RIGHT
            return JUMP_RIGHT
        # Rows are (completion condition, action while waiting, action on completion).
        transitions = {
            110: (room == 19 and y == 235, DOWN, LEFT),
            111: (x <= 17, LEFT, JUMP),
            # The room 19 torch illuminates room 20's disappearing bridge.
            112: (y == 235 and movement == 8, WAIT, RIGHT),
            115: (x >= 105, RIGHT, JUMP_RIGHT),
            117: (x >= 140, RIGHT, JUMP),
        }
        if phase in transitions:
            self.extra_phase, action = advance(phase, transitions[phase])
            return action

        if phase == 113:
            if room == 20 and self.room20_recovery == 0:
                self.room20_recovery = 2
            if self.room20_recovery == 1:
                if room == 20 and x < 10 and y == 235:
                    self.room20_recovery = 2
                return WAIT
            if self.room20_recovery == 2:
                if x < 25:
                    return RIGHT
                if not 0 < int(obs[83]) <= 4:
                    return WAIT
                self.room20_recovery = 3
            if room == 20 and x >= 65:
                self.extra_phase = 114
                return JUMP_RIGHT
            return RIGHT
        return WAIT

    def room23_detour(self, obs, info):
        """Collect the three dark-room treasures and return via rooms 22 and 21."""
        room, x, y, skull, movement = (int(obs[j]) for j in (3, 42, 43, 47, 53))
        stage = self.detour_phase
        if self.life_lost('detour', int(info['lives'])):
            if stage in (35, 45, 46, 36, 37, 38):
                self.detour_retry = True
            if room == 22 and stage in (5, 6, 7, 8, 9):
                self.detour_out_retry = True
        if self.detour_out_retry:
            if room == 22 and x == 77 and y >= 240 and movement in (0, 10):
                self.detour_phase = 5
                self.detour_steps = 1
                self.detour_out_retry = False
            return WAIT
        if self.detour_retry:
            # A death on the final bridge crossing respawns at its ladder.
            if room == 22 and x == 77 and y >= 240 and movement in (0, 10):
                self.detour_phase = 45
                self.detour_retry = False
            return WAIT
        # Cross between the two room 14 ropes, descend, and cross room 22.
        timed = {28: (4, WAIT, 1), 1: (2, DOWN, 2),
                 2: (8, JUMP_LEFT, 3), 3: (15, DOWN, 4),
                 4: (3, RIGHT, 5),
                 6: (7, JUMP_RIGHT, 7), 7: (4, RIGHT, 8),
                 8: (8, JUMP_RIGHT, 9)}
        if stage in timed:
            duration, action, next_stage = timed[stage]
            self.detour_steps += 1
            if self.detour_steps >= duration:
                self.detour_steps = 0
                self.detour_phase = next_stage
            return action

        # Wait on the ladder until the bridge is about to reappear.
        if stage == 5:
            if self.detour_steps == 0:
                if room == 14 and y == 160:
                    if x < 74:
                        return RIGHT
                    if x > 80:
                        return LEFT
                if room == 22 and y >= 240:
                    self.detour_steps = 1
                return DOWN
            if self.detour_steps == 1:
                if 0 < int(obs[83]) <= 12:
                    self.detour_steps = 2
                    return DOWN
                return WAIT
            if y <= 235:
                self.detour_steps = 0
                self.detour_phase = 6
                return JUMP_RIGHT
            return DOWN

        # A repeated LEFT can carry us past the room 22 ladder; realign
        # before climbing, and after a fall wait on the right ledge again.
        if stage == 24 and room == 22 and y == 235 and movement != 6:
            if x > 100:
                self.detour_phase = 17
                return WAIT
            if x < 75:
                return RIGHT
            if x > 79:
                return LEFT

        # Rows are (condition, action while waiting, action on completion, next stage).
        transitions = {
            # Jump the skull and collect the three treasures in room 23.
            9: (room == 23 and x - skull >= 21, RIGHT, JUMP_RIGHT, 10),
            10: (y == 235 and x >= 85 and movement != 6, JUMP_RIGHT, RIGHT, 11),
            11: (x >= 97, RIGHT, JUMP, 12),
            12: (y == 235 and movement == 8, WAIT, RIGHT, 13),
            14: (y == 235 and movement == 8, WAIT, LEFT, 43),
            43: (x <= 117, LEFT, JUMP, 44),
            44: (y == 235 and movement == 8, WAIT, LEFT, 15),
            15: (x - skull <= 48, LEFT, JUMP_LEFT, 16),
            16: (y == 235 and movement != 6, JUMP_LEFT, LEFT, 17),
            # Return across room 22 after respawning at its right ledge.
            22: (y == 235 and x <= 110 and movement != 6, JUMP_LEFT, LEFT, 23),
            23: (x <= 78, LEFT, UP, 24),
            24: (room == 14 and y == 160, UP, DOWN, 35),
            # Time the second descent so the bridge is present when we land.
            35: (room == 22 and y >= 240, DOWN, WAIT, 45),
            45: (8 <= int(obs[83]) <= 12, WAIT, DOWN, 46),
            46: (y == 235, DOWN, JUMP_LEFT, 36),
            36: (y == 235 and x <= 55 and movement != 6, JUMP_LEFT, LEFT, 37),
            37: (x <= 43, LEFT, JUMP_LEFT, 38),
            38: (room == 21 and x > 100, JUMP_LEFT, LEFT, 39),
            39: (x <= 77, LEFT, UP, 40),
        }
        if stage in transitions:
            complete, action, on_complete, next_stage = transitions[stage]
            if complete:
                self.detour_phase = next_stage
                return on_complete
            return action

        # The preceding jump can leave us past the rightmost treasure.
        if stage == 13:
            if x < 134:
                return RIGHT
            if x > 138:
                return LEFT
            self.detour_phase = 14
            return JUMP

        # Wait on the right ledge for the bridge to return, rather than
        # falling and spending a life before the return crossing.
        if stage == 17:
            if room == 22 and x <= 132:
                if 0 < int(obs[83]) <= 4:
                    self.detour_phase = 22
                    return JUMP_LEFT
                return WAIT
            return LEFT
        if stage == 40:
            if room == 21 and y == 235:
                if x < 74:
                    return RIGHT
                if x > 80:
                    return LEFT
            if room == 13 and y >= 195:
                self.detour_phase = 41
                self.prev_spider = int(obs[44])
                return WAIT
            return UP
        if stage == 41:
            spider = int(obs[44])
            moving_right = self.prev_spider is not None and spider > self.prev_spider
            self.prev_spider = spider
            if spider >= 105 and moving_right:
                self.detour_phase = 42
                return UP
            return WAIT
        if stage == 42:
            if y >= 232:
                self.detour_phase = 0
                self.extra_phase = 71
                return LEFT
            return UP
        return WAIT
