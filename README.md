# Shootit

![CI](../../actions/workflows/ci.yml/badge.svg) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

A fast arcade aim trainer built with Python and [pygame-ce](https://pyga.me/). Targets pop up and shrink away. Click them before they vanish, keep your combo alive, and don't touch the bombs.

<p align="center"><img src="docs/gameplay.png" width="45%"> <img src="docs/menu.png" width="45%"></p>

## Features

- **Three difficulties** (Easy / Normal / Hard) with different lives and spawn speeds
- **Combo multiplier**: every 5 hits in a row raises your multiplier, up to x8. Missing a click resets it
- **Gold targets** are worth 5x and restore a life
- **Bombs** (purple) cost a life if you click them. Let them fade
- **Difficulty ramps** the longer you survive
- Particles, floating score popups, screen shake, custom crosshair
- **Persistent high scores** per difficulty
- End-of-run stats: accuracy, targets/sec, best combo, time

## Run

```bash
pip install -r requirements.txt
python Shootit.py
```

## Controls

| Key | Action |
|-----|--------|
| `1` `2` `3` or click | Pick difficulty / start |
| Mouse click | Shoot |
| `P` / `Space` | Pause |
| `R` | Retry (game over) |
| `M` | Back to menu |
| `Esc` | Quit |

## Build an executable

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole Shootit.py
```

The built exe lands in `dist/` (not tracked in git; attach it to a GitHub Release instead).

## License

MIT
