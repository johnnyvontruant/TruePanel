from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "truepanel" / "web" / "server.py"


def text():
    return SERVER.read_text(encoding="utf-8")


def test_server_injects_polish_and_variant_assets_once():
    source = text()

    assert '_COCKPIT_POLISH_MARKER = b"<!-- truepanel-cockpit-polish -->"' in source
    assert 'b\'\\n<script src="/cockpit-polish.js" defer></script>\\n\'' in source
    assert '_COCKPIT_VARIANTS_MARKER = b"<!-- truepanel-cockpit-variants -->"' in source
    assert 'b\'\\n<script src="/cockpit-variants.js" defer></script>\\n\'' in source
    assert 'if _COCKPIT_POLISH_MARKER not in body:' in source
    assert 'if _COCKPIT_VARIANTS_MARKER not in body:' in source


def test_server_serves_cockpit_assets_as_static_gets():
    source = text()

    assert 'parsed.path == "/cockpit-polish.js"' in source
    assert 'self._static_script("cockpit-polish.js", "cockpit_polish_unavailable")' in source
    assert 'parsed.path == "/cockpit-variants.js"' in source
    assert 'self._static_script("cockpit-variants.js", "cockpit_variants_unavailable")' in source


def test_status_augments_storage_with_privacy_safe_bay_mirror():
    source = text()

    assert "from .bay_mirror import BayMirrorProvider" in source
    assert 'storage["bay_mirror"] = mirror' in source
    assert '"read_only_hardware": True' in source
    assert '"privacy_safe": True' in source
    assert '"bays": []' in source
    assert "self.server.bay_mirror_provider.snapshot()" in source
    assert "bay_mirror_provider=None" in source
    assert "or BayMirrorProvider()" in source


def test_bay_mirror_status_path_adds_no_write_route():
    source = text()

    status_start = source.index("    def _status(self, parsed):")
    status_end = source.index("    def _static_script", status_start)
    status = source[status_start:status_end]

    assert "do_POST" not in status
    assert "identify(" not in status
    assert "acknowledge(" not in status
    assert "fan_command" not in status
    assert "lcd_command" not in status


def test_status_localizes_drive_temperatures_to_a_physical_bay():
    source = text()

    assert "from truepanel.hardware.drive_localization import localize_drive_readings" in source
    assert 'storage["temperatures"] = localize_drive_readings(' in source
    assert "self._device_bay_map()" in source
    assert "def _device_bay_map(self)" in source
    assert "self.server.bay_mirror_provider.device_bay_map()" in source
