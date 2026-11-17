"""The same counting sets used by Draw.CompleteAmount; export keys, never meanings."""

import base64
import re

GAMES = [
    "1e1 de sequence",
    "money enlarge",
    "understand rule",
    "7 planet card",
    "2e1 detrap de variant",
    "hero de arena",
    "who be liar",
]
CATEGORIES = "advancemath creator bonus alieninfo game geometry physics history current chemistry1 thermology optics math0 mechanics2 geography message anthropology astronomy".split()
READING_MENUS = "arithmetic|geometry|mechanics|astronomy|geography|anthropology|history|bonus arithmetic riddle|advanced arithmetic|chemistry|electricity|thermology|optics|advanced mechanics|message from mankind|game creator de graph".split(
    "|"
)


def alien_number(value):
    value = int(value)
    if value == 0:
        return "0"
    parts, exponent = [], 0
    while value:
        digit = value % 7
        if digit:
            parts.insert(0, f"{digit}e{exponent}" if exponent else str(digit))
        value //= 7
        exponent += 1
    return " ".join(parts)


def page_key(text):
    return " ".join(alien_number(t) if t.isdigit() else t for t in text.strip().split())


def load_catalog(assets):
    import UnityPy
    from Crypto.Cipher import AES

    env = UnityPy.load(str(assets))
    texts = {}
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        name = obj.peek_name()
        if name not in CATEGORIES and name != "newalien":
            continue
        payload = obj.read().m_Script
        decoded = AES.new(
            b"terrible_artwork", AES.MODE_CBC, b"wedidn'tplaytest"
        ).decrypt(base64.b64decode(payload))
        texts[name] = decoded[: -decoded[-1]].decode("utf-8-sig")
    lines = texts["newalien"].splitlines()
    fields = lines[0].split(",")
    words = []
    for line in lines[1:]:
        if not line.strip():
            continue
        row = dict(zip(fields, line.replace(":", "").split(",")))
        key = row.get("word")
        if (
            key
            and row.get("redirect") != "token"
            and row.get("wordtype", "").split()[:1] != ["token"]
            and row.get("rename", "").strip() in ("", key)
        ):
            words.append(key)
    quizzes, section, pages = [], "", {}
    for category in CATEGORIES:
        for line in texts.get(category, "").splitlines():
            if line.startswith("#"):
                section = page_key(line[1:])
                pages.setdefault(section, [])
            elif (
                line.startswith("@") and section != "ignore" and section not in quizzes
            ):
                quizzes.append(section)
            elif section and section != "ignore" and not line.startswith(("@", "%")):
                pages[section].append(line)
    quizzes.append("last riddle")
    games = [page_key(key) for key in GAMES]
    readings = []
    # These menus lead to CurrentPageIsMessage pages. Only their defined
    # non-quiz children can be completed by reaching the end of the text.
    for menu in READING_MENUS:
        for line in pages.get(menu, []):
            target = page_key(re.sub(r"\[[^\]]*\]|\([^)]*\)", "", line))
            if (
                target in pages
                and target not in quizzes
                and target not in games
                and target not in readings
            ):
                readings.append(target)
    return {
        "questions": quizzes,
        "games": games,
        "texts": readings,
        "words": list(dict.fromkeys(words)),
        "source": "Draw.CompleteAmount counting sets; CurrentPageIsMessage reading menu children. Recorded (win) menu markers render as dim text.",
    }
