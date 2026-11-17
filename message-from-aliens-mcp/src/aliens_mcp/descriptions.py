"""Model-facing and CLI descriptions; keep these spoiler-free."""

INSTRUCTIONS = (
    "Message From Aliens is a game about deciphering a pictographic alien language. Each alien "
    "character is represented by a four-character hash, displayed as hash:annotation. Hashes "
    "identify the same character across pages within the current connection. Use `look` to "
    "inspect the current page, `glyph` to examine character shapes, `click` to interact, `note` "
    "to make annotations, `wait` to advance game time, and `launch_game` to start the game."
)

TOOL_DESCRIPTIONS = {
    "launch_game": """Start the game through Steam, or connect to an existing instance.

Waits up to 45 seconds for a readable page.""",
    "look": """Read the current page as a table or screenshot.

type='table' (default): a 9x24 grid with current annotations and layout markers.
Rows 0..8 run top to bottom; columns 0..23 run left to right.
Single-cell frames use [...]. Multirow frames use top corners ┌...┐,
middle sides │...│, and bottom corners └...┘; empty slots keep their outlines.
type='screenshot': an original-resolution game-window PNG with pixel dimensions
and window style, useful for colors, setting selections, and size.
Each mode compares with its own previous result and returns a short unchanged
message when identical. force=True always returns the complete selected view.""",
    "click": """Click a cell, including a blank cell, on the current grid in the background.

type='left' (default) or 'right' selects the mouse button.
Returns the clicked target, outcome, and any special circumstances.""",
    "note": """Set an annotation for a character, including one not on the current page.

Applies to all occurrences of that character across pages.
text is one line of at most 49 UTF-16 units; an empty string clears the annotation.""",
    "wait": """Advance game time without actually waiting.

seconds is 0.001..86400 per call, measured in real-world seconds.
Available only on pages that support time advancement.
Applies the game's normal time updates and saves the result.""",
    "glyph": """Return a character's shape in the selected format.

format='image' (default): a 64x64 PNG image with bold, antialiased strokes.
format='ascii': adaptive character art using spaces and #.
format='paths': JSON polylines fitted proportionally into 0..100 coordinates,
with a top-left origin, x right and y down. Connect consecutive points within
each path; a repeated first point closes it. Separate paths are not connected.""",
}

CLI_DESCRIPTION = (
    "Read the game with --look, check connectivity with --status, or serve MCP."
)
CLI_HELP = {
    "look": "print the current page and exit",
    "status": "check the Frida connection and exit",
    "json": "emit JSON with --look",
    "raw": "expose internal word keys (development only)",
}
