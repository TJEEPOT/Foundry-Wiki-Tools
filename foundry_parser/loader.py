"""
YAML Template Loader

Handles reading and parsing raw YAML template files from Foundry's
StreamingAssets/Templates directory.
"""

from pathlib import Path
from typing import Any

import yaml

try:
    _YamlLoader = yaml.CSafeLoader
except AttributeError:
    _YamlLoader = yaml.SafeLoader


def _unwrap_yaml(raw: Any, filename: str = "") -> dict[str, Any] | None:
    """Unwrap the two-level YAML nesting into the inner data dict."""
    if not isinstance(raw, dict) or len(raw) != 1:
        return None

    template_type = next(iter(raw))
    type_data = raw[template_type]

    if not isinstance(type_data, dict) or len(type_data) != 1:
        return None

    identifier = next(iter(type_data))
    data = type_data[identifier]

    if not isinstance(data, dict):
        return None

    data["_template_type"] = template_type
    return data


def load_template_file(filepath: Path) -> dict[str, Any]:
    """Load a single YAML template file and return the inner data dict."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = yaml.load(f, Loader=_YamlLoader)
    data = _unwrap_yaml(raw, filepath.name)
    if data is None:
        raise ValueError(f"Unexpected structure in {filepath}")
    return data


def load_template_dir(dirpath: Path) -> dict[str, dict[str, Any]]:
    """Load all YAML files from a template category directory."""
    results: dict[str, dict[str, Any]] = {}
    if not dirpath.is_dir():
        return results
    for filepath in sorted(dirpath.glob("*.yaml")):
        try:
            data = load_template_file(filepath)
            identifier = data.get("identifier", filepath.stem)
            results[identifier] = data
        except Exception as e:
            print(f"Warning: Failed to parse {filepath.name}: {e}")
    return results


def load_template_dir_batch(dirpath: Path) -> dict[str, dict[str, Any]]:
    """Load all YAML files from a directory, pre-reading into memory.

    Faster than load_template_dir because it reads all file contents
    first, then parses them, reducing IO interleaving overhead.
    """
    results: dict[str, dict[str, Any]] = {}
    if not dirpath.is_dir():
        return results

    yaml_files = sorted(dirpath.glob("*.yaml"))
    if not yaml_files:
        return results

    chunks: list[tuple[str, str]] = []
    for filepath in yaml_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            chunks.append((filepath.name, content))
        except Exception as e:
            print(f"Warning: Failed to read {filepath.name}: {e}")

    for filename, content in chunks:
        try:
            raw = yaml.load(content, Loader=_YamlLoader)
            data = _unwrap_yaml(raw, filename)
            if data is not None:
                ident = data.get("identifier", filename.replace(".yaml", ""))
                results[ident] = data
        except Exception as e:
            print(f"Warning: Failed to parse {filename}: {e}")

    return results


def discover_template_dirs(templates_root: Path) -> dict[str, Path]:
    """Discover all template category directories."""
    dirs: dict[str, Path] = {}
    if not templates_root.is_dir():
        raise FileNotFoundError(f"Templates root not found: {templates_root}")
    for child in sorted(templates_root.iterdir()):
        if child.is_dir():
            dirs[child.name] = child
    return dirs
