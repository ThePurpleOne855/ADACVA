"""Agent vertical slice uses fake models, MIDI actions and speech only."""
from fractions import Fraction as F
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from ada_piano.ai_tutor import Tutor
from ada_piano.agent.attempts import AttemptRecorder
from ada_piano.agent.coach import Coach, OpenAIClient
from ada_piano.agent.tools import AgentTools, passage_context, select_passage
from ada_piano.music_sheet import Exercise, ScoreEvent, ScoreNote
from ada_piano.sound_sensor import NoteEvent
from ada_piano.voice.system_tts import VoiceService, system_command


def exercise():
    groups = [(60,), (65,), (60, 64, 67), (62,)]
    events = tuple(ScoreEvent(F(i), tuple(ScoreNote(p, F(1)) for p in g), str(i + 5))
                   for i, g in enumerate(groups))
    return Exercise("Demo", tuple(p for e in events for p in e.pitches), events)


class Review:
    approved = True
    digest = "demo-hash"
    selection = {"start_measure": 5, "end_measure": 8}
    exercise = exercise()

    def context(self):
        if not self.approved:
            raise ValueError("Not approved")
        return {"reviewed": True, "sha256": self.digest, "title": "Demo",
                "musicxml": "private/local/path", "selection": self.selection,
                "limitations": "No rhythm grading", "rests": [],
                "events": [{"measure": e.measure, "onset": str(e.onset),
                            "tones": [{"pitch": t.pitch, "duration": str(t.duration)} for t in e.tones]}
                           for e in self.exercise.events]}


def midi(note, timestamp, kind="note_on"):
    return NoteEvent(note, 0 if kind == "note_off" else 80, timestamp, "test", kind)


def demo_attempt():
    tutor = Tutor(exercise())
    attempt = AttemptRecorder(Review().context(), started_at=0)
    sequence = [(60, .01), (60, .02, "note_off"), (66, .1), (66, .11, "note_off"),
                (66, .2), (66, .21, "note_off"), (65, .3), (65, .31, "note_off"),
                (60, .4), (64, .5), (67, .67), (60, .7, "note_off"),
                (64, .7, "note_off"), (67, .7, "note_off"),
                (60, .8), (64, .82), (67, .84), (60, .9, "note_off"),
                (64, .9, "note_off"), (67, .9, "note_off"), (62, 1)]
    for args in sequence:
        result = tutor.evaluate(midi(*args))
        if result:
            attempt.record(result)
    return attempt


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def respond(self, messages, tools):
        self.requests.append((list(messages), tools))
        return next(self.responses)


def answer(text="Try measure six next."):
    return NS(output=[], output_text=text)


def call(name, arguments):
    return NS(output=[NS(type="function_call", name=name, arguments=json.dumps(arguments), call_id="call-1")], output_text="")


class StructuredTests(unittest.TestCase):
    def test_wrong_note_metadata_and_legacy_text(self):
        tutor = Tutor(exercise())
        result = tutor.evaluate(midi(61, 14.823))
        self.assertEqual((result.type, result.measure, result.score_event_index), ("wrong_note", "5", 0))
        self.assertEqual(result.expected_pitches, (60,))
        self.assertEqual(result.played_pitches, (61,))
        self.assertEqual(result.timestamp, 14.823)
        self.assertEqual(Tutor(exercise()).observe(midi(61, 14.823)), result.message)

    def test_correct(self):
        result = Tutor(exercise()).evaluate(midi(60, 1))
        self.assertEqual(result.type, "correct")
        self.assertFalse(result.complete)

    def test_demo_repeated_error_chord_and_completion(self):
        attempt = demo_attempt()
        summary = attempt.summary()
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["events_completed"], 4)
        self.assertEqual(summary["correct_first_try"], 2)
        wrong = summary["problems"][0]
        self.assertEqual((wrong["type"], wrong["measure"], wrong["occurrences"]), ("wrong_note", "6", 2))
        self.assertEqual(wrong["event_indices"], [1, 1])
        self.assertTrue(wrong["eventually_corrected"])
        chord = next(p for p in summary["problems"] if p["type"] == "chord_attack_spread")
        self.assertAlmostEqual(chord["spread_ms"], 270)
        self.assertEqual(chord["threshold_ms"], 150)
        self.assertEqual(attempt.ended_at, 1)

    def test_stopped_attempt_not_complete(self):
        attempt = AttemptRecorder(Review().context(), started_at=0)
        attempt.finish(1)
        self.assertFalse(attempt.summary()["complete"])
        with self.assertRaises(ValueError):
            attempt.record(Tutor(exercise()).evaluate(midi(60, 2)))

    def test_save_load_and_malformed(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "attempt.json"
            demo_attempt().save(path)
            data = AttemptRecorder.load(path)
            self.assertTrue(data["summary"]["complete"])
            for value in ("bad", "[]", '{"schema_version": 99}', '{"schema_version":1,"results":[],"summary":{}}'):
                path.write_text(value)
                with self.assertRaises(ValueError):
                    AttemptRecorder.load(path)

    def test_unapproved_attempt_rejected(self):
        with self.assertRaises(ValueError):
            AttemptRecorder({"reviewed": False})

    def test_attempt_rejects_out_of_order_timestamps(self):
        attempt = AttemptRecorder(Review().context(), started_at=1)
        tutor = Tutor(exercise())
        with self.assertRaises(ValueError):
            attempt.record(tutor.evaluate(midi(61, .5)))
        attempt.record(tutor.evaluate(midi(61, 2)))
        with self.assertRaises(ValueError):
            attempt.record(tutor.evaluate(midi(61, 1.5)))


class AgentTests(unittest.TestCase):
    def test_context_sanitized_and_approval_required(self):
        data = passage_context(Review())
        self.assertNotIn("musicxml", data)
        self.assertFalse(data["calibrated_fingering_available"])
        self.assertEqual(data["events"][0]["event_index"], 0)
        review = Review()
        review.approved = False
        with self.assertRaises(ValueError):
            passage_context(review)

    def test_no_score_no_attempt(self):
        tools = AgentTools(None)
        self.assertEqual(tools.dispatch("get_current_passage", {}), {"status": "no_approved_score"})
        self.assertEqual(tools.dispatch("get_attempt_summary", {}), {"status": "no_attempt"})

    def test_latest_summary(self):
        summary = demo_attempt().summary()
        self.assertEqual(AgentTools(Review(), summary).dispatch("get_attempt_summary", {}), summary)

    def test_passage_and_action_dispatch(self):
        actions = []
        tools = AgentTools(Review(), action=lambda name, args: actions.append((name, args)) or {"status": "queued"})
        self.assertEqual(select_passage(Review(), "6", "6").notes, (65,))
        self.assertEqual(select_passage(Review(), "6", "6").events[0].onset, 0)
        for name, args in [("play_reference", {"start_measure": "6", "end_measure": "6", "tempo": 60}),
                           ("start_practice", {"start_measure": "6", "end_measure": "6"}), ("stop_practice", {})]:
            self.assertEqual(tools.dispatch(name, args)["status"], "queued")
        self.assertEqual(len(actions), 3)

    def test_forbidden_and_invalid_actions(self):
        tools = AgentTools(Review(), action=lambda *args: self.fail("Invalid action executed"))
        for name, args in [("shell", {}), ("send_midi", {"note": 60}), ("load_file", {"path": "/etc/passwd"}),
            ("get_current_passage", {"path": "x"}), ("start_practice", {"start_measure": "4", "end_measure": "6"}),
            ("start_practice", {"start_measure": "8", "end_measure": "6"}),
            ("play_reference", {"start_measure": "6", "end_measure": "6", "tempo": True}),
            ("play_reference", {"start_measure": "6", "end_measure": "6", "tempo": 301}),
            ("play_reference", {"start_measure": "6", "end_measure": "6", "tempo": float("nan")})]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                tools.dispatch(name, args)

    def test_fake_responses_loop_and_rejected_tool(self):
        client = FakeClient([call("get_attempt_summary", {}), call("shell", {}), answer()])
        coach = Coach(AgentTools(Review(), demo_attempt().summary()), client)
        self.assertIn("six", coach.ask("What should I practice?"))
        self.assertIn("rejected", client.requests[-1][0][-1]["output"])
        self.assertNotIn("private/local/path", str(client.requests))

    def test_cancel_and_tool_limit(self):
        token = Event()
        token.set()
        self.assertEqual(Coach(AgentTools(None), FakeClient([])).ask("Hello", token), "")
        with self.assertRaises(RuntimeError):
            Coach(AgentTools(None), FakeClient([call("get_attempt_summary", {})] * 6)).ask("Hi")

    def test_missing_key_and_network_failure(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
            OpenAIClient()
        tutor = Tutor(exercise())
        client = NS(respond=lambda *args: (_ for _ in ()).throw(OSError("offline")))
        with self.assertRaises(OSError):
            Coach(AgentTools(Review()), client).ask("Help")
        self.assertIn("Correct", tutor.observe(midi(60, 1)))

    def test_responses_adapter_configuration_without_network(self):
        sdk = NS(OpenAI=unittest.mock.Mock())
        with patch.dict("sys.modules", {"openai": sdk}), patch.dict("os.environ", {"OPENAI_API_KEY": "test-only-not-a-key", "ADA_OPENAI_MODEL": "configured-model"}):
            client = OpenAIClient()
            client.respond([], [])
        request = sdk.OpenAI.return_value.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "configured-model")
        self.assertFalse(request["store"])
        self.assertFalse(request["parallel_tool_calls"])
        self.assertIn("instructions", request)

    def test_reference_duration_limits_still_enforced(self):
        review = Review()
        event = ScoreEvent(F(0), (ScoreNote(60, F(101)),), "5")
        review.exercise = Exercise("Long", (60,), (event,))
        with self.assertRaises(ValueError):
            AgentTools(review).dispatch("play_reference", {"start_measure": "5", "end_measure": "5", "tempo": 20})


class VoiceTests(unittest.TestCase):
    def test_missing_engine(self):
        voice = VoiceService(command=[])
        self.addCleanup(voice.close)
        self.assertFalse(voice.available)
        self.assertTrue(voice.say("Hello").is_set())

    def test_worker_queue_replacement_and_cleanup(self):
        started, release = Event(), Event()
        calls = []
        main_thread = get_ident()

        class Process:
            returncode = 0
            def communicate(self, input=None, timeout=None):
                calls.append((input, get_ident()))
                started.set()
                release.wait(1)
            def terminate(self):
                release.set()
            def kill(self):
                release.set()

        voice = VoiceService(command=["fake"], popen=lambda *a, **kw: Process())
        first = voice.say("old")
        self.assertTrue(started.wait(1))
        second = voice.say("queued", replace=False)
        third = voice.say("latest")
        self.assertTrue(second.wait(1))
        self.assertTrue(third.wait(1))
        voice.close()
        self.assertTrue(first.is_set())
        self.assertFalse(voice._thread.is_alive())
        self.assertTrue(all(t != main_thread for _, t in calls))
        self.assertNotIn(b"queued", [t for t, _ in calls])

    def test_crashed_engine_falls_back(self):
        voice = VoiceService(command=["fake"], popen=lambda *a, **kw: (_ for _ in ()).throw(OSError()))
        self.addCleanup(voice.close)
        self.assertTrue(voice.say("Hello").wait(1))
        self.assertFalse(voice.available)
        self.assertIn("text mode", voice.status)

    def test_platform_detection(self):
        with patch("ada_piano.voice.system_tts.shutil.which", return_value=None):
            self.assertIsNone(system_command())
