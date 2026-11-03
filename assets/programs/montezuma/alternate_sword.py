"""Use the sword before collecting the third key and room 23 treasures."""

from alt_policy import Alt
from base_policy import WAIT, DOWN, UP, RIGHT

class Alternate(Alt):
    """Descend from room 13, defeat the room 21 spider, and climb back."""

    def reset(self):
        super().reset()
        self.sword_route = 0
        self.sword_spider = None

    def act(self, o, i):
        (room, y, spider) = map(int, o[[3, 43, 44]])
        if self.alt13_gone and self.detour_phase == 41:
            self.detour_phase = 42
        if self.sword_route == 0 and self.alt == 5 and (self.extra_phase == 61) and (room == 13) and (y >= 240):
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
            4: (not int(o[65]) & 32, DOWN, UP),
            5: (room == 13 and y >= 195, UP, WAIT),
            7: (y >= 232, UP, RIGHT),
        }
        if stage in transitions:
            complete, action, on_complete = transitions[stage]
            if complete:
                self.sword_route += 1
                if stage == 5:
                    self.sword_spider = spider
                elif stage == 7:
                    self.extra_phase = 63
                return on_complete
            return action
        return super().act(o, i)
