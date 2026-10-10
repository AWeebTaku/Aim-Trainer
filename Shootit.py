"""Shootit - an arcade aim trainer. Hit targets, build combos, don't run out of lives."""
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
SCORES_FILE = Path(__file__).with_name("highscores.json")

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
    "Easy": dict(spawn=800, floor=450, grow=0.16, lives=7),
    "Normal": dict(spawn=620, floor=320, grow=0.22, lives=5),
    "Hard": dict(spawn=480, floor=220, grow=0.30, lives=3),
}


def load_scores():
    try:
        return json.loads(SCORES_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_scores(scores):
    try:
        SCORES_FILE.write_text(json.dumps(scores))
    except OSError:
        pass  # read-only install dir: just skip persistence


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
        c = (int(self.x), int(self.y))
        for scale, col in ((1, a), (0.8, b), (0.6, a), (0.4, b)):
            pygame.draw.circle(win, col, c, max(1, int(self.size * scale)))
        if self.kind == "bomb":
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


class Game:
    def __init__(self):
        pygame.init()
        self.win = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Shootit - Aim Trainer")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()
        self.big = pygame.font.Font(None, 96)
        self.mid = pygame.font.Font(None, 42)
        self.small = pygame.font.Font(None, 28)
        self.scores = load_scores()
        self.state, self.diff = "menu", "Normal"
        self.shake = 0

    # ---- helpers -------------------------------------------------------
    def text(self, font, s, color, center=None, topleft=None):
        img = font.render(s, True, color)
        self.win.blit(img, img.get_rect(center=center) if center else topleft)

    def start(self, diff):
        self.diff, self.cfg = diff, DIFFICULTIES[diff]
        self.targets, self.parts, self.pops = [], [], []
        self.score = self.hits = self.clicks = self.combo = self.best_combo = self.misses = 0
        self.elapsed = 0  # ms of unpaused play
        self.spawn_in = 0
        self.lives = self.cfg["lives"]
        self.new_best = False
        self.state = "play"

    def burst(self, x, y, color, n=18):
        self.parts += [Particle(x, y, color) for _ in range(n)]

    @property
    def mult(self):
        return min(1 + self.combo // 5, 8)

    def lose_life(self):
        self.lives -= 1
        self.combo = 0
        self.shake = 12
        if self.lives <= 0:
            best = self.scores.get(self.diff, 0)
            self.new_best = self.score > best
            if self.new_best:
                self.scores[self.diff] = self.score
                save_scores(self.scores)
            self.state = "over"

    # ---- gameplay ------------------------------------------------------
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
                    self.score += pts
                    if gold and self.lives < self.cfg["lives"]:
                        self.lives += 1
                    self.burst(t.x, t.y, GOLD if gold else RED)
                    self.pops.append(Popup(t.x, t.y, f"+{pts}", GOLD if gold else TEXT))
                return
        self.combo = 0  # clicked empty space

    def spawn(self):
        r = random.random()
        kind = "gold" if r < 0.06 else "bomb" if r < 0.06 + min(0.04 + self.elapsed / 600000, 0.14) else "normal"
        x = random.randint(PAD, WIDTH - PAD)
        y = random.randint(PAD + BAR_H, HEIGHT - PAD)
        self.targets.append(Target(x, y, kind, self.cfg["grow"] + self.elapsed / 600000))

    def update(self, dt):
        self.elapsed += dt
        self.spawn_in -= dt
        if self.spawn_in <= 0:
            self.spawn()
            # ramp: interval shrinks 10ms every second until the floor
            self.spawn_in = max(self.cfg["floor"], self.cfg["spawn"] - self.elapsed / 100)
        for t in self.targets:
            t.update(dt)
        for t in [t for t in self.targets if t.dead]:
            self.targets.remove(t)
            if t.kind != "bomb":  # letting a bomb fade is the correct play
                self.pops.append(Popup(t.x, t.y, "MISS", DIM))
                self.misses += 1
                self.lose_life()
        for p in self.parts + self.pops:
            p.update()
        self.parts = [p for p in self.parts if p.life > 0]
        self.pops = [p for p in self.pops if p.life > 0]

    # ---- drawing -------------------------------------------------------
    def draw_bg(self):
        self.win.fill(BG)
        for x in range(0, WIDTH, 50):
            pygame.draw.line(self.win, GRID, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, 50):
            pygame.draw.line(self.win, GRID, (0, y), (WIDTH, y))

    def draw_cursor(self):
        x, y = pygame.mouse.get_pos()
        pygame.draw.circle(self.win, ACCENT, (x, y), 12, 2)
        pygame.draw.line(self.win, ACCENT, (x - 18, y), (x - 6, y), 2)
        pygame.draw.line(self.win, ACCENT, (x + 6, y), (x + 18, y), 2)
        pygame.draw.line(self.win, ACCENT, (x, y - 18), (x, y - 6), 2)
        pygame.draw.line(self.win, ACCENT, (x, y + 6), (x, y + 18), 2)

    def draw_play(self):
        self.draw_bg()
        for t in self.targets:
            t.draw(self.win)
        for p in self.parts:
            p.draw(self.win)
        for p in self.pops:
            self.text(self.small, p.text, p.color, center=(int(p.x), int(p.y) - 30))
        pygame.draw.rect(self.win, PANEL, (0, 0, WIDTH, BAR_H))
        pygame.draw.line(self.win, ACCENT, (0, BAR_H), (WIDTH, BAR_H), 2)
        acc = self.hits / self.clicks * 100 if self.clicks else 100
        self.text(self.mid, f"{self.score:,}", TEXT, topleft=(16, 14))
        self.text(self.small, f"x{self.mult}  combo {self.combo}", GOLD if self.mult > 1 else DIM, topleft=(210, 19))
        self.text(self.small, f"acc {acc:.0f}%", DIM, topleft=(430, 19))
        self.text(self.small, f"{self.elapsed / 1000:.1f}s", DIM, topleft=(550, 19))
        for i in range(self.cfg["lives"]):  # life pips
            col = RED if i < self.lives else GRID
            pygame.draw.circle(self.win, col, (WIDTH - 20 - i * 24, BAR_H // 2), 8)

    def draw_menu(self):
        self.draw_bg()
        self.text(self.big, "SHOOTIT", ACCENT, center=(WIDTH // 2, 130))
        self.text(self.small, "click targets  |  keep your combo  |  gold heals  |  don't click bombs", DIM, center=(WIDTH // 2, 190))
        for i, d in enumerate(DIFFICULTIES):
            sel = d == self.diff
            r = pygame.Rect(WIDTH // 2 - 200, 250 + i * 80, 400, 64)
            pygame.draw.rect(self.win, PANEL, r, border_radius=12)
            pygame.draw.rect(self.win, ACCENT if sel else GRID, r, 3, border_radius=12)
            self.text(self.mid, f"{i + 1}  {d}", TEXT if sel else DIM, center=(r.x + 110, r.centery))
            self.text(self.small, f"best {self.scores.get(d, 0):,}", GOLD, center=(r.right - 80, r.centery))
        self.text(self.small, "1-3 or click to start   |   P pause   |   Esc quit", DIM, center=(WIDTH // 2, HEIGHT - 40))

    def menu_rects(self):
        return {d: pygame.Rect(WIDTH // 2 - 200, 250 + i * 80, 400, 64) for i, d in enumerate(DIFFICULTIES)}

    def draw_over(self):
        self.draw_bg()
        self.text(self.big, "GAME OVER", RED, center=(WIDTH // 2, 120))
        self.text(self.mid, f"Score  {self.score:,}", TEXT, center=(WIDTH // 2, 210))
        if self.new_best:
            self.text(self.mid, "NEW HIGH SCORE!", GOLD, center=(WIDTH // 2, 255))
        else:
            self.text(self.small, f"best ({self.diff}): {self.scores.get(self.diff, 0):,}", DIM, center=(WIDTH // 2, 255))
        acc = self.hits / self.clicks * 100 if self.clicks else 0
        secs = max(self.elapsed / 1000, 0.1)
        stats = [("Hits", self.hits), ("Accuracy", f"{acc:.1f}%"), ("Speed", f"{self.hits / secs:.2f} t/s"),
                 ("Best combo", self.best_combo), ("Time", f"{secs:.1f}s")]
        for i, (k, v) in enumerate(stats):
            self.text(self.mid, k, DIM, topleft=(WIDTH // 2 - 160, 320 + i * 44))
            img = self.mid.render(str(v), True, TEXT)
            self.win.blit(img, (WIDTH // 2 + 160 - img.get_width(), 320 + i * 44))
        self.text(self.small, "R / click: retry   |   M: menu   |   Esc: quit", DIM, center=(WIDTH // 2, HEIGHT - 40))

    # ---- main loop -----------------------------------------------------
    def run(self):
        paused = False
        while True:
            dt = self.clock.tick(FPS)
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    pygame.quit()
                    sys.exit()
                if self.state == "menu":
                    if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        self.start(list(DIFFICULTIES)[e.key - pygame.K_1])
                    if e.type == pygame.MOUSEBUTTONDOWN:
                        for d, r in self.menu_rects().items():
                            if r.collidepoint(e.pos):
                                self.start(d)
                    if e.type == pygame.MOUSEMOTION:
                        for d, r in self.menu_rects().items():
                            if r.collidepoint(e.pos):
                                self.diff = d
                elif self.state == "play":
                    if e.type == pygame.KEYDOWN and e.key in (pygame.K_p, pygame.K_SPACE):
                        paused = not paused
                    if e.type == pygame.WINDOWFOCUSLOST:
                        paused = True
                    if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and not paused:
                        self.click(e.pos)
                else:  # over
                    if e.type == pygame.MOUSEBUTTONDOWN or (e.type == pygame.KEYDOWN and e.key == pygame.K_r):
                        self.start(self.diff)
                    if e.type == pygame.KEYDOWN and e.key == pygame.K_m:
                        self.state = "menu"

            if self.state == "play" and not paused:
                self.update(dt)

            {"menu": self.draw_menu, "play": self.draw_play, "over": self.draw_over}[self.state]()
            if self.state == "play" and paused:
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
