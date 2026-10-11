"""Strict Responses function schemas; runtime validation is still mandatory."""


def tool(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties), "additionalProperties": False}}


MEASURES = {"start_measure": {"type": "string"}, "end_measure": {"type": "string"}}
TOOLS = [
    tool("get_current_passage", "Read only the approved score passage and its limitations.", {}),
    tool("get_attempt_summary", "Read measured performance facts, or a no-attempt result.", {}),
    tool("play_reference", "Request approved measures at a safe tempo. Application announces before sound.",
         {**MEASURES, "tempo": {"type": "number", "minimum": 20, "maximum": 300}}),
    tool("start_practice", "Start guided pitch/chord practice on approved measure labels, after reference ends.", MEASURES),
    tool("stop_practice", "Stop practice, recording and reference sound safely.", {}),
    tool("list_pieces", "List the pre-checked pieces, passages and hands that can be loaded by name.", {}),
    tool("load_piece", "Load a pre-checked piece by title. Use empty strings for the default passage (whole) and hands.",
         {"piece": {"type": "string"}, "passage": {"type": "string"}, "hands": {"type": "string"}}),
    tool("start_play_through", "Record an uninterrupted play-through of approved measures; scored when the learner stops.", MEASURES),
    tool("get_performance_report", "Read the latest measured play-through report for the loaded passage.", {}),
    tool("play_notes", "Play up to 16 notes on the piano, as a melody or one chord, to demonstrate pitches, intervals or a chord.",
         {"notes": {"type": "string", "description": "Space-separated notes like 'C4 E4 G4' or 'F#4'"},
          "chord": {"type": "boolean"}, "tempo": {"type": "number", "minimum": 30, "maximum": 200}}),
    tool("replay_my_playing", "Play back the learner's own latest play-through of the loaded passage, so they can hear it.", {}),
]
