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
            state, team, players, round, elapsed, total, cool, inv, dash,
            dashCooldown, hitTime, p: {...p}, ball: ball && {...ball},
            stick: {...stick}, keys: {...keys}
        })""")

    def center_player(self):
        self.page.evaluate("{ const b=bounds(); p.x=b.x+b.w/2; p.y=b.y+b.h/2; }")
        return self.page.evaluate("({...p})")

    def collide(self):
        # Aim a real collision at the active player's hit circle. The game still
        # runs its normal update, feedback, elimination and transition handlers.
        self.page.evaluate("inv=0; ball={x:p.x,y:p.y-3,vx:0,vy:0,r:11}")
        self.page.clock.run_for(35)

    def eliminate_team(self):
        for remaining in (2, 1, 0):
            self.collide()
            self.assertEqual(self.page.evaluate("players"), remaining)
            self.assertEqual(self.page.evaluate("state"), "hit")
            self.page.clock.run_for(700)
        self.assertEqual(self.page.evaluate("state"), "between")

    def assert_fresh_round(self, team, round_number):
        data = self.snapshot()
        self.assertEqual((data["state"], data["team"], data["round"], data["players"]),
                         ("play", team, round_number, 3))
        self.assertEqual((data["elapsed"], data["total"], data["dash"], data["dashCooldown"]),
                         (0, 0, 0, 0))
        self.assertIsNone(data["ball"])
        self.assertEqual(self.page.evaluate("thrower"), 0)
        self.assertAlmostEqual(data["cool"], 1.1)
        self.assertGreater(data["inv"], 0)
        self.assertEqual(data["keys"], {})
        self.assertEqual(data["stick"], {"x": 0, "y": 0})
        self.assertIn(f"TEAM {chr(65 + team)}", self.page.locator("#team").inner_text())
        self.assertIn("3 LEFT", self.page.locator("#team").inner_text())
        self.assertEqual(self.page.locator("#round").inner_text(), f"ROUND {round_number}")
        self.assertTrue(self.page.locator("#dodge").is_enabled())

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

    def test_hit_feedback_exact_elimination_next_team_and_restart(self):
        self.start()
        self.page.clock.run_for(200)
        for remaining in (2, 1, 0):
            self.collide()
            self.assertEqual(self.page.evaluate("state"), "hit")
            self.assertEqual(self.page.evaluate("players"), remaining)
            self.assertIn(f"{remaining} LEFT", self.page.locator("#team").inner_text())
            self.assertTrue(self.page.locator("#feedback").is_visible())
            self.assertTrue(self.page.locator("#feedback").inner_text().strip())
            score_at_hit = self.page.evaluate("total")
            self.page.clock.run_for(250)
            self.assertEqual(self.page.evaluate("players"), remaining,
                             "One collision must eliminate exactly one teammate")
            self.assertEqual(self.page.evaluate("total"), score_at_hit,
                             "Survival time must not grow during hit feedback")
            if remaining == 2:
                # Pausing hit feedback must preserve its remaining time and resume
                # the same elimination, rather than skipping to the next player.
                self.page.locator("#pause").click()
                hit_time = self.page.evaluate("hitTime")
                self.page.clock.run_for(1000)
                self.assertEqual(self.page.evaluate("hitTime"), hit_time)
                self.page.locator("#start").click()
                self.assertEqual(self.page.evaluate("state"), "hit")
            self.page.clock.run_for(450)
            self.assertEqual(self.page.evaluate("state"), "play" if remaining else "between")
            if remaining:
                self.assertGreater(self.page.evaluate("inv"), 0)
                self.assertIsNone(self.page.evaluate("ball"))
        self.assertIn("NEXT TEAM", self.page.locator("#start").inner_text())
        self.assert_modal_focus()
        final_total = self.page.evaluate("total")
        self.page.clock.run_for(2000)
        self.assertEqual(self.page.evaluate("total"), final_total)
        self.page.locator("#start").click()
        self.assert_fresh_round(1, 2)
        self.page.locator("#pause").click()
        self.page.locator("#restart").click()
        self.assert_fresh_round(0, 1)
        self.eliminate_team()
        self.page.locator("#restart").click()
        self.assert_fresh_round(0, 1)

    def test_real_throwing_loop_eliminates_a_stationary_team(self):
        self.start(quiet=False)
        seen_counts = {3}
        seen_throwers = set()
        for _ in range(200):
            self.page.clock.run_for(100)
            data = self.snapshot()
            seen_counts.add(data["players"])
            if data["ball"] is not None:
                seen_throwers.add(self.page.evaluate("thrower"))
            if data["state"] == "between":
                break
        self.assertEqual(self.page.evaluate("state"), "between",
                         "Real alternating throws must complete a round without injected collisions")
        self.assertEqual(seen_counts, {3, 2, 1, 0})
        self.assertEqual(seen_throwers, {0, 1})
        self.assertGreater(self.page.evaluate("total"), 3)
        self.assertEqual(self.page.evaluate("players"), 0)

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
