"""Color-based Battle Zone aiming with continuous fire and movement."""

import numpy as np


class Policy:
    def __init__(self, spec):
        pass

    def reset(self):
        pass

    def act(self, obs, info):
        # Enemy vehicles are blue; the red fallback also sees explosions.
        # Restrict detection to the landscape, excluding the radar and display.
        screen = obs[82:145].astype(np.int16)
        red, green, blue = screen[:, :, 0], screen[:, :, 1], screen[:, :, 2]
        xs = np.nonzero((blue > red + 30) & (blue > green + 10))[1]
        if xs.size < 4:
            xs = np.nonzero((red > green + 60) & (np.abs(green - blue) < 5) & (red > 145))[1]

        if xs.size < 4:
            return 15  # move and turn left while searching, firing
        x = xs.mean()
        # The gun is just left of screen center; allow four pixels of slack.
        if x < 73:
            return 17  # reverse and turn left, firing
        if x > 81:
            return 11  # turn right, firing
        return 13      # reverse and fire
