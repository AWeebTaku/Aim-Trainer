"""Aim Trainer - an arcade aim trainer with five drills: Classic, Reaction, Precision, Tracking, Flick."""
import json
import math
import random
import sys
from pathlib import Path

import pygame

WIDTH, HEIGHT = 900, 650
BAR_H = 56
PAD = 40
FPS = 60


def scores_path():
    # per-user data dir: survives packaged one-file builds (their install dir is a wiped temp folder)
    try:
        return Path(pygame.system.get_pref_path("Aim-Trainer", "Aim-Trainer")) / "highscores.json"
    except Exception:
        return Path.home() / ".aim_trainer_highscores.json"


SCORES_FILE = scores_path()

BG = (10, 14, 28)
GRID = (20, 28, 52)
PANEL = (22, 30, 56)
TEXT = (230, 236, 255)
DIM = (120, 132, 170)
ACCENT = (0, 220, 190)
RED = (255, 70, 90)
GOLD = (255, 200, 40)
BOMB = (150, 90, 255)

DIFFICULTIES = {
    # Classic: spawn -> floor (ms between targets) and grow rate both ease in over RAMP_MS, then stop: no inhuman speeds
    # radius / speed (px/s) are for Precision, Flick and Tracking
    "Easy": dict(spawn=850, floor=650, grow=0.16, lives=7, radius=26, speed=150),
    "Normal": dict(spawn=700, floor=500, grow=0.20, lives=5, radius=19, speed=220),
    "Hard": dict(spawn=560, floor=400, grow=0.26, lives=3, radius=14, speed=300),
}
RAMP_MS = 180_000
RAMP_GROW = 0.3  # targets end up at most 30% faster than at the start


def load_scores():
    try:
        raw = json.loads(SCORES_FILE.read_text())
    except (OSError, ValueError):
        return {}
    # scores saved before the other modes existed were keyed by difficulty only
    return {(k if ":" in k else f"classic:{k}"): v for k, v in raw.items()}


def save_scores(scores):
    try:
        SCORES_FILE.write_text(json.dumps(scores))
    except OSError:
        pass  # read-only install dir: just skip persistence


def rings(win, x, y, size, a=RED, b=TEXT):
    for scale, col in ((1, a), (0.8, b), (0.6, a), (0.4, b)):
        pygame.draw.circle(win, col, (int(x), int(y)), max(1, int(size * scale)))


def rand_pos(margin):
    return random.randint(PAD, WIDTH - PAD), random.randint(BAR_H + margin, HEIGHT - PAD)


class Target:
    MAX = 32

    def __init__(self, x, y, kind, grow):
        self.x, self.y, self.kind = x, y, kind
        self.size, self.dir = 0.0, 1
        self.rate = grow * (1.4 if kind == "gold" else 1.0)

    def update(self, dt):
        step = self.rate * dt * FPS / 1000 * 3
        if self.size + step >= self.MAX:
            self.dir = -1
        self.size += step * self.dir

    @property
    def dead(self):
        return self.size <= 0

    def hit(self, pos):
        return math.dist(pos, (self.x, self.y)) <= self.size

    def draw(self, win):
        a, b = {"normal": (RED, TEXT), "gold": (GOLD, TEXT), "bomb": (BOMB, (30, 20, 60))}[self.kind]
        rings(win, self.x, self.y, self.size, a, b)
        if self.kind == "bomb":
            c = (int(self.x), int(self.y))
            pygame.draw.line(win, TEXT, (c[0] - 6, c[1] - 6), (c[0] + 6, c[1] + 6), 3)
            pygame.draw.line(win, TEXT, (c[0] - 6, c[1] + 6), (c[0] + 6, c[1] - 6), 3)


class Particle:
    def __init__(self, x, y, color):
        ang, spd = random.uniform(0, math.tau), random.uniform(1, 6)
        self.x, self.y, self.color = x, y, color
        self.vx, self.vy = math.cos(ang) * spd, math.sin(ang) * spd
        self.life = self.max = random.randint(20, 40)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.15
        self.life -= 1

    def draw(self, win):
        r = max(1, int(4 * self.life / self.max))
        pygame.draw.circle(win, self.color, (int(self.x), int(self.y)), r)


class Popup:
    def __init__(self, x, y, text, color):
        self.x, self.y, self.text, self.color, self.life = x, y, text, color, 45

    def update(self):
        self.y -= 1
        self.life -= 1


def tick(things):
    for t in things:
        t.update()
    return [t for t in things if t.life > 0]


class Mode:
    """One drill. Game calls click/update/draw until `done`, then reads score() and stats()."""
    key = name = desc = ""
    score_label = "Score"
    over_title = "RESULTS"
    lower = False       # lower score is better (times)
    uses_diff = True

    def __init__(self, g, diff):
        self.g, self.diff, self.cfg = g, diff, DIFFICULTIES[diff]
        self.done = False

    @staticmethod
    def fmt(v):
        return f"{v:,}"

    def aim(self):
        """Where a perfect player would point right now (used by the CI smoke test)."""
        return (0, 0)

    def click(self, pos): ...
    def update(self, dt, mouse): ...
    def draw(self): ...
    def score(self): return 0
    def stats(self): return []


class Classic(Mode):
    key, name = "classic", "Classic"
    desc = "Shrinking targets. Build combos, dodge bombs."
    over_title = "GAME OVER"

    def __init__(self, g, diff):
        super().__init__(g, diff)
        self.targets, self.parts, self.pops = [], [], []
        self.pts = self.hits = self.clicks = self.combo = self.best_combo = 0
        self.elapsed = self.spawn_in = 0
        self.lives = self.cfg["lives"]

    @property
    def ramp(self):
        return min(self.elapsed / RAMP_MS, 1)

    @property
    def mult(self):
        return min(1 + self.combo // 5, 8)

    def burst(self, x, y, color, n=18):
        self.parts += [Particle(x, y, color) for _ in range(n)]

    def lose_life(self):
        self.lives -= 1
        self.combo = 0
        self.g.shake = 12
        self.done = self.lives <= 0

    def click(self, pos):
        self.clicks += 1
        for t in reversed(self.targets):  # topmost first
            if t.hit(pos):
                self.targets.remove(t)
                if t.kind == "bomb":
                    self.burst(t.x, t.y, BOMB, 30)
                    self.pops.append(Popup(t.x, t.y, "BOMB! -1 life", BOMB))
                    self.lose_life()
                else:
                    gold = t.kind == "gold"
                    self.hits += 1
                    self.combo += 1
                    self.best_combo = max(self.best_combo, self.combo)
                    pts = (50 if gold else 10) * self.mult
                    self.pts += pts
                    if gold and self.lives < self.cfg["lives"]:
                        self.lives += 1
                    self.burst(t.x, t.y, GOLD if gold else RED)
                    self.pops.append(Popup(t.x, t.y, f"+{pts}", GOLD if gold else TEXT))
                return
        self.combo = 0  # clicked empty space

    def spawn(self):
        r = random.random()
        kind = "gold" if r < 0.06 else "bomb" if r < 0.06 + 0.04 + 0.06 * self.ramp else "normal"
        x, y = rand_pos(PAD)
        self.targets.append(Target(x, y, kind, self.cfg["grow"] * (1 + RAMP_GROW * self.ramp)))

    def update(self, dt, mouse):
        self.elapsed += dt
        self.spawn_in -= dt
        if self.spawn_in <= 0:
            self.spawn()
            self.spawn_in = self.cfg["spawn"] + (self.cfg["floor"] - self.cfg["spawn"]) * self.ramp
        for t in self.targets:
            t.update(dt)
        for t in [t for t in self.targets if t.dead]:
            self.targets.remove(t)
            if t.kind != "bomb":  # letting a bomb fade is the correct play
                self.pops.append(Popup(t.x, t.y, "MISS", DIM))
                self.lose_life()
        self.parts, self.pops = tick(self.parts), tick(self.pops)

    def draw(self):
        g = self.g
        g.draw_bg()
        for t in self.targets:
            t.draw(g.win)
        for p in self.parts:
            p.draw(g.win)
        for p in self.pops:
            g.text(g.small, p.text, p.color, center=(int(p.x), int(p.y) - 30))
        acc = self.hits / self.clicks * 100 if self.clicks else 100
        g.bar((16, g.mid, f"{self.pts:,}", TEXT),
              (210, g.small, f"x{self.mult}  combo {self.combo}", GOLD if self.mult > 1 else DIM),
              (430, g.small, f"acc {acc:.0f}%", DIM),
              (550, g.small, f"{self.elapsed / 1000:.1f}s", DIM))
        for i in range(self.cfg["lives"]):  # life pips
            pygame.draw.circle(g.win, RED if i < self.lives else GRID, (WIDTH - 20 - i * 24, BAR_H // 2), 8)

    def score(self):
        return self.pts

    def stats(self):
        acc = self.hits / self.clicks * 100 if self.clicks else 0
        secs = max(self.elapsed / 1000, 0.1)
        return [("Hits", self.hits), ("Accuracy", f"{acc:.1f}%"), ("Speed", f"{self.hits / secs:.2f} t/s"),
                ("Best combo", self.best_combo), ("Time", f"{secs:.1f}s")]


class Reaction(Mode):
    key, name = "reaction", "Reaction"
    desc = "Click the instant the screen turns green. Five rounds."
    score_label = "Average"
    lower, uses_diff = True, False
    ROUNDS = 5

    def __init__(self, g, diff):
        super().__init__(g, diff)
        self.times, self.early, self.last, self.t0 = [], 0, 0, 0
        self.wait()

    def wait(self):
        self.phase, self.timer = "wait", random.randint(1500, 4000)

    @staticmethod
    def fmt(v):
        return f"{v} ms"

    def click(self, pos):
        if self.phase == "wait":  # jumped the gun
            self.early += 1
            self.phase, self.timer = "early", 1200
        elif self.phase == "go":
            self.last = pygame.time.get_ticks() - self.t0
            self.times.append(self.last)
            self.phase, self.timer = "result", 1200
        else:
            self.timer = 0  # skip the pause

    def update(self, dt, mouse):
        self.timer -= dt
        if self.timer > 0:
            return
        if self.phase == "wait":
            self.phase, self.timer, self.t0 = "go", 10**9, pygame.time.get_ticks()
        elif self.phase == "early" or (self.phase == "result" and len(self.times) < self.ROUNDS):
            self.wait()
        elif self.phase == "result":
            self.done = True

    def draw(self):
        g = self.g
        bg, msg, col = {"wait": ((70, 18, 30), "Wait for green...", TEXT),
                        "go": (ACCENT, "CLICK!", (4, 17, 15)),
                        "early": ((70, 18, 30), "Too soon!", RED),
                        "result": (PANEL, f"{self.last} ms", ACCENT)}[self.phase]
        g.win.fill(bg)
        g.text(g.big, msg, col, center=(WIDTH // 2, HEIGHT // 2))
        g.bar((16, g.mid, f"Round {min(len(self.times) + (self.phase != 'result'), self.ROUNDS)}/{self.ROUNDS}", TEXT),
              (300, g.small, f"too soon: {self.early}", DIM))

    def score(self):
        return round(sum(self.times) / len(self.times)) if self.times else 0

    def stats(self):
        return [("Rounds", ", ".join(map(str, self.times))), ("Fastest", f"{min(self.times, default=0)} ms"),
                ("Slowest", f"{max(self.times, default=0)} ms"), ("Too soon", self.early)]


class Precision(Mode):
    key, name = "precision", "Precision"
    desc = "20 small targets. Closer to center scores more."
    N = 20

    def __init__(self, g, diff):
        super().__init__(g, diff)
        self.r = self.cfg["radius"]
        self.n = self.hits = self.pts = self.t = 0
        self.offsets, self.pops = [], []
        self.x, self.y = rand_pos(PAD)

    def aim(self):
        return (self.x, self.y)

    def click(self, pos):
        d = math.dist(pos, (self.x, self.y))
        p = round(100 * (1 - d / self.r)) if d <= self.r else 0
        if p:
            self.hits += 1
            self.offsets.append(d)
        self.pts += p
        self.pops.append(Popup(self.x, self.y, f"+{p}" if p else "MISS", GOLD if p > 90 else TEXT if p else DIM))
        self.n += 1
        if self.n >= self.N:
            self.done = True
        else:
            self.x, self.y = rand_pos(PAD)

    def update(self, dt, mouse):
        self.t += dt
        self.pops = tick(self.pops)

    def draw(self):
        g = self.g
        g.draw_bg()
        rings(g.win, self.x, self.y, self.r)
        for p in self.pops:
            g.text(g.small, p.text, p.color, center=(int(p.x), int(p.y) - self.r - 14))
        g.bar((16, g.mid, f"{self.pts:,}", TEXT), (210, g.small, f"shot {min(self.n + 1, self.N)}/{self.N}", DIM),
              (430, g.small, f"{self.t / 1000:.1f}s", DIM))

    def score(self):
        return self.pts

    def stats(self):
        avg = sum(self.offsets) / len(self.offsets) if self.offsets else 0
        return [("Hits", f"{self.hits}/{self.N}"), ("Avg distance from center", f"{avg:.1f}px"),
                ("Accuracy", f"{self.hits / max(self.n, 1) * 100:.0f}%"), ("Time", f"{self.t / 1000:.1f}s")]


class Tracking(Mode):
    key, name = "tracking", "Tracking"
    desc = "Keep your cursor on the moving target for 30 seconds."
    DURATION = 30_000

    def __init__(self, g, diff):
        super().__init__(g, diff)
        self.r, self.speed = self.cfg["radius"] + 8, self.cfg["speed"]
        self.x, self.y = WIDTH / 2, HEIGHT / 2
        self.ang, self.turn, self.turn_in = random.uniform(0, math.tau), 0, 0
        self.t = self.on_ms = self.cur = self.best = 0
        self.on = False

    def aim(self):
        return (self.x, self.y)

    def update(self, dt, mouse):
        self.t += dt
        self.turn_in -= dt
        if self.turn_in <= 0:  # pick a new gentle curve every 0.5 to 1.5 s
            self.turn, self.turn_in = random.uniform(-2.5, 2.5), random.randint(500, 1500)
        self.ang += self.turn * dt / 1000
        self.x += math.cos(self.ang) * self.speed * dt / 1000
        self.y += math.sin(self.ang) * self.speed * dt / 1000
        r = self.r
        if self.x < r or self.x > WIDTH - r:
            self.x, self.ang = min(max(self.x, r), WIDTH - r), math.pi - self.ang
        if self.y < BAR_H + r or self.y > HEIGHT - r:
            self.y, self.ang = min(max(self.y, BAR_H + r), HEIGHT - r), -self.ang
        self.on = math.dist(mouse, (self.x, self.y)) <= r
        if self.on:
            self.on_ms += dt
            self.cur += dt
            self.best = max(self.best, self.cur)
        else:
            self.cur = 0
        self.done = self.t >= self.DURATION

    def draw(self):
        g = self.g
        g.draw_bg()
        rings(g.win, self.x, self.y, self.r, ACCENT if self.on else RED, TEXT)
        g.bar((16, g.mid, f"{self.on_ms / max(self.t, 1) * 100:.0f}% on target", ACCENT if self.on else TEXT),
              (330, g.small, f"{max(self.DURATION - self.t, 0) / 1000:.1f}s left", DIM),
              (520, g.small, f"streak {self.cur / 1000:.1f}s", DIM))

    def score(self):
        return round(self.on_ms / 10)

    def stats(self):
        return [("On target", f"{self.on_ms / max(self.t, 1) * 100:.0f}%"),
                ("Longest streak", f"{self.best / 1000:.1f}s"), ("Time on target", f"{self.on_ms / 1000:.1f}s")]


class Flick(Mode):
    key, name = "flick", "Flick"
    desc = "Hit 30 targets as fast as you can. Misclicks add 0.5 s."
    score_label = "Time"
    lower = True
    N, PENALTY = 30, 500

    def __init__(self, g, diff):
        super().__init__(g, diff)
        self.r = self.cfg["radius"]
        self.n = self.t = self.miss = 0
        self.x, self.y = rand_pos(PAD)

    @staticmethod
    def fmt(v):
        return f"{v:.2f}s"

    def aim(self):
        return (self.x, self.y)

    def click(self, pos):
        if math.dist(pos, (self.x, self.y)) > self.r:
            self.miss += 1
            return
        self.n += 1
        if self.n >= self.N:
            self.done = True
            return
        px, py = self.x, self.y
        for _ in range(20):  # make each flick a real jump
            self.x, self.y = rand_pos(PAD)
            if math.dist((px, py), (self.x, self.y)) > 220:
                break

    def update(self, dt, mouse):
        self.t += dt

    def draw(self):
        g = self.g
        g.draw_bg()
        rings(g.win, self.x, self.y, self.r)
        g.bar((16, g.mid, f"{self.score():.2f}s", TEXT), (210, g.small, f"{self.n}/{self.N}", DIM),
              (330, g.small, f"misses {self.miss}", RED if self.miss else DIM))

    def score(self):
        return round((self.t + self.miss * self.PENALTY) / 1000, 2)

    def stats(self):
        clicks = self.n + self.miss
        return [("Targets", self.n), ("Accuracy", f"{self.n / max(clicks, 1) * 100:.0f}%"),
                ("Misclicks", f"{self.miss} (+{self.miss * self.PENALTY / 1000:.1f}s)"),
                ("Per target", f"{self.t / max(self.n, 1):.0f} ms")]


MODES = [Classic, Reaction, Precision, Tracking, Flick]


class Game:
    def __init__(self):
        pygame.init()
        self.win = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Aim Trainer")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.big = pygame.font.Font(None, 96)
        self.mid = pygame.font.Font(None, 42)
        self.small = pygame.font.Font(None, 28)
        self.tiny = pygame.font.Font(None, 24)
        self.scores = load_scores()
        self.state, self.diff, self.sel = "menu", "Normal", 0
        self.shake, self.paused = 0, False

    # ---- helpers -------------------------------------------------------
    def text(self, font, s, color, center=None, topleft=None):
        img = font.render(s, True, color)
        self.win.blit(img, img.get_rect(center=center) if center else topleft)

    def key_for(self, cls):
        return f"{cls.key}:{self.diff}" if cls.uses_diff else cls.key

    def start(self):
        self.mode = MODES[self.sel](self, self.diff)
        self.paused, self.new_best, self.state = False, False, "play"

    def finish(self):
        m = self.mode
        v, key = m.score(), self.key_for(type(m))
        best = self.scores.get(key)
        self.new_best = (best is None and (m.lower or v > 0)) or (best is not None and (v < best if m.lower else v > best))
        if self.new_best:
            self.scores[key] = v
            save_scores(self.scores)
        self.state = "over"

    # ---- drawing -------------------------------------------------------
    def draw_bg(self):
        self.win.fill(BG)
        for x in range(0, WIDTH, 50):
            pygame.draw.line(self.win, GRID, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, 50):
            pygame.draw.line(self.win, GRID, (0, y), (WIDTH, y))

    def bar(self, *items):
        pygame.draw.rect(self.win, PANEL, (0, 0, WIDTH, BAR_H))
        pygame.draw.line(self.win, ACCENT, (0, BAR_H), (WIDTH, BAR_H), 2)
        for x, font, s, col in items:
            self.text(font, s, col, topleft=(x, 14 if font is self.mid else 19))

    def draw_cursor(self):
        x, y = pygame.mouse.get_pos()
        pygame.draw.circle(self.win, ACCENT, (x, y), 12, 2)
        pygame.draw.line(self.win, ACCENT, (x - 18, y), (x - 6, y), 2)
        pygame.draw.line(self.win, ACCENT, (x + 6, y), (x + 18, y), 2)
        pygame.draw.line(self.win, ACCENT, (x, y - 18), (x, y - 6), 2)
        pygame.draw.line(self.win, ACCENT, (x, y + 6), (x, y + 18), 2)

    def row_rect(self, i):
        return pygame.Rect(WIDTH // 2 - 330, 175 + i * 72, 660, 62)

    def chip_rect(self, i):
        return pygame.Rect(WIDTH // 2 - 195 + i * 135, 548, 125, 40)

    def draw_menu(self):
        self.draw_bg()
        self.text(self.big, "AIM TRAINER", ACCENT, center=(WIDTH // 2, 80))
        self.text(self.small, "pick a drill", DIM, center=(WIDTH // 2, 136))
        for i, cls in enumerate(MODES):
            sel, r = i == self.sel, self.row_rect(i)
            pygame.draw.rect(self.win, PANEL, r, border_radius=12)
            pygame.draw.rect(self.win, ACCENT if sel else GRID, r, 3, border_radius=12)
            self.text(self.mid, f"{i + 1}  {cls.name}", TEXT if sel else DIM, topleft=(r.x + 18, r.y + 8))
            self.text(self.tiny, cls.desc, DIM, topleft=(r.x + 52, r.y + 38))
            best = self.scores.get(self.key_for(cls))
            self.text(self.small, f"best {cls.fmt(best)}" if best is not None else "no score yet", GOLD if best is not None else GRID,
                      center=(r.right - 80, r.centery))
        for i, d in enumerate(DIFFICULTIES):
            r, sel = self.chip_rect(i), d == self.diff
            pygame.draw.rect(self.win, PANEL, r, border_radius=10)
            pygame.draw.rect(self.win, ACCENT if sel else GRID, r, 3, border_radius=10)
            self.text(self.small, d, TEXT if sel else DIM, center=r.center)
        self.text(self.tiny, "left/right: difficulty (Reaction ignores it)   |   1-5 or click: start   |   Esc: quit", DIM,
                  center=(WIDTH // 2, HEIGHT - 38))

    def draw_over(self):
        m = self.mode
        self.draw_bg()
        self.text(self.big, m.over_title, RED if m.over_title == "GAME OVER" else ACCENT, center=(WIDTH // 2, 120))
        self.text(self.mid, f"{m.score_label}  {m.fmt(m.score())}", TEXT, center=(WIDTH // 2, 210))
        best = self.scores.get(self.key_for(type(m)))
        if self.new_best:
            self.text(self.mid, "NEW BEST!", GOLD, center=(WIDTH // 2, 255))
        elif best is not None:
            self.text(self.small, f"best: {m.fmt(best)}", DIM, center=(WIDTH // 2, 255))
        for i, (k, v) in enumerate(m.stats()):
            self.text(self.mid, k, DIM, topleft=(WIDTH // 2 - 250, 320 + i * 44))
            img = self.mid.render(str(v), True, TEXT)
            self.win.blit(img, (WIDTH // 2 + 250 - img.get_width(), 320 + i * 44))
        self.text(self.small, "R / click: retry   |   M: menu   |   Esc: quit", DIM, center=(WIDTH // 2, HEIGHT - 40))

    # ---- main loop -----------------------------------------------------
    def handle(self, e):
        if self.state == "menu":
            if e.type == pygame.KEYDOWN:
                if pygame.K_1 <= e.key < pygame.K_1 + len(MODES):
                    self.sel = e.key - pygame.K_1
                    self.start()
                elif e.key in (pygame.K_UP, pygame.K_DOWN):
                    self.sel = (self.sel + (1 if e.key == pygame.K_DOWN else -1)) % len(MODES)
                elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    ds = list(DIFFICULTIES)
                    self.diff = ds[(ds.index(self.diff) + (1 if e.key == pygame.K_RIGHT else -1)) % len(ds)]
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.start()
            if e.type == pygame.MOUSEMOTION:
                for i in range(len(MODES)):
                    if self.row_rect(i).collidepoint(e.pos):
                        self.sel = i
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, d in enumerate(DIFFICULTIES):
                    if self.chip_rect(i).collidepoint(e.pos):
                        self.diff = d
                if self.row_rect(self.sel).collidepoint(e.pos):
                    self.start()
        elif self.state == "play":
            if e.type == pygame.KEYDOWN and e.key in (pygame.K_p, pygame.K_SPACE):
                self.paused = not self.paused
            if e.type == pygame.WINDOWFOCUSLOST:
                self.paused = True
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and not self.paused:
                self.mode.click(e.pos)
        else:  # over
            if e.type == pygame.MOUSEBUTTONDOWN or (e.type == pygame.KEYDOWN and e.key == pygame.K_r):
                self.start()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_m:
                self.state = "menu"

    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    pygame.quit()
                    sys.exit()
                self.handle(e)

            if self.state == "play" and not self.paused:
                self.mode.update(dt, pygame.mouse.get_pos())
                if self.mode.done:
                    self.finish()

            {"menu": self.draw_menu, "play": lambda: self.mode.draw(), "over": self.draw_over}[self.state]()
            if self.state == "play" and self.paused:
                veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                veil.fill((0, 0, 0, 150))
                self.win.blit(veil, (0, 0))
                self.text(self.big, "PAUSED", TEXT, center=(WIDTH // 2, HEIGHT // 2))
            self.draw_cursor()
            if self.shake > 0:  # screen shake on life loss
                self.shake -= 1
                self.win.blit(self.win.copy(), (random.randint(-5, 5), random.randint(-5, 5)))
            pygame.display.flip()


if __name__ == "__main__":
    Game().run()
