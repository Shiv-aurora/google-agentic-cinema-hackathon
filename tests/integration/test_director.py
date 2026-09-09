import json

import pytest

from services.api.agent.director import coverage_requirements, validate_proposal
from services.api.agent.director import generation_config, LiveProposal
from services.api.agent.styles import DIRECTING_PRESETS, directing_style
from google.adk.agents import Agent
from services.api.agent.voice import VoiceIntent


def test_exact_percentage_requirement_rounds_up_to_frames():
    note = "Create a Bella-focused version. Give camera b at least 75% of the whole take."
    assert coverage_requirements(note, 136) == {"b": 102}
    assert coverage_requirements("Bella at least 75%", 137) == {"b": 103}
    with pytest.raises(ValueError):
        coverage_requirements("camera a at least 60%. camera b at least 60%.", 100)


def test_rejects_a_renderable_edit_that_misses_direction():
    proposal = {"name": "Bella", "explanation": "Her reaction", "segments": [
        {"camera": "c", "start_frame": 0, "end_frame": 36, "reason": "Establish"},
        {"camera": "b", "start_frame": 36, "end_frame": 136, "reason": "Hold reaction"},
    ]}
    with pytest.raises(ValueError, match="needs at least 102 frames"):
        validate_proposal(json.dumps(proposal), 136/30, {"b": 102})
    proposal["segments"][0]["end_frame"] = proposal["segments"][1]["start_frame"] = 34
    result = validate_proposal(json.dumps(proposal), 136/30, {"b": 102})
    assert result["segments"][1]["end"] == 136/30


def test_endpoint_correction_reports_exact_frames_not_rounded_seconds():
    proposal = {"name": "Bella", "explanation": "Hold", "segments": [
        {"camera": "b", "start_frame": 0, "end_frame": 39, "reason": "Hold"}]}
    with pytest.raises(ValueError, match="end at frame 1183, not 39"):
        validate_proposal(json.dumps(proposal), 1183/30, {"b": 888})


def test_live_schema_uses_adk_agent_field_not_generation_config():
    agent = Agent(name="test_live", model="gemini-2.5-flash-lite", tools=[],
                  output_schema=LiveProposal, generate_content_config=generation_config(True))
    assert agent.output_schema is LiveProposal
    assert agent.generate_content_config.response_schema is None
    assert agent.generate_content_config.max_output_tokens == 512


def test_directing_presets_are_bounded_and_fall_back_safely():
    assert set(DIRECTING_PRESETS) == {"classic", "reaction", "patient", "tension"}
    assert DIRECTING_PRESETS["tension"]["minimum_hold"] < DIRECTING_PRESETS["patient"]["minimum_hold"]
    assert directing_style({"directing_preset": "reaction"})[0] == "reaction"
    key, style = directing_style({"directing_preset": "unknown"})
    assert key == "classic"
    assert style == DIRECTING_PRESETS["classic"]


def test_voice_can_carry_a_creative_live_direction():
    intent = VoiceIntent(kind="direct", preset="tension", explanation="Use the rising tension preset")
    assert intent.kind == "direct"
    assert intent.preset == "tension"
