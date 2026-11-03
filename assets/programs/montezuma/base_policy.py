"""Explicit RAM-based route through the first level of Montezuma's Revenge."""

# Atari actions, held for four game frames.
WAIT, JUMP, UP, RIGHT, LEFT, DOWN = 0, 1, 2, 3, 4, 5
JUMP_RIGHT, JUMP_LEFT = 11, 12


class Policy:
    # A zero duration waits for the observation checks in act().
    ROUTE = ((DOWN, 13), (RIGHT, 8), (JUMP_RIGHT, 6), (WAIT, 1),
             (JUMP_RIGHT, 7), (DOWN, 10), (LEFT, 0), (JUMP_LEFT, 7),
             (LEFT, 0), (UP, 10), (LEFT, 3), (JUMP, 8), (RIGHT, 0),
             (WAIT, 0), (LEFT, 3), (JUMP_LEFT, 10), (LEFT, 2))

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
        self.extra_lives = None
        self.return_skull = None
        self.detour_phase = 0
        self.room5_skull = None
        self.detour_steps = 0
        self.room20_recovery = 0
        self.room20_lives = None
        self.first_skull = None
        self.first_skull_staged = False
        self.prev_landed = False

    def act(self, obs, info: dict):
        if self.phase == 12:
            if self.lives is None:
                self.lives = int(info['lives'])
            if int(info['lives']) < self.lives:
                self.phase = 13
                self.elapsed = 0
        if self.phase == 13 and int(obs[42]) == 77 and int(obs[43]) == 235:
            self.phase = 14
            self.elapsed = 0
        if self.phase == 6:
            x, skull = int(obs[42]), int(obs[47])
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
        if self.phase == 8 and int(obs[42]) <= 21:
            self.phase += 1
            self.elapsed = 0
        if self.phase >= len(self.ROUTE):
            return self.navigate_lasers(obs, info)
        action, duration = self.ROUTE[self.phase]
        self.elapsed += 1
        if duration and self.elapsed >= duration:
            self.phase += 1
            self.elapsed = 0
        return action

    def navigate_lasers(self, obs, info):
        # Room 0 treasure, then room 4 spider and the room 10 treasure.
        room, x, timer = int(obs[3]), int(obs[42]), int(obs[83])
        if not self.laser_entered:
            if room != 0 or x < 140:
                return LEFT
            self.laser_entered = True
        if self.laser_phase == 0 and timer >= 32:
            self.laser_phase = 1
        if self.laser_phase == 1 and x <= 130:
            self.laser_phase = 2
        if self.laser_phase == 2 and timer >= 32:
            self.laser_phase = 3
        if self.laser_phase == 3 and x <= 102:
            self.laser_phase = 4
        if self.laser_phase == 4 and x <= 54:
            self.laser_phase = 5
        if self.laser_phase == 5 and timer >= 32:
            self.laser_phase = 6
        if self.laser_phase == 6 and x <= 26:
            self.laser_phase = 7
        if self.laser_phase == 7:
            self.jump_steps += 1
            if self.jump_steps <= 8:
                return JUMP
            self.laser_phase = 8
        if self.laser_phase == 8 and timer >= 32:
            self.laser_phase = 9
        if self.laser_phase == 9 and x >= 54:
            self.laser_phase = 10
        if self.laser_phase == 10 and x >= 74:
            self.laser_phase = 11
        y = int(obs[43])
        if self.laser_phase == 11 and room == 4 and y >= 240:
            self.laser_phase = 12
        if self.laser_phase == 12:
            spider = int(obs[44])
            if spider <= 55 and self.prev_spider is not None and spider < self.prev_spider:
                self.laser_phase = 13
            self.prev_spider = spider
        if self.laser_phase == 13 and room == 10 and y >= 240:
            self.laser_phase = 14
        if self.laser_phase == 14 and y <= 235:
            self.laser_phase = 15
        if self.laser_phase == 15 and x <= 15:
            self.laser_phase = 16
        if self.laser_phase == 16:
            self.jump_steps += 1
            if self.jump_steps <= 18:
                return JUMP
            return self.explore_lower_rooms(obs, info)
        if self.laser_phase in (1, 3, 4, 6, 15):
            return LEFT
        if self.laser_phase in (9, 10):
            return RIGHT
        if self.laser_phase in (11, 13, 14):
            return DOWN
        return WAIT

    def explore_lower_rooms(self, obs, info):
        room, x, y, spider = (int(obs[j]) for j in (3, 42, 43, 44))
        phase = self.extra_phase
        if phase >= 99:
            return self.after_treasure(obs, info)

        if self.detour_phase:
            return self.room23_detour(obs, info)
        if phase == 68:
            if x >= 80 and int(obs[53]) == 4:
                self.detour_phase = 28
                self.detour_steps = 0
                return self.room23_detour(obs, info)
            return WAIT

        # A row is (completion condition, action while waiting, action on completion).
        movement, timer = int(obs[53]), int(obs[83])
        lost_life = self.extra_lives is not None and int(info['lives']) < self.extra_lives
        transitions = {
            # Return from room 10 and descend toward the room 8 key.
            1: (x == 77 and y > 240, WAIT, UP),
            4: (y >= 232, UP, LEFT),
            9: (x <= 79, LEFT, DOWN),
            10: (room == 9 and y > 240, DOWN, DOWN),
            11: (y <= 235, DOWN, LEFT),
            14: (x <= 31, LEFT, JUMP_LEFT),
            15: (room == 8 and x > 100, JUMP_LEFT, DOWN),
            16: (x <= 110, LEFT, JUMP_LEFT),
            17: (movement == 4, JUMP_LEFT, UP),
            19: (lost_life, LEFT, WAIT),
            # Return to room 1 and unlock the right door.
            20: (room == 8 and x > 130 and y == 235, WAIT, RIGHT),
            21: (room == 9 and x <= 10, RIGHT, RIGHT),
            26: (x >= 75, RIGHT, UP),
            27: (room == 3 and 230 <= y <= 240, UP, RIGHT),
            28: (room == 4 and x < 50, RIGHT, RIGHT),
            32: (x <= 76, LEFT, UP),
            33: (room == 0 and 230 <= y <= 235, UP, RIGHT),
            34: (x >= 102, RIGHT, WAIT),
            35: (timer >= 32, WAIT, RIGHT),
            36: (x >= 130, RIGHT, WAIT),
            37: (timer >= 32, WAIT, RIGHT),
            38: (room == 1 and x < 15, RIGHT, RIGHT),
            43: (room == 2 and x < 20, RIGHT, RIGHT),
            # Collect the sword and the keys in rooms 7 and 14.
            44: (x >= 75, RIGHT, DOWN),
            45: (room == 6 and y > 240, DOWN, DOWN),
            46: (y <= 235, DOWN, LEFT),
            47: (x <= 9, LEFT, JUMP),
            48: (y == 235, WAIT, RIGHT),
            49: (room == 7 and x < 20, RIGHT, WAIT),
            50: (timer >= 32, WAIT, RIGHT),
            51: (x >= 27, RIGHT, WAIT),
            52: (timer >= 32, WAIT, RIGHT),
            53: (x >= 55, RIGHT, RIGHT),
            54: (x >= 103, RIGHT, WAIT),
            55: (timer >= 32, WAIT, RIGHT),
            58: (timer >= 32, WAIT, LEFT),
            59: (x <= 103, LEFT, LEFT),
            60: (x <= 75, LEFT, DOWN),
            63: (y <= 237, DOWN, RIGHT),
            64: (room == 14 and x < 20, RIGHT, RIGHT),
            65: (x >= 34, RIGHT, JUMP_RIGHT),
            66: (movement == 4, JUMP_RIGHT, DOWN),
            # Return from the room 23 detour to the room 12 lasers.
            71: (room == 12 and x > 100, LEFT, WAIT),
            # Cross room 12 and open the room 5 doors.
            72: (x <= 131, LEFT, WAIT),
            81: (room == 11 and x > 120, LEFT, LEFT),
            84: (x <= 78, LEFT, UP),
            85: (room == 5 and 155 <= y <= 165, UP, LEFT),
            86: (x <= 57, LEFT, RIGHT),
            87: (x >= 101, RIGHT, RIGHT),
            # Reach the room 5 treasure via both ropes.
            88: (x >= 117, RIGHT, JUMP_RIGHT),
            89: (movement == 4, JUMP_RIGHT, UP),
            91: (y == 198 and movement == 18, JUMP_LEFT, LEFT),
            94: (x <= 53, LEFT, JUMP_LEFT),
            95: (movement == 4, JUMP_LEFT, UP),
            96: (y >= 228, UP, JUMP_RIGHT),
            97: (x >= 74, JUMP_RIGHT, WAIT),
        }
        if phase in transitions:
            complete, action, on_complete = transitions[phase]
            if complete:
                self.extra_phase += 1
                return on_complete
            return action

        # Leave the rope when the skull is moving away from the landing.
        if phase == 90:
            if y < 210:
                return UP
            skull = int(obs[47])
            moving_left = self.room5_skull is not None and skull < self.room5_skull
            self.room5_skull = skull
            if moving_left and 48 <= skull <= 50:
                self.extra_phase = 91
                return JUMP_LEFT
            return WAIT

        if phase == 92:
            skull = int(obs[47])
            moving_right = self.room5_skull is not None and skull > self.room5_skull
            self.room5_skull = skull
            if moving_right and x - skull <= 46:
                self.extra_phase = 93
                self.extra_steps = 1
                return JUMP_LEFT
            return WAIT

        # Start and hold each timed jump. The start counts as its first step.
        jump_starts = {
            7: (x <= 125, LEFT, JUMP_LEFT),
            12: (x <= 61, LEFT, JUMP_LEFT),
            22: (x >= 5, RIGHT, JUMP_RIGHT),
            24: (x >= 41, RIGHT, JUMP_RIGHT),
            29: (spider - x <= 14, RIGHT, JUMP_RIGHT),
            39: (x >= 50, RIGHT, JUMP_RIGHT),
            41: (x >= 88, RIGHT, JUMP_RIGHT),
            82: (x <= 120, LEFT, JUMP_LEFT),
        }
        if phase in jump_starts:
            ready, action, jump = jump_starts[phase]
            if ready:
                self.extra_phase += 1
                self.extra_steps = 1
                return jump
            return action

        # Timed pauses and jump holds: (number of steps, action, last action).
        timed = {
            6: (9, WAIT, LEFT),
            8: (7, JUMP_LEFT, JUMP_LEFT),
            13: (7, JUMP_LEFT, JUMP_LEFT),
            23: (7, JUMP_RIGHT, JUMP_RIGHT),
            25: (7, JUMP_RIGHT, JUMP_RIGHT),
            30: (7, JUMP_RIGHT, JUMP_RIGHT),
            31: (8, WAIT, LEFT),
            40: (6, JUMP_RIGHT, JUMP_RIGHT),
            42: (6, JUMP_RIGHT, JUMP_RIGHT),
            57: (8, WAIT, WAIT),
            83: (7, JUMP_LEFT, JUMP_LEFT),
            93: (7, JUMP_LEFT, JUMP_LEFT),
        }
        if phase in timed:
            duration, action, last_action = timed[phase]
            self.extra_steps += 1
            if self.extra_steps >= duration:
                self.extra_phase += 1
                if phase == 30:
                    self.extra_steps = 0
                return last_action
            return action

        # The remaining phases track lives, enemy motion, or laser crossings.
        if phase == 0:
            if self.extra_lives is None:
                self.extra_lives = int(info['lives'])
            if int(info['lives']) < self.extra_lives:
                self.extra_phase = 1
                return WAIT
            return RIGHT  # Fall from the spent bridge and respawn at the ladder.
        if phase == 2:
            if room == 4 and y >= 195:
                self.extra_phase = 3
                self.prev_spider = spider
                return WAIT
            return UP
        if phase == 3:
            moving_right = self.prev_spider is not None and spider > self.prev_spider
            self.prev_spider = spider
            if spider >= 105 and moving_right:
                self.extra_phase = 4
                return UP
            return WAIT
        if phase == 5:
            if room == 3 and x > 100:
                self.extra_phase = 6
                self.extra_steps = 0
                return WAIT
            return LEFT
        if phase == 18:
            if y >= 235:
                self.extra_phase = 19
                self.extra_lives = int(info['lives'])
                return JUMP
            return UP
        if phase == 56:
            if x >= 131:
                self.extra_phase = 57
                self.extra_steps = 0
                return JUMP
            return RIGHT
        if phase == 61:
            if room == 13 and y > 240:
                self.extra_phase = 62
                self.prev_spider = None
                return WAIT
            return DOWN
        if phase == 62:
            moving_left = self.prev_spider is not None and spider < self.prev_spider
            self.prev_spider = spider
            if spider <= 55 and moving_left:
                self.extra_phase = 63
                return DOWN
            return WAIT
        if phase == 67:
            if y <= 185:
                self.extra_phase = 68
                return JUMP_RIGHT
            return DOWN
        if phase in (73, 75, 77, 79):
            if timer >= 32:
                self.extra_phase += 1
                return LEFT
            return WAIT
        if phase in (74, 76, 78, 80):
            target = {74: 103, 76: 79, 78: 51, 80: 27}[phase]
            if x <= target:
                self.extra_phase += 1
                return WAIT
            return LEFT
        if phase == 98:
            self.extra_phase = 99
            return JUMP
        return WAIT

    def after_treasure(self, obs, info):
        """Return from room 5 and collect the torch and room 20 treasures."""
        room, x, y, skull, movement = (int(obs[j]) for j in (3, 42, 43, 47, 53))
        phase = self.extra_phase
        # On one of the four start-frame phases a jump pressed on the first
        # landed step is ignored and the player walks off the ledge, so wait
        # until the landing has been observed on two consecutive steps.
        if phase == 99:
            landed = y == 235 and movement == 8
            settled = landed and self.prev_landed
            self.prev_landed = landed
            if not settled:
                return WAIT
            self.extra_phase = 100
            return JUMP_LEFT
        # A fall can occur after the first jump as well as on the approach.
        # Retry from the left ledge whenever a crossing costs a life.
        if 113 <= phase <= 117 and room == 20:
            lives = int(info['lives'])
            if self.room20_lives is None:
                self.room20_lives = lives
            elif lives < self.room20_lives:
                self.room20_lives = lives
                self.room20_recovery = 1
                self.extra_phase = 113
                return WAIT
        # Rows are (completion condition, action while waiting, action on completion).
        transitions = {
            99: (y == 235 and movement == 8, WAIT, JUMP_LEFT),
            102: (y == 198 and x >= 58, JUMP_RIGHT, RIGHT),
            105: (x >= 96 and y == 198, JUMP_RIGHT, RIGHT),
            106: (True, JUMP_RIGHT, JUMP_RIGHT),
            107: (movement == 4, JUMP_RIGHT, DOWN),
            108: (y <= 157, DOWN, LEFT),
            109: (x <= 77, LEFT, DOWN),
            110: (room == 19 and y == 235, DOWN, LEFT),
            111: (x <= 17, LEFT, JUMP),
            # The room 19 torch illuminates room 20's disappearing bridge.
            112: (y == 235 and movement == 8, WAIT, RIGHT),
            114: (y == 235 and movement != 6, JUMP_RIGHT, RIGHT),
            115: (x >= 105, RIGHT, JUMP_RIGHT),
            116: (y == 235 and movement != 6, JUMP_RIGHT, RIGHT),
            117: (x >= 140, RIGHT, JUMP),
        }
        if phase in transitions:
            complete, action, on_complete = transitions[phase]
            if complete:
                self.extra_phase += 1
                return on_complete
            return action

        if phase == 100:
            if movement == 4:
                self.extra_phase = 101
                self.return_skull = skull
                return WAIT
            return JUMP_LEFT
        if phase == 101:
            moving_right = self.return_skull is not None and skull > self.return_skull
            self.return_skull = skull
            if 48 <= skull <= 52 and moving_right:
                self.extra_phase = 102
                return JUMP_RIGHT
            return WAIT
        if phase == 103:
            if x >= 66:
                self.extra_phase = 104
                self.return_skull = skull
                return WAIT
            return RIGHT
        if phase == 104:
            moving_left = self.return_skull is not None and skull < self.return_skull
            self.return_skull = skull
            if moving_left and skull - x <= -21:
                self.extra_phase = 105
                return JUMP_RIGHT
            return WAIT
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
        # Cross between the two room 14 ropes, descend, and cross room 22.
        timed = {28: (4, WAIT, 1), 1: (4, DOWN, 2),
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
