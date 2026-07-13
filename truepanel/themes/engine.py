"""
TruePanel Theme Engine 2.0.

Theme packs are YAML configuration layers with metadata, display vocabulary,
bar characters, startup language, and alert presentation.
"""

from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None


PACKS_DIR = Path(__file__).resolve().parent / "packs"


@dataclass(frozen=True)
class ThemePack:
    pack_id: str
    name: str
    description: str
    author: str
    version: str
    data: dict
    path: Path

    @property
    def theme(self):
        return self.data.get("theme", {})

    @property
    def graphics(self):
        return self.data.get("graphics", {})


def safe_pack_id(value):
    value = str(value or "").strip().lower()
    return "".join(char for char in value if char.isalnum() or char in "-_")


def pack_path(pack_id):
    return PACKS_DIR / f"{safe_pack_id(pack_id)}.yaml"


def load_yaml(path):
    if yaml is None or not path.exists():
        return {}

    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def load_theme_pack(pack_id):
    pack_id = safe_pack_id(pack_id) or "default"
    path = pack_path(pack_id)
    data = load_yaml(path)

    if not data:
        return None

    metadata = data.get("metadata", {})

    return ThemePack(
        pack_id=pack_id,
        name=str(metadata.get("name", pack_id.replace("-", " ").title())),
        description=str(metadata.get("description", "")),
        author=str(metadata.get("author", "TruePanel")),
        version=str(metadata.get("version", "1.0")),
        data=data,
        path=path,
    )


def discover_theme_packs():
    packs = []

    if not PACKS_DIR.exists():
        return packs

    for path in sorted(PACKS_DIR.glob("*.yaml")):
        pack = load_theme_pack(path.stem)

        if pack is not None:
            packs.append(pack)

    return packs


def validate_theme_pack(pack):
    errors = []

    if pack is None:
        return ["Theme pack could not be loaded"]

    if not pack.name:
        errors.append("metadata.name is required")

    graphics = pack.graphics

    for key in ("filled", "empty", "healthy", "warning", "critical"):
        value = graphics.get(key)

        if value is not None and len(str(value)) != 1:
            errors.append(f"graphics.{key} must be one character")

    return errors


class Theme:
    def __init__(self, config=None):
        self.config = config or {}
        self.values = self.config.get("theme", {})
        self.graphics = self.config.get("graphics", {})

    def text(self, key, default=""):
        return str(self.values.get(key, default))

    def glyph(self, key, default="?"):
        value = str(self.graphics.get(key, default))
        return value[:1] if value else default

    def bar(self, percent, width=16):
        try:
            percent = max(0.0, min(100.0, float(percent)))
        except (TypeError, ValueError):
            percent = 0.0

        width = max(1, int(width))
        filled_count = int(round(width * percent / 100.0))

        return (
            self.glyph("filled", "#") * filled_count
            + self.glyph("empty", "-") * (width - filled_count)
        )[:width]

    def status(self, priority):
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 0

        if priority >= 100:
            return self.glyph("critical", "X")
        if priority >= 70:
            return self.glyph("warning", "!")
        if priority >= 40:
            return self.glyph("info", "i")

        return self.glyph("healthy", "O")
