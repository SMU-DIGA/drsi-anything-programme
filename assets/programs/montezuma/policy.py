"""Episode controller: complete the first level and continue on the next."""
from alternate_extended import Extended
from base_policy import Policy as FirstLevelRoute, DOWN, UP, LEFT, RIGHT, JUMP_LEFT, JUMP_RIGHT, WAIT


class SecondLevel(FirstLevelRoute):
    """Reuse the early route with the faster skull on the second level."""

    def reset(self):
        super().reset()
        self.gem_stage = 0
        self.gem_lives = None
        self.exit_lives = None

    def room8_treasures(self, obs, info):
        """Use the center rope to collect the two prizes above the pit."""
        x, y, movement = (int(obs[j]) for j in (42, 43, 53))
        stage = self.gem_stage
        if stage in (0, 4):
            if x <= 115:
                self.gem_stage += 1
                return JUMP_LEFT
            return LEFT
        if stage == 1:
            if movement == 4:
                self.gem_stage = 2
                return UP
            return JUMP_LEFT
        if stage == 2:
            if y >= 235:
                self.gem_stage = 3
                self.gem_lives = int(info['lives'])
                return JUMP_LEFT
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
        if stage == 5:
            if x <= 101:
                self.gem_stage = 6
            return JUMP_LEFT
        if stage == 6:
            if movement == 4:
                self.gem_stage = 7
                return UP
            return WAIT
        if stage == 7:
            if y >= 235:
                self.gem_stage = 8
                self.exit_lives = int(info['lives'])
                return JUMP_RIGHT
            return UP
        if stage == 8:
            if int(info['lives']) < self.exit_lives:
                self.gem_stage = 9
                return WAIT
            return RIGHT
        room = int(obs[3])
        # Return from room 8 to the ladder above room 4.
        transitions = {
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
        return WAIT

    def act(self, obs, info):
        if self.phase == 0:
            if int(obs[43]) <= 199:
                self.phase = 1
                self.elapsed = 0
            return DOWN
        if (self.phase == 6 and self.first_skull_staged
                and int(obs[42]) - int(obs[47]) <= 52):
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
        if ((self.extra_phase >= 16 and int(obs[3]) == 8 and self.gem_stage != 15)
                or 6 <= self.gem_stage < 15):
            return self.room8_treasures(obs, info)
        action = super().act(obs, info)
        if self.extra_phase == 5 and int(obs[3]) == 4 and int(obs[42]) <= 42:
            return JUMP_LEFT
        return action


class Policy:
    def __init__(self, spec):
        self.spec = spec
        self.reset()

    def reset(self):
        self.controller = Extended(self.spec)
        self.second_level = False

    def act(self, obs, info):
        if (not self.second_level and self.controller.visit == 30
                and int(obs[3]) == 1 and int(obs[42]) == 77):
            self.controller = SecondLevel(self.spec)
            self.second_level = True
        return self.controller.act(obs, info)
