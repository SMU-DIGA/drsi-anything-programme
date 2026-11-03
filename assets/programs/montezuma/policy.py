"""Episode controller: complete the first level and continue on the next."""
from alternate_extended import Extended
from alt_policy import Alt
from base_policy import Policy as FirstLevelRoute, DOWN, UP, LEFT, RIGHT, JUMP, JUMP_LEFT, JUMP_RIGHT, WAIT


class SecondLevel(FirstLevelRoute):
    """Reuse the early route with the faster skull on the second level."""

    def reset(self):
        super().reset()
        self.gem_stage = 0
        self.gem_lives = None
        self.lower_stage = 0
        self.lower_steps = 0
        self.lower_treasure = 0
        self.bridge_return = 0
        self.exit_route = 0
        self.key_return = 0
        self.crossing = Alt({})
        self.finish = Extended({})

    def room8_treasures(self, obs, info):
        """Use the center rope to collect the two prizes above the pit."""
        room, x, y, movement = (int(obs[j]) for j in (3, 42, 43, 53))
        stage = self.gem_stage
        # Rows are (completion condition, action while waiting, action on completion).
        transitions = {
            # Jump to the centre rope and climb (again after the respawn).
            0: (x <= 115, LEFT, JUMP_LEFT),
            1: (movement == 4, JUMP_LEFT, UP),
            4: (x <= 115, LEFT, JUMP_LEFT),
            5: (x <= 101, JUMP_LEFT, JUMP_LEFT),
            6: (movement == 4, WAIT, UP),
            # Return from room 8 to the ladder above room 4.
            10: (room == 9 and 75 <= x <= 82, RIGHT, UP),
            11: (room == 3 and 230 <= y <= 240, UP, RIGHT),
            12: (room == 4 and 22 <= x <= 45, RIGHT, JUMP_RIGHT),
            13: (x >= 50 and y == 235, JUMP_RIGHT, RIGHT),
            14: (x >= 75, RIGHT, UP),
        }
        if stage in transitions:
            complete, action, on_complete = transitions[stage]
            if complete:
                self.gem_stage += 1
                if stage == 14:
                    self.extra_phase = 33
                return on_complete
            return action
        if stage in (2, 7):
            if y >= 235:
                self.gem_stage += 1
                self.gem_lives = int(info['lives'])
                return JUMP_LEFT if stage == 2 else JUMP_RIGHT
            return UP
        if stage == 3:
            lives = int(info['lives'])
            self.gem_lives = max(self.gem_lives, lives)
            if lives < self.gem_lives:
                self.gem_stage = 31
                return WAIT
            return LEFT
        if stage in (31, 9):
            if x >= 140 and y == 235 and movement in (8, 18):
                self.gem_stage = 4 if stage == 31 else 10
                return LEFT if stage == 31 else RIGHT
            return WAIT
        if stage == 8:
            if int(info['lives']) < self.gem_lives:
                self.gem_stage = 9
                return WAIT
            return RIGHT
        return WAIT

    def return_across_room20(self, room, x, y, mv, timer):
        # Re-cross room 20 to collect the two prizes above the bridge.
        stage = self.bridge_return
        transitions = {
            0: (y == 235 and mv == 8, WAIT, LEFT),
            1: (x <= 132, LEFT, WAIT),
            2: (0 < timer <= 20, WAIT, JUMP_LEFT),
            3: (y == 235 and x <= 110, JUMP_LEFT, LEFT),
            4: (x <= 103, LEFT, JUMP_LEFT),
            5: (y == 235 and x <= 80, JUMP_LEFT, LEFT),
            6: (x <= 73, LEFT, JUMP_LEFT),
            7: (y == 235 and x <= 55, JUMP_LEFT, LEFT),
            9: (room == 19 or (x <= 25 and y == 235), JUMP_LEFT, LEFT),
        }
        if stage in transitions:
            complete, action, on_complete = transitions[stage]
            if complete:
                self.bridge_return += 1
                return on_complete
            return action
        if stage == 8 and room == 20 and x <= 50 and y == 235:
            self.bridge_return = 9
            return JUMP_LEFT
        if room == 19 and x <= 17:
            return WAIT
        return LEFT

    def lower_corridor(self, obs, room, x, y, enemy, timer):
        """Collect the dark-room prizes and return toward rooms 5 and 20."""
        # Continue from the room 7 ladder into the dark lower corridor.
        mv = int(obs[53])
        if self.lower_stage == 0 and self.extra_phase == 61 and room == 21 and y == 235:
            self.lower_stage = 1
        if self.lower_stage == 1:
            if room == 22:
                self.lower_stage = 2
                self.lower_steps = 0
            elif x < 145:
                return RIGHT
            elif 100 <= int(obs[0]) % 128 <= 103:
                return RIGHT
            else:
                return WAIT
        if self.lower_stage == 2:
            if room == 23:
                self.lower_stage = 3
            else:
                n = self.lower_steps
                self.lower_steps += 1
                if n < 3:
                    return WAIT
                if n < 10:
                    return JUMP_RIGHT
                if n == 10:
                    return RIGHT
                if n < 18:
                    return JUMP_RIGHT
                return RIGHT
        if self.lower_stage == 3:
            if self.lower_treasure >= 6:
                self.lower_stage = 4
            elif self.lower_treasure % 2 == 0:
                target = (97, 117, 137)[self.lower_treasure // 2]
                if x >= target:
                    self.lower_treasure += 1
                    return JUMP
                return RIGHT
            elif y == 235 and mv == 8:
                self.lower_treasure += 1
                return RIGHT
            else:
                return WAIT
        # Return through room 22, use the room 14 ropes, and descend again.
        # Rows are (completion condition, action while waiting, next action).
        transitions = {
            4: (room == 22 and x <= 132, LEFT, WAIT),
            5: (0 < timer <= 4, WAIT, JUMP_LEFT),
            6: (y == 235 and x <= 110 and mv != 6, JUMP_LEFT, LEFT),
            7: (x <= 78, LEFT, UP),
            8: (room == 14 and y == 160, UP, JUMP_LEFT),
            9: (mv == 4, JUMP_LEFT, UP),
            10: (y >= 235, UP, JUMP_RIGHT),
            11: (y == 235 and mv == 8, WAIT, DOWN),
            12: (y <= 185, DOWN, JUMP_LEFT),
            13: (mv == 4 and x < 80, JUMP_LEFT, DOWN),
            14: (y <= 160, DOWN, RIGHT),
            15: (x >= 75, RIGHT, DOWN),
            16: (room == 22 and y >= 240, DOWN, WAIT),
            17: (8 <= timer <= 12, WAIT, DOWN),
            18: (y == 235, DOWN, LEFT),
            19: (x - enemy <= 20, LEFT, JUMP_LEFT),
            20: (y == 235 and x < enemy, JUMP_LEFT, LEFT),
            22: (x <= 78, LEFT, UP),
            23: (room == 13 and 232 <= y <= 240, UP, LEFT),
            24: (x - enemy <= 10, LEFT, JUMP_LEFT),
            25: (y == 235 and x < enemy, JUMP_LEFT, LEFT),
        }
        if self.lower_stage in transitions:
            complete, action, on_complete = transitions[self.lower_stage]
            if complete:
                self.lower_stage += 1
                return on_complete
            return action
        if self.lower_stage == 21:
            if room == 21 and x > 100:
                self.lower_stage = 22
            return LEFT
        if self.lower_stage == 26:
            if room == 12 and x > 100:
                self.lower_stage = 27
                self.extra_phase = 71
            else:
                return LEFT
        if self.lower_stage == 27 and self.extra_phase == 86 and room == 5:
            # The single key opens the right door, which leads to the prize.
            self.extra_phase = 87
        # The room 5 skull moves twice as fast on the second level. Start
        # the platform crossing earlier than the first-level jump.
        if self.lower_stage == 27 and self.extra_phase == 92:
            skull = int(obs[47])
            moving_right = self.room5_skull is not None and skull > self.room5_skull
            self.room5_skull = skull
            if moving_right and x - skull <= 52:
                self.extra_phase = 93
                self.extra_steps = 1
                return JUMP_LEFT
            return WAIT
        if self.lower_stage == 27 and self.extra_phase == 104:
            skull = int(obs[47])
            moving_left = self.return_skull is not None and skull < self.return_skull
            self.return_skull = skull
            if moving_left and skull - x <= -15:
                self.extra_phase = 105
                return JUMP_RIGHT
            return WAIT
        # Both room 19 enemies start to the left of the ladder on this level.
        # Head right to the bridge and treasure before they can turn back.
        if (self.lower_stage == 27 and self.extra_phase == 110
                and room == 19 and y == 235):
            self.extra_phase = 113
        if self.lower_stage == 27 and self.extra_phase >= 118:
            return self.return_across_room20(room, x, y, mv, timer)
        return None

    def act(self, obs, info):
        room, x, y, enemy, timer = (int(obs[j]) for j in (3, 42, 43, 44, 83))
        # Cross the room 10 bridge back to its ladder after taking the key.
        # This saves the life previously spent falling from the bridge.
        if (self.key_return == 0 and self.phase == 17 and self.laser_phase == 16
                and self.jump_steps >= 18 and room == 10):
            self.key_return = 1
        key_crossing = {
            1: (x >= 25, RIGHT, WAIT),
            2: (0 < timer <= 4, WAIT, RIGHT),
            3: (x >= 75, RIGHT, UP),
            4: (room == 4 and 230 <= y <= 240, UP, LEFT),
        }
        if self.key_return in key_crossing:
            complete, action, on_complete = key_crossing[self.key_return]
            if complete:
                self.key_return += 1
                if self.key_return == 5:
                    self.extra_phase = 5
                return on_complete
            return action
        # Retain the room 10 key by descending from room 4 directly to the
        # lower corridor instead of opening the starting room's right door.
        if self.exit_route == 0 and self.gem_stage == 14 and room == 4 and x >= 75:
            self.exit_route = 1
            self.crossing.at = 0
        if self.exit_route == 1 and self.crossing.at >= 23:
            self.exit_route = 2
        if self.exit_route == 1:
            return self.crossing.cross_to_room7(obs, info, room, x, y, enemy, timer)
        exit_crossing = {
            2: (room == 13 and x < 100 and enemy - x <= 10, RIGHT, JUMP_RIGHT),
            3: (y == 235 and x > enemy, JUMP_RIGHT, RIGHT),
            4: (x >= 75, RIGHT, UP),
        }
        if self.exit_route in exit_crossing:
            complete, action, on_complete = exit_crossing[self.exit_route]
            if complete:
                self.exit_route += 1
                return on_complete
            return action
        if self.exit_route == 5:
            if room == 7 and 230 <= y <= 240:
                self.gem_stage = 15
                self.extra_phase = 54
                self.exit_route = 6
            else:
                return UP
        if self.exit_route == 6:
            if self.extra_phase == 60 and room == 7 and 75 <= x <= 80:
                self.extra_phase = 61
                return DOWN
            # Descend the center ladder through room 5 without spending
            # either key, then collect the room 20 prizes.
            if self.lower_stage == 27 and self.extra_phase == 85 and room == 5 and 155 <= y <= 165:
                self.extra_phase = 110
                return DOWN
            if (self.lower_stage == 27 and self.extra_phase >= 118
                    and self.bridge_return >= 8 and room == 19
                    and 10 <= x <= 17 and y == 235):
                self.exit_route = 7
                self.finish.visit = 2
                return LEFT
        if self.exit_route == 7:
            # The safe room 18 ledge starts at x 132; align there before
            # waiting for the bridge and skull cycle.
            if self.finish.visit == 3 and room == 18 and x <= 131:
                return RIGHT
            if self.finish.visit == 8 and room == 17 and x <= 20:
                self.finish.visit = 29
            return self.finish.act(obs, info)
        if self.phase == 0:
            if y <= 199:
                self.phase = 1
                self.elapsed = 0
            return DOWN
        if (self.phase == 6 and self.first_skull_staged
                and x - int(obs[47]) <= 52):
            self.phase = 7
            self.elapsed = 0
        # There is no moving spider on this ladder in the second level.
        if self.laser_phase == 12:
            self.laser_phase = 13
        # The room 4 snake is stationary on this level, so no patrol wait is
        # needed after climbing back up from the room 10 key.
        if self.extra_phase == 3:
            self.extra_phase = 4
        # The sword encounter is complete after entering room 8.
        if ((self.extra_phase >= 16 and room == 8 and self.gem_stage != 15)
                or 6 <= self.gem_stage < 15):
            return self.room8_treasures(obs, info)
        # The sword was already collected on this level. Leave the room 6
        # ladder to the right, with the spider behind us, instead of detouring
        # left and meeting it on the return.
        if (self.extra_phase == 46 and room == 6
                and y <= 235):
            self.extra_phase = 49
            return RIGHT
        action = self.lower_corridor(obs, room, x, y, enemy, timer)
        if action is not None:
            return action
        action = super().act(obs, info)
        if self.extra_phase == 5 and room == 4 and x <= 42:
            return JUMP_LEFT
        return action


class ThirdLevel(SecondLevel):
    """Collect the starting-room key and door on the faster third level."""

    def reset(self):
        super().reset()
        self.third_approaching = False
        self.third_skull = None
        self.third_room0_lives = None
        self.third_room0_recover = False
        self.third_snakes = 0

    def act(self, obs, info):
        if self.phase >= 17 and int(obs[3]) == 0:
            lives = int(info['lives'])
            if self.third_room0_lives is not None and lives < self.third_room0_lives:
                self.third_room0_recover = True
            self.third_room0_lives = lives
            if self.third_room0_recover:
                if (int(obs[42]) >= 140 and int(obs[43]) == 235
                        and int(obs[53]) in (8, 18)):
                    self.third_room0_recover = False
                    self.laser_phase = 0
                    self.laser_entered = False
                else:
                    return WAIT
        if self.key_return == 5 and self.extra_phase == 5 and int(obs[3]) == 4:
            x, y = int(obs[42]), int(obs[43])
            # Walk to each snake, then hold the jump until landing.
            transitions = {
                0: (x <= 62, LEFT, JUMP_LEFT),
                1: (y == 235 and x <= 40, JUMP_LEFT, LEFT),
                2: (x <= 28, LEFT, JUMP_LEFT),
                3: (y == 235 and x <= 15, JUMP_LEFT, LEFT),
            }
            if self.third_snakes in transitions:
                complete, action, on_complete = transitions[self.third_snakes]
                if complete:
                    self.third_snakes += 1
                    return on_complete
                return action
            return LEFT
        if self.phase == 6:
            x, skull = int(obs[42]), int(obs[47])
            moving_left = self.third_skull is not None and skull < self.third_skull
            if moving_left and 62 <= skull <= 70:
                self.third_approaching = True
            self.third_skull = skull
            if not self.third_approaching:
                return WAIT
            if x - skull <= 60:
                self.phase = 7
                self.elapsed = 0
                return JUMP_LEFT
            return LEFT
        return super().act(obs, info)


class Policy:
    def __init__(self, spec):
        self.spec = spec
        self.reset()

    def reset(self):
        self.controller = Extended(self.spec)
        self.second_level = False
        self.third_level = False

    def act(self, obs, info):
        if (not self.second_level and self.controller.visit == 30
                and int(obs[3]) == 1 and int(obs[42]) == 77):
            self.controller = SecondLevel(self.spec)
            self.second_level = True
        if (self.second_level and not self.third_level
                and self.controller.exit_route == 7 and self.controller.finish.visit == 30
                and int(obs[3]) == 1 and int(obs[42]) == 77):
            self.controller = ThirdLevel(self.spec)
            self.third_level = True
        return self.controller.act(obs, info)
