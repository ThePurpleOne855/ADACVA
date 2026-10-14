"""Spoken controls and calibrated hand evidence, without hardware or a cloud call."""
import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from ada_piano import pieces
from .coach import Coach
from .local_commands import parse
from .tools import AgentTools


class ControlTests(unittest.TestCase):
    def test_control_arguments_from_digits_and_spoken_numbers(self):
        cases = {
            "ADA, list MIDI inputs": ("midi_list", {"direction": "input"}),
            "select MIDI output number two": ("midi_select", {"direction": "output", "selection": "2"}),
            "select input USB MIDI": ("midi_select", {"direction": "input", "selection": "usb midi"}),
            "select camera one": ("camera_select", {"selection": "1"}),
            "tempo sixty five": ("tempo", {"value": 65}),
            "set tempo to one hundred and twenty bpm": ("tempo", {"value": 120}),
            "tempo 500": ("tempo", {"value": 500}),
            "slower": ("tempo", {"delta": -10}),
            "measures two to fifteen": ("passage", {"start_measure": "2", "end_measure": "15"}),
            "practice measure 3": ("guided_passage", {"start_measure": "3", "end_measure": "3"}),
            "left hand": ("hands", {"hands": "left"}),
            "use both hands": ("hands", {"hands": "both"}),
            "stop listening": ("listening", {"enabled": False}),
            "show tools": ("show_tools", {"visible": True}),
            "speech speed 0.85": ("speech_speed", {"value": .85}),
            "use natural offline voice": ("voice_select", {"selection": "natural offline"}),
            "import score number two": ("import_score", {"selection": "2"}),
            "import score /tmp/My Score.musicxml": ("import_score", {"selection": "/tmp/My Score.musicxml"}),
            "select camera rtsp://192.168.1.5:8554/video": ("camera_select", {"selection": "rtsp://192.168.1.5:8554/video"}),
            "select score staff all": ("score_select", {"field": "staff", "selection": "all"}),
            "calibrate left hand": ("calibrate", {"hand": "left"}),
        }
        for words, result in cases.items():
            with self.subTest(words=words):
                self.assertEqual(parse(words, []), result)

    def test_actions_and_questions_are_distinct(self):
        catalog = pieces.catalog()
        for command in ("status", "calibrate hands", "calibration done", "reset calibration",
                        "hand report", "guided practice", "save session", "quit", "list voices",
                        "list score files", "read score", "next measure", "approve passage", "cancel import"):
            with self.subTest(command=command):
                self.assertIsNotNone(parse(command, catalog))
        for question in ("How do I calibrate hands?", "Which tempo should I use?",
                         "Explain MIDI inputs", "What is the best voice?", "Why did I stop?",
                         "Can you help with measure three in the left hand?"):
            with self.subTest(question=question):
                self.assertIsNone(parse(question, catalog))
        self.assertEqual(parse("ADA practice Fur Elise theme right hand", catalog)[0], "load")

    def test_hand_evidence_is_included_and_missing_evidence_is_explicit(self):
        absent = AgentTools(None).dispatch("get_hand_summary", {})
        self.assertEqual(absent["status"], "no_hand_evidence")
        hands = {"status": "calibrated", "matched": 4, "unmatched": 2,
                 "limitations": "Inferred associations, not confirmed fingering."}
        tools = AgentTools(None, hands=hands)
        self.assertEqual(tools.dispatch("get_hand_summary", {}), hands)
        with self.assertRaises(ValueError):
            tools.dispatch("get_hand_summary", {"invent": True})
        client = NS(respond=Mock(return_value=NS(output=[], output_text="Four notes have camera associations.")))
        Coach(tools, client).ask("How were my hands?")
        evidence = client.respond.call_args.args[0][-1]["content"].split(": ", 1)[1]
        self.assertEqual(json.loads(evidence)["hands"], hands)


if __name__ == "__main__":
    unittest.main()
