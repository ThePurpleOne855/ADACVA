"""Desktop smoke tests; skipped when Tk or a display is unavailable."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, PropertyMock

from ada_piano.note_reader import NoteReader
from test_note_reader import FakeBackend, note, control
from ada_piano.playback import ReferencePlayer
from test_playback import FakeOutputBackend, message
from ada_piano.camera.stream import CameraFrame
from ada_piano.score_import.conversion import ScoreImporter
from test_musicxml import note as score_note, score


class FakeCameraWorker:
    def __init__(self):
        self.running = False
        self.closed = False
        self.status = "Camera off."
        self.frame = None
        self.started = []

    def start(self, index):
        self.started.append(index)
        self.running = True
        self.status = "Tracking 1 hand(s)."
        self.frame = CameraFrame(b"P6\n2 2\n255\n" + bytes([0, 255, 0]) * 4, 1)

    def snapshot(self):
        frame, self.frame = self.frame, None
        return frame, self.status

    def stop(self):
        self.running = False
        self.status = "Camera stopped."

    def close(self):
        self.stop()
        self.closed = True

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
        self.camera_worker = FakeCameraWorker()
        self.window = NoteReaderWindow(self.root, reader=self.reader, player=self.player,
                                       camera_worker=self.camera_worker)
        # Withdrawn test windows do not receive the canvas Configure event.
        self.window.keyboard._draw()
        self.addCleanup(self.window.close)

    def run_gui(self, milliseconds=100):
        self.root.after(milliseconds, self.root.quit)
        self.root.mainloop()

    def test_embedded_camera_and_midi_update_together(self):
        self.window.camera.start()
        self.backend.ports[-1].messages.append(note(number=64))
        self.run_gui()
        self.assertIn("E4", self.window.latest.get())
        self.assertEqual(self.window.camera._photo.width(), 2)
        self.assertIn("Tracking 1", self.window.camera.status.get())
        self.window.camera.stop()
        self.assertIsNone(self.window.camera._photo)
        self.assertTrue(self.reader.connected)
        self.window.close()
        self.assertTrue(self.camera_worker.closed)

    def test_camera_failure_keeps_midi_connected(self):
        self.camera_worker.status = "Camera error: Device unavailable"
        self.backend.ports[-1].messages.append(note())
        self.run_gui()
        self.assertIn("Device unavailable", self.window.camera.status.get())
        self.assertIn("C4", self.window.latest.get())
        self.assertTrue(self.reader.connected)

    def test_camera_selector_switches_without_disconnecting_midi(self):
        panel = self.window.camera
        with patch("ada_piano.camera.gui.camera_choices", return_value={"Built-in": 0, "USB camera": 4}):
            panel.refresh()
        panel.start()
        self.run_gui()
        panel.selection.set("USB camera")
        panel._selected()
        self.run_gui()
        self.assertEqual(self.camera_worker.started, [0, 4])
        self.assertTrue(self.reader.connected)
        self.assertIn("Camera 4", panel.status.get())

    def load_score_preview(self, content=None, document=None):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        source = folder / "melody.musicxml"
        source.write_text(document if document is not None else score(score_note() if content is None else content), encoding="utf-8")
        panel = self.window.score
        panel.importer = ScoreImporter(folder / "library")
        panel.import_file(source)
        self.run_gui(250)
        self.assertEqual(panel.importer.status.state, "ready")
        panel.preview()
        self.assertIsNotNone(panel.review, panel.status.get())
        return panel

    def test_piano_part_is_preferred_over_rest_only_voice(self):
        document = score('<note><rest/><duration>1</duration></note>')
        document = document.replace('<part-name>Piano</part-name>', '<part-name>Voice</part-name>')
        document = document.replace('</part-list>', '<score-part id="P2"><part-name>Piano</part-name></score-part></part-list>')
        document = document.replace('</score-partwise>', '<part id="P2"><measure number="1">' + score_note() + '</measure></part></score-partwise>')
        panel = self.load_score_preview(document=document)
        self.assertEqual(panel._selected_part()['id'], 'P2')
        self.assertEqual(panel.review.exercise.notes, (60,))

    def test_whole_piece_selects_all_measures_and_both_hands(self):
        from test_musicxml import measures
        upper = score_note(extra='<voice>1</voice><staff>1</staff>')
        lower = '<backup><duration>1</duration></backup>' + score_note('E', extra='<voice>2</voice><staff>2</staff>')
        panel = self.load_score_preview(document=measures(*([upper + lower] * 6)))
        self.assertEqual(panel.last.get(), '4')
        panel.confirmed.set(True)
        panel.approve()
        panel.preview_whole()
        self.assertIsNone(panel.loaded)
        self.assertFalse(panel.confirmed.get())
        self.assertEqual((panel.first.get(), panel.last.get(), panel.staff.get(), panel.voice.get()), ('1', '6', '', ''))
        self.assertIsNotNone(panel.review, panel.status.get())
        self.assertEqual(len(panel.review.exercise.events), 6)
        self.assertTrue(all(event.pitches == (60, 64) for event in panel.review.exercise.events))

    def test_repeat_preview_and_mode_change_invalidates_approval(self):
        panel = self.load_score_preview('<barline><repeat direction="forward"/></barline>' + score_note())
        panel.confirmed.set(True)
        panel.approve()
        self.assertTrue(panel.agent_context()["selection"]["written_order"])
        panel.written_order.set(False)
        self.assertIsNone(panel.loaded)
        self.assertIsNone(panel.review)
        panel.preview()
        self.assertIn('repeat', panel.status.get())

    def test_score_requires_approval_and_selection_changes_invalidate_it(self):
        panel = self.load_score_preview()
        panel.approve()
        self.assertIsNone(panel.loaded)
        panel.confirmed.set(True)
        panel.approve()
        self.assertIsNotNone(panel.loaded, panel.status.get())
        self.assertEqual(panel.agent_context()["events"][0]["tones"][0]["pitch"], 60)
        self.assertTrue((panel._folder / "reviewed-exercise.json").exists())
        panel.voice.set("1")
        self.assertIsNone(panel.loaded)
        self.assertIsNone(panel.review)
        self.assertFalse(panel.confirmed.get())
        self.assertEqual(str(panel.play_button["state"]), "disabled")

    def test_approved_score_plays_and_reference_does_not_grade_practice(self):
        panel = self.load_score_preview()
        panel.confirmed.set(True)
        panel.approve()
        self.window.playback.tempo.set("300")
        panel.play()
        self.run_gui(300)
        sent = [m.note for m in self.output_backend.port.messages if m.type == "note_on"]
        self.assertEqual(sent, [60])
        self.assertIsNone(panel.tutor)
        panel.practice()
        self.assertIsNotNone(panel.tutor)
        event = self.reader.state.consume(note())
        panel.observe(event, "Reference")
        panel.observe(event, "Demo")
        self.assertEqual(panel.tutor.position, 0)
        panel.observe(event, "Piano")
        self.assertIn("Exercise complete", panel.feedback.get())
        self.assertIsNone(panel.tutor)

    def test_score_import_error_does_not_disconnect_midi(self):
        panel = self.window.score
        panel.import_file("/missing/file.pdf")
        self.assertIn("Cannot import", panel.status.get())
        self.assertTrue(self.reader.connected)

    def test_failed_pdf_keeps_preview_disabled_and_preserves_reason(self):
        from ada_piano.score_import.conversion import ImportStatus
        panel = self.window.score
        self.assertEqual(str(panel.preview_button["state"]), "disabled")
        with patch.object(type(panel.importer), "status", new_callable=PropertyMock) as status:
            status.return_value = ImportStatus("error", "Audiveris was not found.")
            panel.preview()
        self.assertIn("No MusicXML", panel.status.get())
        self.assertIn("Audiveris was not found", panel.status.get())
        self.assertIsNone(panel.review)

    def test_score_cannot_replace_automatic_converter(self):
        panel = self.window.score
        with patch("ada_piano.score_import.gui.filedialog.askopenfilename", return_value="/scores/fur_elise.pdf"):
            panel.choose_executable()
        self.assertEqual(panel.executable.get(), "auto")
        self.assertIn("Choose PDF / MusicXML", panel.status.get())
        self.assertIn("automatic", panel.converter_label.get())

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
