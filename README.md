# Balance Ball: Salone Edition — Alpha v0.3

A single-file HTML Canvas browser game celebrating its Sierra Leonean Salone identity, with a sandy court, colorful neighborhood, and green-and-gold presentation. The game runs offline without a build step, installed packages, accounts, or networking.

## Play locally

Open `index.html` in a browser. Alternatively, serve the repository with Python:

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000>. Any static host can also serve the same file.

## Controls

- Move with WASD or the arrow keys, or use the mobile analog joystick. Joystick distance controls movement speed; one pointer owns the stick so another finger can press DODGE at the same time.
- Press Space or DODGE for a 0.27-second evasive dash, with a 1.5-second cooldown shown on the button.
- Press P or Escape, or use the on-screen pause button, to pause and resume. Losing window focus or switching tabs pauses automatically; explicitly resume to continue. Paused time does not advance gameplay or cooldowns.

## Team survival

One ball and two opposing automated throwers challenge three teammates in the middle of the court. Each hit eliminates one player and shows HIT feedback for 0.65 seconds before the next teammate enters with brief protection. When all three players are out, the round ends and its survival score stays visible.

Choose NEXT TEAM to advance the team and round with three players and a fresh score. RESTART begins again at Team A, Round 1. Survival time is a provisional digital scoring mechanic, not a verified traditional rule.

This remains a lightweight 2D browser prototype: no networking, accounts, leaderboard, multiplayer, or 3D.

## Browser checks

The browser tests require Python, the Python Playwright package, and Chromium. These are development test tools, not game runtime dependencies. Install them in your development environment if needed:

```sh
python3 -m pip install playwright
python3 -m playwright install chromium
```

Run the gameplay checks from the repository root:

```sh
python3 -m unittest discover -s tests -v
```
