from pathlib import Path

from truepanel.compatibility import collect_compatibility


class FakeEnclosure:
    def __init__(
        self,
        *,
        available=True,
        slots=6,
        populated=4,
    ):
        self._available = available
        self._slots = slots
        self._populated = populated

    def enclosures(self):
        if not self._available:
            return []

        return [Path("/sys/class/enclosure/6:0:0:0")]

    def slots(self):
        return [
            object()
            for _ in range(self._slots)
        ]

    def populated_slots(self):
        return [
            object()
            for _ in range(self._populated)
        ]


def make_root(
    tmp_path,
    *,
    version="25.10.5",
    serial=True,
    vendor="INSYDE",
    product="QW56",
):
    etc = tmp_path / "etc"
    etc.mkdir()

    if version is not None:
        (etc / "version").write_text(version)

    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True)

    (dmi / "sys_vendor").write_text(vendor)
    (dmi / "product_name").write_text(product)

    dev = tmp_path / "dev"
    dev.mkdir()

    if serial:
        (dev / "ttyS1").touch()

    return tmp_path


def test_known_passive_capabilities_are_supported(
    tmp_path,
):
    root = make_root(tmp_path)

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: Path(
            "/sys/class/hwmon/hwmon10/device"
        ),
        enclosure=FakeEnclosure(),
    )

    assert report.classification == "SUPPORTED"
    assert report.installation_mode == "OBSERVATION ONLY"
    assert "LOCKED" in report.hardware_control

    identity = next(
        item
        for item in report.checks
        if item.name == "QNAP Identity"
    )

    assert identity.status == "REVIEW"


def test_qnap_dmi_identity_is_recognized(
    tmp_path,
):
    root = make_root(
        tmp_path,
        vendor="QNAP Systems, Inc.",
        product="TVS-872XT",
    )

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: None,
        enclosure=FakeEnclosure(
            available=False
        ),
    )

    identity = next(
        item
        for item in report.checks
        if item.name == "QNAP Identity"
    )

    assert identity.status == "PASS"


def test_partial_when_only_some_capabilities_exist(
    tmp_path,
):
    root = make_root(
        tmp_path,
        serial=False,
    )

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: Path(
            "/sys/class/hwmon/hwmon10/device"
        ),
        enclosure=FakeEnclosure(
            available=False
        ),
    )

    assert report.classification == "PARTIAL"


def test_missing_truenas_platform_is_unsupported(
    tmp_path,
):
    root = make_root(
        tmp_path,
        version=None,
    )

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: None,
        enclosure=FakeEnclosure(
            available=False
        ),
    )

    assert report.classification == "UNSUPPORTED"


def test_survey_always_locks_hardware_control(
    tmp_path,
):
    root = make_root(tmp_path)

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: Path(
            "/sys/class/hwmon/hwmon10/device"
        ),
        enclosure=FakeEnclosure(),
    )

    safety = next(
        item
        for item in report.checks
        if item.name == "Safety Authority"
    )

    assert safety.status == "PASS"
    assert "passive" in safety.detail
    assert "locked" in safety.detail


def test_fan_channel_inventory_reports_interfaces(
    tmp_path,
):
    root = make_root(tmp_path)

    hwmon = tmp_path / "hwmon-device"
    hwmon.mkdir()

    for name in (
        "fan1_input",
        "fan2_input",
        "pwm1",
        "pwm1_enable",
        "pwm2",
        "pwm2_enable",
    ):
        (hwmon / name).touch()

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: hwmon,
        enclosure=FakeEnclosure(),
    )

    telemetry = next(
        item
        for item in report.checks
        if item.name == "Fan Telemetry"
    )

    pwm = next(
        item
        for item in report.checks
        if item.name == "PWM Interfaces"
    )

    assert telemetry.status == "PASS"
    assert "fan1_input" in telemetry.detail
    assert "fan2_input" in telemetry.detail

    assert pwm.status == "PASS"
    assert "pwm1 + pwm1_enable" in pwm.detail
    assert "pwm2 + pwm2_enable" in pwm.detail


def test_missing_fan_inputs_prevents_full_support(
    tmp_path,
):
    root = make_root(tmp_path)

    hwmon = tmp_path / "hwmon-device"
    hwmon.mkdir()

    (hwmon / "pwm1").touch()
    (hwmon / "pwm1_enable").touch()

    report = collect_compatibility(
        root=root,
        fintek_finder=lambda: hwmon,
        enclosure=FakeEnclosure(),
    )

    assert report.classification == "PARTIAL"

    telemetry = next(
        item
        for item in report.checks
        if item.name == "Fan Telemetry"
    )

    assert telemetry.status == "REVIEW"
