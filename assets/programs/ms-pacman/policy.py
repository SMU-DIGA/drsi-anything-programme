"""Navigate the maze, collect pellets, and keep away from ghosts."""
import heapq
from maze import XS, YS, MAZES

# ALE minimal actions: right, left, down, up.
DIRS = {2:(1,0), 3:(-1,0), 4:(0,1), 1:(0,-1)}
REVERSE = {2:3, 3:2, 4:1, 1:4}
POWER_BITS = {(18,14):32, (158,14):8, (18,146):16, (158,146):4}
FAST_LOSS_WINDOW = 600

class Policy:
    def __init__(self, spec):
        self.load_maze(0)
        self.reset()

    def load_maze(self, maze_type):
        self.maze_type = maze_type
        rows, vertical, horizontal, tunnels = MAZES[maze_type]
        self.graph = {}
        self.pellet_bits = []
        # Dot flags are arranged in three RAM bytes per horizontal row.
        columns = {18:(0,64), 26:(1,128), 34:(1,32), 42:(1,8),
                   50:(1,2), 58:(2,1), 66:(2,4), 74:(2,16),
                   102:(1,16), 110:(1,4), 118:(1,1), 126:(2,2),
                   134:(2,8), 142:(2,32), 150:(2,128), 158:(0,16)}
        for j, y in enumerate(YS):
            for i, x in enumerate(XS):
                if rows[j][i] == '#':
                    continue
                p = (x,y)
                if rows[j][i] == 'o' and p not in POWER_BITS:
                    offset, bit = columns[x]
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
        self.last_loss = None
        self.cautious = False
        self.needed_caution = False
        self.prev_ghosts = None

    def nearest(self, x, y):
        return min(self.graph, key=lambda p: abs(p[0]-x)+abs(p[1]-y))

    def active_ghosts(self, obs):
        frightened = (int(obs[116]) & 63) > 8
        for i in range(4):
            if frightened and int(obs[1+i]) & 128:
                continue
            x, y = int(obs[6+i]), int(obs[12+i])
            if not (74 <= x <= 102 and 60 <= y <= 88):
                yield x, y

    def ghost_distances(self, obs):
        # Dijkstra gives distances along corridors rather than through walls.
        dist = {}
        heap = []
        for x, y in self.active_ghosts(obs):
            if not (12 <= x <= 166 and 0 <= y <= 164):
                continue
            p = self.nearest(x,y)
            d = (abs(p[0]-x)/2.5 + abs(p[1]-y)/3.5)
            if d < dist.get(p, 1e9):
                dist[p] = d
                heapq.heappush(heap,(d,p))
        while heap:
            d,p = heapq.heappop(heap)
            if d != dist[p] or d > 22:
                continue
            for q,_,c in self.graph[p]:
                nd=d+c
                if nd < dist.get(q,1e9) and nd <= 22:
                    dist[q]=nd; heapq.heappush(heap,(nd,q))
        return dist

    def choose(self, start, heading, pellets, danger, fruit=None):
        # After rapid life losses, give ghosts more room. On earlier layouts,
        # also reduce reversals that can send us back into a pursuing ghost.
        radius = (18 if self.maze_type >= 2 else 16) if self.cautious else 14
        # After recovering an extra life, retain a smaller safety buffer if
        # a later loss once again leaves only one life.
        if self.needed_caution and not self.cautious and self.last_lives == 1 and self.maze_type >= 2:
            radius += 1
        reversal_cost = 3.0 if self.cautious and self.maze_type < 2 else 1.5
        def risk(node):
            return max(0, radius-danger.get(node,100))**2 * 1.8

        heap=[]
        best={}
        for q, action, cost in self.graph[start]:
            turn = 0 if action == heading else 2.7
            if action == REVERSE.get(heading): turn += reversal_cost
            total = cost+turn+risk(q)
            if total < best.get(q,1e9):
                best[q]=total; heapq.heappush(heap,(total,q,action))
        # Remember the nearest pellet while looking for a short, low-risk
        # route to the moving fruit. Fall back if the detour is too costly.
        pellet_choice = None
        pellet_cost = 1e9
        while heap:
            d,p,first = heapq.heappop(heap)
            if d != best[p]: continue
            if d > min(22, pellet_cost + 12) and pellet_choice is not None:
                return pellet_choice
            if fruit is not None and p == fruit and d <= 22:
                return first
            if p in pellets and pellet_choice is None:
                if fruit is None:
                    return first
                pellet_choice, pellet_cost = first, d
            for q,_,cost in self.graph[p]:
                nd=d+cost+risk(q)
                if nd < best.get(q,1e9):
                    best[q]=nd; heapq.heappush(heap,(nd,q,first))
        # If no pellets remain, continue exploring.
        if pellet_choice is not None:
            return pellet_choice
        return self.graph[start][0][1] if self.graph[start] else heading

    def corridor_margins(self, start, danger):
        # Missing ghost distances are at least 22 because the search is truncated.
        margins = []
        for q, action, cost in self.graph[start]:
            previous, node, elapsed = start, q, cost
            margin = danger.get(node, 22) - elapsed
            while len(self.graph[node]) == 2 and elapsed < 16:
                # Every two-edge corridor in the fixed mazes has a forward edge.
                following = next(edge for edge in self.graph[node] if edge[0] != previous)
                previous, node = node, following[0]
                elapsed += following[2]
                margin = min(margin, danger.get(node, 22) - elapsed)
            margins.append((margin, action))
        return margins

    def safe_choice(self, p, choice, danger, obs):
        maze_type = self.maze_type
        recovered = self.needed_caution and not self.cautious and self.last_lives == 1
        x, y = int(obs[10]), int(obs[16])
        dx, dy = DIRS[self.heading]
        reverse = REVERSE[self.heading]

        def ghost_offsets():
            for gx, gy in self.active_ghosts(obs):
                yield (gx-x)*dx + (gy-y)*dy, abs((gx-x)*dy - (gy-y)*dx)

        # In caution or recovery, compare interception margins at
        # corridor exits. Recovery can also permit a safe reversal.
        if maze_type >= 2 and (self.cautious or (recovered and len(self.graph[p]) >= 3)):
            margins = self.corridor_margins(p, danger)
            planned_margin = next((m for m, a in margins if a == choice), 100)
            forward_margins = [(m, a) for m, a in margins if a != reverse]
            if self.cautious and forward_margins:
                safe_margin, safe_action = max(forward_margins)
                if planned_margin <= 2 and safe_margin > 5 and safe_margin > planned_margin + 5:
                    choice = safe_action
            elif recovered:
                reverse_margin = next((m for m, a in margins if a == reverse), -100)
                if (choice != reverse and forward_margins and max(m for m, _ in forward_margins) <= 2
                        and planned_margin <= 2 and reverse_margin > 5 and reverse_margin > planned_margin + 6):
                    choice = reverse
        # When the planned exit leads straight into a ghost, take an
        # available safer exit even if it postpones the nearest dot.
        exits = [(danger.get(q, 100), a) for q, a, _ in self.graph[p]]
        planned = next((d for d, a in exits if a == choice), 100)
        if exits:
            safe, escape = max(exits)
            if planned < 6 and safe > 8 and safe > planned + 5 and escape != reverse:
                choice = escape
        # When a ghost is directly behind us, a comparably safe side
        # exit can break pursuit before another narrow passage.
        if recovered and choice == self.heading and len(self.graph[p]) >= 3:
            chased = any(-8 <= along < 0 and cross <= 2
                         for along, cross in ghost_offsets())
            if chased:
                forward = next((d for d, a in exits if a == self.heading), 0)
                sides = [(d, a) for d, a in exits
                         if a not in (self.heading, reverse)]
                if sides:
                    side_distance, side_action = max(sides)
                    if side_distance > 5 and side_distance >= forward - 2:
                        choice = side_action
        # Turning with a close pursuer behind can let it catch up.
        # In cautious mode, continue straight when that exit is comparably safe.
        if (self.cautious
                and choice not in (self.heading, reverse)):
            chased = any(-20 <= along < 0 and cross <= 4
                         for along, cross in ghost_offsets())
            forward = next((d for d, a in exits if a == self.heading), None)
            side = next((d for d, a in exits if a == choice), 100)
            # Do not commit to a long straight escape if another ghost is
            # already near the corridor ahead and could intercept it.
            threatened_ahead = any(0 < along <= 60 and cross <= 32
                                   for along, cross in ghost_offsets())
            if (chased and not threatened_ahead and forward is not None
                    and forward > 5 and forward >= side - 2):
                choice = self.heading
        return choice

    def act(self, obs, info):
        maze_type = min(int(obs[0]), 3)
        if maze_type != self.maze_type:
            self.load_maze(maze_type)
            self.decision = None
            self.prev_dot_count = None
        x,y = int(obs[10]),int(obs[16])
        lives = int(info.get('lives',3))
        self.steps += 1
        if lives > 1:
            self.cautious = False
        if lives < self.last_lives:
            # Keep the cautious mode until an extra life is earned.
            if (lives == 1 and self.last_loss is not None
                    and self.steps - self.last_loss <= FAST_LOSS_WINDOW):
                self.cautious = True
                self.needed_caution = True
            self.last_loss = self.steps
            self.prev = None
            self.heading = self.action = 3
            self.decision = None
        self.last_lives = lives
        if self.prev is not None:
            dx,dy=x-self.prev[0],y-self.prev[1]
            if abs(dx)>100: dx = -1 if dx>0 else 1
            if abs(dx)>0 or abs(dy)>0:
                self.heading = (2 if dx>0 else 3) if abs(dx)>abs(dy) else (4 if dy>0 else 1)
                self.still=0
            else:
                self.still += 1
        self.prev=(x,y)
        # Re-read dot flags rather than guessing consumption from position.
        powers = {p for p,bit in POWER_BITS.items() if int(obs[117]) & bit}
        dots = {p for p, i, bit in self.pellet_bits if int(obs[i]) & bit}
        if self.prev_dot_count is not None and len(dots) > self.prev_dot_count + 20:
            self.decision = None
        self.prev_dot_count = len(dots)
        pellets = powers | dots
        # Reconsider at the next graph point, early enough to buffer a turn.
        dx,dy=DIRS[self.heading]
        candidates=[]
        for p in self.graph:
            along=(p[0]-x)*dx+(p[1]-y)*dy
            cross=abs((p[0]-x)*dy-(p[1]-y)*dx)
            if cross <= 2 and -0.1 <= along <= 4:
                candidates.append((along,p))
        if candidates:
            along,p=min(candidates)
            key=(p,self.heading)
            if key != self.decision or self.still >= 3:
                danger = self.ghost_distances(obs)
                # Fruit moves through the maze and is worth much more on
                # later boards. Earlier fruit is pursued only when very close.
                fruit = None
                fx, fy = int(obs[11]), int(obs[17])
                fruit_distance = abs(fx-x) + abs(fy-y)
                if (12 <= fx <= 166 and 0 <= fy <= 164
                        and fruit_distance <= (40 if maze_type >= 2 else 15)
                        and not (self.needed_caution and lives == 1 and danger.get(p, 100) < 18)):
                    target = self.nearest(fx, fy)
                    if target != p:
                        fruit = target
                choice=self.choose(p,self.heading,pellets,danger,fruit)
                choice = self.safe_choice(p, choice, danger, obs)
                if choice == REVERSE[self.heading] and along > 1:
                    self.action = self.heading
                    self.decision = None
                else:
                    self.action = choice
                    self.decision = key
                self.still=0
        elif self.still >= 3:
            p=self.nearest(x,y)
            danger = self.ghost_distances(obs)
            self.action=self.choose(p,self.heading,pellets,danger)
            self.decision=(p,self.heading)
            self.still=0
        # A head-on ghost in a corridor can collide between graph decisions.
        # In the recovery state, reverse if it approaches and the rear is clear.
        ghosts = list(self.active_ghosts(obs))
        if (self.needed_caution and not self.cautious and lives == 1
                and maze_type >= 2 and self.action == self.heading
                and self.prev_ghosts is not None):
            dx, dy = DIRS[self.heading]
            ahead = False
            behind_clear = True
            for gx, gy in ghosts:
                along = (gx-x)*dx + (gy-y)*dy
                cross = abs((gx-x)*dy - (gy-y)*dx)
                if cross <= 3 and -30 <= along < 0:
                    behind_clear = False
                if cross <= 3 and 0 < along <= 24:
                    for j in range(4):
                        if (gx, gy) == (int(obs[6+j]), int(obs[12+j])):
                            if int(obs[116]) & 63 and int(obs[1+j]) & 128:
                                break
                            px, py = self.prev_ghosts[j]
                            if (gx-px)*dx + (gy-py)*dy < 0:
                                ahead = True
                            # A ghost entering the junction ahead from a side
                            # can turn into the corridor before we reach it.
                            if 0 < along <= 12 and (gx-px)*dx + (gy-py)*dy == 0:
                                for nx, ny in self.graph:
                                    node_along = (nx-x)*dx + (ny-y)*dy
                                    node_cross = abs((nx-x)*dy - (ny-y)*dx)
                                    if (len(self.graph[(nx, ny)]) >= 3
                                            and 0 < node_along <= 12 and node_cross <= 2
                                            and abs(gx-nx) + abs(gy-ny) <= 4
                                            and abs(px-nx) + abs(py-ny) > abs(gx-nx) + abs(gy-ny)):
                                        ahead = True
                                        break
                            break
            if ahead and behind_clear:
                self.action = REVERSE[self.heading]
                self.decision = None
        self.prev_ghosts = [(int(obs[6+j]), int(obs[12+j])) for j in range(4)]
        return self.action
