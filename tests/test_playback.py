from dataclasses import replace
import time
from types import SimpleNamespace
import unittest

from ada_piano.playback import PlaybackNote, ReferencePlayer, parse_note, validate_notes


def message(kind, **values):
    return SimpleNamespace(type=kind, **values)


class FakeOutput:
    def __init__(self):
        self.messages = []
        self.closed = False
        self.fail_note = None

    def send(self, msg):
        if msg.type == "note_on" and msg.note == self.fail_note:
            raise OSError("Send failed")
        self.messages.append(msg)

    def close(self):
        self.closed = True


class FakeOutputBackend:
    def __init__(self):
        self.names = ["mioXC output"]
        self.port = FakeOutput()
        self.opens = 0
        self.error = None

    def get_output_names(self):
        return list(self.names)

    def open_output(self, name):
        self.opens += 1
        if self.error:
            raise self.error
        return self.port


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Playback did not reach the expected state")


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeOutputBackend()
        self.player = ReferencePlayer(self.backend, message_factory=message)
        self.addCleanup(self.player.close)

    def play(self, notes, tempo=300):
        self.player.play_notes(notes, port_name="mioXC output", tempo=tempo)

    def finish(self):
        wait_until(lambda: self.player.status.state != "playing")
        self.player.close()

    def test_named_notes_and_range(self):
        for name, expected in (("C4", 60), ("F#4", 66), ("Bb3", 58), ("C-1", 0), ("G9", 127), ("60", 60)):
            self.assertEqual(parse_note(name), expected)
        for name in ("H4", "128", "C10", "-1", "", "C"):
            with self.assertRaises(ValueError):
                parse_note(name)

    def test_validation_rejects_bad_or_unbounded_requests_before_output(self):
        default = PlaybackNote(60)
        for changed in (replace(default, note=True), replace(default, velocity=0),
                        replace(default, channel=17), replace(default, start_beat=-1),
                        replace(default, duration_beats=0), replace(default, duration_beats=float("nan")),
                        replace(default, start_beat=float("inf")), replace(default, duration_beats=1500)):
            with self.subTest(note=changed), self.assertRaises(ValueError):
                self.play([changed], tempo=90)
        for tempo in (0, 301, True, float("inf")):
            with self.assertRaises(ValueError):
                self.play([default], tempo=tempo)
        for notes in ([], [default] * 4097, [60]):
            with self.assertRaises(ValueError):
                self.play(notes)
        self.assertEqual(self.backend.opens, 0)

    def test_json_request_validates_and_plays(self):
        self.player.play_request({"tempo": 300, "notes": [{"note": 60, "duration_beats": 0.05}]},
                                 port_name="mioXC output")
        self.finish()
        self.assertEqual(self.player.status.state, "finished")
        self.assertEqual([m.note for m in self.backend.port.messages if m.type == "note_on"], [60])

    def test_json_request_rejects_arbitrary_commands(self):
        for request in ({"notes": [{"note": 60}], "sysex": [1]}, {"notes": [60]},
                        {"notes": [{"note": 60, "port_name": "other"}]}, {"notes": []}):
            with self.assertRaises(ValueError):
                self.player.play_request(request, port_name="mioXC output")
        self.assertEqual(self.backend.opens, 0)

    def test_chord_and_adjacent_repeated_note_order(self):
        self.play([PlaybackNote(60, 0, .05), PlaybackNote(64, 0, .05), PlaybackNote(60, .05, .05)])
        self.finish()
        events = self.player.drain_events()
        self.assertEqual([(e.kind, e.note) for e in events],
                         [("on", 60), ("on", 64), ("off", 60), ("off", 64), ("on", 60), ("off", 60)])
        self.assertTrue(all(e.source == "reference" for e in events))
        self.assertTrue(all(e.duration > 0 for e in events if e.kind == "off"))
        self.assertTrue(self.backend.port.closed)

    def test_tempo_and_initial_rest_are_scheduled(self):
        self.play([PlaybackNote(60, .2, .5)], tempo=300)
        time.sleep(.01)
        self.assertFalse(any(m.type == "note_on" for m in self.backend.port.messages))
        self.finish()
        on, off = self.player.drain_events()
        self.assertGreaterEqual(off.timestamp - on.timestamp, .07)
        self.assertLess(off.timestamp - on.timestamp, .5)

    def test_overlapping_pitch_rejected_but_separate_channels_allowed(self):
        with self.assertRaises(ValueError):
            self.play([PlaybackNote(60), PlaybackNote(60, .5)])
        validate_notes([PlaybackNote(60), PlaybackNote(60, channel=2)], 90)

    def test_stop_releases_active_notes_and_pedal(self):
        self.play([PlaybackNote(60, duration_beats=20), PlaybackNote(64, duration_beats=20)])
        wait_until(lambda: sum(m.type == "note_on" for m in self.backend.port.messages) == 2)
        self.player.stop()
        self.finish()
        self.assertEqual(self.player.status.state, "stopped")
        self.assertEqual({m.note for m in self.backend.port.messages if m.type == "note_off"}, {60, 64})
        last = self.backend.port.messages[-1]
        self.assertEqual((last.type, last.control, last.value), ("control_change", 64, 0))

    def test_stop_during_initial_rest_sends_no_notes(self):
        self.play([PlaybackNote(60, start_beat=10)])
        self.player.stop()
        self.finish()
        self.assertFalse(any(m.type == "note_on" for m in self.backend.port.messages))

    def test_send_failure_releases_other_notes_and_closes(self):
        self.backend.port.fail_note = 64
        self.play([PlaybackNote(60), PlaybackNote(64)])
        self.finish()
        self.assertEqual(self.player.status.state, "error")
        self.assertIn("Send failed", self.player.status.detail)
        self.assertIn(60, [m.note for m in self.backend.port.messages if m.type == "note_off"])
        self.assertTrue(self.backend.port.closed)

    def test_open_failure_and_missing_port(self):
        self.backend.error = OSError("Device busy")
        self.play([PlaybackNote(60)])
        self.finish()
        self.assertIn("Device busy", self.player.status.detail)

    def test_missing_port(self):
        self.backend.names = []
        self.play([PlaybackNote(60)])
        self.finish()
        self.assertEqual(self.backend.opens, 0)
        self.assertIn("unavailable", self.player.status.detail)

    def test_unplug_mid_playback_is_reported_and_cleaned_up(self):
        self.play([PlaybackNote(60, duration_beats=20)])
        wait_until(lambda: any(m.type == "note_on" for m in self.backend.port.messages))
        self.backend.names = []
        self.finish()
        self.assertIn("disconnected", self.player.status.detail)
        self.assertTrue(self.backend.port.closed)

    def test_busy_requests_are_rejected_and_close_releases_notes(self):
        self.play([PlaybackNote(60, duration_beats=20)])
        wait_until(lambda: any(m.type == "note_on" for m in self.backend.port.messages))
        with self.assertRaisesRegex(RuntimeError, "Stop"):
            self.play([PlaybackNote(64)])
        self.player.close()
        self.assertTrue(self.backend.port.closed)
        self.assertTrue(any(m.type == "note_off" for m in self.backend.port.messages))
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.play([PlaybackNote(64)])
