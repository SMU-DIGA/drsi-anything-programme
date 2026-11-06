"""Image-based Q*bert controller: visit the remaining uncolored cubes."""
from collections import deque, Counter
import numpy as np
import cv2


class Policy:
    def __init__(self, spec):
        self.reset()

    def reset(self):
        self.cooldown = 0
        self.last_move = 0
        self.previous_cell = None
        self.lives = None
        self.tiles = {(r, c): False for r in range(6) for c in range(r + 1)}
        self.base_color = (45, 87, 176)
        self.completed = False
        self.complete_ticks = 0
        self.round_index = 0
        self.intermediate_color = None
        self.pending_color = None
        self.pending_count = 0
        self.edge_bounces = 0

    @staticmethod
    def neighbors(cell):
        r, c = cell
        for action, dr, dc in ((3, 1, 1), (5, 1, 0), (2, -1, 0), (4, -1, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < 6 and 0 <= cc <= rr:
                yield action, (rr, cc)

    def act(self, obs, info):
        lives = info.get('lives')
        if self.lives is not None and lives != self.lives:
            self.cooldown = 0
            self.previous_cell = None
            self.edge_bounces = 0
        self.lives = lives
        # Each round starts with all diamonds the same color and changes
        # them on landing.
        if self.completed:
            # The end-of-round color flash takes about 40 observations. The
            # next round can reuse the same side color, so wait for the flash
            # rather than relying on the side color to change.
            self.complete_ticks += 1
            if self.complete_ticks <= 3:
                return self.flash_move
            if self.complete_ticks >= 48:
                colors = []
                for r, c in self.tiles:
                    x, y = 78 - 12*r + 24*c, 36 + 29*r
                    color = tuple(int(v) for v in obs[y, x-5])
                    if color not in ((0, 0, 0), (181, 83, 40)):
                        colors.append(color)
                if colors:
                    self.base_color = max(set(colors), key=colors.count)
                    self.tiles = dict.fromkeys(self.tiles, False)
                    self.completed = False
                    self.cooldown = 0
                    self.previous_cell = None
                    self.complete_ticks = 0
                    self.round_index += 1
                    self.intermediate_color = None
                    self.pending_color = None
                    self.pending_count = 0
                    self.edge_bounces = 0
            return 0
        observed = {}
        for r, c in self.tiles:
            x, y = 78 - 12*r + 24*c, 36 + 29*r
            pixels = obs[y, x-7:x+8]
            colors, counts = np.unique(pixels, axis=0, return_counts=True)
            valid = [(int(n), tuple(int(v) for v in col))
                     for col, n in zip(colors, counts)
                     if tuple(col) not in ((0, 0, 0), (181, 83, 40))]
            if valid:
                n, color = max(valid)
                if n >= 10:
                    observed[r, c] = color
        if (4 <= self.round_index < 8 or self.round_index >= 12) and self.intermediate_color is None:
            possible = Counter(color for color in observed.values()
                               if color != self.base_color and color != (146, 70, 192))
            if possible:
                candidate = possible.most_common(1)[0][0]
                if candidate == self.pending_color:
                    self.pending_count += 1
                else:
                    self.pending_color, self.pending_count = candidate, 1
                if self.pending_count >= 3:
                    self.intermediate_color = candidate
        for cell, color in observed.items():
            if (4 <= self.round_index < 8 or self.round_index >= 12):
                # During a palette change, the screen can briefly contain a
                # mixture of channels from the two earlier tile colors.
                if (self.intermediate_color is not None and
                    color not in (self.base_color, self.intermediate_color) and
                    all(v in (a, b) for v, a, b in
                        zip(color, self.base_color, self.intermediate_color))):
                    continue
                self.tiles[cell] = (color != self.base_color and
                                    self.intermediate_color is not None and
                                    color != self.intermediate_color)
            else:
                self.tiles[cell] = color != self.base_color
        if all(self.tiles.values()):
            self.completed = True
            destinations = dict(self.neighbors(self.previous_cell)) if self.previous_cell else {}
            target = destinations.get(self.last_move)
            onward = dict(self.neighbors(target)) if target else {}
            self.flash_move = self.last_move if self.last_move in onward else next(iter(onward), 0)
            return self.flash_move
        if self.cooldown:
            repeat = self.cooldown >= 5
            self.cooldown -= 1
            return self.last_move if repeat else 0
        # The orange player stands about 11 pixels above each tile's center.
        mask = np.all(obs == (181, 83, 40), axis=2)
        candidates = []
        for r, c in self.tiles:
            x, y = 78 - 12*r + 24*c, 25 + 29*r
            patch = mask[max(0,y-11):y+12, max(0,x-9):x+10]
            count = int(patch.sum())
            if count >= 38:
                ys, xs = np.nonzero(patch)
                cy = max(0,y-11) + ys.mean()
                if abs(cy-y) < 5:
                    candidates.append((count, (r, c)))
        if not candidates:
            return 0
        cell = max(candidates)[1]
        edge_pairs = (((4, 0), (5, 0)), ((4, 4), (5, 5)))
        if any(cell in pair and self.previous_cell in pair and cell != self.previous_cell
               for pair in edge_pairs):
            self.edge_bounces += 1
        else:
            self.edge_bounces = 0
        # Purple balls and Coily share this distinctive sprite color. Avoid
        # their current position and nearby landing squares, while still
        # seeking the nearest unfinished cube.
        danger = np.all(obs == (146, 70, 192), axis=2).astype(np.uint8)
        danger[:, :5] = 0
        danger[:, 155:] = 0
        joined = cv2.dilate(danger, np.ones((3, 3), np.uint8))
        count, _, stats, centroids = cv2.connectedComponentsWithStats(joined)
        enemies = []
        for k in range(1, count):
            x, y, w, h, area = stats[k]
            if 4 <= w <= 17 and 6 <= h <= 27 and area >= 20 and y > 10:
                enemies.append((centroids[k][0], centroids[k][1]))

        # A disc may be available beside the fourth-row edge. Jumping onto
        # it can carry the player away from a nearby pursuer.
        r, c = cell
        if r == 4 and c in (0, 4) and enemies:
            x, y = 78 - 12*r + 24*c, 25 + 29*r
            nearest = min(max(abs(x-ex)/12, abs(y-ey)/29) for ex, ey in enemies)
            disc_x = 12 if c == 0 else 140
            disc_present = np.count_nonzero(obs[138:140, disc_x:disc_x+8]) >= 8
            # After repeated trips to the bottom corner, use the disc if a
            # pursuer blocks the inside exit before it closes the trap.
            corner = (5, 0) if c == 0 else (5, 5)
            inward = 1 if c == 0 else -1
            blocked = self.edge_bounces >= 6 and self.previous_cell == corner and any(
                0 < inward*(ex-x) < 24 and abs(ey-y) < 12 for ex, ey in enemies)
            if (nearest < 1.5 or blocked) and disc_present:
                self.previous_cell = cell
                self.last_move = 4 if c == 0 else 2
                self.cooldown = 6
                return self.last_move

        def distance_to_goal(start):
            queue = deque([(start, 0)])
            seen = {start}
            while queue:
                here, dist = queue.popleft()
                if not self.tiles[here] and here != cell:
                    return dist
                for _, nxt in self.neighbors(here):
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append((nxt, dist + 1))
            return 100

        choices = []
        for order, (move, nxt) in enumerate(self.neighbors(cell)):
            r, c = nxt
            x, y = 78 - 12*r + 24*c, 25 + 29*r
            risk = 0.0
            for ex, ey in enemies:
                dist = max(abs(x-ex)/12, abs(y-ey)/29)
                if dist < 1.0:
                    risk += 12
                elif dist < 1.8:
                    risk += 4
                elif dist < 2.5:
                    risk += 0.5
            # A dead end is risky if a nearby enemy can cover both exits
            # before the next jump, even when the landing itself is clear.
            exits = list(self.neighbors(nxt))
            if len(exits) == 2 and enemies:
                threatened = []
                for _, (er, ec) in exits:
                    xx, yy = 78 - 12*er + 24*ec, 25 + 29*er
                    threatened.append(any(max(abs(xx-ex)/12, abs(yy-ey)/29) < 2.5
                                          for ex, ey in enemies))
                if all(threatened):
                    risk += 1.5
            # Toggle rounds can undo progress when bouncing between the
            # same two cubes; prefer another equally useful move.
            repeat = 0.1 if self.round_index >= 8 and nxt == self.previous_cell else 0
            choices.append((distance_to_goal(nxt) + risk + repeat, order, move))
        if not choices:
            return 0
        action = min(choices)[2]
        self.previous_cell = cell
        self.cooldown = 6
        self.last_move = action
        return action
