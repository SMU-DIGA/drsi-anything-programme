"""Sweep and fire, dodging nearby hazards and aiming at the mothership.

Normal-wave hazards persist a short dodge direction, with a timed shield for
predicted bird or projectile collisions. Boss projectiles are avoided while
screen-wide flashes are ignored.
"""

import numpy as np
import cv2


SHIP = (213, 130, 74)
RED = (167, 26, 26)
WHITE = (236, 236, 236)


def bright_non_green(image):
    """Find bright red/blue pixels, excluding green-dominant sprites."""
    red, green, blue = image[:, :, 0], image[:, :, 1], image[:, :, 2]
    return ((red > 80) | (blue > 80)) & ~((green > red) & (green > blue))


class Policy:
    def __init__(self, spec: dict):
        self.reset()

    def reset(self) -> None:
        self.t = 0
        self.sweep_dir = 1
        self.sweep_age = 0
        self.dodge = 0
        self.dodge_target = 80
        self.normal_dodge = 0
        self.normal_dodge_dir = 1
        self.boss = False
        self.boss_x = 80
        self.birds = []
        self.last_shield = -1000
        self.shield_pending = 0

    def act(self, obs, info: dict) -> int:
        self.t += 1
        self.sweep_age += 1
        if self.sweep_age == 30:
            self.sweep_age = 0
            self.sweep_dir = -self.sweep_dir
        direction = self.sweep_dir
        ship_x = np.where(np.all(obs[174:183] == SHIP, axis=2))[1]
        red_x = np.where(np.all(obs[70:168] == RED, axis=2))[1]

        # Remember the hull's original center as shots remove parts of it.
        if not self.boss and len(red_x) >= 400:
            self.boss = True
            self.boss_x = (int(np.min(red_x)) + int(np.max(red_x))) // 2
        elif self.boss and len(red_x) < 100:
            self.boss = False
            self.dodge = 0

        if len(ship_x):
            x = int(np.mean(ship_x))

            if self.boss:
                target = self.boss_x
                bullet_y, bullet_x = np.where(np.all(obs[105:183] == WHITE, axis=2))
                flash = len(bullet_x) > 1000
                close = np.where(np.abs(bullet_x - x) < 15)[0] if not flash else []
                if len(close) and (self.dodge == 0 or np.max(bullet_y[close]) >= 40):
                    threat = close[np.argmax(bullet_y[close])]
                    direction = -1 if bullet_x[threat] >= x else 1
                    self.dodge_target = max(14, min(140, x + 22 * direction))
                    self.dodge = 6

                if self.dodge:
                    self.dodge -= 1
                    target = self.dodge_target

                if abs(x - target) <= 2:
                    return self.t % 2

                direction = 1 if x < target else -1

            else:
                area = obs[155:168]
                danger = bright_non_green(area)
                # Enemy shots are white; thin colored vertical lines are our shots.
                white = np.all(area == WHITE, axis=2)
                adjacent = np.zeros_like(danger)
                adjacent[:, 1:] |= danger[:, :-1]
                adjacent[:, :-1] |= danger[:, 1:]
                danger &= white | adjacent

                ys, xs = np.where(danger & (np.abs(np.arange(160)[None, :] - x) < 14))
                if len(xs):
                    closest = np.argmax(ys)
                    self.normal_dodge_dir = -1 if xs[closest] > x else 1
                    self.normal_dodge = 4

                if self.normal_dodge > 0:
                    self.normal_dodge -= 1
                    direction = self.normal_dodge_dir
                else:
                    # Steer early when the current course intersects a falling shot.
                    shot_y, shot_x = np.where(np.all(obs[118:168] == WHITE, axis=2))
                    if len(shot_x) < 100:
                        for sx in np.unique(shot_x):
                            bottom = 118 + np.max(shot_y[shot_x == sx])
                            horizon = (174 - bottom) / 8
                            if not 1 < horizon <= 7:
                                continue
                            future = max(16, min(140, x + direction * 4 * horizon))
                            alternate = max(16, min(140, x - direction * 4 * horizon))
                            if abs(sx - future) < 7 and abs(sx - alternate) > abs(sx - future) + 3:
                                direction = -direction
                                self.normal_dodge_dir = direction
                                self.normal_dodge = 4
                                break
            # Avoid becoming stuck at the edge, except while dodging.
            dodge_active = self.dodge if self.boss else self.normal_dodge
            if not dodge_active:
                if x < 22:
                    direction = 1
                    if not self.boss and self.sweep_dir < 0:
                        self.sweep_dir, self.sweep_age = 1, 0
                elif x > 132:
                    direction = -1
                    if not self.boss and self.sweep_dir > 0:
                        self.sweep_dir, self.sweep_age = -1, 0

        # Shield when a projectile or diving bird is about to meet our path.
        if len(ship_x) and not self.boss:
            if self.t - self.last_shield > 100:
                shot_y, shot_x = np.where(np.all(obs[140:173] == WHITE, axis=2))
                if len(shot_x) < 100:
                    for sx in np.unique(shot_x):
                        bottom = 140 + np.max(shot_y[shot_x == sx])
                        horizon = (174 - bottom) / 8
                        ship_future = max(16, min(140, x + direction * 4 * horizon))
                        if 0 < horizon <= 3 and abs(sx - ship_future) < 6:
                            self.last_shield = self.t
                            self.shield_pending = 2
                            break
            view = obs[135:173]
            colored = bright_non_green(view)
            _, _, stats, _ = cv2.connectedComponentsWithStats(colored.astype(np.uint8))
            birds = [(x0 + w / 2, y0 + 135 + h) for x0, y0, w, h, size in stats[1:]
                     if size >= 15 and w >= 5 and h >= 3]
            if self.t - self.last_shield > 100:
                for bx, by in birds:
                    matches = [(px, py) for px, py in self.birds
                               if abs(px - bx) <= 7 and abs(py - by) <= 7]
                    if not matches:
                        continue
                    px, py = min(matches, key=lambda p: (p[0] - bx)**2 + (p[1] - by)**2)
                    vx, vy = bx - px, by - py
                    if not 2 <= vy <= 6:
                        continue
                    horizon = (172 - by) / vy
                    if 0 < horizon <= 4 and abs((bx + vx * horizon) - (x + direction * 4 * horizon)) < 14:
                        self.last_shield = self.t
                        self.shield_pending = 2
                        break
            self.birds = birds
        else:
            self.birds = []
        if self.shield_pending:
            self.shield_pending -= 1
            return 4 + (3 if self.t % 2 == 0 else 0)

        # Alternate fire and release: actions 2/3 move, 5/6 move and fire.
        move = 2 if direction == 1 else 3
        return move + (3 if self.t % 2 == 0 else 0)
