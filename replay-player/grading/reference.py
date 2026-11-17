"""Extract original English keys and the game's complete dictionary entries."""

from __future__ import annotations

import base64
import hashlib
import re
from fractions import Fraction
from pathlib import Path

DEFAULT_ASSETS = Path(
    r"E:\Software\Steam\steamapps\common\Message From Aliens"
    r"\MessageFromAliens_Data\resources.assets"
)


def extract_reference(assets):
    import UnityPy
    from Crypto.Cipher import AES

    env = UnityPy.load(str(assets))
    table = None
    for obj in env.objects:
        if obj.type.name == "TextAsset" and obj.peek_name() == "newalien":
            raw = AES.new(
                b"terrible_artwork", AES.MODE_CBC, b"wedidn'tplaytest"
            ).decrypt(base64.b64decode(obj.read().m_Script))
            table = raw[: -raw[-1]].decode("utf-8-sig")
            break
    if table is None:
        raise ValueError("The game assets contain no newalien dictionary")
    lines = table.splitlines()
    fields = lines[0].split(",")
    rows = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        row = dict(zip(fields, line.replace(":", "").split(",")))
        if row.get("word"):
            rows[row["word"]] = row
    entries = {}
    for key, row in rows.items():
        wordtype = row.get("wordtype", "")
        components = [row.get("component1", ""), row.get("component2", "")]
        radicals = []
        if row.get("struct") not in ("s", "exp"):
            for component in components:
                if component in rows:
                    radicals.append(rows[component].get("rename") or component)
        intro = f"{key} be {wordtype}"
        if wordtype.split()[:1] == ["token"]:
            intro = f"{key} benot word"
        if radicals:
            structure = f"{key} de radicial be " + " and ".join(radicals)
        elif wordtype.split()[:1] != ["token"]:
            structure = f"{key} be basic radicial"
        else:
            structure = ""
        meaning = row.get("meaning", "")
        entry = {
            "key": key,
            "english": key,
            "rename": row.get("rename") or key,
            "redirect": row.get("redirect", ""),
            "wordtype": wordtype,
            "meaning_raw": meaning,
            "dictionary_text": "\n".join(
                [intro, structure, "", meaning.replace(";", "\n")]
            ),
            "components": radicals,
        }
        # Preserve numeric source tokens rather than accidentally reading a
        # base-seven exponent as a decimal exponent or losing unit notation.
        value = numeric_value(key)
        if value is not None:
            entry["numeric_value"] = value
        entries[key] = entry
    return {
        "assets_fingerprint": hashlib.sha256(assets.read_bytes()).hexdigest(),
        "source": "resources.assets/newalien; dictionary header follows Draw's word-info rendering",
        "notation": "Dictionary text is the author's tokenized English, not fluent prose. Semicolons mean line breaks; de is possessive. Numeric key aeN represents a * 7^N; numeric_value is exact when present. Original unit/numeric tokens in meaning_raw are preserved without reinterpretation.",
        "entries": entries,
    }


def numeric_value(key):
    match = re.fullmatch(r"(-?\d+)(?:e(-?\d+))?", key)
    if not match:
        return None
    number = Fraction(int(match[1])) * Fraction(7) ** int(match[2] or 0)
    return str(number)


def reference_for(reference, key):
    entry = reference["entries"].get(key)
    if entry is None and (value := numeric_value(key)) is not None:
        entry = {
            "key": key,
            "english": key,
            "numeric_value": value,
            "dictionary_text": "No dictionary row; meaning follows the numeric key notation.",
        }
    if entry is None:
        return None
    result = dict(entry)
    renamed = reference["entries"].get(entry.get("rename"))
    if renamed and renamed["key"] != key:
        result["renamed_entry"] = renamed
    return result
