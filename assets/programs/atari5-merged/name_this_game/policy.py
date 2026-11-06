"""Follow the boat and intercept the shark when it dives."""
import numpy as np

class Policy:
    def __init__(self, spec: dict):
        self.reset()

    def reset(self) -> None:
        self.shark_x = None
        self.direction = 0
        self.tip_x = None
        self.tip_direction = 0
        self.speed_samples = []

    def act(self, obs, info: dict) -> int:
        # Track the boat to collect air and score while keeping the gun firing.
        boat = np.where((obs[8:20, :, 0] == 184) & (obs[8:20, :, 1] == 70))[1]
        diver = np.where((obs[140:155, :, 0] == 92) & (obs[140:155, :, 1] == 186))[1]
        if not len(boat) or not len(diver):
            return 1
        muzzle = np.where((obs[140:142, :, 0] == 92) & (obs[140:142, :, 1] == 186))[1]
        target = np.mean(boat)
        position = np.mean(diver)
        # The shark is the broad gray shape; narrow gray pixels are harpoons.
        grey = (obs[74:140, :, 0] == 170) & (obs[74:140, :, 1] == 170)
        rows = np.where(grey.sum(axis=1) >= 6)[0]
        if len(rows):
            row = rows[0]
            y = int(row) + 74
            _, xs = np.where(grey[row:row + 12])
            x = float(np.mean(xs))
            if self.shark_x is not None and abs(x - self.shark_x) >= 1:
                new_direction = 1 if x > self.shark_x else -1
                if new_direction == self.direction or self.direction == 0:
                    disp = abs(x - self.shark_x)
                    if 2 <= disp <= 20:
                        self.speed_samples.append(disp)
                        if len(self.speed_samples) > 5:
                            self.speed_samples.pop(0)
                else:
                    self.speed_samples.clear()
                self.direction = new_direction
            self.shark_x = x
            if self.direction:
                # The shark swims more slowly on its first low pass.
                target = np.clip(x + (10 if y < 91 else 40) * self.direction, 15, 145)
                if y >= 91 and (x - position) * self.direction > 15:
                    # It has passed: prepare for its return across the screen.
                    target = 80
        else:
            self.shark_x = None
            self.speed_samples.clear()
        # Cut a tentacle before it reaches the diver's level.
        deadband = 3
        depths = []
        if not len(rows) or y < 91:
            tentacles = np.all(obs[110:140, 12:148] == 0, axis=2)
            widths = tentacles.sum(axis=1)
            depths = np.where((widths > 0) & (widths < 25))[0]
        if len(depths):
            tips = np.where(tentacles[depths[-1]])[0] + 12
            groups = np.split(tips, np.where(np.diff(tips) > 1)[0] + 1)
            tip = min((float(np.mean(g)) for g in groups), key=lambda x: abs(x - position))
            if self.tip_x is None or abs(tip - self.tip_x) >= 20:
                self.tip_direction = 0
            elif abs(tip - self.tip_x) >= 1:
                self.tip_direction = 1 if tip > self.tip_x else -1
            self.tip_x = tip
            if len(muzzle):
                position = np.mean(muzzle)
                target = tip + 2 * self.tip_direction
                deadband = 1.5
        else:
            self.tip_x = None
            self.tip_direction = 0
        delta = target - position
        move = 1 if delta > deadband else -1 if delta < -deadband else 0
        shoot = True
        if len(rows) and y >= 94 and self.direction:
            # Predict where the shark and muzzle will meet as a harpoon rises.
            # Use a recent median horizontal speed when it is consistently
            # faster than the default, but never below the default 8 px/step.
            if len(self.speed_samples) >= 3:
                shark_speed = max(8.0, min(14.0, float(np.median(self.speed_samples))))
            else:
                shark_speed = 8.0
            if len(muzzle):
                gun_x = float(np.mean(muzzle)) + 3 * move
                shark_x = x + self.direction * shark_speed * max(0, (133 - y) / 14)
                shoot = abs(shark_x - gun_x) <= 7
        if move > 0:
            return 4 if shoot else 2
        if move < 0:
            return 5 if shoot else 3
        return 1 if shoot else 0
