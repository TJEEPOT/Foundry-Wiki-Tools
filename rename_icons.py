"""
rename_icons.py — Rename extracted AssetStudio sprites to wiki naming convention.

Input:  image/Sprite/*_512.png  (from AssetStudio export)
Output: wiki_images/*.png       (named Item_{Display Name}.png)
Report: wiki_images/_mapping.csv

Naming convention matches the existing Foundry Wiki:
    File:Item_Assembler_I.png  (underscores, Item_ prefix)

Collision handling:
  - Multiple icons with the same display name: first match wins (all share
    the same image on the wiki), others noted in the report.
  - Same display name but different entity types (e.g. item vs research):
    the lower-priority type gets a parenthetical suffix, e.g.
    Item_Burner_Generator_(Research).png

Priority order for first-match wins: item > research > sky_platform >
element > exploration_unlock > achievement
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Load game data
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from foundry_parser.game_data import GameData

GAME_DIR = Path(__file__).parent.parent / "FOUNDRY"
# Allow override via CLI arg
if len(sys.argv) > 1:
    GAME_DIR = Path(sys.argv[1])

print(f"Loading game data from {GAME_DIR} ...")
gd = GameData.from_game_dir(GAME_DIR)

# ---------------------------------------------------------------------------
# Build icon_id -> (display_name, entity_type) map
# Priority: item > research > sky_platform > element > exploration_unlock > achievement
# ---------------------------------------------------------------------------
PRIORITY = ["item", "research", "sky_platform", "element", "exploration_unlock", "achievement"]
icon_map: dict[str, tuple[str, str]] = {}  # icon_id -> (name, etype)

def add(icon: str, name: str, etype: str) -> None:
    if not icon or not name:
        return
    if icon not in icon_map:
        icon_map[icon] = (name, etype)
    else:
        # Replace only if incoming priority is higher
        current_etype = icon_map[icon][1]
        if PRIORITY.index(etype) < PRIORITY.index(current_etype):
            icon_map[icon] = (name, etype)

for ident, item in gd.items.items():
    add(item.icon, item.name, "item")
for ident, r in gd.research.items():
    add(r.icon, r.name, "research")
for ident, u in gd.sky_platform_upgrades.items():
    add(u.icon, u.name, "sky_platform")
for ident, e in gd.elements.items():
    add(e.icon, e.name, "element")
for ident, ul in gd.exploration_unlocks.items():
    add(ul.icon, ul.title, "exploration_unlock")
for db_id, db in gd.raw_categories.get("AchievementDatabaseTemplate", {}).items():
    for a in db.get("achievements", []):
        add(a.get("iconIdentifier", ""), a.get("displayName", ""), "achievement")

print(f"  {len(icon_map)} icon mappings built.")

# ---------------------------------------------------------------------------
# Type suffix for disambiguation when same display name, different etype
# ---------------------------------------------------------------------------
TYPE_SUFFIX = {
    "research": "(Research)",
    "sky_platform": "(Space Station)",
    "element": "(Element)",
    "exploration_unlock": "(Exploration)",
    "achievement": "(Achievement)",
    "item": "",
}

def wiki_filename(name: str, etype: str) -> str:
    suffix = TYPE_SUFFIX.get(etype, "")
    display = name + (f" {suffix}" if suffix else "")
    return "Item_" + display.replace(" ", "_") + ".png"

# ---------------------------------------------------------------------------
# Resolve all extracted sprites
# ---------------------------------------------------------------------------
sprite_dir = Path(__file__).parent / "image" / "Sprite"
out_dir = Path(__file__).parent / "wiki_images"
out_dir.mkdir(exist_ok=True)

files = sorted(sprite_dir.glob("*.png"))
print(f"  {len(files)} sprite files found in {sprite_dir.name}/")

rows = []           # for CSV report
used_wiki_names: dict[str, str] = {}   # wiki_filename -> icon_id that claimed it
copied = 0
skipped_dup = 0
unmatched = []

for f in files:
    stem = f.stem  # e.g. assembler_i_512
    icon_id = stem[:-4] if stem.endswith("_512") else stem  # strip _512

    if icon_id not in icon_map:
        unmatched.append(stem)
        rows.append({
            "original": f.name,
            "wiki_filename": "",
            "display_name": "",
            "entity_type": "UNMATCHED",
            "note": "",
        })
        continue

    name, etype = icon_map[icon_id]
    wname = wiki_filename(name, etype)

    if wname in used_wiki_names:
        # Another icon already claimed this wiki name
        prev_icon = used_wiki_names[wname]
        rows.append({
            "original": f.name,
            "wiki_filename": wname,
            "display_name": name,
            "entity_type": etype,
            "note": f"DUPLICATE — {prev_icon} already written as this name",
        })
        skipped_dup += 1
        continue

    # Copy with new name
    dest = out_dir / wname
    shutil.copy2(f, dest)
    used_wiki_names[wname] = icon_id
    copied += 1
    rows.append({
        "original": f.name,
        "wiki_filename": wname,
        "display_name": name,
        "entity_type": etype,
        "note": "",
    })

# ---------------------------------------------------------------------------
# Write CSV report
# ---------------------------------------------------------------------------
csv_path = out_dir / "_mapping.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["original", "wiki_filename", "display_name", "entity_type", "note"])
    writer.writeheader()
    writer.writerows(rows)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\nDone.")
print(f"  Copied   : {copied}")
print(f"  Duplicates (same wiki name, skipped) : {skipped_dup}")
print(f"  Unmatched (no game data entry)       : {len(unmatched)}")
print(f"\nOutput folder : {out_dir}")
print(f"Mapping CSV   : {csv_path}")
