"""Extract the game's Latin and Chinese fonts for the private local player."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSETS = Path(
    r"E:\Software\Steam\steamapps\common\Message From Aliens"
    r"\MessageFromAliens_Data\sharedassets0.assets"
)
FONTS = {
    "PTSans-Regular": "pt-sans-regular.ttf",
    "FangZhengHeiTi-GBK-1": "fz-hei.ttf",
}


def export_fonts(assets: Path):
    import UnityPy

    output = ROOT / "data" / "fonts"
    output.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(assets.read_bytes()).hexdigest()
    manifest = output / "source.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == fingerprint and all(
            (output / filename).is_file() for filename in FONTS.values()
        ):
            return
    env = UnityPy.load(str(assets))
    found = set()
    for obj in env.objects:
        if obj.type.name != "Font" or obj.peek_name() not in FONTS:
            continue
        font = obj.read()
        if not font.m_FontData:
            raise ValueError(f"No embedded font data for {font.m_Name}")
        (output / FONTS[font.m_Name]).write_bytes(bytes(font.m_FontData))
        found.add(font.m_Name)
    if missing := FONTS.keys() - found:
        raise ValueError(f"Missing game fonts: {sorted(missing)}")
    manifest.write_text(
        json.dumps({"fingerprint": fingerprint, "fonts": FONTS}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    export_fonts(parser.parse_args().assets)
