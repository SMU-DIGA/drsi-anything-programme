"""Navigate the maze, collect pellets, and keep away from ghosts."""
import heapq
from maze import XS, YS, MAZES

# ALE minimal actions: right, left, down, up.
DIRS = {2:(1,0), 3:(-1,0), 4:(0,1), 1:(0,-1)}
REVERSE = {2:3, 3:2, 4:1, 1:4}
POWER_BITS = {(18,14):32, (158,14):8, (18,146):16, (158,146):4}
# Dot flags are arranged in three RAM bytes per horizontal row:
# x column -> (byte offset within the row, bit).
DOT_COLUMNS = {18:(0,64), 26:(1,128), 34:(1,32), 42:(1,8),
               50:(1,2), 58:(2,1), 66:(2,4), 74:(2,16),
               102:(1,16), 110:(1,4), 118:(1,1), 126:(2,2),
               134:(2,8), 142:(2,32), 150:(2,128), 158:(0,16)}

# Tuned for sticky actions (2026-11-04); see NOTES.md for rejected variants.
GHOST_REVERSE_PENALTY = 4.0   # extra steps for a ghost to reach the node behind it
GHOST_HORIZON = 22            # ghost-distance search is truncated here
RISK_RADIUS = 14              # ghost distances below this add risk
AVOID_COST = 25.0             # extra cost on power pellets being saved
POWER_TRIGGER = 20            # save power pellets while ghosts are this far
TURN_COST = 2.7
REV_COST = 1.5
REV_COOLDOWN = 14             # within this many steps of a reversal...
REV_COOLDOWN_COST = 10.0      # ...another reversal costs this much more
HUNT_MIN_TIMER = 6
HUNT_BUDGET = 0.5
FRUIT_EARLY = 15              # fruit pursuit range on maze types 0-1 (40 later)
# Escape check (2026-11-04, g002): only take exits that still have a way out.
ESCAPE_MARGIN = 2.0           # steps we must beat a ghost to a node by
ESCAPE_DEPTH = 12             # steps of safe travel that count as escaped
HOUSE_EXIT_Y = 70             # in-house ghosts above this y count as leaving
# Eating dots slows Pac-Man, which matters when a ghost is following.
DOT_SLOW = 0.2                # escape check: edges onto a dot take this much longer
OCCUPIED_COST = 40.0          # route cost of walking an edge into an oncoming ghost


def in_house(x, y):
    return 74 <= x <= 102 and 60 <= y <= 88

def on_screen(x, y):
    return 12 <= x <= 166 and 0 <= y <= 164

def frightened_timer(obs):
    return int(obs[116]) & 63

def ghost_pos(obs, j):
    return int(obs[6+j]), int(obs[12+j])

def is_frightened(obs, j):
    return bool(int(obs[1+j]) & 128)

def offsets(x, y, dx, dy, px, py):
    """Position of (px, py) along and across the direction (dx, dy) from (x, y)."""
    return (px-x)*dx + (py-y)*dy, abs((px-x)*dy - (py-y)*dx)


class Policy:
    def __init__(self, spec):
        self.load_maze(0)
        self.reset()

    def load_maze(self, maze_type):
        self.maze_type = maze_type
        rows, vertical, horizontal, tunnels = MAZES[maze_type]
        self.graph = {}
        self.pellet_bits = []
        for j, y in enumerate(YS):
            for i, x in enumerate(XS):
                if rows[j][i] == '#':
                    continue
                p = (x,y)
                if rows[j][i] == 'o' and p not in POWER_BITS:
                    offset, bit = DOT_COLUMNS[x]
                    self.pellet_bits.append((p, 59 + 3*j + offset, bit))
                edges = []
                for action, (di, dj) in DIRS.items():
                    ii, jj = i+di, j+dj
                    if not (0 <= ii < len(XS) and 0 <= jj < len(YS)) or rows[jj][ii] == '#':
                        continue
                    if dj and vertical[min(j,jj)][i] == '0':
                        continue
                    if di and horizontal is not None and horizontal[j][min(i,ii)] == '0':
                        continue
                    q = (XS[ii],YS[jj])
                    cost = abs(q[0]-x)/2.5 + abs(q[1]-y)/3.5
                    edges.append((q,action,cost))
                self.graph[p] = edges
        # Side tunnels join the left and right borders.
        for y in tunnels:
            a,b = (18,y),(158,y)
            self.graph[a].append((b,3,8.0)); self.graph[b].append((a,2,8.0))
        center_rows = (2,26,50,98,122,146) if maze_type == 3 else (2,26,50,98,122,158)
        for y in center_rows:
            base = 59 + 3 * YS.index(y)
            self.pellet_bits.extend((((88,y), base+1, 64), ((88,y), base+2, 64)))

    def reset(self):
        if self.maze_type != 0:
            self.load_maze(0)
        self.prev = None
        self.heading = 3
        self.action = 3
        self.last_lives = 3
        self.still = 0
        self.decision = None
        self.prev_dot_count = None
        self.steps = 0
        self.prev_ghosts = None
        self.prev_flags = None
        self.ghost_dir = [None]*4
        self.eyes = [False]*4
        self.last_reverse = -100
        self.occupied = set()

    def nearest(self, x, y):
        return min(self.graph, key=lambda p: abs(p[0]-x)+abs(p[1]-y))

    def active_ghosts(self, obs):
        """Ghosts that can kill us: not frightened, not eyes, not in the house."""
        frightened = frightened_timer(obs) > 8
        for j in range(4):
            if (frightened and is_frightened(obs, j)) or self.eyes[j]:
                continue
            x, y = ghost_pos(obs, j)
            if not in_house(x, y):
                yield j, x, y

    def ghost_distances(self, obs, house=False):
        # Dijkstra gives distances along corridors rather than through walls.
        dist = {}
        heap = []
        occupied = self.occupied = set()
        def seed(p, d):
            if d < dist.get(p, 1e9):
                dist[p] = d
                heapq.heappush(heap,(d,p))
        for j, x, y in self.active_ghosts(obs):
            if not on_screen(x, y):
                continue
            ahead = behind = None
            if self.ghost_dir[j] is not None:
                gdx, gdy = self.ghost_dir[j]
                scale = 2.5 if gdx else 3.5
                for p in self.graph:
                    along, cross = offsets(x, y, gdx, gdy, *p)
                    if cross > 3 or abs(along) > 26:
                        continue
                    if along >= 0:
                        if ahead is None or along < ahead[0]:
                            ahead = (along, p)
                    elif behind is None or along > behind[0]:
                        behind = (along, p)
            if ahead is not None:
                # Ghosts rarely reverse, so the node behind is reached late.
                seed(ahead[1], ahead[0]/scale)
                if behind is not None:
                    seed(behind[1], -behind[0]/scale + GHOST_REVERSE_PENALTY)
                    # Walking this edge against the ghost meets it head-on,
                    # whatever the arrival times at the two end nodes say.
                    if ahead[0] > 0:
                        occupied.add((ahead[1], behind[1]))
            else:
                p = self.nearest(x,y)
                seed(p, abs(p[0]-x)/2.5 + abs(p[1]-y)/3.5)
        if house:
            # A ghost in the upper part of the house is on its way out through
            # the door above it and will appear at the door node shortly.
            frightened = frightened_timer(obs) > 8
            door = self.nearest(88, 50)
            for j in range(4):
                x, y = ghost_pos(obs, j)
                if (in_house(x, y) and y <= HOUSE_EXIT_Y and not self.eyes[j]
                        and not (frightened and is_frightened(obs, j))):
                    seed(door, abs(door[1]-y)/3.5 + abs(door[0]-x)/2.5)
        while heap:
            d,p = heapq.heappop(heap)
            if d != dist[p] or d > GHOST_HORIZON:
                continue
            for q,_,c in self.graph[p]:
                nd=d+c
                if nd < dist.get(q,1e9) and nd <= GHOST_HORIZON:
                    dist[q]=nd; heapq.heappush(heap,(nd,q))
        return dist

    def has_escape(self, start, q, cost, danger, powers=(), dots=(), pursued=False):
        """Can we get from start through exit q to a node no ghost reaches first?

        Our arrival time at each node must beat the ghost-distance estimate by
        ESCAPE_MARGIN. Normally an out-of-horizon node or ESCAPE_DEPTH steps
        of travel is enough; when pursued, require 20 steps of travel. A
        reachable power pellet also counts as an escape.
        """
        occupied = self.occupied
        if (start, q) in occupied:
            return False
        best = {start: 0.0}
        # Eating dots slows us down, so a following ghost gains on us.
        if q in dots:
            cost *= 1 + DOT_SLOW
        heap = [(cost, q)]
        while heap:
            t, p = heapq.heappop(heap)
            if t >= best.get(p, 1e9):
                continue
            g = danger.get(p)
            if g is not None and t + ESCAPE_MARGIN > g:
                continue
            best[p] = t
            # A close pursuer can follow through several turns, so look past
            # the first apparently clear node before calling that route safe.
            if ((g is None and not pursued) or t >= (20 if pursued else ESCAPE_DEPTH)
                    or p in powers):
                return True
            for r, _, c in self.graph[p]:
                if (p, r) in occupied:
                    continue
                if r in dots:
                    c *= 1 + DOT_SLOW
                if t + c < best.get(r, 1e9):
                    heapq.heappush(heap, (t + c, r))
        return False

    def safe_exits(self, start, danger, powers=(), dots=(), pursued=False):
        safe = {a for q, a, c in self.graph[start]
                if self.has_escape(start, q, c, danger, powers, dots, pursued)}
        return safe if safe else None

    def search(self, start, heading, danger, avoid, cooldown, allowed=None):
        """Ghost-aware Dijkstra from start; yields (cost, node, first action)."""
        def risk(node):
            g = danger.get(node, 100)
            return max(0, RISK_RADIUS-g)**2 * 1.8 + (AVOID_COST if node in avoid else 0)
        heap=[]
        best={}
        occupied = self.occupied
        for q, action, cost in self.graph[start]:
            if allowed is not None and action not in allowed:
                continue
            turn = 0 if action == heading else TURN_COST
            if action == REVERSE.get(heading):
                turn += REV_COST
                # Avoid dithering: a recent reversal is not undone lightly.
                if cooldown and self.steps - self.last_reverse <= REV_COOLDOWN:
                    turn += REV_COOLDOWN_COST
            total = cost+turn+risk(q)
            if (start, q) in occupied:
                total += OCCUPIED_COST
            if total < best.get(q,1e9):
                best[q]=total; heapq.heappush(heap,(total,q,action))
        while heap:
            d,p,first = heapq.heappop(heap)
            if d != best[p]: continue
            yield d, p, first
            for q,_,cost in self.graph[p]:
                nd=d+cost+risk(q)
                if (p, q) in occupied:
                    nd += OCCUPIED_COST
                if nd < best.get(q,1e9):
                    best[q]=nd; heapq.heappush(heap,(nd,q,first))

    def choose(self, start, heading, pellets, danger, avoid=(), fruit=None, allowed=None):
        # Remember the nearest pellet while looking for a short, low-risk
        # route to the moving fruit. Fall back if the detour is too costly.
        pellet_choice = None
        pellet_cost = 1e9
        for d, p, first in self.search(start, heading, danger, avoid, True, allowed):
            if d > min(22, pellet_cost + 12) and pellet_choice is not None:
                return pellet_choice
            if fruit is not None and p == fruit and d <= 22:
                return first
            if p in pellets and pellet_choice is None:
                if fruit is None:
                    return first
                pellet_choice, pellet_cost = first, d
        # If no pellets remain, continue exploring.
        if pellet_choice is not None:
            return pellet_choice
        if allowed:
            return min(allowed)
        return self.graph[start][0][1] if self.graph[start] else heading

    def hunt(self, start, heading, obs, danger, avoid):
        # Frightened ghosts are worth 200-1600 points; chase one that we can
        # reach well before the frightened timer (one tick per two steps) ends.
        timer = frightened_timer(obs)
        if timer <= HUNT_MIN_TIMER:
            return None
        prey = set()
        for j in range(4):
            gx, gy = ghost_pos(obs, j)
            if is_frightened(obs, j) and not in_house(gx, gy) and on_screen(gx, gy):
                prey.add(self.nearest(gx, gy))
        if not prey or start in prey:
            return None
        limit = HUNT_BUDGET * 2 * (timer - HUNT_MIN_TIMER)
        for d, p, first in self.search(start, heading, danger, avoid, False):
            if d > limit:
                return None
            if p in prey:
                return first
        return None

    def escape_exit(self, p, choice, danger):
        # When the planned exit leads straight into a ghost, take a safer
        # non-reversing exit even if it postpones the nearest dot.
        exits = [(danger.get(q, 100), a) for q, a, _ in self.graph[p]]
        planned = next((d for d, a in exits if a == choice), 100)
        if exits:
            safe, escape = max(exits)
            if planned < 6 and safe > 8 and safe > planned + 5 and escape != REVERSE[self.heading]:
                return escape
        return choice

    def head_on_threat(self, obs, x, y):
        # A ghost approaching head-on in our corridor, or entering the
        # junction just ahead from a side, can collide between decisions.
        # Reverse only if the corridor behind us is clear.
        dx, dy = DIRS[self.heading]
        ahead = False
        for j, gx, gy in self.active_ghosts(obs):
            along, cross = offsets(x, y, dx, dy, gx, gy)
            if cross > 3:
                continue
            if -30 <= along < 0:
                # A distant ghost moving away behind us is not an immediate
                # obstacle to a reversal; a close or closing ghost still is.
                px, py = self.prev_ghosts[j]
                moving = (gx-px)*dx + (gy-py)*dy
                if along >= -10 or moving >= 0:
                    return False
                continue
            if not 0 < along <= 24:
                continue
            if frightened_timer(obs) and is_frightened(obs, j):
                continue
            px, py = self.prev_ghosts[j]
            moving = (gx-px)*dx + (gy-py)*dy
            if moving < 0:
                ahead = True
            elif moving == 0 and along <= 12:
                for node in self.graph:
                    node_along, node_cross = offsets(x, y, dx, dy, *node)
                    nx, ny = node
                    if (len(self.graph[node]) >= 3
                            and 0 < node_along <= 12 and node_cross <= 2
                            and abs(gx-nx) + abs(gy-ny) <= 4
                            and abs(px-nx) + abs(py-ny) > abs(gx-nx) + abs(gy-ny)):
                        ahead = True
                        break
        return ahead

    def update_tracking(self, obs, x, y, lives):
        self.steps += 1
        if lives < self.last_lives:
            # All ghosts respawn after a life loss, including the one outside
            # the house, so none of the previous eyes remain harmless.
            self.eyes = [False]*4
            self.prev = None
            self.heading = self.action = 3
            self.decision = None
        self.last_lives = lives
        # A frightened ghost that loses its frightened bit while the timer is
        # still running has been eaten: its eyes return home and are harmless.
        timer = frightened_timer(obs)
        flags = [int(obs[1+j]) for j in range(4)]
        for j in range(4):
            gx, gy = ghost_pos(obs, j)
            if self.prev_flags is not None and timer > 2:
                if self.prev_flags[j] & 128 and not flags[j] & 128:
                    self.eyes[j] = True
            if self.eyes[j] and (in_house(gx, gy) or flags[j] & 128):
                self.eyes[j] = False
        self.prev_flags = flags
        # Each ghost's direction of travel since the previous frame.
        if self.prev_ghosts is not None:
            for j in range(4):
                gx, gy = ghost_pos(obs, j)
                px, py = self.prev_ghosts[j]
                mx, my = gx-px, gy-py
                if abs(mx) > 20 or abs(my) > 20:
                    self.ghost_dir[j] = None
                elif mx or my:
                    self.ghost_dir[j] = ((1 if mx > 0 else -1), 0) if abs(mx) > abs(my) else (0, (1 if my > 0 else -1))
        # Our own heading; tunnel wraps count as one step.
        if self.prev is not None:
            dx,dy=x-self.prev[0],y-self.prev[1]
            if abs(dx)>100: dx = -1 if dx>0 else 1
            if abs(dx)>0 or abs(dy)>0:
                self.heading = (2 if dx>0 else 3) if abs(dx)>abs(dy) else (4 if dy>0 else 1)
                self.still=0
            else:
                self.still += 1
        self.prev=(x,y)

    def decide(self, obs, p, x, y, powers, dots):
        danger = self.ghost_distances(obs)
        # Fruit moves through the maze and is worth much more on
        # later boards. Earlier fruit is pursued only when very close.
        fruit = None
        fx, fy = int(obs[11]), int(obs[17])
        if (on_screen(fx, fy)
                and abs(fx-x) + abs(fy-y) <= (40 if self.maze_type >= 2 else FRUIT_EARLY)):
            target = self.nearest(fx, fy)
            if target != p:
                fruit = target
        # Save power pellets until a ghost is close enough to be
        # worth eating, rather than wasting them on an empty maze.
        targets = powers | dots
        avoid = ()
        if (powers and dots and (frightened_timer(obs) > 8
                                 or danger.get(p, 100) >= POWER_TRIGGER)):
            targets = dots
            avoid = powers
        choice = self.hunt(p, self.heading, obs, danger, avoid)
        if choice is None:
            choice = self.choose(p, self.heading, targets, danger, avoid, fruit)
        choice = self.escape_exit(p, choice, danger)
        # Do not walk into a pocket that the ghosts can close off: if another
        # exit still has a way out, plan within those exits. Ghosts about to
        # leave the house count here but not in the route risk (too timid).
        dx, dy = DIRS[self.heading]
        pursued = any(-18 <= along < 0 and cross <= 3
                      for _, gx, gy in self.active_ghosts(obs)
                      for along, cross in [offsets(x, y, dx, dy, gx, gy)])
        safe = self.safe_exits(p, self.ghost_distances(obs, True), powers, dots, pursued)
        if safe is not None and choice not in safe:
            choice = self.choose(p, self.heading, targets, danger, avoid, fruit, safe)
        return choice

    def act(self, obs, info):
        maze_type = min(int(obs[0]), 3)
        if maze_type != self.maze_type:
            self.load_maze(maze_type)
            self.eyes = [False]*4
            self.decision = None
            self.prev_dot_count = None
        x,y = int(obs[10]),int(obs[16])
        self.update_tracking(obs, x, y, int(info.get('lives',3)))
        # Re-read dot flags rather than guessing consumption from position.
        powers = {p for p,bit in POWER_BITS.items() if int(obs[117]) & bit}
        dots = {p for p, i, bit in self.pellet_bits if int(obs[i]) & bit}
        if self.prev_dot_count is not None and len(dots) > self.prev_dot_count + 20:
            self.eyes = [False]*4
            self.decision = None   # a new board started
        self.prev_dot_count = len(dots)
        # Decide at the next graph point, early enough to buffer a turn.
        dx,dy=DIRS[self.heading]
        candidates=[]
        for p in self.graph:
            along, cross = offsets(x, y, dx, dy, *p)
            if cross <= 2 and -0.1 <= along <= 4:
                candidates.append((along,p))
        if candidates:
            p = min(candidates)[1]
            key=(p,self.heading)
            if key != self.decision or self.still >= 3:
                choice = self.decide(obs, p, x, y, powers, dots)
                if choice == REVERSE[self.heading]:
                    self.last_reverse = self.steps
                self.action = choice
                self.decision = key
                self.still=0
        elif self.still >= 3:
            p=self.nearest(x,y)
            self.action=self.choose(p,self.heading,powers | dots,self.ghost_distances(obs))
            self.decision=(p,self.heading)
            self.still=0
        if (self.action == self.heading and self.prev_ghosts is not None
                and self.head_on_threat(obs, x, y)):
            self.action = REVERSE[self.heading]
            self.decision = None
            self.last_reverse = self.steps
        self.prev_ghosts = [ghost_pos(obs, j) for j in range(4)]
        return self.action
