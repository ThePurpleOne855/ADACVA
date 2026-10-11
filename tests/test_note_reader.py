from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ada_piano.note_reader import NoteReader, NoteState


def note(kind="note_on", number=60, velocity=80, channel=0):
    return SimpleNamespace(type=kind, note=number, velocity=velocity, channel=channel)


def control(number, value=0, channel=0):
    return SimpleNamespace(type="control_change", control=number, value=value, channel=channel)


class FakePort:
    def __init__(self):
        self.messages = deque()
        self.closed = False
        self.close_count = 0
        self.error = None

    def poll(self):
        if self.error:
            raise self.error
        return self.messages.popleft() if self.messages else None

    def close(self):
        self.closed = True
        self.close_count += 1


class FakeBackend:
    def __init__(self):
        self.names = ["USB MIDI"]
        self.ports = []
        self.error = None

    def get_input_names(self):
        return list(self.names)

    def open_input(self, name):
        if self.error:
            raise self.error
        port = FakePort()
        self.ports.append(port)
        return port


class NoteStateTests(unittest.TestCase):
    def test_duration_pairs_notes_and_channels_with_both_release_formats(self):
        state = NoteState()
        with patch("ada_piano.note_reader.monotonic", side_effect=[10, 10.25, 10.5, 11, 12, 13]):
            self.assertIsNone(state.consume(note()).duration)
            state.consume(note(number=64))
            state.consume(note(channel=1))
            self.assertEqual(state.consume(note("note_off")).duration, 1)
            self.assertEqual(state.consume(note(number=64, velocity=0)).duration, 1.75)
            self.assertEqual(state.consume(note("note_off", channel=1)).duration, 2.5)

    def test_duration_ends_at_release_even_with_sustain(self):
        state = NoteState()
        state.consume(control(64, 127))
        with patch("ada_piano.note_reader.monotonic", side_effect=[0, 0.5]):
            state.consume(note())
            self.assertEqual(state.consume(note("note_off")).duration, 0.5)
        self.assertEqual(state.sustain, {1})

    def test_duration_is_unknown_after_reset_or_unmatched_release(self):
        state = NoteState()
        self.assertIsNone(state.consume(note("note_off")).duration)
        for reset in (SimpleNamespace(type="reset"), control(120), control(123)):
            with self.subTest(reset=reset):
                state.consume(note())
                state.consume(note(channel=1))
                state.consume(reset)
                self.assertIsNone(state.consume(note("note_off")).duration)
                other = state.consume(note("note_off", channel=1))
                if reset.type != "reset":
                    self.assertIsNotNone(other.duration)
        state.consume(note())
        state.reset()
        self.assertIsNone(state.consume(note("note_off")).duration)

    def test_repeated_press_restarts_duration(self):
        state = NoteState()
        with patch("ada_piano.note_reader.monotonic", side_effect=[1, 2, 2.75]):
            state.consume(note())
            state.consume(note())
            self.assertEqual(state.consume(note("note_off")).duration, 0.75)

    def test_chord_and_both_release_encodings(self):
        state = NoteState()
        for number in (60, 64, 67):
            event = state.consume(note(number=number))
            self.assertEqual(event.kind, "on")
        self.assertEqual(event.channel, 1)
        self.assertEqual(state.note_count, 3)
        self.assertEqual(len(state.held), 3)
        self.assertEqual(state.consume(note(velocity=0)).kind, "off")
        self.assertEqual(state.consume(note("note_off", 64)).kind, "off")
        state.consume(note("note_off", 67))
        self.assertFalse(state.held)
        self.assertEqual(state.note_count, 3)

    def test_same_pitch_on_separate_channels_and_midi_bounds(self):
        state = NoteState()
        self.assertEqual(state.consume(note(number=0)).name, "C-1")
        self.assertEqual(state.consume(note(number=127, channel=15)).name, "G9")
        state.consume(note(channel=0))
        state.consume(note(channel=1))
        state.consume(note("note_off", channel=0))
        self.assertIn((2, 60), state.held)
        self.assertNotIn((1, 60), state.held)

    def test_sustain_does_not_keep_released_keys_held(self):
        state = NoteState()
        state.consume(control(64, 127))
        state.consume(note())
        state.consume(note("note_off"))
        self.assertFalse(state.held)
        self.assertEqual(state.sustain, {1})
        state.consume(control(64, 63))
        self.assertFalse(state.sustain)

    def test_channel_reset_and_system_reset(self):
        for controller in (120, 123):
            with self.subTest(controller=controller):
                state = NoteState()
                state.consume(note())
                state.consume(note(channel=1))
                state.consume(control(controller))
                self.assertEqual(state.held, {(2, 60): 80})
                state.consume(control(64, 127, channel=1))
                state.consume(control(121, channel=1))
                self.assertFalse(state.sustain)
                state.consume(SimpleNamespace(type="reset"))
                self.assertFalse(state.held)
                self.assertEqual(state.note_count, 0)

    def test_other_messages_and_unmatched_releases(self):
        state = NoteState()
        for kind in ("clock", "sysex", "pitchwheel", "active_sensing"):
            self.assertIsNone(state.consume(SimpleNamespace(type=kind)))
        state.consume(note("note_off"))
        self.assertFalse(state.held)


class NoteReaderTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.reader = NoteReader(self.backend)

    def test_poll_and_disconnect_cleanup(self):
        self.reader.connect("USB MIDI")
        port = self.backend.ports[-1]
        port.messages.extend([note(), control(64, 127), note(number=64)])
        self.assertEqual([event.note for event in self.reader.poll()], [60, 64])
        self.assertEqual(self.reader.state.sustain, {1})
        self.reader.disconnect()
        self.reader.disconnect()
        self.assertEqual(port.close_count, 1)
        self.assertFalse(self.reader.state.held)
        self.assertFalse(self.reader.state.sustain)
        self.assertFalse(self.reader.connected)
        self.assertEqual(self.reader.poll(), [])

    def test_invalid_port_and_failed_open(self):
        with self.assertRaises(ValueError):
            self.reader.connect("")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.reader.connect("Missing")
        self.backend.error = OSError("Device busy")
        with self.assertRaisesRegex(OSError, "Device busy"):
            self.reader.connect("USB MIDI")
        self.assertFalse(self.reader.connected)

    def test_reconnect_closes_old_port(self):
        self.reader.connect("USB MIDI")
        first = self.backend.ports[-1]
        self.reader.state.consume(note())
        self.reader.connect("USB MIDI")
        self.assertTrue(first.closed)
        self.assertFalse(self.reader.state.held)
        self.assertTrue(self.reader.connected)

    def test_unplug_detected_even_when_port_not_marked_closed(self):
        self.reader.connect("USB MIDI")
        port = self.backend.ports[-1]
        self.reader.state.consume(note())
        self.backend.names = []
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            self.reader.check_connection()
        self.assertTrue(port.closed)
        self.assertFalse(self.reader.state.held)

    def test_poll_error_cleans_up(self):
        self.reader.connect("USB MIDI")
        port = self.backend.ports[-1]
        port.error = OSError("Device lost")
        with self.assertRaisesRegex(OSError, "Device lost"):
            self.reader.poll()
        self.assertTrue(port.closed)
        self.assertFalse(self.reader.connected)

    def test_poll_bounds_work_even_with_non_note_messages(self):
        self.reader.connect("USB MIDI")
        port = self.backend.ports[-1]
        port.messages.extend([SimpleNamespace(type="clock") for _ in range(300)])
        port.messages.append(note())
        self.assertEqual(self.reader.poll(), [])
        self.assertEqual(len(port.messages), 45)
        self.assertEqual(len(self.reader.poll()), 1)

    def test_activity_counts_non_note_messages_and_resets_on_reconnect(self):
        self.reader.connect("USB MIDI")
        self.backend.ports[-1].messages.extend([control(64, 127), note()])
        self.reader.poll()
        self.assertEqual(self.reader.message_count, 2)
        self.assertEqual(self.reader.last_message, "note_on")
        self.assertGreaterEqual(self.reader.last_received, self.reader.connected_at)
        self.reader.connect("USB MIDI")
        self.assertEqual(self.reader.message_count, 0)
        self.assertIsNone(self.reader.last_received)


if __name__ == "__main__":
    unittest.main()
