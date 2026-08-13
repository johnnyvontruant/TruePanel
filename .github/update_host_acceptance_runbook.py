from pathlib import Path


doc = Path("docs/CLEAN_INSTALL_VALIDATION.md")
text = doc.read_text(encoding="utf-8")

fan = (
    "sudo ./bin/truepanel host fan-safety \\\n"
    "  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml\n"
)
acceptance = (
    "sudo ./bin/truepanel host acceptance \\\n"
    "  --root / \\\n"
    "  --config /mnt/POOL/DATASET/TruePanel/truepanel.yaml\n"
)

assert text.count(fan) >= 3
text = text.replace(fan, fan + acceptance, 3)

old = (
    "- `host fan-safety` confirms motherboard Automatic mode when fan control is enabled;\n"
    "- `host cutover-plan` reports `Cutover execution: DISABLED`.\n"
)
new = (
    "- `host fan-safety` confirms motherboard Automatic mode when fan control is enabled;\n"
    "- `host acceptance` reports `Host acceptance: PASS`;\n"
    "- `host cutover-plan` reports `Cutover execution: DISABLED`.\n"
)
assert text.count(old) == 1
text = text.replace(old, new, 1)

old = "- Host readiness result;\n- fan-safety result;\n"
new = (
    "- Host readiness result;\n"
    "- fan-safety result;\n"
    "- Host acceptance result;\n"
)
assert text.count(old) == 1
text = text.replace(old, new, 1)

doc.write_text(text, encoding="utf-8")


test = Path("tests/test_clean_install_documentation.py")
test_text = test.read_text(encoding="utf-8")
addition = '''\n\ndef test_clean_install_runbook_uses_host_acceptance_gate():\n    text = read(RUNBOOK)\n\n    assert text.count("host acceptance") >= 4\n    assert "Host acceptance: PASS" in text\n    assert "Host acceptance result" in text\n'''
assert "def test_clean_install_runbook_uses_host_acceptance_gate():" not in test_text
test.write_text(test_text.rstrip() + addition + "\n", encoding="utf-8")
