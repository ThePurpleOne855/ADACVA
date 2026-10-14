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


if __name__ == "__main__":
    unittest.main()
