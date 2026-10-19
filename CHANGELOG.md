# Development changelog

## Alpha v0.4 — two-team matches and progressive difficulty

- Replaced endless team rotation with exactly two three-player teams: Blue starts dodging against Red, then Red dodges against Blue. Individual replacements retain their team color; both automated throwers change color when the roles switch.
- Added a clear team-switch screen and a match-complete result after six eliminations across two rounds. Results include each player's survival duration, both cumulative team totals, and a winner or tie. PLAY AGAIN and restart clear the entire match.
- Kept raw per-player survival durations and modular `scoreTeam` aggregation. Totals are compared at displayed 0.1-second precision, so equal displayed totals tie. This is temporary digital scoring, not a culturally validated traditional rule.
- Added per-dodger speed stages at 0, 5, 10, 15, and 20 seconds: 1.00×, 1.15×, 1.30×, 1.50×, and 1.65× the 290 px/s baseline. Difficulty resets for every replacement, freezes during pause and HIT feedback, and changes in-flight speed while preserving heading.
- Updated the HUD with dodging/throwing team names, player number, player clock, team total, round out of two, and speed. Team labels accompany consistent Blue and Red shirts and remaining-player markers.
- Preserved the Salone setting and Sierra Leonean identity, single-ball Canvas architecture, two opposing automated throwers, existing bounded straight angled shots, and desktop/mobile controls. No runtime packages or network services were added.
- Expanded automated gameplay checks and documented a manual desktop/mobile full-match checklist in the README. The checklist describes checks to perform, not completed physical-device validation.

Known limitations: physical iOS/Android play is unverified; random aim makes rounds nonidentical; frame-step clamping can slow simulation time under heavy frame drops. Difficulty, reaction time, and competitive balance need further playtesting, and scoring needs community validation. Curved throws remain planned for v0.5 after core validation; v0.4 has no curving or homing.

## Alpha v0.3 — stable browser controls and round lifecycle

- Added analog joystick ownership and cancellation handling, simultaneous move/dodge touches, a 0.27-second dash with a visible 1.5-second cooldown, and protection against repeat-triggered dashes.
- Added pause/resume controls and automatic pause on focus or tab loss, with gameplay timers frozen until explicit resume.
- Added visible HIT feedback, one-player-per-hit elimination, protected respawn, and reliable round/restart state cleanup.
- Preserved the single-file offline Canvas game, Sierra Leonean presentation, and static-file setup; added browser gameplay checks without runtime dependencies.
