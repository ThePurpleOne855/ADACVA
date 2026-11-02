"""Native controls for the quiet practice view; no audio or hardware is started."""

import gc
import unittest
from unittest.mock import Mock

try:
    import tkinter as tk
    from ada_piano.note_reader.accessible import AccessibleView
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Tkinter is not installed")
class AccessibleViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Desktop unavailable: {exc}")
        self.root.withdraw()
        self.status = tk.StringVar(value="Ready to practice.")
        self.submit, self.talk, self.stop, self.tools = (Mock() for _ in range(4))
        self.view = AccessibleView(self.root, submit=self.submit, talk=self.talk,
                                   stop=self.stop, tools=self.tools, status=self.status)
        self.view.pack(fill="both", expand=True)
        self.addCleanup(self.close_view)

    def close_view(self):
        self.view.close()
        self.root.destroy()
        self.view = None
        gc.collect()

    def test_message_submission_trims_text_and_clears_the_entry(self):
        self.view.entry.insert(0, "  Practice middle C  ")
        self.assertEqual(self.view._send(), "break")
        self.submit.assert_called_once_with("Practice middle C")
        self.assertEqual(self.view.entry.get(), "")
        self.assertTrue(self.view.entry.bind("<Return>"))

    def test_empty_message_does_not_submit(self):
        self.view._send()
        self.view.entry.insert(0, "   ")
        self.view._send()
        self.submit.assert_not_called()

    def test_failed_submission_preserves_message(self):
        self.submit.side_effect = RuntimeError("Coach unavailable")
        self.view.entry.insert(0, "Play C major")
        with self.assertRaisesRegex(RuntimeError, "Coach unavailable"):
            self.view._send()
        self.assertEqual(self.view.entry.get(), "Play C major")

    def test_named_native_controls_invoke_their_actions(self):
        for button, callback in ((self.view.talk_button, self.talk),
                                 (self.view.stop_button, self.stop),
                                 (self.view.tools_button, self.tools)):
            self.assertIsInstance(button, tk.Button)
            self.assertTrue(button.cget("text"))
            self.assertTrue(button.cget("takefocus"))
            self.assertGreater(button.cget("highlightthickness"), 0)
            button.invoke()
            callback.assert_called_once_with()
        self.assertFalse(self.root.tk.getboolean(self.view.background.cget("takefocus")))

    def test_status_and_transcript_are_available_as_native_text(self):
        self.status.set("Listening. Say what you would like to practice.")
        self.assertEqual(str(self.view.status_label.cget("textvariable")), str(self.status))
        self.assertEqual(self.view.status_label.cget("text"), self.status.get())
        self.view.append("ADA", "Your piano is connected.")
        self.view.append("You", "Let's practice.")
        text = self.view.transcript.get("1.0", "end")
        self.assertIn("ADA: Your piano is connected.", text)
        self.assertIn("You: Let's practice.", text)
        self.assertEqual(self.view.transcript.cget("state"), "disabled")
        self.assertTrue(self.view.transcript.cget("takefocus"))
        self.assertTrue(self.view.transcript.bind("<Tab>"))
        self.assertTrue(self.view.transcript.bind("<Shift-Tab>"))

    def test_transcript_history_is_bounded(self):
        for turn in range(220):
            self.view.append("ADA", f"Turn {turn}")
        self.assertLessEqual(int(self.view.transcript.index("end-1c").split(".")[0]), 300)
        self.assertIn("Turn 219", self.view.transcript.get("1.0", "end"))

    def test_controls_fit_at_the_minimum_window_size(self):
        self.view.pack_forget()
        self.view.place(x=0, y=0, width=700, height=500)
        self.root.update_idletasks()
        for widget in (self.view.entry, self.view.talk_button, self.view.stop_button,
                       self.view.tools_button, self.view.transcript):
            left = widget.winfo_rootx() - self.view.winfo_rootx()
            top = widget.winfo_rooty() - self.view.winfo_rooty()
            self.assertGreaterEqual(left, 0)
            self.assertGreaterEqual(top, 0)
            self.assertLessEqual(left + widget.winfo_width(), 700)
            self.assertLessEqual(top + widget.winfo_height(), 500)

    def test_close_is_repeatable_and_stops_late_updates_without_timers(self):
        self.view.append("ADA", "Ready.")
        before = self.view.transcript.get("1.0", "end")
        self.view.close()
        self.view.close()
        self.view.append("ADA", "Late update")
        self.view.entry.insert(0, "Late command")
        self.view._send()
        self.view.focus_message()
        self.assertEqual(self.view.transcript.get("1.0", "end"), before)
        self.submit.assert_not_called()
        self.assertEqual(self.root.tk.call("after", "info"), "")

    def test_a_take_arriving_mid_animation_leaves_no_orphan_timer(self):
        cells = [{"measure": "1", "dots": ["ok", "ok"], "ring": False}, {"measure": "2", "dots": ["miss"], "ring": True}]
        self.view.show_take(cells, 2, 3, key="ode", note="Measure 2: F sharp 4 instead of F 4.")
        self.view.show_take(cells, 3, 3, key="ode", note="Every note right.")  # first animation still running
        self.assertEqual([take["score"] for take in self.view._takes], ["2 / 3", "3 / 3"])
        self.view.close()
        self.assertEqual(self.root.tk.call("after", "info"), "")

    def test_takes_compare_only_within_the_same_passage(self):
        cells = [{"measure": "1", "dots": ["ok"], "ring": False}]
        self.view.show_take(cells, 1, 1, key="measures 1-2")
        self.view.show_take(cells, 0, 1, key="measures 3-4")
        self.assertEqual([take["key"] for take in self.view._takes], ["measures 3-4"])
        self.view.set_context(piece="Ode to Joy · measures 3 to 4 · right hand")
        self.assertEqual(self.view._takes, [])  # a new piece or passage starts a fresh comparison

    def test_text_size_steps_and_resets(self):
        self.assertEqual([self.view.change_scale(step) for step in (1, 1, 0, -1, -1, -1)],
                         [1.15, 1.3, 1.0, 0.9, 0.8, 0.8])

    def test_without_pillow_the_view_still_works_with_tk_text(self):
        from unittest.mock import patch
        with patch("ada_piano.note_reader.lettering.available", return_value=False):
            view = AccessibleView(self.root, submit=self.submit, talk=self.talk, stop=self.stop,
                                  tools=self.tools, status=self.status)
        self.addCleanup(view.close)
        self.assertEqual(view.talk_button.cget("text"), "Talk to ADA (F1)")
        self.assertEqual(str(view.talk_button.cget("image")), "")
        view.append("ADA", "Plain text still reads.")
        self.assertIn("ADA: Plain text still reads.", view.transcript.get("1.0", "end"))


@unittest.skipIf(tk is None, "Tkinter is not installed")
class TakeEvidenceTests(unittest.TestCase):
    """Pure evidence shaping: the real scorer on synthetic notes, no Tk window."""

    def report(self, changes, hold=0.9):
        from ada_piano import pieces
        from ada_piano.ai_tutor.performance import PlayThrough, compare
        exercise = pieces.load(pieces.find("ode to joy", pieces.catalog()), "whole", None).exercise
        take = PlayThrough(100.0)
        for index, event in enumerate(exercise.events):
            onset = 100.5 + float(event.onset) * 0.75
            for tone in event.tones:
                pitch = changes.get(index, tone.pitch)
                if pitch is not None:
                    take.observe("on", pitch, 80, 0, onset)
                    take.observe("off", pitch, 0, 0, onset + hold * float(tone.duration) * 0.75)
        take.finish(140)
        return exercise, compare(exercise, take.notes, target_bpm=80)

    def test_one_dot_per_note_grouped_by_measure_with_the_trouble_ringed(self):
        from ada_piano.note_reader.accessible import take_cells, take_note
        exercise, report = self.report({5: 66})  # F sharp 4 for F 4, the second note of measure 2
        cells = take_cells(exercise, report)
        self.assertEqual([len(cell["dots"]) for cell in cells], [4, 4, 4, 3, 4, 4, 4, 3])
        self.assertEqual(cells[1], {"measure": "2", "dots": ["ok", "miss", "ok", "ok"], "ring": True})
        self.assertEqual(sum(dot == "miss" for cell in cells for dot in cell["dots"]), 1)
        self.assertEqual([cell["ring"] for cell in cells].count(True), 1)
        self.assertEqual(take_note(report), "Measure 2: F sharp 4 instead of F 4.")

    def test_clean_and_unfinished_takes_say_so(self):
        from ada_piano.note_reader.accessible import take_cells, take_note
        exercise, report = self.report({})
        self.assertEqual(take_note(report), "Every note right.")
        self.assertTrue(all(dot == "ok" for cell in take_cells(exercise, report) for dot in cell["dots"]))
        exercise, report = self.report({}, hold=0.3)  # every key released far too soon
        self.assertEqual(report["measures_needing_work"][0], "1")  # the scorer's ranking, not ours
        self.assertEqual(take_note(report), "Measure 1: E 4 was held too briefly.")
        exercise, report = self.report({index: None for index in range(20, 30)})  # stopped early
        cells = take_cells(exercise, report)
        self.assertEqual(cells[-1]["dots"], ["rest", "rest", "rest"])
        self.assertFalse(report["complete"])

    def test_state_words(self):
        from ada_piano.note_reader.accessible import state_word
        self.assertEqual(state_word("Recording. Say ADA finish recording or press F6 for results; Escape stops."),
                         ("Recording", True))
        self.assertEqual(state_word("Listening for one question; pause when finished."), ("Listening", True))
        self.assertEqual(state_word("ADA is thinking. Say ADA stop or press Escape to cancel."), ("Thinking", True))
        self.assertEqual(state_word("Microphone off."), ("Microphone off", False))
        self.assertEqual(state_word("Microphone paused while ADA speaks or reference sound plays."), ("Paused", False))
        self.assertEqual(state_word(""), ("Ready", False))


if __name__ == "__main__":
    unittest.main()
