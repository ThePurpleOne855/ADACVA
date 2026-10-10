"""Desktop smoke tests; skipped when Tk or a display is unavailable."""

import unittest

from ada_piano.note_reader import NoteReader
from test_note_reader import FakeBackend, note, control

try:
    import tkinter as tk
    from ada_piano.note_reader.gui import NoteReaderWindow
except ImportError:
    tk = None


@unittest.skipIf(tk is None, "Tkinter is not installed")
class NoteReaderGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Desktop unavailable: {exc}")
        self.root.withdraw()
        self.backend = FakeBackend()
        self.reader = NoteReader(self.backend)
        self.window = NoteReaderWindow(self.root, reader=self.reader)
        # Withdrawn test windows do not receive the canvas Configure event.
        self.window.keyboard._draw()
        self.addCleanup(self.window.close)

    def run_gui(self, milliseconds=100):
        self.root.after(milliseconds, self.root.quit)
        self.root.mainloop()

    def test_live_notes_and_stop(self):
        self.window.connect()
        self.backend.ports[-1].messages.extend([note(), note(number=64)])
        self.run_gui()
        self.assertIn("E4", self.window.latest.get())
        self.assertIn("C4", self.window.held.get())
        self.assertEqual(len(self.window.log.get_children()), 2)
        self.assertEqual(self.window.keyboard.active, {60, 64})
        self.assertEqual(self.window.keyboard.itemcget(self.window.keyboard.key_items[60], "fill"), "#22c55e")
        self.window.disconnect()
        self.assertEqual(self.window.held.get(), "Held keys: none")
        self.assertTrue(self.backend.ports[-1].closed)
        self.assertFalse(self.window.keyboard.active)

    def test_demo_switch_cleans_live_port(self):
        self.window.connect()
        port = self.backend.ports[-1]
        self.window.start_demo()
        self.run_gui(550)
        self.assertTrue(port.closed)
        self.assertIn("DEMO", self.window.status.get())
        self.assertIn("C4", self.window.latest.get())
        self.assertEqual(self.reader.state.sustain, {1})

    def test_bounded_history_clear_and_connection_error(self):
        event = self.reader.state.consume(note())
        for _ in range(505):
            self.window._record(event)
        self.assertEqual(len(self.window.log.get_children()), 500)
        self.window.clear_log()
        self.assertFalse(self.window.log.get_children())
        self.assertIn((1, 60), self.reader.state.held)
        self.backend.error = OSError("Device busy")
        self.window.connect()
        self.assertIn("Device busy", self.window.status.get())
        self.assertFalse(self.reader.connected)

    def test_prefers_instrument_to_midi_through(self):
        self.window.disconnect()
        self.backend.names = ["Midi Through:Midi Through Port-0 14:0", "mioXC:mioXC MIDI 1 28:0"]
        self.window.port.set("")
        self.window.refresh()
        self.assertEqual(self.window.port.get(), self.backend.names[1])
        self.window.connect()
        self.assertEqual(self.reader.port_name, self.backend.names[1])

    def test_single_instrument_auto_connects_on_startup(self):
        self.assertTrue(self.reader.connected)
        self.assertEqual(self.reader.port_name, "USB MIDI")

    def test_release_preserves_other_channel_and_marks_last_note(self):
        port = self.backend.ports[-1]
        port.messages.extend([note(number=61), note(number=61, channel=1),
                              note("note_off", number=61)])
        self.run_gui()
        self.assertEqual(self.window.keyboard.active, {61})
        port.messages.append(note(number=61, velocity=0, channel=1))
        self.run_gui()
        self.assertFalse(self.window.keyboard.active)
        keyboard = self.window.keyboard
        self.assertEqual(keyboard.last_played, 61)
        self.assertEqual(keyboard.itemcget(keyboard.key_items[61], "fill"), keyboard.BLACK)
        self.assertEqual(keyboard.itemcget(keyboard.key_items[61], "outline"), keyboard.LAST)

    def test_no_notes_diagnostic_and_control_activity(self):
        self.reader.connected_at -= 6
        self.run_gui()
        self.assertIn("No key presses received", self.window.activity.get())
        self.assertIn("PC mode = OFF", self.window.activity.get())
        self.backend.ports[-1].messages.append(control(64, 127))
        self.run_gui()
        self.assertIn("MIDI messages: 1", self.window.activity.get())
        self.assertIn("control_change", self.window.activity.get())

    def test_transposed_note_range_and_resize_keep_highlights(self):
        keyboard = self.window.keyboard
        for number in (0, 127, 60):
            with self.subTest(number=number):
                keyboard.show_notes({number}, number)
                keyboard._draw()
                self.assertEqual(len(keyboard.key_items), 61)
                self.assertIn(number, keyboard.key_items)
                self.assertEqual(keyboard.itemcget(keyboard.key_items[number], "fill"), keyboard.PRESSED)
