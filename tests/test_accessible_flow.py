"""Voice-first flow: load a checked piece by name, record, get measured feedback."""
import json
import unittest
from unittest.mock import patch

import test_note_reader_gui as existing
from test_agent import FakeClient, answer, call
from test_agent_gui import FakeVoice
from test_note_reader import note

from ada_piano import pieces
from ada_piano.agent.tools import AgentTools

ODE = [64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 64, 62, 62,
       64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 62, 60, 60]


@unittest.skipIf(existing.tk is None, "Tk unavailable")
class AccessibleFlowTests(unittest.TestCase):
    setUp = existing.NoteReaderGuiTests.setUp
    close_window = existing.NoteReaderGuiTests.close_window
    run_gui = existing.NoteReaderGuiTests.run_gui

    def panel(self, client=None):
        coach = self.window.coach
        coach.voice.close()
        coach.voice = FakeVoice()
        coach.client = client
        coach.speak.set(True)
        return coach

    def say(self, coach, text):
        coach.text.set(text)
        coach.ask()

    def play(self, pitches, wrong=None):
        port = self.backend.ports[-1]
        for index, pitch in enumerate(pitches):
            pitch = wrong.get(index, pitch) if wrong else pitch
            port.messages.extend([note(number=pitch), note("note_off", number=pitch)])
        self.run_gui(120)

    def test_offline_voice_flow_without_api(self):
        coach = self.panel()
        with patch.dict("os.environ", {}, clear=True):
            self.say(coach, "ADA practice ode to joy".removeprefix("ADA "))
            self.assertEqual(self.window.score.loaded.piece["id"], "ode_to_joy")
            self.assertIn("Loaded Ode to Joy", coach.voice.messages[-1])
            self.say(coach, "record")
            self.assertIsNotNone(self.window.score.take)
            self.play(ODE, wrong={5: 66})
            self.say(coach, "How did I do?")
        self.assertIsNone(self.window.score.take)
        report = self.window.score.performance_summary()
        self.assertEqual((report["correct"], report["wrong"], report["notes_expected"]), (29, 1, 30))
        self.assertIn("29 of 30 notes correct", coach.voice.messages[-1])
        self.assertIn("measure 2", coach.voice.messages[-1])

    def test_silence_ends_take_and_reference_is_not_recorded(self):
        coach = self.panel()
        self.say(coach, "practice fur elise theme right hand")
        self.assertEqual(self.window.score.loaded.selection["staff"], "1")
        self.window.score.play_through()
        self.play([76, 75])
        with patch("ada_piano.score_import.gui.monotonic", return_value=10 ** 6):
            self.run_gui(200)
        self.assertIsNone(self.window.score.take)
        self.assertFalse(self.window.score.performance_summary()["complete"])

    def test_unknown_piece_and_unsupported_hand_are_spoken(self):
        coach = self.panel()
        self.say(coach, "ode to joy left hand")
        self.assertIn("supports: right", coach.voice.messages[-1])
        self.assertIsNone(self.window.score.loaded)

    def test_coach_can_load_piece_then_start_play_through(self):
        client = FakeClient([call("load_piece", {"piece": "Für Elise", "passage": "theme", "hands": ""}),
                             call("start_play_through", {"start_measure": "1", "end_measure": "2"}),
                             answer("Recording measures one and two. Off you go.")])
        coach = self.panel(client)
        self.say(coach, "I'd like to work on the beginning of that Beethoven piece")
        self.run_gui(300)
        self.assertEqual(self.window.score.loaded.piece["passage"], "theme")
        self.assertIsNotNone(self.window.score.take)
        self.assertEqual({e.measure for e in self.window.score.take_exercise.events}, {"1", "2"})
        self.assertIn("Off you go", coach.transcript.get("1.0", "end"))
        outputs = [json.loads(m["output"]) for m in client.requests[-1][0]
                   if isinstance(m, dict) and m.get("type") == "function_call_output"]
        self.assertEqual(outputs[0]["status"], "loaded")
        self.assertNotIn("_review", outputs[0])
        self.assertEqual(outputs[1]["status"], "recording")

    def test_report_reaches_model_evidence(self):
        coach = self.panel(FakeClient([answer("Measure two: F, not F sharp.")]))
        self.window.score.load_piece("ode to joy")
        self.window.score.play_through()
        self.play(ODE, wrong={5: 66})
        self.window.score.finish_take()
        self.say(coach, "What should I fix first?")
        self.run_gui(200)
        evidence = [m for m in coach.client.requests[0][0] if m.get("role") == "developer"][0]["content"]
        self.assertIn('"wrong": 1', evidence)
        self.assertIn("F sharp4", evidence)


class ToolTests(unittest.TestCase):
    def test_list_and_validated_load(self):
        actions = []
        review = pieces.load(pieces.find("ode"))
        def action(name, args):
            actions.append((name, args))
            return {"status": "loaded", "_review": review}
        tools = AgentTools(None, action=action)
        titles = [p["title"] for p in tools.dispatch("list_pieces", {})["pieces"]]
        self.assertIn("Ode to Joy", titles)
        self.assertEqual(tools.dispatch("get_performance_report", {}), {"status": "no_play_through"})
        with self.assertRaises(ValueError):
            tools.dispatch("load_piece", {"piece": "/etc/passwd", "passage": "", "hands": ""})
        with self.assertRaises(ValueError):
            tools.dispatch("load_piece", {"piece": "ode", "passage": "chorus", "hands": ""})
        self.assertEqual(tools.dispatch("load_piece", {"piece": "ode to joy", "passage": "", "hands": ""}),
                         {"status": "loaded"})
        self.assertEqual(actions, [("load_piece", {"piece": "ode_to_joy", "passage": "whole", "hands": "right"})])
        self.assertIs(tools.review, review)
        self.assertTrue(tools.dispatch("get_current_passage", {})["title"].startswith("Ode to Joy"))


if __name__ == "__main__":
    unittest.main()
