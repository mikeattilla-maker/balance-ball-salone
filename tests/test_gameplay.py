"""Browser regressions for the Canvas game, with no application dependencies.

Run: python -m unittest discover -s tests -v
Requires Python Playwright and system Chromium (chromium/chromium-browser), or
Playwright's Chromium installed with `python -m playwright install chromium`.
Tests serve the checkout on an ephemeral localhost port and use a paused browser
clock; collision fixtures exercise boundaries without random timing or screenshots.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import math
import shutil
import threading
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class GameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(QuietHandler, directory=str(ROOT))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.playwright = sync_playwright().start()
        launch_options = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        executable = shutil.which("chromium") or shutil.which("chromium-browser")
        if executable:
            launch_options["executable_path"] = executable
        cls.browser = cls.playwright.chromium.launch(**launch_options)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()

    def setUp(self):
        self.errors = []
        self.open_page()

    def open_page(self, mobile=False):
        if hasattr(self, "context"):
            self.context.close()
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844} if mobile else {"width": 1024, "height": 768},
            device_scale_factor=1,
            is_mobile=mobile,
            has_touch=mobile,
        )
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.clock.install(time=0)
        self.page.goto(self.url, wait_until="load")
        self.page.clock.pause_at(1000)
        self.assertEqual(self.page.evaluate("state"), "menu")

    def tearDown(self):
        try:
            self.assertEqual(self.errors, [], "Browser reported an uncaught JavaScript error")
        finally:
            self.context.close()

    def start(self, quiet=True):
        self.page.locator("#start").click()
        self.assertEqual(self.page.evaluate("state"), "play")
        # Control tests isolate input from incoming balls. The natural lifecycle
        # test leaves the real throwing and collision loop completely untouched.
        if quiet:
            self.page.evaluate("cool=60")

    def snapshot(self):
        return self.page.evaluate("""() => ({
            state, team, players, currentPlayer, round, elapsed, total, cool, inv, dash,
            dashCooldown, hitTime, p: {...p}, ball: ball && {...ball},
            stick: {...stick}, keys: {...keys}, playerTimes:playerTimes.map(times=>[...times]),
            multiplier:difficultyMultiplier()
        })""")

    def center_player(self):
        self.page.evaluate("{ const b=bounds(); p.x=b.x+b.w/2; p.y=b.y+b.h/2; }")
        return self.page.evaluate("({...p})")

    def collide(self, duration=None):
        # Use the real collision/recording path. Optional exact durations let the
        # scoring tests distinguish raw times from rounded display precision.
        self.page.evaluate("""duration => {
            if(duration!==null) {elapsed=duration;total=scoreTeam(playerTimes[team])+elapsed;}
            inv=0;ball={x:p.x,y:p.y-3,vx:0,vy:0,r:11};
            if(duration!==null) update(0);
        }""", duration)
        if duration is None:
            self.page.clock.run_for(35)

    def eliminate_team(self, times=None):
        team_index=self.page.evaluate("team")
        for index, remaining in enumerate((2, 1, 0)):
            self.assertEqual(self.page.evaluate("currentPlayer"), index+1)
            self.collide(None if times is None else times[index])
            self.assertEqual(self.page.evaluate("players"), remaining)
            self.assertEqual(self.page.evaluate("state"), "hit")
            self.assertEqual(self.page.evaluate("playerTimes[team].length"), index+1)
            if times is not None:
                self.assertEqual(self.page.evaluate("playerTimes[team]"), times[:index+1])
                self.assertAlmostEqual(self.page.evaluate("total"), sum(times[:index+1]))
            self.page.clock.run_for(700)
        self.assertEqual(self.page.evaluate("state"), "between" if team_index==0 else "finished")

    def assert_fresh_round(self, team, round_number):
        data = self.snapshot()
        self.assertEqual((data["state"], data["team"], data["round"], data["players"],data["currentPlayer"]),
                         ("play", team, round_number, 3,1))
        self.assertEqual((data["elapsed"], data["total"], data["dash"], data["dashCooldown"]),
                         (0, 0, 0, 0))
        self.assertIsNone(data["ball"])
        self.assertEqual(self.page.evaluate("thrower"), 0)
        self.assertAlmostEqual(data["cool"], 1.1)
        self.assertGreater(data["inv"], 0)
        self.assertEqual(data["keys"], {})
        self.assertEqual(data["stick"], {"x": 0, "y": 0})
        self.assertEqual(data["playerTimes"][team], [])
        dodging,throwing=("BLUE","RED") if team==0 else ("RED","BLUE")
        self.assertIn(f"DODGING {dodging}", self.page.locator("#team").inner_text())
        self.assertIn("PLAYER 1 OF 3", self.page.locator("#team").inner_text())
        self.assertIn(f"ROUND {round_number}/2", self.page.locator("#round").inner_text())
        self.assertIn(f"THROWS: {throwing}", self.page.locator("#round").inner_text())
        self.assertTrue(self.page.locator("#dodge").is_enabled())
        self.assertEqual(self.page.locator("#difficulty").inner_text(), "SPEED 1.00×")
        self.assertEqual(self.page.evaluate("difficultyMultiplier()"), 1)
        self.assertTrue(self.page.locator("#results").is_hidden())

    def assert_fresh_match(self):
        self.assert_fresh_round(0,1)
        self.assertEqual(self.page.evaluate("playerTimes"), [[],[]])
        self.assertEqual(self.page.evaluate("activeTeam().name"), "Blue")
        self.assertEqual(self.page.evaluate("throwingTeam().name"), "Red")

    def assert_modal_focus(self):
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "start")
        for direction in ("Tab", "Shift+Tab"):
            for _ in range(5):
                self.page.keyboard.press(direction)
                self.assertFalse(self.page.evaluate(
                    "Boolean(document.activeElement.closest('#hud, #controls'))"
                ), "Modal keyboard navigation must not reach underlying gameplay controls")
        self.page.locator("#start").focus()

    def test_keyboard_buttons_pause_and_modal_focus(self):
        self.assert_modal_focus()
        self.page.keyboard.press("Space")
        self.assertEqual(self.page.evaluate("state"), "play")
        self.assertEqual(self.page.evaluate("dashCooldown"), 0,
                         "Space on PLAY NOW must activate the focused button")
        self.page.evaluate("cool=60")
        self.page.locator("#pause").focus()
        self.page.keyboard.press("Space")
        self.assertEqual(self.page.evaluate("state"), "paused",
                         "Space must retain native keyboard activation of PAUSE")
        self.assertEqual(self.page.evaluate("dashCooldown"), 0)
        self.assert_modal_focus()
        self.page.keyboard.press("Space")
        self.assertEqual(self.page.evaluate("state"), "play")
        self.page.locator("#dodge").focus()
        self.page.keyboard.press("Space")
        self.assertGreater(self.page.evaluate("dash"), 0,
                           "The on-screen DODGE button must work with a keyboard")
        self.assertAlmostEqual(self.page.evaluate("dashCooldown"), 1.5)
        self.page.keyboard.down("p")
        self.assertEqual(self.page.evaluate("state"), "paused")
        self.page.keyboard.down("p")
        self.assertEqual(self.page.evaluate("state"), "paused",
                         "A repeated pause key must not immediately resume")
        self.page.keyboard.up("p")
        self.page.keyboard.press("Escape")
        self.assertEqual(self.page.evaluate("state"), "play")

    def test_keyboard_movement_and_diagonal_speed(self):
        self.start()
        distances = []
        for held in (("ArrowRight",), ("d", "s")):
            origin = self.center_player()
            for key in held:
                self.page.keyboard.down(key)
            self.page.clock.run_for(250)
            for key in held:
                self.page.keyboard.up(key)
            position = self.page.evaluate("({...p})")
            distances.append(math.hypot(position["x"] - origin["x"], position["y"] - origin["y"]))
        self.assertGreater(distances[0], 50)
        self.assertLess(distances[0], 65)
        self.assertAlmostEqual(distances[0], distances[1], delta=5,
                               msg="Diagonal movement must not be faster than cardinal movement")
        self.page.keyboard.down("ArrowLeft")
        self.page.clock.run_for(3000)
        self.page.keyboard.up("ArrowLeft")
        self.assertAlmostEqual(self.page.evaluate("p.x"), self.page.evaluate("bounds().x+20"), delta=1)

    def test_dash_cooldown_and_space_repeat(self):
        self.start()
        self.page.keyboard.down("Space")
        self.assertGreater(self.page.evaluate("dash"), 0)
        self.assertAlmostEqual(self.page.evaluate("dashCooldown"), 1.5)
        self.assertTrue(self.page.locator("#dodge").is_disabled())
        self.page.clock.run_for(350)
        self.assertEqual(self.page.evaluate("dash"), 0)
        remaining = self.page.evaluate("dashCooldown")
        self.assertGreater(remaining, 1)
        self.page.keyboard.down("Space")  # A repeated keydown while still held.
        self.assertEqual(self.page.evaluate("dash"), 0)
        self.assertEqual(self.page.evaluate("dashCooldown"), remaining)
        self.page.keyboard.up("Space")
        self.page.keyboard.press("Space")  # A new press is also blocked during cooldown.
        self.assertEqual(self.page.evaluate("dash"), 0)
        self.assertEqual(self.page.evaluate("dashCooldown"), remaining)
        self.page.clock.run_for(1250)
        self.assertEqual(self.page.evaluate("dashCooldown"), 0)
        self.assertTrue(self.page.locator("#dodge").is_enabled())
        self.page.keyboard.down("Space")
        self.assertGreater(self.page.evaluate("dash"), 0)
        self.page.clock.run_for(1600)
        self.assertEqual(self.page.evaluate("dashCooldown"), 0)
        self.page.keyboard.down("Space")
        self.assertEqual(self.page.evaluate("dash"), 0,
                         "Holding Space must not create another dash when cooldown expires")
        self.page.keyboard.up("Space")
        self.page.locator("#dodge").click()
        self.assertGreater(self.page.evaluate("dash"), 0)
        self.assertNotEqual(self.page.locator("#dash-status").inner_text().strip(), "")

    def test_pause_freezes_timers_and_resume_clears_stale_input(self):
        self.start()
        self.page.evaluate("ball={x:p.x-150,y:p.y-80,vx:15,vy:0,r:11}")
        self.page.keyboard.down("d")
        self.page.keyboard.press("Space")
        self.page.clock.run_for(100)
        self.page.locator("#pause").click()
        frozen = self.snapshot()
        self.assertEqual(frozen["state"], "paused")
        self.assertEqual(frozen["keys"], {})
        self.assertEqual(frozen["stick"], {"x": 0, "y": 0})
        self.assertTrue(self.page.locator("#dodge").is_disabled())
        self.page.clock.run_for(1800)
        self.assertEqual(self.snapshot(), frozen, "Pause must freeze score, ball and all gameplay timers")
        self.assertIn("RESUME", self.page.locator("#start").inner_text())
        self.page.locator("#start").click()
        self.page.clock.run_for(100)
        resumed = self.snapshot()
        self.assertEqual(resumed["state"], "play")
        self.assertEqual(resumed["p"], frozen["p"], "A held key must be pressed again after resume")
        self.assertGreater(resumed["total"], frozen["total"])
        self.assertLess(resumed["dashCooldown"], frozen["dashCooldown"])
        self.page.keyboard.up("d")
        self.page.evaluate("window.dispatchEvent(new Event('blur'))")
        self.assertEqual(self.page.evaluate("state"), "paused")
        self.page.locator("#start").click()
        self.page.evaluate("""() => {
            Object.defineProperty(document, 'hidden', {configurable:true, value:true});
            Object.defineProperty(document, 'visibilityState', {configurable:true, value:'hidden'});
            document.dispatchEvent(new Event('visibilitychange'));
            delete document.hidden;
            delete document.visibilityState;
        }""")
        self.assertEqual(self.page.evaluate("state"), "paused")

    def test_hit_feedback_player_rotation_team_switch_and_restart(self):
        self.start()
        self.page.clock.run_for(200)
        for remaining in (2,1,0):
            self.collide()
            self.assertEqual(self.page.evaluate("state"), "hit")
            self.assertEqual(self.page.evaluate("players"), remaining)
            self.assertEqual(self.page.evaluate("currentPlayer"), 3-remaining)
            self.assertEqual(self.page.evaluate("playerTimes[0].length"), 3-remaining)
            self.assertTrue(self.page.locator("#feedback").is_visible())
            self.assertTrue(self.page.locator("#feedback").inner_text().strip())
            score_at_hit=self.page.evaluate("({total,elapsed,times:playerTimes.map(t=>[...t])})")
            self.page.evaluate("takeHit()")
            self.page.clock.run_for(250)
            self.assertEqual(self.page.evaluate("({total,elapsed,times:playerTimes.map(t=>[...t])})"),score_at_hit,
                             "A hit must record once and freeze both survival timers")
            if remaining==2:
                self.page.locator("#pause").click()
                hit_time=self.page.evaluate("hitTime")
                self.page.clock.run_for(1000)
                self.assertEqual(self.page.evaluate("hitTime"),hit_time)
                self.page.locator("#start").click()
                self.assertEqual(self.page.evaluate("state"),"hit")
            self.page.clock.run_for(450)
            self.assertEqual(self.page.evaluate("state"),"play" if remaining else "between")
            if remaining:
                self.assertEqual(self.page.evaluate("currentPlayer"),4-remaining)
                self.assertLess(self.page.evaluate("elapsed"),.1)
                self.assertGreater(self.page.evaluate("inv"),0)
                self.assertIsNone(self.page.evaluate("ball"))
                self.assertEqual(self.page.evaluate("difficultyMultiplier()"),1)
                self.assertIn(f"PLAYER {4-remaining} OF 3",self.page.locator("#team").inner_text())
        self.assertEqual(self.page.evaluate("team"),0,"Roles change only when the next round starts")
        self.assertEqual(self.page.evaluate("playerTimes[1]"),[])
        self.assertIn("SWITCH",self.page.locator("#panel").inner_text().upper())
        self.assertEqual(self.page.locator("#start").inner_text(),"START RED ROUND")
        self.assert_modal_focus()
        frozen=self.snapshot()
        self.page.clock.run_for(2000)
        self.assertEqual(self.snapshot(),frozen)
        self.page.locator("#start").click()
        self.assert_fresh_round(1,2)
        unchanged=self.snapshot()
        self.page.evaluate("nextTeam()")
        self.assertEqual(self.snapshot(),unchanged,"An extra round request must not create another team")
        self.page.locator("#pause").click()
        self.page.locator("#restart").click()
        self.assert_fresh_match()
        self.eliminate_team()
        self.page.locator("#restart").click()
        self.assert_fresh_match()

    def test_real_throwing_loop_completes_exactly_two_rounds(self):
        self.page.evaluate("Math.random=()=>.99")
        self.start(quiet=False)
        opportunities=set()
        throwers={0:set(),1:set()}
        for team_index in (0,1):
            terminal="between" if team_index==0 else "finished"
            for _ in range(200):
                data=self.snapshot()
                opportunities.add((data["team"],data["currentPlayer"]))
                if data["ball"] is not None:
                    throwers[team_index].add(self.page.evaluate("thrower"))
                if data["state"]==terminal:
                    break
                self.page.clock.run_for(100)
            self.assertEqual(self.page.evaluate("state"),terminal,
                             "Real alternating throws must complete each three-player round")
            self.assertEqual(len(self.page.evaluate("playerTimes[team]")),3)
            if team_index==0:
                self.page.locator("#start").click()
        self.assertEqual(opportunities,{(0,1),(0,2),(0,3),(1,1),(1,2),(1,3)})
        self.assertEqual(throwers,{0:{0,1},1:{0,1}})
        recorded=self.page.evaluate("playerTimes")
        self.assertTrue(all(time>0 for times in recorded for time in times))
        self.assertEqual(self.page.evaluate("matchResult().scores"),[sum(times) for times in recorded])
        frozen=self.snapshot()
        self.page.evaluate("nextTeam()")
        self.page.clock.run_for(3000)
        self.assertEqual(self.snapshot(),frozen,"A completed match must stay finished")

    def spawned_ball(self, age=0, thrower_index=0, random_values=(0.99,), player_y=None):
        return self.page.evaluate("""options => {
            let randomIndex=0;
            Math.random=()=>options.randomValues[Math.min(randomIndex++,options.randomValues.length-1)];
            elapsed=total=options.age;
            thrower=options.throwerIndex;
            ball=null;
            cool=0;
            inv=1000;
            const b=bounds();
            p.x=b.x+b.w/2;
            p.y=options.playerY===null ? b.y+b.h/2 : options.playerY;
            update(0);
            return {ball:{...ball},p:{...p},b,age:elapsed,
                multiplier:difficultyMultiplier(),hud:$('difficulty').textContent};
        }""", {"age": age, "throwerIndex": thrower_index,
                 "randomValues": list(random_values), "playerY": player_y})

    def test_difficulty_thresholds_change_actual_spawned_speeds_and_cap(self):
        self.start()
        stages=((0,1),(4.999,1),(5,1.15),(9.999,1.15),(10,1.3),
                (14.999,1.3),(15,1.5),(19.999,1.5),(20,1.65),(300,1.65))
        for age,expected in stages:
            with self.subTest(age=age):
                shot=self.spawned_ball(age=age)
                self.assertEqual(shot["multiplier"],expected)
                self.assertAlmostEqual(math.hypot(shot["ball"]["vx"],shot["ball"]["vy"]),290*expected)
                self.assertEqual(shot["ball"]["speedMultiplier"],expected)
                self.assertEqual(shot["hud"],f"SPEED {expected:.2f}×")
        self.assertEqual(self.page.evaluate("BASE_BALL_SPEED"),290)

    def test_difficulty_freezes_on_pause_and_resets_for_each_dodger(self):
        self.start()
        self.page.evaluate("elapsed=total=20;renderHUD()")
        self.page.locator("#pause").click()
        frozen=self.snapshot()
        self.page.clock.run_for(5000)
        self.assertEqual(self.snapshot(),frozen)
        self.assertEqual(self.page.locator("#difficulty").inner_text(),"SPEED 1.65×")
        self.page.locator("#start").click()
        self.collide()
        hit_age=self.page.evaluate("elapsed")
        self.assertGreaterEqual(hit_age,20)
        self.page.clock.run_for(300)
        self.assertEqual(self.page.evaluate("elapsed"),hit_age)
        self.page.clock.run_for(400)
        self.assertEqual(self.page.evaluate("currentPlayer"),2)
        self.assertLess(self.page.evaluate("elapsed"),.1)
        self.assertEqual(self.page.evaluate("difficultyMultiplier()"),1)
        self.assertEqual(self.page.locator("#difficulty").inner_text(),"SPEED 1.00×")
        self.assertAlmostEqual(self.page.evaluate("playerTimes[0][0]"),hit_age)
        self.assertGreaterEqual(self.page.evaluate("total"),hit_age)
        self.collide(7)
        self.page.clock.run_for(700)
        self.assertEqual(self.page.evaluate("currentPlayer"),3)
        self.assertEqual(self.page.evaluate("difficultyMultiplier()"),1)
        self.collide(12)
        self.page.clock.run_for(700)
        self.page.locator("#start").click()
        self.assert_fresh_round(1,2)
        self.assertEqual(len(self.page.evaluate("playerTimes[0]")),3)
        self.page.locator("#pause").click()
        self.page.locator("#restart").click()
        self.assert_fresh_match()

    def test_ball_speed_changes_in_flight_at_each_player_time_threshold(self):
        self.start()
        for threshold,previous,current in ((5,1,1.15),(10,1.15,1.3),(15,1.3,1.5),(20,1.5,1.65)):
            with self.subTest(threshold=threshold):
                initial=self.spawned_ball(age=threshold-.01,random_values=(0,.999))["ball"]
                self.assertEqual(initial["speedMultiplier"],previous)
                after=self.page.evaluate("update(.02);({...ball})")
                self.assertEqual(after["speedMultiplier"],current)
                self.assertAlmostEqual(math.hypot(after["vx"],after["vy"]),290*current)
                self.assertAlmostEqual(after["vx"]/initial["vx"],current/previous)
                self.assertAlmostEqual(after["vy"]/initial["vy"],current/previous)
                self.assertAlmostEqual(after["x"]-initial["x"],after["vx"]*.02)
                self.assertAlmostEqual(after["y"]-initial["y"],after["vy"]*.02)
                stable=self.page.evaluate("update(.01);({...ball})")
                self.assertEqual((stable["vx"],stable["vy"]),(after["vx"],after["vy"]))
        # Collision fixtures do not represent production throws and have no stage
        # metadata. Their specified velocities must remain usable and finite.
        fixture=self.page.evaluate("elapsed=4.99;inv=100;ball={x:p.x-150,y:p.y-80,vx:15,vy:5,r:11};update(.02);({...ball})")
        self.assertEqual((fixture["vx"],fixture["vy"]),(15,5))

    def test_ball_motion_is_dt_independent_with_one_ball_and_fixed_heading(self):
        self.start()
        outcomes=[]
        for step,count in ((.01,20),(.02,10),(.025,8)):
            initial=self.spawned_ball(age=6)["ball"]
            outcome=self.page.evaluate("""options=>{
                const original=ball,nextThrower=thrower;
                throwBall();
                const guarded=ball===original && thrower===nextThrower;
                cool=-10;
                for(let i=0;i<options.count;i++) update(options.step);
                return {ball:{...ball},guarded,same:ball===original,elapsed,total};
            }""",{"step":step,"count":count})
            self.assertTrue(outcome["guarded"])
            self.assertTrue(outcome["same"])
            self.assertEqual((outcome["ball"]["vx"],outcome["ball"]["vy"]),(initial["vx"],initial["vy"]))
            self.assertAlmostEqual(outcome["ball"]["x"],initial["x"]+initial["vx"]*.2)
            self.assertAlmostEqual(outcome["ball"]["y"],initial["y"]+initial["vy"]*.2)
            self.assertAlmostEqual(outcome["elapsed"],6.2)
            self.assertAlmostEqual(outcome["total"],6.2)
            outcomes.append(outcome)
        for outcome in outcomes[1:]:
            self.assertAlmostEqual(outcome["ball"]["x"],outcomes[0]["ball"]["x"])
            self.assertAlmostEqual(outcome["total"],outcomes[0]["total"])

    def test_throw_variation_is_bounded_straight_and_keeps_targets_on_court(self):
        self.start()
        court = self.page.evaluate("bounds()")
        for thrower_index in (0, 1):
            deviations = []
            for samples in ((.99,), (.25,), (.249, 0), (0, 0), (0, .999)):
                shot = self.spawned_ball(age=30, thrower_index=thrower_index, random_values=samples)
                ball = shot["ball"]
                direct = math.atan2(shot["p"]["y"] - ball["y"], shot["p"]["x"] - ball["x"])
                heading = math.atan2(ball["vy"], ball["vx"])
                deviation = math.degrees(math.atan2(math.sin(heading-direct), math.cos(heading-direct)))
                self.assertLessEqual(abs(deviation), 8.000001)
                self.assertAlmostEqual(math.hypot(ball["vx"], ball["vy"]), 478.5)
                if samples[0] >= .25:
                    self.assertAlmostEqual(deviation, 0, places=7)
                else:
                    self.assertGreater(abs(deviation), .01)
                    deviations.append(deviation)
                in_flight = self.page.evaluate("""() => {
                    const original=ball;
                    for(let i=0;i<20;i++) update(.01);
                    return {same:ball===original,ball:{...ball}};
                }""")
                self.assertTrue(in_flight["same"])
                self.assertEqual((in_flight["ball"]["vx"], in_flight["ball"]["vy"]), (ball["vx"], ball["vy"]))
                self.assertAlmostEqual(in_flight["ball"]["x"], ball["x"] + ball["vx"] * .2)
                self.assertAlmostEqual(in_flight["ball"]["y"], ball["y"] + ball["vy"] * .2)
            self.assertLess(deviations[-2] * deviations[-1], 0,
                            "Deterministic random extremes must vary aim to both sides")
            for player_y in (court["y"] + 30, court["y"] + court["h"] - 30):
                for samples in ((0, 0), (0, .999)):
                    shot = self.spawned_ball(thrower_index=thrower_index,
                                             random_values=samples, player_y=player_y)
                    ball = shot["ball"]
                    target_y = ball["y"] + (shot["p"]["x"] - ball["x"]) * ball["vy"] / ball["vx"]
                    self.assertGreaterEqual(target_y, court["y"] + 30 - 1e-7)
                    self.assertLessEqual(target_y, court["y"] + court["h"] - 30 + 1e-7)

    def canvas_team_colors(self):
        return self.page.evaluate("""() => {
            draw();
            const b=bounds();
            const pixel=(x,y)=>Array.from(ctx.getImageData(Math.floor(x*D),Math.floor(y*D),1,1).data).slice(0,3);
            const label=$('team'),style=getComputedStyle(label);
            return {shirt:pixel(p.x,p.y),markers:[0,1,2].map(i=>pixel(b.x+50+i*28,b.y+b.h+12)),
                throwers:[pixel(b.x-22,b.y+b.h/2),pixel(b.x+b.w+22,b.y+b.h/2)],
                hudColor:style.borderLeftColor};
        }""")

    def test_two_team_colors_follow_dodging_and_throwing_roles(self):
        self.start()
        palette=[{"name":"Blue","color":"#0072b2"},{"name":"Red","color":"#a63636"}]
        self.assertEqual(self.page.evaluate("TEAM_COLORS"),palette)
        rgb_colors=([0,114,178],[166,54,54])
        for team_index in (0,1):
            rgb,opponent=rgb_colors[team_index],rgb_colors[1-team_index]
            self.assertEqual(self.page.evaluate("activeTeam()"),palette[team_index])
            self.assertEqual(self.page.evaluate("throwingTeam()"),palette[1-team_index])
            self.page.evaluate("inv=0;renderHUD()")
            initial=self.canvas_team_colors()
            self.assertEqual(initial["shirt"],rgb)
            self.assertEqual(initial["markers"],[rgb,rgb,rgb])
            self.assertEqual(initial["throwers"],[opponent,opponent])
            self.assertEqual(initial["hudColor"],f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})")
            for remaining in (2,1,0):
                self.collide()
                self.assertEqual(self.page.evaluate("state"),"hit")
                visible=self.canvas_team_colors()
                self.assertEqual(visible["shirt"],rgb,"An elimination must preserve the dodging team's shirt")
                self.assertEqual(visible["throwers"],[opponent,opponent])
                for index,marker in enumerate(visible["markers"]):
                    if index<remaining:self.assertEqual(marker,rgb)
                    else:self.assertNotEqual(marker,rgb)
                self.page.clock.run_for(700)
                if remaining:
                    self.page.evaluate("inv=0")
                    replacement=self.canvas_team_colors()
                    self.assertEqual(replacement["shirt"],rgb)
                    self.assertEqual(replacement["throwers"],[opponent,opponent])
                    self.assertEqual(replacement["markers"][:remaining],[rgb]*remaining)
            self.assertEqual(self.page.evaluate("state"),"between" if team_index==0 else "finished")
            if team_index==0:
                self.assertEqual(self.page.evaluate("team"),0)
                self.page.locator("#start").click()
                self.assert_fresh_round(1,2)
        self.page.locator("#start").click()
        self.assert_fresh_match()
        self.page.evaluate("inv=0")
        restarted=self.canvas_team_colors()
        self.assertEqual(restarted["shirt"],rgb_colors[0])
        self.assertEqual(restarted["throwers"],[rgb_colors[1],rgb_colors[1]])

    def test_mobile_player_team_score_and_difficulty_hud_fit_small_viewports(self):
        self.open_page(mobile=True)
        self.start()
        for width,height in ((320,568),(360,640),(568,320)):
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.clock.run_for(40)
            for team_index in (0,1):
                with self.subTest(viewport=(width,height),team=team_index):
                    layout=self.page.evaluate("""index=>{
                        team=index;round=index+1;currentPlayer=3;players=1;elapsed=333.3;total=999.9;renderHUD();
                        const rect=element=>{
                            const r=element.getBoundingClientRect();
                            return {id:element.id,x:r.x,y:r.y,right:r.right,bottom:r.bottom,
                                scrollWidth:element.scrollWidth,clientWidth:element.clientWidth};
                        };
                        return {scrollWidth:document.documentElement.scrollWidth,hud:rect($('hud')),
                            items:['team','score','round','dash-status','difficulty','pause'].map(id=>rect($(id)))};
                    }""",team_index)
                    self.assertLessEqual(layout["scrollWidth"],width)
                    for item in [layout["hud"],*layout["items"]]:
                        self.assertGreaterEqual(item["x"],0,item["id"])
                        self.assertGreaterEqual(item["y"],0,item["id"])
                        self.assertLessEqual(item["right"],width,item["id"])
                        self.assertLessEqual(item["bottom"],height,item["id"])
                        self.assertLessEqual(item["scrollWidth"],item["clientWidth"]+1,item["id"])
                    for index,first in enumerate(layout["items"]):
                        for second in layout["items"][index+1:]:
                            overlap_x=min(first["right"],second["right"])-max(first["x"],second["x"])
                            overlap_y=min(first["bottom"],second["bottom"])-max(first["y"],second["y"])
                            self.assertFalse(overlap_x>1 and overlap_y>1,f"HUD fields overlap: {first['id']} and {second['id']}")

    def test_match_scoring_blue_win_red_win_and_display_precision_tie(self):
        self.start()
        pure=self.page.evaluate("""()=>{
            const times=[.1,.2,.3],before=JSON.stringify(times);
            return {empty:scoreTeam([]),sum:scoreTeam(times),unchanged:JSON.stringify(times)===before};
        }""")
        self.assertEqual(pure["empty"],0)
        self.assertAlmostEqual(pure["sum"],.6)
        self.assertTrue(pure["unchanged"])
        cases=(([1.04,2.02,3.01],[.5,1.5,2.5],0),
               ([.5,1.5,2.5],[1.04,2.02,3.01],1),
               ([.11,.12,.11],[.1,.1,.11],None))
        for blue,red,winner in cases:
            with self.subTest(winner=winner):
                self.eliminate_team(blue)
                self.assertEqual(self.page.evaluate("playerTimes"),[blue,[]])
                self.page.locator("#start").click()
                self.assert_fresh_round(1,2)
                self.eliminate_team(red)
                result=self.page.evaluate("matchResult()")
                for actual,expected in zip(result["scores"],(sum(blue),sum(red))):
                    self.assertAlmostEqual(actual,expected)
                self.assertEqual(result["winner"],winner)
                self.assertEqual(self.page.evaluate("playerTimes"),[blue,red])
                self.assertEqual(self.page.evaluate("playerTimes.flat().length"),6)
                self.assertTrue(self.page.locator("#results").is_visible())
                for label,times in (("blue",blue),("red",red)):
                    details=self.page.locator(f"#{label}-times").inner_text()
                    for value in times:self.assertIn(f"{value:.1f}",details)
                    self.assertIn(f"{sum(times):.1f}",self.page.locator(f"#{label}-total").inner_text())
                text=self.page.locator("#panel").inner_text()
                if winner is None:self.assertIn("TIE",text.upper())
                else:
                    name=("BLUE","RED")[winner]
                    self.assertRegex(text.upper(),rf"(?s)({name}.*WIN|WIN.*{name})")
                self.assertEqual(self.page.locator("#start").inner_text(),"PLAY AGAIN")
                self.assert_modal_focus()
                final=self.snapshot()
                self.page.evaluate("nextTeam();takeHit()")
                self.page.clock.run_for(1000)
                self.assertEqual(self.snapshot(),final,"A finished match must reject extra teams and eliminations")
                self.page.locator("#start").click()
                self.assert_fresh_match()

    def test_finished_mobile_play_again_fully_resets_match(self):
        self.open_page(mobile=True)
        self.start()
        for width,height in ((320,568),(568,320)):
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.clock.run_for(40)
            self.eliminate_team([.1,.2,.3])
            self.page.locator("#start").tap()
            self.eliminate_team([.3,.2,.1])
            self.assertEqual(self.page.evaluate("state"),"finished")
            self.assertTrue(self.page.locator("#results").is_visible())
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"),width)
            if height>=568:
                action=self.page.locator("#start").bounding_box()
                self.assertGreaterEqual(action["y"],0)
                self.assertLessEqual(action["y"]+action["height"],height,
                                     "Portrait mobile Play Again must be visible without scrolling")
            self.page.locator("#start").scroll_into_view_if_needed()
            self.page.locator("#start").tap()
            self.assert_fresh_match()

    def test_mobile_visible_focus_notifications_keep_real_joystick_active(self):
        # CDP supplies real touch input. Blur notifications are synthetic because
        # Chromium cannot reproduce an iPhone Safari focus quirk or its cause.
        for width,height in ((390,844),(820,1180)):
            with self.subTest(viewport=(width,height)):
                self.open_page(mobile=True)
                self.page.set_viewport_size({"width":width,"height":height})
                self.page.clock.run_for(40)
                self.start()
                self.assertTrue(self.page.evaluate("touchLayout"))
                self.assertFalse(self.page.evaluate("document.hidden"))
                self.page.locator("#pause").focus()
                self.page.locator("#pause").evaluate("button=>button.blur()")
                self.assertEqual(self.page.evaluate("state"),"play")
                session=self.context.new_cdp_session(self.page)
                box=self.page.locator("#pad").bounding_box()
                x,y=box["x"]+box["width"]/2+25,box["y"]+box["height"]/2
                self.touch(session,"touchStart",[(1,x,y)])
                before=self.page.evaluate("({owner:activePointer,stick:{...stick},x:p.x})")
                self.assertGreater(before["stick"]["x"],0)
                self.page.evaluate("window.dispatchEvent(new Event('blur'))")
                self.assertEqual(self.page.evaluate("state"),"play",
                                 "A visible touch page must ignore spurious window blur")
                self.page.evaluate("$('pause').dispatchEvent(new FocusEvent('blur',{bubbles:true}))")
                self.assertEqual(self.page.evaluate("state"),"play")
                self.assertEqual(self.page.evaluate("activePointer"),before["owner"])
                self.assertEqual(self.page.evaluate("({...stick})"),before["stick"])
                self.page.clock.run_for(100)
                self.assertGreater(self.page.evaluate("p.x"),before["x"])
                self.page.locator("#pause").click()
                self.assertEqual(self.page.evaluate("state"),"paused",
                                 "Manual pause must still work while a joystick finger is down")
                self.assertIsNone(self.page.evaluate("activePointer"))
                self.assertEqual(self.page.evaluate("({...stick})"),{"x":0,"y":0})
                self.page.locator("#start").click()
                origin=self.page.evaluate("p.x")
                self.touch(session,"touchMove",[(1,x+5,y)])
                self.page.clock.run_for(100)
                self.assertEqual(self.page.evaluate("p.x"),origin,
                                 "A pre-pause finger must be pressed again after resume")
                self.touch(session,"touchCancel",[])

    def test_desktop_focus_notifications_only_pause_for_window_blur(self):
        self.start()
        self.assertFalse(self.page.evaluate("touchLayout"))
        self.page.locator("#pause").focus()
        self.page.locator("#pause").evaluate("button=>button.blur()")
        self.assertEqual(self.page.evaluate("state"),"play")
        self.page.keyboard.down("d")
        self.page.evaluate("$('pause').dispatchEvent(new FocusEvent('blur',{bubbles:true}))")
        self.assertEqual(self.page.evaluate("state"),"play",
                         "A descendant blur notification must not pause the window")
        self.assertTrue(self.page.evaluate("keys.d"))
        self.page.evaluate("window.dispatchEvent(new Event('blur'))")
        self.assertEqual(self.page.evaluate("state"),"paused",
                         "Desktop window focus loss must still pause")
        self.assertEqual(self.page.evaluate("keys"),{})
        self.page.keyboard.up("d")

    def test_mobile_hidden_visibility_and_pagehide_pause_and_release_input(self):
        self.open_page(mobile=True)
        self.start()
        session=self.context.new_cdp_session(self.page)
        box=self.page.locator("#pad").bounding_box()
        x,y=box["x"]+box["width"]/2+25,box["y"]+box["height"]/2
        for event in ("visibilitychange","pagehide"):
            with self.subTest(event=event):
                self.touch(session,"touchStart",[(1,x,y)])
                self.page.keyboard.down("d")
                self.assertGreater(self.page.evaluate("stick.x"),0)
                if event=="visibilitychange":
                    self.page.evaluate("""()=>{
                        Object.defineProperty(document,'hidden',{configurable:true,value:true});
                        Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
                        document.dispatchEvent(new Event('visibilitychange'));
                        delete document.hidden;delete document.visibilityState;
                    }""")
                else:
                    self.page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'))")
                self.assertEqual(self.page.evaluate("state"),"paused")
                self.assertIsNone(self.page.evaluate("activePointer"))
                self.assertEqual(self.page.evaluate("({...stick})"),{"x":0,"y":0})
                self.assertEqual(self.page.evaluate("keys"),{})
                frozen=self.snapshot()
                self.page.evaluate("window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'))")
                self.page.clock.run_for(200)
                self.assertEqual(self.snapshot(),frozen,"Returning to the page must require explicit resume")
                self.page.keyboard.up("d")
                self.touch(session,"touchCancel",[])
                self.page.locator("#start").click()
                self.assertEqual(self.page.evaluate("state"),"play")

    def touch(self, session, kind, points):
        # CDP touchEnd lists the contacts ending, not contacts still held.
        session.send("Input.dispatchTouchEvent", {
            "type": kind,
            "touchPoints": [{"id": ident, "x": x, "y": y, "radiusX": 2,
                             "radiusY": 2, "force": 1} for ident, x, y in points],
        })

    def test_mobile_deadzone_multitouch_dash_and_cancel(self):
        self.open_page(mobile=True)
        self.start()
        session = self.context.new_cdp_session(self.page)
        box = self.page.locator("#pad").bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.mouse.move(x + 20, y)
        self.assertEqual(self.page.evaluate("({...stick})"), {"x": 0, "y": 0})
        self.touch(session, "touchStart", [(1, x + 2, y)])
        self.assertEqual(self.page.evaluate("({...stick})"), {"x": 0, "y": 0},
                         "Small finger jitter must remain inside the deadzone")
        origin = self.page.evaluate("p.x")
        self.page.clock.run_for(100)
        self.assertEqual(self.page.evaluate("p.x"), origin)
        self.touch(session, "touchMove", [(1, x + 15, y)])
        magnitude = self.page.evaluate("stick.x")
        self.assertGreater(magnitude, 0)
        self.assertLess(magnitude, 0.8)
        self.page.clock.run_for(100)
        self.assertGreater(self.page.evaluate("p.x"), origin)
        self.assertLess(self.page.evaluate("p.x") - origin, 20,
                        "Partial joystick deflection must preserve analog speed")
        owner = self.page.evaluate("activePointer")
        self.touch(session, "touchStart", [(1, x + 15, y), (2, x - 20, y)])
        self.touch(session, "touchMove", [(1, x + 15, y), (2, x - 35, y)])
        self.assertAlmostEqual(self.page.evaluate("stick.x"), magnitude)
        self.assertEqual(self.page.evaluate("activePointer"), owner)
        self.touch(session, "touchEnd", [(2, x - 35, y)])
        self.assertAlmostEqual(self.page.evaluate("stick.x"), magnitude,
                               msg="Lifting a second finger must not release the joystick owner")
        dodge = self.page.locator("#dodge").bounding_box()
        dx, dy = dodge["x"] + dodge["width"] / 2, dodge["y"] + dodge["height"] / 2
        self.touch(session, "touchStart", [(1, x + 15, y), (2, dx, dy)])
        self.assertGreater(self.page.evaluate("dash"), 0,
                           "DODGE must work while a different finger owns the joystick")
        self.assertGreater(self.page.evaluate("dashCooldown"), 1.4)
        self.assertAlmostEqual(self.page.evaluate("stick.x"), magnitude)
        self.touch(session, "touchCancel", [])
        self.assertEqual(self.page.evaluate("({...stick})"), {"x": 0, "y": 0})
        self.assertIsNone(self.page.evaluate("activePointer"))
        self.touch(session, "touchStart", [(3, x + 25, y)])
        self.assertGreater(self.page.evaluate("stick.x"), 0)
        self.page.evaluate("pad.dispatchEvent(new PointerEvent('lostpointercapture', {pointerId:activePointer}))")
        self.assertEqual(self.page.evaluate("({...stick})"), {"x": 0, "y": 0})
        self.assertIsNone(self.page.evaluate("activePointer"))

    def test_mobile_resize_releases_drag_and_clamps_player(self):
        self.open_page(mobile=True)
        self.start()
        session = self.context.new_cdp_session(self.page)
        box = self.page.locator("#pad").bounding_box()
        self.touch(session, "touchStart", [(1, box["x"] + box["width"] - 8,
                                            box["y"] + box["height"] / 2)])
        self.assertGreater(self.page.evaluate("stick.x"), 0)
        self.page.evaluate("{ const b=bounds(); p.x=b.x+b.w-20; p.y=b.y+b.h-30; }")
        self.page.set_viewport_size({"width": 844, "height": 390})
        self.page.clock.run_for(40)
        data = self.page.evaluate("({p:{...p},b:bounds(),width:c.width,height:c.height,stick:{...stick},activePointer})")
        self.assertEqual((data["width"], data["height"]), (844, 390))
        self.assertEqual(data["stick"], {"x": 0, "y": 0})
        self.assertIsNone(data["activePointer"])
        self.assertGreaterEqual(data["p"]["x"], data["b"]["x"] + 20)
        self.assertLessEqual(data["p"]["x"], data["b"]["x"] + data["b"]["w"] - 20)
        self.assertGreaterEqual(data["p"]["y"], data["b"]["y"] + 30)
        self.assertLessEqual(data["p"]["y"], data["b"]["y"] + data["b"]["h"] - 30)
        for control in ("#pad", "#dodge", "#pause"):
            rect = self.page.locator(control).bounding_box()
            self.assertGreaterEqual(rect["x"], 0)
            self.assertGreaterEqual(rect["y"], 0)
            self.assertLessEqual(rect["x"] + rect["width"], 844)
            self.assertLessEqual(rect["y"] + rect["height"], 390)


if __name__ == "__main__":
    unittest.main()
