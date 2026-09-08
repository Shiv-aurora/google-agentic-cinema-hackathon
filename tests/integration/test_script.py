from services.api.agent.script import ScriptFollower, script_lines
from services.api.store import SCRIPT


def test_script_alignment_nearby_and_uncertainty():
    follower = ScriptFollower(SCRIPT)
    assert len(script_lines(SCRIPT)) == 6
    assert follower.observe("some unrelated production noise") is None
    assert follower.observe("I never sent it") is None  # No unexplained jump to reveal.
    assert follower.observe("you kept the ticket")["id"] == 0
    assert follower.observe("I thought you might come back for it")["id"] == 1
    assert follower.observe("it's been three years")["id"] == 2
    assert follower.observe("I know how long it's been")["id"] == 3
    assert follower.observe("the letter never reached me")["id"] == 4
    assert follower.observe("I never sent it")["id"] == 5
    assert not follower.observe("I never sent it")["changed"]
