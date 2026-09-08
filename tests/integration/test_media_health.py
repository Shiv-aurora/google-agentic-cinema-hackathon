from services.media.hub import recording_coverage


def test_fragments_and_observed_dropouts_do_not_claim_complete_coverage():
    recordings = {"a": [{"duration": 4}], "b": [{"duration": 6}, {"duration": 4}], "c": [{"duration": 10}]}
    assert recording_coverage(recordings, 10) == {"a": False, "b": True, "c": True}
    assert recording_coverage(recordings, 10, ["b"]) == {"a": False, "b": False, "c": True}
    assert recording_coverage({}, 10) == {"a": False, "b": False, "c": False}
