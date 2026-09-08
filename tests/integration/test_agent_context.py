from services.api.agent.context import take_context


def test_creative_context_keeps_dialogue_and_cuts_without_clock_payloads():
    take = {"id": "take", "duration": 30, "source_offsets": {"a": .5},
            "frame_read_batches": [{"packet": "large audit payload"}] * 180,
            "monitor_observations": ["audit only"], "alignment": {"frames": [1] * 1800},
            "decisions": [{"camera": "a", "time": n} for n in range(50)],
            "transcripts": [{"text": "Actual dialogue", "audio_end": 2, "words": ["raw"]}]*25,
            "edits": [{"id": str(n), "status": "READY", "segments": [], "output": {"debug": "large"}} for n in range(10)]}
    result = take_context(take)
    assert result["id"] == "take" and result["source_offsets"] == {"a": .5}
    assert not {"frame_read_batches", "monitor_observations", "alignment"} & result.keys()
    assert len(result["decisions"]) == 40 and len(result["transcripts"]) == 20
    assert "words" not in result["transcripts"][0]
    assert len(result["edits"]) == 8 and "output" not in result["edits"][0]
    assert len(take["frame_read_batches"]) == 180
    assert take_context(None) is None
