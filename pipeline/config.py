"""Config overlay system: immutable preset + user overrides."""
from __future__ import annotations
import copy
from pathlib import Path
import yaml
from pipeline.paths import config_file as _config_file_path


def load_preset(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def apply_overlay(base: dict, overlay: dict) -> dict:
    merged = copy.deepcopy(base)
    for feed in overlay.get("add_feeds", []):
        merged.setdefault("feeds", []).append(feed)
    remove_names = set(overlay.get("remove_feeds", []))
    if remove_names:
        merged["feeds"] = [f for f in merged.get("feeds", []) if f.get("name", "") not in remove_names]
    for topic, words in overlay.get("add_keywords", {}).items():
        merged.setdefault("keywords", {})[topic] = words
    for topic in overlay.get("remove_keywords", []):
        merged.get("keywords", {}).pop(topic, None)
    if "max_items" in overlay:
        merged.setdefault("scoring", {})["max_items"] = overlay["max_items"]
    if "schedule_time" in overlay:
        merged["schedule_time"] = overlay["schedule_time"]
    if "timezone" in overlay:
        merged["timezone"] = overlay["timezone"]
    return merged


def resolve_config(
    preset_dir: Path | None = None,
    preset_name: str | None = None,
    user_config_path: Path | None = None,
) -> dict:
    if user_config_path is None:
        user_config_path = _config_file_path()
    user_config: dict = {}
    if user_config_path.exists():
        with user_config_path.open("r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
    if preset_name is None:
        preset_name = user_config.get("preset", "ai-engineering")
    if preset_name == "blank":
        base = {"feeds": [], "keywords": {}, "scoring": {"max_items": 10}, "retention": {}}
    else:
        if preset_dir is None:
            preset_dir = Path(__file__).resolve().parent.parent / "presets"
        preset_path = preset_dir / f"{preset_name}.yaml"
        if not preset_path.exists():
            raise FileNotFoundError(f"Preset not found: {preset_path}")
        base = load_preset(preset_path)
    if user_config:
        return apply_overlay(base, user_config)
    return base
