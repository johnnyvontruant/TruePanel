"""LCD runtime entry-path contracts."""

from pathlib import Path


def test_cli_resolves_lcd_menu_from_project_root():
    source = Path("truepanel/cli.py").read_text(
        encoding="utf-8",
    )

    assert "Path(__file__).resolve().parents[1]" in source
    assert '/ "lcd-menu.py"' in source
    assert 'runpy.run_path("lcd-menu.py"' not in source
