"""Episode controller: complete the first level and continue on the next."""
from alternate_extended import Extended
from alt_policy import Alt
from base_policy import (Policy as FirstLevelRoute, advance, climb_from_respawn,
                         standing_jump, FALLING, DOWN, UP, LEFT, RIGHT, JUMP, JUMP_LEFT, JUMP_RIGHT, WAIT)


class SecondLevel(FirstLevelRoute):
    """Reuse the early route with the faster skull on the second level."""
    # Room 22 entry: start when RAM[0] % 128 is in R22..R22+3.
    R22 = 100

    def reset(self):
        super().reset()
        self.gem_stage = 0
        self.gem_lives = None
        self.lower_stage = 0
        self.lower_steps = 0
        self.lower22_out_retry = False
        self.lower22_first_death = False
        self.lower22_return_retry = False
        self.lower_treasure = 0
        self.lower_return_retry = False
        self.bridge_return = 0
        self.exit_route = 0
        self.exit_cross_retry = False
        self.key_return = 0
        self.room4_recover = False
        self.return_start_recover = False
        self.crossing = Alt({})
        self.finish = Extended({})
        self.finish.second_level = True

    def room8_treasures(self, obs, info):
        """Collect an affordable prize, then return to the room 9 ladder."""
        room, x, y, movement = (int(obs[j]) for j in (3, 42, 43, 53))
        stage = self.gem_stage
        # Returning from the pit costs a life; reserve lives for the exit.
        # The third level has a key here instead of the second-level prizes.
        if (stage == 0 and room == 8
                and (int(info['lives']) <= 3 or self.third_level)):
            self.gem_stage = 5
            return RIGHT
        # Stop before the room 4 snake so a repeated RIGHT cannot shift a
        # running jump into it on the way back from room 8.
        if (stage == 7 and room == 4 and y == 235 and 14 <= x < int(obs[44])):
            enemy = int(obs[44])
            action = standing_jump(x, enemy - 11, enemy - 8, movement,
                                   rightward=True)
            if action == JUMP_RIGHT:
                self.gem_stage = 8
            if action is not None:
                return action
        # Rows are (completion condition, action while waiting, action on completion).
        transitions = {
            # Jump to the centre rope and climb.
            0: (x <= 115, LEFT, JUMP_LEFT),
            1: (movement == 4, JUMP_LEFT, UP),
            # Respawn after the first trip and return: a second trip costs a
            # life, and the approach may already have taken the other prize.
            4: (x >= 140 and y == 235 and movement in (8, 18), WAIT, RIGHT),
            # Return from room 8 to the ladder above room 4. At x 75 in room 4,
            # act() hands over to the descent toward room 7.
            5: (room == 9 and 75 <= x <= 82, RIGHT, UP),
            6: (room == 3 and 230 <= y <= 240, UP, RIGHT),
            7: (room == 4 and 19 <= x <= 45, RIGHT, JUMP_RIGHT),
            8: (x >= 50 and y == 235, JUMP_RIGHT, RIGHT),
            9: (x >= 75, RIGHT, UP),
        }
        if stage in transitions:
            self.gem_stage, action = advance(stage, transitions[stage])
            return action
        if stage == 2:
            if y >= 235:
                self.gem_stage += 1
                self.gem_lives = int(info['lives'])
                return JUMP_LEFT
            return UP
        # stage 3: walk left over the pit until the trip costs a life.
        lives = int(info['lives'])
        self.gem_lives = max(self.gem_lives, lives)
        if lives < self.gem_lives:
            self.gem_stage = 4
            return WAIT
        return LEFT

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
            self.bridge_return, action = advance(stage, transitions[stage])
            return action
        if stage == 8 and room == 20 and x <= 50 and y == 235:
            self.bridge_return = 9
            return JUMP_LEFT
        if room == 19 and x <= 17:
            return WAIT
        return LEFT

    def lower_corridor(self, obs, info, room, x, y, enemy, timer):
        """Collect the dark-room prizes and return toward rooms 5 and 20."""
        # Continue from the room 7 ladder into the dark lower corridor.
        mv = int(obs[53])
        if self.lower_stage in (17, 18, 19, 20) and room == 22:
            if self.life_lost('lower22_return', int(info['lives'])):
                self.lower22_return_retry = True
            if self.lower22_return_retry:
                if x == 77 and y >= 240 and mv in (0, 10):
                    self.lower_stage = 17
                    self.lower22_return_retry = False
                return WAIT
        if self.lower_stage in (24, 25, 26) and room == 13:
            if self.life_lost('lower_return', int(info['lives'])):
                self.lower_return_retry = True
            if self.lower_return_retry:
                action = climb_from_respawn(x, y, mv)
                if action is not None:
                    return action
                if x == 77:
                    return LEFT
                if y == 235 and x < 74:
                    self.lower_stage = 26 if enemy >= 75 else 24
                    self.lower_return_retry = False
                    return LEFT
                return WAIT
        # A repeated UP can carry the player above the room 13 floor, where
        # jumps are ignored; climb back down and restart the crossing.
        if (self.lower_stage in (24, 25) and room == 13 and x == 77
                and y > 237 and mv == 10):
            self.lower_stage = 24
            return DOWN
        # Leftward over the stationary room 13 snake: only starts 9--13 px
        # right of it clear it, and a sticky repeat of LEFT during a running
        # jump shifts the start. Stop near the snake and jump from standing,
        # where a repeated input only delays the jump in place.
        if (self.lower_stage == 24 and room == 13 and y == 235
                and not self.third_level and x - enemy > 0):
            if x - enemy > 14:
                return LEFT
            action = standing_jump(x, enemy + 9, enemy + 13, mv, rightward=False)
            if action == JUMP_LEFT:
                self.lower_stage = 25
            if action is not None:
                return action
        if self.lower_stage == 0 and self.extra_phase == 61 and room == 21 and y == 235:
            self.lower_stage = 1
        if self.lower_stage == 1:
            if room == 22:
                self.lower_stage = 2
                self.lower_steps = 0
            elif x < 145:
                return RIGHT
            elif self.R22 <= int(obs[0]) % 128 <= self.R22 + 3:
                return RIGHT
            else:
                return WAIT
        if self.lower_stage == 2:
            if self.life_lost('lower22_out', int(info['lives'])):
                self.lower22_out_retry = True
                self.lower22_first_death = True
            if self.lower22_out_retry:
                if (room == 22 and x < 10 and y == 235 and mv in (8, 18)
                        and self.R22 + 4 <= int(obs[0]) % 128 <= self.R22 + 7):
                    self.lower22_out_retry = False
                    self.lower_steps = 0
                else:
                    return WAIT
            if room == 23:
                self.lower_stage = 3
            elif self.third_level and not self.lower22_first_death:
                return self.room22_first_pass(x, y, enemy, mv, timer, int(obs[0]))
            else:
                n = self.lower_steps
                self.lower_steps += 1
                # Third-level room 22 has an approaching enemy at the entry.
                # Leave immediately, then wait on the left ledge until the
                # regular bridge-crossing jump is due.
                if self.third_level and n < 10:
                    return JUMP_RIGHT if n < 6 else WAIT
                if n < 3:
                    return WAIT
                if n < 8:
                    return JUMP_RIGHT
                # Release jump before landing so the next jump can register
                # even if a sticky action repeats the previous input.
                if n < 10:
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
        # Likewise at the room 22 ladder; after a fall from the bridge,
        # wait for it again from the right ledge.
        if self.lower_stage == 8 and room == 22 and y == 235 and mv != 6:
            if x > 100:
                self.lower_stage = 4
                return WAIT
            if x < 75:
                return RIGHT
            if x > 79:
                return LEFT
        # A repeated left input can carry the player past the room 21 ladder.
        if self.lower_stage == 23 and room == 21 and y == 235:
            if x < 74:
                return RIGHT
            if x > 80:
                return LEFT
        # A sticky UP can swallow the jump from the left rope. Retry it
        # before descending; otherwise the return jump misses the left rope.
        if (self.lower_stage == 11 and room == 14 and x < 80
                and y == 235 and mv == 8):
            return JUMP_RIGHT
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
            19: (x - enemy <= (22 if int(info['lives']) == 1 else 20), LEFT, JUMP_LEFT),
            20: (y == 235 and x < enemy, JUMP_LEFT, LEFT),
            21: (room == 21 and x > 100, LEFT, LEFT),
            22: (x <= 78, LEFT, UP),
            23: (room == 13 and 232 <= y <= 240, UP, LEFT),
            # Leftward over the x 44 snake: start from x 53--57 (a jump
            # from 58 comes down on it).
            24: (x - enemy <= 12, LEFT, JUMP_LEFT),
            25: (y == 235 and x < enemy, JUMP_LEFT, LEFT),
        }
        if self.lower_stage in transitions:
            self.lower_stage, action = advance(self.lower_stage, transitions[self.lower_stage])
            return action
        if self.lower_stage == 26:
            if room == 12 and x > 100:
                self.lower_stage = 27
                self.extra_phase = 71
            else:
                return LEFT
        # Both room 19 enemies start to the left of the ladder on this level.
        # Head right to the bridge and treasure before they can turn back.
        if (self.lower_stage == 27 and self.extra_phase == 110
                and room == 19 and y == 235):
            self.extra_phase = 113
        if self.lower_stage == 27 and self.extra_phase >= 118:
            # The third-level key is at the right ledge. A repeated RIGHT
            # can shift the first jump past it; retry while its flag is set.
            if (self.third_level and room == 20 and self.bridge_return == 0
                    and int(obs[66]) & 1):
                if y != 235 or mv == 18:
                    return WAIT
                if mv == 8:
                    if x > 143:
                        return LEFT
                    if x < 140:
                        return RIGHT
                    return JUMP
            return self.return_across_room20(room, x, y, mv, timer)
        return None

    def act(self, obs, info):
        room, x, y, enemy, timer = (int(obs[j]) for j in (3, 42, 43, 44, 83))
        action = self.after_death(obs, info, room, x, y)
        if action is None:
            action = self.key_and_exit_route(obs, info, room, x, y, enemy, timer)
        if action is not None:
            return action
        if (self.phase == 6 and self.first_skull_staged
                and x - int(obs[47]) <= 52):
            self.phase = 7
            self.elapsed = 0
        # There is no moving spider on this ladder in the second level.
        if self.laser_phase == 12:
            self.laser_phase = 13
        # The sword encounter is complete after entering room 8.
        if ((self.extra_phase >= 16 and room == 8 and self.gem_stage != 10)
                or 5 <= self.gem_stage < 10):
            return self.room8_treasures(obs, info)
        action = self.lower_corridor(obs, info, room, x, y, enemy, timer)
        if action is not None:
            return action
        # The second-level room 4 snake can be hit when a repeated LEFT
        # shifts the running take-off. Stop and jump from a safe gap.
        if (not self.third_level and self.extra_phase == 5 and room == 4
                and y == 235 and 0 < x - enemy <= 16):
            action = standing_jump(x, enemy + 10, enemy + 12,
                                   int(obs[53]), rightward=False)
            if action is not None:
                return action
        action = super().act(obs, info)
        if self.extra_phase == 5 and room == 4 and x <= 42:
            return JUMP_LEFT
        return action

    def after_death(self, obs, info, room, x, y):
        """Respawn handling for the room 7 prize, lasers, the return to the
        start ladder and room 4; None when not recovering."""
        if self.exit_route == 6 and room == 7 and 54 <= self.extra_phase <= 60:
            action = self.recover_room7_prize(obs, info)
            if action is not None:
                return action
        # ThirdLevel.act handles its own room 0 respawns.
        if self.wait_after_laser_death(obs, info, room0=not self.third_level):
            return WAIT
        if room == 1 and 14 <= self.phase <= 17 and not self.laser_entered:
            if self.life_lost('return_start', int(info['lives'])):
                self.return_start_recover = True
            if self.return_start_recover:
                if x == 77 and y == 235 and int(obs[53]) in (8, 18):
                    self.phase = 14
                    self.elapsed = 0
                    self.return_start_recover = False
                return WAIT
        if self.phase >= 17 and self.laser_phase == 16 and self.extra_phase == 5 and room == 4:
            if self.life_lost('room4', int(info['lives'])):
                self.room4_recover = True
            if self.room4_recover:
                if int(obs[53]) in FALLING:
                    return WAIT
                if 74 <= x <= 80:
                    return UP if y < 235 else DOWN if y > 235 else LEFT
                self.room4_recover = False
        return None

    def key_and_exit_route(self, obs, info, room, x, y, enemy, timer):
        """Return across room 10 with its key, descend from room 4 through
        rooms 10--13 to room 7, and later leave via rooms 18, 17 and 15."""
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
            self.key_return, action = advance(self.key_return, key_crossing[self.key_return])
            if self.key_return == 5:
                self.extra_phase = 5
            return action
        # Retain the room 10 key by descending from room 4 directly to the
        # lower corridor instead of opening the starting room's right door.
        if self.exit_route == 0 and self.gem_stage == 9 and room == 4 and x >= 75:
            self.exit_route = 1
            self.crossing.at = 0
        if self.exit_route == 1 and self.crossing.at >= 23:
            self.exit_route = 2
        if self.exit_route == 1:
            return self.crossing.cross_to_room7(obs, info, room, x, y, enemy, timer)
        if self.exit_route in (2, 3, 4) and room == 13:
            if self.life_lost('exit_cross', int(info['lives'])):
                self.exit_cross_retry = True
            if self.exit_cross_retry:
                if x < 10 and y == 235 and int(obs[53]) in (8, 18):
                    # Once the left snake is gone, the ladder is clear.
                    self.exit_route = 4 if enemy >= 90 else 2
                    self.exit_cross_retry = False
                return WAIT
        if (self.third_level and self.exit_route == 2
                and room == 13 and x >= 75):
            self.exit_route = 4
        exit_crossing = {
            # A stationary snake at x 44 is cleared by jumps from x 33--37
            # (gap 7--11); jumps from x 32 land on it.
            2: (not self.third_level and room == 13 and x < 100
                and enemy - x <= 11, RIGHT, JUMP_RIGHT),
            3: (y == 235 and x > enemy, JUMP_RIGHT, RIGHT),
            4: (x >= 75, RIGHT, UP),
        }
        if self.exit_route in exit_crossing:
            self.exit_route, action = advance(self.exit_route, exit_crossing[self.exit_route])
            return action
        if self.exit_route == 5:
            if room == 7 and 230 <= y <= 240:
                self.gem_stage = 10
                self.extra_phase = 54
                self.exit_route = 6
            else:
                return UP
        if self.exit_route == 6:
            if self.extra_phase == 60 and room == 7 and 75 <= x <= 80:
                self.extra_phase = 61
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
        return None


class ThirdLevel(SecondLevel):
    """Collect the starting-room key and door on the faster third level."""
    third_level = True

    def reset(self):
        super().reset()
        self.crossing.third_level = True
        self.third_approaching = False
        self.third_skull = None
        self.third_room0_recover = False
        self.third_snakes = 0
        self.third_room4_recover = False
        self.third_right_stage = 0
        self.third_right_retry = False
        self.third_room21_jumping = False
        self.third22_first_stage = 0
        self.third22_enemy = None
        self.third22_still = 0
        self.third19_enemy = None
        self.third19_jumping = False
        self.third19_torch = 0
        self.third11_return_wait = 0
        self.third_low_life_route = 0

    def act(self, obs, info):
        room, x, y, enemy, movement = (int(obs[j]) for j in (3, 42, 43, 44, 53))
        # On entry from the room 12 lasers a jumping enemy is directly
        # overhead and moving left at the player's walking speed. Let it
        # pull ahead before following it toward the ladder.
        if (self.lower_stage == 27 and self.extra_phase in (81, 82)
                and room == 11 and x >= 140 and self.third11_return_wait < 5):
            self.third11_return_wait += 1
            return WAIT
        if (self.third_low_life_route or
                (self.lower_stage == 0 and self.extra_phase == 61
                 and room == 21 and y == 235 and int(info['lives']) <= 4)):
            return self.room14_low_life(room, x, y, movement)
        if (self.exit_route == 6 and self.lower_stage == 27
                and self.bridge_return >= 9 and room == 19):
            action = self.room19_return(x, y, enemy, movement, int(info['lives']))
            if action is not None:
                return action
        if self.lower_stage == 1 and room == 21:
            action = self.room21_enemy(x, y, enemy, movement)
            if action is not None:
                return action
        if room == 4 and self.exit_route == 0 and 7 <= self.gem_stage <= 9:
            return self.room4_rightward(obs, info, x, y, enemy, movement)
        if (self.phase >= 17 and room == 0
                and self.wait_after_room0_death(x, y, movement, int(info['lives']))):
            return WAIT
        if self.key_return == 5 and self.extra_phase == 5 and room == 4:
            return self.room4_leftward(x, y, movement, int(info['lives']))
        if self.phase == 6:
            return self.opening_skull(obs, info, x)
        return super().act(obs, info)

    def room14_low_life(self, room, x, y, movement):
        # With few lives, skip the dangerous room 23 detour and go back via
        # room 13 to the room 14 ropes and pickup.
        stage = self.third_low_life_route
        if stage == 0:
            self.third_low_life_route = 1
            return UP
        transitions = {
            1: (room == 13 and 230 <= y <= 240, UP, RIGHT),
            2: (room == 14 and x < 20, RIGHT, RIGHT),
            3: (x >= 30, RIGHT, JUMP_RIGHT),
            4: (movement == 4, JUMP_RIGHT, UP),
        }
        if stage in transitions:
            self.third_low_life_route, action = advance(stage, transitions[stage])
            return action
        if y >= 235:
            self.third_low_life_route = 0
            self.lower_stage = 11
            return JUMP_RIGHT
        return UP

    def room22_first_pass(self, x, y, enemy, movement, timer, clock):
        # Let the jumping enemy turn at the entry, then follow it on foot.
        previous = self.third22_enemy
        self.third22_enemy = enemy
        if self.third22_first_stage == 0:
            # An enemy removed by an earlier death leaves its x coordinate
            # frozen. Resume the timed crossing at the usual bridge phase.
            self.third22_still = self.third22_still + 1 if enemy == previous else 0
            if self.third22_still >= 8:
                if 100 <= clock % 128 <= 103:
                    self.lower22_first_death = True
                    self.lower_steps = 0
                return WAIT
            if previous is not None and enemy > previous and 14 <= enemy <= 22:
                self.third22_first_stage = 1
                return RIGHT
            return WAIT
        transitions = {
            1: (x >= 20, RIGHT, WAIT),
            2: (16 <= timer <= 20, WAIT, JUMP_RIGHT),
            3: (x >= 45 and y == 235 and movement != 6, JUMP_RIGHT, RIGHT),
        }
        if self.third22_first_stage in transitions:
            self.third22_first_stage, action = advance(
                self.third22_first_stage, transitions[self.third22_first_stage])
            return action
        return RIGHT

    def room19_return(self, x, y, enemy, movement, lives):
        # On the return from room 20 the fast enemy can run toward us.
        # Jump only while it is advancing; after a death it stays frozen.
        if self.life_lost('third19_return', lives):
            self.third19_jumping = False
            self.third19_torch = 3
        previous = self.third19_enemy
        self.third19_enemy = enemy
        if movement in FALLING:
            return WAIT
        # The torch on the left ledge was skipped on the outbound trip.
        # Take it now only when the enemy is far away and moving right.
        torch_trip = {
            1: (y > 235, JUMP, WAIT),
            2: (y == 235 and movement == 8, WAIT, LEFT),
        }
        if self.third19_torch in torch_trip:
            self.third19_torch, action = advance(
                self.third19_torch, torch_trip[self.third19_torch])
            return action
        if (self.third19_torch == 0 and 10 <= x <= 18 and y == 235
                and enemy - x >= 40 and previous is not None and enemy > previous):
            self.third19_torch = 1
            return JUMP
        if self.third19_jumping:
            if y == 235 and movement != 6 and x < enemy:
                self.third19_jumping = False
            else:
                return JUMP_LEFT
        if (previous is not None and enemy > previous and y == 235
                and 0 < x - enemy <= 27):
            self.third19_jumping = True
            return JUMP_LEFT
        return None

    def room21_enemy(self, x, y, enemy, movement):
        """Jump the stationary room 21 enemy on the way to room 22."""
        if movement in FALLING:
            self.third_room21_jumping = False
            return WAIT
        if x == 77 and y > 235:  # respawned on the ladder
            self.third_room21_jumping = False
            return DOWN
        if self.third_room21_jumping:
            if y == 235 and x > enemy:
                self.third_room21_jumping = False
            else:
                return JUMP_RIGHT
        # Jump from standing 7--11 px short of it: a running jump can be
        # shifted by a repeated RIGHT and died from 7 px.
        if 0 < enemy - x <= 15 and (y == 235 or movement == 18):
            action = standing_jump(x, enemy - 11, enemy - 7, movement, rightward=True)
            self.third_room21_jumping = action == JUMP_RIGHT
            return action
        return None

    def room4_rightward(self, obs, info, x, y, enemy, movement):
        """Cross room 4's two snakes rightward, then descend toward room 7."""
        if self.life_lost('third_right', int(info['lives'])):
            self.third_right_retry = True
        if self.third_right_retry:
            if movement in FALLING or not (x <= 10 and y == 235):
                return WAIT
            self.third_right_retry = False
            self.third_right_stage = 2 if enemy > 30 else 0
        # Enemy (RAM44) > 30 means the first snake (x 18) is gone.
        if self.third_right_stage == 0:
            if enemy > 30:
                self.third_right_stage = 2
            elif x >= 4 and y == 235:
                # A repeated RIGHT can shift a running take-off too close to
                # the snake, so stop within a safe take-off window first.
                action = standing_jump(x, 7, 9, movement, rightward=True)
                if action == JUMP_RIGHT:
                    self.third_right_stage = 1
                if action is not None:
                    return action
            else:
                return RIGHT
        # The second snake (RAM44 = 50) is cleared by running jumps from
        # x 39--43; a slipped one rose into it and a standing jump from
        # 38 landed on it. Jump from standing at 39--41.
        if self.third_right_stage == 2 and y == 235:
            if x < 34:
                return RIGHT
            action = standing_jump(x, 39, 41, movement, rightward=True)
            if action == JUMP_RIGHT:
                self.third_right_stage = 3
            if action is not None:
                return action
        crossings = {
            1: (y == 235 and x >= 28 and movement != 6, JUMP_RIGHT, RIGHT),
            2: (x >= 38, RIGHT, JUMP_RIGHT),
            3: (y == 235 and x >= 60 and movement != 6, JUMP_RIGHT, RIGHT),
        }
        if self.third_right_stage in crossings:
            self.third_right_stage, action = advance(
                self.third_right_stage, crossings[self.third_right_stage])
            return action
        self.gem_stage = 9
        if x < 75:
            return RIGHT
        self.exit_route = 1
        self.crossing.at = 0
        return self.crossing.cross_to_room7(obs, info, 4, x, y, enemy, int(obs[83]))

    def wait_after_room0_death(self, x, y, movement, lives):
        """After a room 0 death, wait for the right-edge respawn, then restart
        the lasers (acting on the respawn step itself, unlike earlier levels)."""
        if self.life_lost('third_room0', lives):
            self.third_room0_recover = True
        if not self.third_room0_recover:
            return False
        if x >= 140 and y == 235 and movement in (8, 18):
            self.third_room0_recover = False
            self.laser_phase = 0
            self.laser_entered = False
            return False
        return True

    def room4_leftward(self, x, y, movement, lives):
        """Return left across room 4's two snakes after the room 10 key."""
        if self.life_lost('third_room4', lives):
            self.third_room4_recover = True
        if self.third_room4_recover:
            action = climb_from_respawn(x, y, movement)
            if action is not None:
                return action
            if x == 77:
                return LEFT
            if not (y == 235 and x < 77):
                return WAIT
            self.third_room4_recover = False
            self.third_snakes = 0
        # The first snake is cleared only from x 60--63: a running jump
        # from 59 rises into it and one from 64 lands on it. Stop and
        # jump from standing there, so a repeated input cannot shift it.
        # Likewise for the second snake (x 18): a running jump from 28
        # rose into it; jump from standing at x 28--30.
        standing = {0: (66, 60, 62), 2: (34, 28, 30)}
        if self.third_snakes in standing and y == 235:
            near, lo, hi = standing[self.third_snakes]
            if x > near:
                return LEFT
            action = standing_jump(x, lo, hi, movement, rightward=False)
            if action == JUMP_LEFT:
                self.third_snakes += 1
            if action is not None:
                return action
        # Walk to each snake, then hold the jump until landing.
        transitions = {
            0: (x <= 62, LEFT, JUMP_LEFT),
            1: (y == 235 and x <= 44, JUMP_LEFT, LEFT),
            2: (x <= 30, LEFT, JUMP_LEFT),
            3: (y == 235 and x <= 15, JUMP_LEFT, LEFT),
        }
        if self.third_snakes in transitions:
            self.third_snakes, action = advance(self.third_snakes, transitions[self.third_snakes])
            return action
        return LEFT

    def opening_skull(self, obs, info, x):
        """Opening phase 6: follow the faster skull once it turns left at
        x 62--70, and jump it at a gap of 60; deaths use the base retry."""
        opening = self.life_baselines.get('opening')
        if self.opening_recover or (opening is not None and int(info['lives']) < opening):
            return super().act(obs, info)
        if self.opening_skull_vanished(obs):
            self.phase = 8
            return LEFT
        skull = int(obs[47])
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


class Policy:
    def __init__(self, spec):
        self.spec = spec
        self.reset()

    def reset(self):
        self.controller = Extended(self.spec)
        self.level = 1
        self.ladder_miss = 0

    def act(self, obs, info):
        if int(obs[3]) == 1 and int(obs[42]) == 77:
            if self.level == 1 and self.controller.visit == 30:
                self.controller = SecondLevel(self.spec)
                self.level = 2
            elif (self.level >= 2 and self.controller.exit_route == 7
                  and self.controller.finish.visit == 30):
                # A later-level return may be a respawn; explore again either way.
                self.controller = ThirdLevel(self.spec)
                self.level += 1
        action = self.controller.act(obs, info)
        # The central ladders are at x 77. A sticky repeat of the approach
        # input can carry the player a step past one, after which UP or DOWN
        # is ignored and the route waits forever. If UP/DOWN has had no
        # effect on the floor for several steps, step back toward the ladder.
        x, y, mv = int(obs[42]), int(obs[43]), int(obs[53])
        if (action in (UP, DOWN) and y == 235 and mv in (8, 18)
                and 66 <= x <= 88 and not 74 <= x <= 80):
            self.ladder_miss += 1
            if self.ladder_miss >= 6:
                return RIGHT if x < 77 else LEFT
        else:
            self.ladder_miss = 0
        return action
