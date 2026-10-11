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
    tool("stop_practice", "Stop practice and reference sound safely.", {}),
]
