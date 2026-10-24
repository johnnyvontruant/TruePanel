"""Single-use physical authorization token security regressions."""
from truepanel.loadmaster.host_token import TokenVerifier, issue


def test_valid_token_is_single_use():
    key = b"k" * 32
    token = issue(key, "a" * 64, "6ADA-80D5", "serial", now=100)
    verifier = TokenVerifier(key)
    assert verifier.consume("a" * 64, "6ADA-80D5", "serial", token, now=101)
    assert not verifier.consume("a" * 64, "6ADA-80D5", "serial", token, now=102)


def test_expiry_and_future_issuance_are_rejected():
    key = b"k" * 32
    token = issue(key, "a" * 64, "6ADA-80D5", "serial", now=100)
    assert not TokenVerifier(key).consume("a" * 64, "6ADA-80D5", "serial", token, now=111)
    assert not TokenVerifier(key).consume("a" * 64, "6ADA-80D5", "serial", token, now=99)


def test_token_bound_to_plan_uuid_and_serial():
    key = b"k" * 32
    token = issue(key, "a" * 64, "6ADA-80D5", "serial", now=100)
    verifier = TokenVerifier(key)
    assert not verifier.consume("b" * 64, "6ADA-80D5", "serial", token, now=100)
    assert not verifier.consume("a" * 64, "OTHER", "serial", token, now=100)
    assert not verifier.consume("a" * 64, "6ADA-80D5", "OTHER", token, now=100)
    assert verifier.consume("a" * 64, "6ADA-80D5", "serial", token, now=100)


def test_wrong_key_or_malformed_payload_rejected():
    token = issue(b"k" * 32, "a" * 64, "drive", "serial", now=100)
    assert not TokenVerifier(b"x" * 32).consume("a" * 64, "drive", "serial", token, now=100)
    assert not TokenVerifier(b"k" * 32).consume("a" * 64, "drive", "serial", {}, now=100)


def test_host_request_requires_token():
    from truepanel.loadmaster.link import validate
    _, result = validate({"action":"start","source":"host",
                          "digest":"a"*64, "confirm":True})
    assert result["ok"] is False
    assert result["status"] == "invalid"
