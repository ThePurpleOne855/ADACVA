"""Desktop smoke tests; skipped when Tk or a display is unavailable."""

import unittest
from unittest.mock import patch

from ada_piano.note_reader import NoteReader
from test_note_reader import FakeBackend, note, control
from ada_piano.playback import ReferencePlayer
from test_playback import FakeOutputBackend, message

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
        self.output_backend = FakeOutputBackend()
        self.player = ReferencePlayer(self.output_backend, message_factory=message)
        self.window = NoteReaderWindow(self.root, reader=self.reader, player=self.player)
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

    def test_reference_controls_send_notes_without_counting_them_as_input(self):
        panel = self.window.playback
        panel.tempo.set("300")
        panel.beats.set("0.1")
        panel.sequence.set("C4 D4 E4")
        panel.play_sequence()
        self.run_gui(200)
        self.assertEqual(self.player.status.state, "finished")
        self.assertEqual(self.reader.state.note_count, 0)
        rows = self.window.log.get_children()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(self.window.log.set(row, "source") == "Reference" for row in rows))
        self.assertFalse(panel.active)

    def test_reference_highlight_and_stop(self):
        self.window._play_key(61)
        self.run_gui(100)
        keyboard = self.window.keyboard
        self.assertIn(61, keyboard.reference)
        self.assertEqual(keyboard.itemcget(keyboard.key_items[61], "fill"), keyboard.REFERENCE)
        self.assertEqual(self.reader.state.note_count, 0)
        self.window.playback.stop()
        self.run_gui(100)
        self.assertFalse(keyboard.reference)
        self.assertEqual(self.player.status.state, "stopped")

    def test_bad_reference_input_does_not_open_output(self):
        panel = self.window.playback
        panel.sequence.set("C4 not-a-note")
        panel.play_sequence()
        self.assertEqual(self.output_backend.opens, 0)
        self.assertIn("Invalid note", panel.status.get())
        panel.pitch.set("C4")
        panel.beats.set("nan")
        panel.play_note()
        self.assertEqual(self.output_backend.opens, 0)

    def test_reference_does_not_auto_select_software_loopback(self):
        panel = self.window.playback
        self.output_backend.names = ["Midi Through:Midi Through Port-0 14:0", "RtMidiIn Client:RtMidi input 128:0"]
        panel.refresh()
        self.assertEqual(panel.output.get(), "")
        self.assertIn("Only software outputs", panel.status.get())

    def test_canvas_click_on_black_key_plays_black_key(self):
        from types import SimpleNamespace
        keyboard = self.window.keyboard
        # Draw at a practical size even though the window remains hidden.
        with patch.object(keyboard, "winfo_width", return_value=1000):
            keyboard._draw()
        x1, y1, x2, y2 = keyboard.coords(keyboard.key_items[61])
        keyboard._click(SimpleNamespace(x=(x1 + x2) / 2, y=(y1 + y2) / 2))
        self.run_gui(100)
        sent = [m.note for m in self.output_backend.port.messages if m.type == "note_on"]
        self.assertEqual(sent, [61])

    def test_duration_column_on_release_and_after_clearing_log(self):
        with patch("ada_piano.note_reader.monotonic", side_effect=[10, 11.375]):
            self.window._record(self.reader.state.consume(note()))
            row = self.window.log.get_children()[-1]
            self.assertEqual(self.window.log.set(row, "duration"), "—")
            self.window.clear_log()
            self.window._record(self.reader.state.consume(note(velocity=0)))
        row = self.window.log.get_children()[-1]
        self.assertEqual(self.window.log.set(row, "duration"), "1.375")
        self.assertEqual(self.window.log.set(row, "event"), "OFF")

    def test_disconnect_discards_unfinished_duration(self):
        self.window._record(self.reader.state.consume(note()))
        self.window.disconnect()
        self.window.connect()
        self.window._record(self.reader.state.consume(note("note_off")))
        row = self.window.log.get_children()[-1]
        self.assertEqual(self.window.log.set(row, "duration"), "—")

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
