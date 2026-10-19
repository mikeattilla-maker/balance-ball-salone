# Balance Ball: Salone Edition — Alpha v0.4

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

## A two-team match

Exactly two teams have three dodgers each. Team Blue (`#0072b2`) starts in the middle; Team Red (`#a63636`) occupies both opposing automated thrower positions. One ball is in play at a time. A hit eliminates one dodger and shows HIT feedback for 0.65 seconds before the next teammate enters with brief protection. Shirts and remaining-player markers keep the same team color through individual eliminations.

After Blue's third elimination, the team-switch screen explains the new roles. Choose START RED ROUND: Red's three players dodge in the middle while both throwers wear Blue. After Red's third elimination, MATCH COMPLETE shows both teams' results, each player's survival time, and the winner or tie. There are exactly two rounds; no additional teams enter. PLAY AGAIN resets the entire match to Blue dodging against Red, with all scores, eliminations, timers, and assignments cleared. Restarting from the pause screen also begins a fresh match.

The HUD identifies the dodging and throwing teams by name, the active player (1 of 3 through 3 of 3), the active player's clock, team total, round (1 of 2 or 2 of 2), and speed multiplier. Team identity does not depend on color alone.

## Temporary scoring

Record each player's raw survival duration, then sum all three durations for that team's result. Compare team totals rounded to one decimal place; equal displayed totals produce a tie. Otherwise, the higher total wins. Paused time and HIT transitions do not count as survival time.

This scoring is a provisional digital mechanic, **not a culturally validated traditional rule**. The `scoreTeam` function keeps aggregation separate from match flow so community-validated rules can replace it later. Preserving the game's Sierra Leonean identity includes seeking that validation rather than presenting this scoring as established tradition.

## Progressive difficulty

Ball speed follows the **active dodger's** survival time, using the existing 290 px/s baseline:

| Active player's survival | Speed multiplier | Ball speed |
| --- | --- | --- |
| 0–<5 seconds | 1.00× | 290 px/s |
| 5–<10 seconds | 1.15× | 333.5 px/s |
| 10–<15 seconds | 1.30× | 377 px/s |
| 15–<20 seconds | 1.50× | 435 px/s |
| 20 seconds and later | 1.65× | 478.5 px/s |

The multiplier resets to 1.00× for each replacement dodger. Pausing freezes the timer and speed without resetting progress. Threshold changes affect the ball already in flight immediately, preserving its heading; the HUD's SPEED indicator shows the active multiplier.

Existing straight angled throws remain: each throw has a 25% chance of a modest upward or downward aim variation, bounded to 8 degrees, with the aim target constrained to the playable court's vertical limits. Once thrown, a ball keeps its heading; it does not curve or home in on a moving player.

This remains a lightweight 2D browser prototype: no networking, accounts, leaderboard, multiplayer, new maps, character selection, or 3D conversion. Curved throws are planned for v0.5 after core gameplay validation, not included in v0.4.

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

## Manual gameplay checklist

These are instructions for manual validation, not a record of checks already executed.

On a desktop browser:

- Start a match: Blue Player 1 of 3 should dodge, both throwers should be Red, and the active clock, team total, and SPEED should start at zero / 1.00×. Check WASD, arrows, diagonals, and Space; held or repeated Space must not bypass the 1.5-second cooldown.
- Survive across 5, 10, 15, and 20 seconds. Confirm the listed speed stages change actual ball movement, including an existing ball's speed, while its heading stays straight. Pause with P, Escape, and the button; clocks, difficulty, ball, and cooldown should freeze and resume without losing the current stage. Switching tabs must require explicit resume.
- Eliminate all three Blue players. Each hit should remove exactly one player, show brief feedback, and introduce the next Blue teammate with a fresh clock and 1.00× difficulty. Blue's third elimination should show a role-switch message. START RED ROUND should introduce Red Player 1 of 3 and turn both throwers Blue while preserving Blue's recorded results.
- Eliminate all three Red players. Confirm MATCH COMPLETE contains exactly three player times per team, cumulative totals, and the correct winner or tie at 0.1-second precision. Wait to confirm play stays stopped. PLAY AGAIN, and separately a pause-screen restart, must restore the initial assignments and clear all six player records and timers.

On physical mobile devices:

- Drag the joystick at partial and full travel, then hold it with one finger while pressing DODGE with another. A second joystick touch must not take control. Release or cancel a gesture and confirm movement stops.
- Check portrait at a 320 CSS-pixel viewport width and rotate to landscape. Team roles, player number, clocks, round, SPEED, and pause controls should stay readable and usable. Rotation should keep the player inside the court and clear the old ball.
- Pause during movement and a cooldown, then switch apps or lock the screen. Returning must require explicit resume and a fresh movement touch, with no stale input or reset difficulty.
- Complete all six eliminations: verify Blue-to-Red role switching, both thrower colors, the final results, and PLAY AGAIN reset using touch controls.

## Known limitations and remaining playtesting

- Physical iOS and Android devices have not been verified; browser touch emulation does not replace device testing.
- Random aim variations make the two rounds different challenges rather than identical seeded trials.
- Survival uses active simulation time. Frame steps are capped at 35 ms, so heavy frame drops can slow the timer compared with wall-clock time.
- Speed stages, reaction time near the throwers, touch handling, and competitive balance still need founder and community playtesting. Survival scoring remains provisional pending cultural validation.
- v0.5 curved-throw mechanics are planned only after this match structure and core gameplay are validated.
