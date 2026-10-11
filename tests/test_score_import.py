"""Exercise the real subprocess boundary with a small fake converter."""

from fractions import Fraction as F
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from ada_piano.music_sheet import Exercise, ScoreEvent, ScoreNote
from ada_piano.score_import.conversion import ScoreImporter, score_parts
from ada_piano.score_import.review import ReviewedScore, playback_notes
from ada_piano.ai_tutor import Tutor
from ada_piano.playback import ReferencePlayer
from ada_piano.sound_sensor import simulated_notes
from test_playback import FakeOutputBackend, message, wait_until
from test_musicxml import note, score


def finished(importer, timeout=5):
    deadline = monotonic() + timeout
    while importer.running:
        if monotonic() > deadline:
            raise AssertionError("Import did not stop")
        sleep(0.01)
    return importer.status


class ScoreImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.xml = self.root / "original.musicxml"
        self.xml.write_text(score(note() + note("D")), encoding="utf-8")
        self.pdf = self.root / "two pages ; score.pdf"
        self.pdf.write_bytes(b"%PDF-test fixture")

    def test_written_order_review_preserves_mode_and_playback(self):
        self.xml.write_text(score('<barline><repeat direction="forward"/></barline>' + note() + note('D')
                                  + '<barline><repeat direction="backward"/></barline>'), encoding='utf-8')
        review = ReviewedScore(self.xml, written_order=True)
        review.approve()
        self.assertTrue(review.context()['selection']['written_order'])
        self.assertEqual(len(playback_notes(review.exercise)), 2)
        saved = review.save(self.root)
        self.assertTrue(json.loads(saved.read_text())['selection']['written_order'])

    def importer(self, script=None, **kwargs):
        if script is not None:
            executable = self.root / "fake_converter.py"
            executable.write_text(script, encoding="utf-8")
            kwargs["command"] = [sys.executable, str(executable)]
        importer = ScoreImporter(self.root / "saved scores", **kwargs)
        self.addCleanup(importer.close)
        return importer

    def test_direct_musicxml_is_copied_and_requires_review(self):
        importer = self.importer()
        importer.start(self.xml)
        status = finished(importer)
        self.assertEqual(status.state, "ready")
        self.assertNotEqual(status.source, self.xml)
        self.assertEqual(status.source.read_bytes(), self.xml.read_bytes())
        manifest = json.loads((status.folder / "import.json").read_text())
        self.assertFalse(manifest["reviewed"])
        self.assertEqual(score_parts(status.outputs[0])[0]["id"], "P1")
        review = ReviewedScore(status.outputs[0], part="P1", start_measure=1, end_measure=1)
        with self.assertRaisesRegex(ValueError, "approve"):
            review.context()
        review.approve()
        saved = review.save(status.folder)
        context = json.loads(saved.read_text())
        self.assertEqual(context["events"][0]["tones"][0]["pitch"], 60)
        self.assertTrue(context["reviewed"])

    def test_pdf_conversion_retains_diagnostics_and_multiple_results(self):
        script = (
            "import pathlib, sys\n"
            "out = pathlib.Path(sys.argv[sys.argv.index('-output') + 1])\n"
            "assert sys.argv[-2] == '--'\n"
            "assert pathlib.Path(sys.argv[-1]).read_bytes().startswith(b'%PDF')\n"
            "(out / 'nested').mkdir()\n"
            f"(out / 'nested' / 'one.musicxml').write_text({self.xml.read_text()!r})\n"
            f"(out / 'two.xml').write_text({self.xml.read_text()!r})\n"
            "print('Transcription finished', flush=True)\n"
        )
        importer = self.importer(script)
        importer.start(self.pdf)
        status = finished(importer)
        self.assertEqual(status.state, "ready", status.detail)
        self.assertEqual(len(status.outputs), 2)
        self.assertIn("Transcription finished", importer.diagnostics())
        self.assertEqual(status.source.read_bytes(), self.pdf.read_bytes())
        command = json.loads((status.folder / "command.json").read_text())
        self.assertIn("-export", command)
        self.assertIn("-transcribe", command)
        self.assertIn("-save", command)
        # Continue through the same approved exercise used by GUI and agents.
        review = ReviewedScore(status.outputs[0], part="P1")
        review.approve()
        backend = FakeOutputBackend()
        player = ReferencePlayer(backend, message_factory=message)
        self.addCleanup(player.close)
        player.play_notes(playback_notes(review.exercise, tempo=300),
                          port_name="mioXC output", tempo=300)
        wait_until(lambda: player.status.state != "playing")
        self.assertEqual(player.status.state, "finished")
        self.assertEqual([m.note for m in backend.port.messages if m.type == "note_on"], [60, 62])
        tutor = Tutor(review.exercise)
        for event in simulated_notes([60, 62], releases=True):
            tutor.observe(event)
        self.assertTrue(tutor.complete)

    def test_exit_failure_and_invalid_output_are_not_ready(self):
        for script, detail in (("import sys; print('OCR failed'); sys.exit(7)", "code 7"),
                               ("print('No output')", "no readable MusicXML")):
            with self.subTest(detail=detail):
                importer = self.importer(script)
                importer.start(self.pdf)
                status = finished(importer)
                self.assertEqual(status.state, "error")
                self.assertIn(detail, status.detail)
                self.assertFalse(status.outputs)
                self.assertTrue((status.folder / "import.json").exists())

    def test_cancel_stops_process_and_prevents_loading(self):
        importer = self.importer("import time; print('Started', flush=True); time.sleep(30)")
        importer.start(self.pdf)
        deadline = monotonic() + 3
        while "Started" not in importer.diagnostics():
            if monotonic() > deadline:
                self.fail("Converter did not start")
            sleep(0.01)
        with self.assertRaisesRegex(RuntimeError, "running"):
            importer.start(self.xml)
        importer.cancel()
        status = finished(importer)
        self.assertEqual(status.state, "cancelled")
        self.assertFalse(status.outputs)
        self.assertTrue(status.source.exists())

    def test_timeout_stops_process(self):
        importer = self.importer("import time; time.sleep(30)", timeout=0.05)
        importer.start(self.pdf)
        status = finished(importer)
        self.assertEqual(status.state, "error")
        self.assertIn("time limit", status.detail)

    def test_closing_importer_cancels_active_conversion(self):
        importer = self.importer("import time; time.sleep(30)")
        importer.start(self.pdf)
        importer.close()
        self.assertEqual(finished(importer).state, "cancelled")

    def test_missing_audiveris_and_bad_xml_have_actionable_errors(self):
        importer = self.importer()
        with patch("ada_piano.score_import.conversion.shutil.which", return_value=None):
            importer.start(self.pdf)
            status = finished(importer)
        self.assertEqual(status.state, "error")
        self.assertIn("Install Audiveris", status.detail)
        self.xml.write_text("<not-music/>")
        importer.start(self.xml)
        self.assertEqual(finished(importer).state, "error")

    def test_changed_file_cannot_be_approved(self):
        review = ReviewedScore(self.xml)
        self.xml.write_text(score(note("E")))
        with self.assertRaisesRegex(ValueError, "changed"):
            review.approve()
        self.assertFalse(review.approved)


class ScorePlaybackTests(unittest.TestCase):
    def test_preserves_chords_durations_and_rest_gaps(self):
        events = (ScoreEvent(F(1), (ScoreNote(60, F(2)), ScoreNote(64, F(1)))),
                  ScoreEvent(F(4), (ScoreNote(67, F(1, 2)),)))
        exercise = Exercise("Passage", (60, 64, 67), events)
        notes = playback_notes(exercise, tempo=120)
        self.assertEqual([(n.note, n.start_beat, n.duration_beats) for n in notes],
                         [(60, 1, 2), (64, 1, 1), (67, 4, 0.5)])

    def test_unison_is_one_key_but_overlapping_retrigger_is_rejected(self):
        event = ScoreEvent(F(0), (ScoreNote(60, F(1)), ScoreNote(60, F(2))))
        exercise = Exercise("Unison", (60,), (event,))
        notes = playback_notes(exercise)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].duration_beats, 2)
        exercise = Exercise("Overlap", (60, 60), (event, ScoreEvent(F(1), (ScoreNote(60, F(1)),))))
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            playback_notes(exercise)
