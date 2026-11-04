"""Practice piano, camera lifecycle, and layout with fake hardware."""

import unittest
from unittest.mock import patch

import test_accessible_integration as integration
from test_live_practice import press
from test_note_reader import note
from ada_piano.camera.stream import CameraFrame


class PracticeGuiTests(unittest.TestCase):
    setUp = integration.AccessibleIntegrationTests.setUp
    close_window = integration.AccessibleIntegrationTests.close_window
    run_gui = integration.AccessibleIntegrationTests.run_gui

    def test_piano_grades_loaded_score_and_releases_clear_color(self):
        w = self.window
        w.score.load_piece('ode to joy')
        panel = w.home.practice
        panel.keyboard._draw()
        for pitch, expected_color in ((60, panel.keyboard.WRONG), (64, panel.keyboard.PRESSED)):
            event = w.reader.state.consume(note(number=pitch))
            w._record(event)
            w._show_state()
            self.assertEqual(panel.keyboard.itemcget(panel.keyboard.key_items[pitch], 'fill'), expected_color)
        self.assertEqual(panel.follow.tutor.position, 1)
        event = w.reader.state.consume(note('note_off', number=64))
        w._record(event)
        w._show_state()
        self.assertNotEqual(panel.keyboard.itemcget(panel.keyboard.key_items[64], 'fill'), panel.keyboard.PRESSED)
        panel.restart_button.invoke()
        self.assertEqual(panel.follow.tutor.position, 0)
        w.score.load_piece('fur elise', hands='right')
        w._show_state()
        self.assertEqual(panel.follow.expected, w.score.loaded.exercise.events[0].pitches)
        event = w.reader.state.consume(note(number=120))
        w._record(event)
        w._show_state()
        self.assertIn(120, panel.keyboard.key_items)
        self.assertEqual(panel.keyboard.itemcget(panel.keyboard.key_items[120], 'fill'), panel.keyboard.WRONG)

    def _reopen(self, camera_present):
        self.close_window()
        self.root = integration.existing.tk.Tk()
        self.root.withdraw()
        with patch("ada_piano.note_reader.gui.has_camera", return_value=camera_present), \
                patch("ada_piano.camera.gui.best_camera", return_value=(0, "Camera 0")), \
                patch("ada_piano.agent.gui.CoachPanel.use_best_voice"):
            self.window = integration.existing.NoteReaderWindow(
                self.root, reader=integration.NoteReader(self.backend),
                player=integration.ReferencePlayer(integration.FakeOutputBackend(),
                                                   message_factory=integration.message),
                camera_worker=integration.existing.FakeCameraWorker(), voice=self.voice,
                microphone=integration.FakeMicrophone(), accessible=True,
                session_directory=self.temp.name)
        self.window.keyboard._draw()

    def test_camera_connects_automatically_when_available(self):
        self._reopen(camera_present=True)
        self.assertEqual(self.window.camera.worker.started, [0])

    def test_camera_stays_off_when_no_camera_is_available(self):
        self._reopen(camera_present=False)
        self.assertEqual(self.window.camera.worker.started, [])
        self.assertFalse(self.window.camera.worker.running)

    def test_reference_playback_does_not_advance_live_score(self):
        w = self.window
        w.score.load_piece('ode to joy')
        with patch.object(type(w.playback.player), 'status') as status:
            status.state = 'playing'
            w._record(press(64))
        self.assertEqual(w.home.practice.follow.tutor.position, 0)

    def test_camera_frame_is_shared_and_stop_clears_large_preview(self):
        w = self.window
        panel = w.home.practice
        frame = CameraFrame(b'P6\n2 4\n255\n' + bytes([0, 255, 0]) * 8, 1)
        w._camera_frame(frame)
        panel.preview.configure(width=300, height=200)
        panel._draw_camera()
        self.assertIs(panel._frame, frame)
        self.assertLessEqual(panel._photo.width(), max(1, panel.preview.winfo_width()))
        self.assertLessEqual(panel._photo.height(), max(1, panel.preview.winfo_height()))
        w.camera.stop()
        self.assertIsNone(panel._frame)

    def test_main_practice_replaces_chat_and_controls_fit(self):
        w = self.window
        self.root.overrideredirect(True)
        self.root.deiconify()
        self.run_gui(300)
        self.root.geometry("1000x760")
        w.score.load_piece('fur elise', hands='both')
        self.root.update_idletasks()
        w._show_state()
        self.root.update_idletasks()
        self.run_gui(100)
        panel = w.home.practice
        self.assertFalse(w.home._words.winfo_manager())
        self.assertFalse(w.home.status_label.winfo_manager())
        for widget in (panel.keyboard, panel.preview, panel.camera_button, panel.restart_button,
                       panel._labels['feedback']):
            self.assertTrue(widget.winfo_ismapped(), f"{widget} at scale {w.home.scale}")
            self.assertGreater(widget.winfo_width(), 1, f"{widget}: panel {panel.winfo_width()}x{panel.winfo_height()}, camera {panel.preview.master.winfo_geometry()}")
            self.assertGreater(widget.winfo_height(), 1)
            x = widget.winfo_rootx() - panel.winfo_rootx()
            y = widget.winfo_rooty() - panel.winfo_rooty()
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + widget.winfo_width(), panel.winfo_width())
            self.assertLessEqual(y + widget.winfo_height(), panel.winfo_height())

    def test_enlarged_text_keeps_long_score_feedback_reachable(self):
        w = self.window
        self.root.overrideredirect(True)
        self.root.deiconify()
        self.run_gui(300)
        self.root.geometry("1000x760")
        w.score.load_piece("fur elise", hands="both")
        for scale in (1.3, 1.75):
            while w.home.scale < scale:
                w.text_size(1)
            self.run_gui(300)
            panel = w.home.practice
            for widget in (panel.preview, panel.camera_button, panel.restart_button,
                           panel._labels["expected"], panel._labels["feedback"]):
                self.assertTrue(widget.winfo_ismapped(), f"{widget} at scale {w.home.scale}")
                self.assertGreater(widget.winfo_height(), 1)
            panel.viewport.yview_moveto(1)
            self.root.update_idletasks()
            self.assertTrue(panel.keyboard.winfo_ismapped())
            bottom = panel.keyboard.winfo_rooty() + panel.keyboard.winfo_height()
            self.assertLessEqual(bottom, panel.viewport.winfo_rooty() + panel.viewport.winfo_height())
