"""English text shown to the model or CLI. Native code sends error codes only."""

from __future__ import annotations

from .rendering.table import render_cell

ERRORS = {
    "GAME_NOT_RUNNING": "Game is not running. Call launch_game() to start it, then retry this "
    "tool.",
    "ACCESS_DENIED": "The game is running, but access was denied. Run the MCP server as the same "
    "Windows user and at the same integrity level as the game.",
    "PROCESS_QUERY_FAILED": "Cannot query game processes: {detail}",
    "MULTIPLE_INSTANCES": "Multiple game instances are running. Keep one instance and retry.",
    "LAUNCH_FAILED": "Cannot launch through Steam: {detail}. Check that Steam is installed and "
    "signed in.",
    "WINDOW_UNAVAILABLE": "Game window is unavailable. Call launch_game() to start or reconnect "
    "to the game.",
    "CONNECT_FAILED": "Cannot connect to MessageFromAliens.exe: {detail}. Start the game with "
    "Steam running and run this server as the same user.",
    "TRANSPORT_FAILED": "Game connection failed: {detail}",
    "INTERNAL_ERROR": "The game could not complete the operation. Check the server diagnostic "
    "log.",
    "QUIT_UNCONFIRMED": "Game requested exit but is still running.",
    "PAGE_NOT_READY": "Game page is not ready",
    "LAUNCH_TIMEOUT": "Game did not become ready within 45 seconds: {detail}. Check Steam or the "
    "game window, then retry launch_game().",
    "UNKNOWN_HASH": "Unknown glyph hash: {hash}",
    "HASH_EXHAUSTED": "The four-character glyph ID space is exhausted",
    "INVALID_HASH": "hash must be a four-character lowercase token from look",
    "INVALID_LOOK_TYPE": "type must be 'table' or 'screenshot'",
    "INVALID_FORCE": "force must be a boolean",
    "INVALID_ROW": "row must be an integer from 0 to 8",
    "INVALID_COL": "col must be an integer from 0 to 23",
    "INVALID_BUTTON": "type must be 'left' or 'right'",
    "INVALID_TEXT_TYPE": "text must be a string",
    "INVALID_TEXT_LINE": "text must be a single line without null characters",
    "INVALID_TEXT_LENGTH": "text must be at most 49 UTF-16 units",
    "INVALID_SECONDS": "seconds must be a finite number from 0.001 to 86400",
    "INVALID_GLYPH_FORMAT": "format must be 'ascii', 'paths', or 'image'",
    "INVALID_TABLE_FORMAT": "format must be markdown or text",
    "INVALID_GLYPH_PATHS": "Glyph paths must contain finite 2D coordinates",
    "WINDOW_HIDDEN": "Game window is minimized or hidden; no screenshot is available",
    "DPI_QUERY_FAILED": "Cannot query physical game window dimensions",
    "DIMENSIONS_UNAVAILABLE": "Game window dimensions are unavailable",
    "EMPTY_CLIENT_AREA": "Game window has no drawable client area",
    "CAPTURE_TIMEOUT": "Timed out waiting for a game window screenshot",
    "CAPTURE_CLOSED": "Game window capture closed without a frame",
    "CAPTURE_FAILED": "Cannot capture the game window: {detail}",
    "ASSEMBLY_NOT_READY": "Game assembly is not ready yet",
    "DRAW_NOT_FOUND": "Draw not found",
    "PAGE_CHANGED": "Page changed while reading; call look again",
    "CATALOGUE_UNAVAILABLE": "Game character catalogue is unavailable",
    "GLYPH_RENDERER_UNAVAILABLE": "Game character renderer is unavailable",
    "WAIT_UNAVAILABLE": "wait is not available on the current page",
    "TIMER_NOT_INITIALIZED": "The game timer is not initialized",
    "TIMER_CAPACITY": "The requested interval exceeds the game timer capacity",
    "TIME_RESTORE_FAILED": "Time advance failed and the previous timer state could not be "
    "restored",
    "UNITY_METHOD_UNAVAILABLE": "Required Unity method is unavailable",
    "UNITY_REJECTED": "Unity rejected the operation",
    "PAGE_UNAVAILABLE": "Game page is unavailable",
    "CELL_UNAVAILABLE": "Game grid cell is unavailable",
    "POSITION_UNAVAILABLE": "Character position is unavailable",
    "CAMERA_UNAVAILABLE": "Game camera is unavailable",
    "OUTSIDE_CAMERA": "Character is outside the game camera",
    "THREAD_CHANGED": "Game window thread changed; reconnect",
    "NATIVE_BINDING_UNAVAILABLE": "Required Unity native binding is unavailable",
    "BACKGROUND_RESTORE_FAILED": "Could not restore the game background setting",
    "URL_DECODE_FAILED": "External URL was blocked, but its address could not be decoded",
    "URL_INTERCEPT_UNAVAILABLE": "External URL interception is unavailable",
    "UPDATE_UNAVAILABLE": "Game Update is unavailable",
    "INPUT_BINDING_UNAVAILABLE": "Input binding is unavailable",
    "ANNOTATION_LOST": "Annotation did not survive the game update",
    "TIME_SAVE_FAILED": "Game time advanced, but saving failed: {cause}",
    "CLICK_NOT_READ": "Game did not read the injected click",
    "INVALID_GRID_POSITION": "Expected row 0..8 and col 0..23",
    "THREAD_UNAVAILABLE": "Game window thread is unavailable",
    "INPUT_BUSY": "Another input operation is still being processed",
    "INPUT_TIMEOUT": "Input operation timed out waiting for the game main thread",
    "WAKE_FAILED": "Could not wake the game window thread",
    "IDENTITY_FIELD_UNAVAILABLE": "Character identity field is unavailable",
    "ANNOTATION_FIELD_UNAVAILABLE": "No unfocused character annotation field is available",
    "ANNOTATION_TOO_LONG": "Annotation exceeds the game input limit",
    "ANNOTATION_NOT_COMMITTED": "Game did not commit the annotation",
    "OFF_PAGE_ANNOTATION_FAILED": "Could not complete the annotation while the character is off "
    "the current page. Open a page where the character appears, check its annotation, and call "
    "note again if needed.",
    "ANNOTATION_RESTORE_FAILED": "Annotation failed ({cause}); restoring the original text also "
    "failed ({restore})",
    "CHARACTER_UNAVAILABLE": "Character is unavailable",
    "INVALID_NATIVE_ANNOTATION": "Annotation must be a single-line string without null "
    "characters",
    "RUNTIME_UNSUPPORTED": "Unsupported game runtime: Mono or IL2CPP is required",
    "RUNTIME_NOT_READY": "Game runtime is not ready yet",
    "CLI_LOOK_REQUIRED": "--json, --raw and --format require --look",
}


def error_text(code: str, **details) -> str:
    template = ERRORS.get(code, ERRORS["INTERNAL_ERROR"])
    for key in ("cause", "restore"):
        if key in details:
            details[key] = error_text(details[key])
    return template.format(**details)


def unchanged(view: str) -> str:
    return f"Unchanged: {view} is identical to the previous {view} look."


def advanced_time(seconds: float) -> str:
    return f"Advanced game time by {seconds:g} seconds."


def closed_click(confirmed: bool) -> str:
    return (
        "The game exited after this click."
        if confirmed
        else "The game process exited; whether this click completed is unknown."
    )


def describe_screenshot(picture) -> str:
    style = "bordered" if picture.bordered else "borderless"
    return (
        f"Screenshot: {picture.width}x{picture.height} pixels; "
        f"client area: {picture.client_width}x{picture.client_height} pixels; "
        f"window style: {style}."
    )


def describe_click(result: dict) -> str:
    button = result["type"]
    target = result.get("target")
    position = f"({result['row']}, {result['col']})"
    if target and target.get("empty") is True:
        character = render_cell(
            None,
            boxed=bool(target.get("boxed")),
            frame=target.get("frame"),
        )
        label = f"{character} (blank)" if character else "blank"
        subject = f"{label} at {position}"
    elif target:
        character = render_cell(
            target,
            boxed=target.get("boxed", False),
            underlined=target.get("underlined", False),
        )
        subject = f"{character} at {position}"
    else:
        subject = f"{position} (target unknown)"
    if result["game_running"] is False:
        if result["ok"] and result.get("click_status") == "quit_requested":
            return (
                f"The game has closed: the {button} click on {subject} requested exit. "
                "Call launch_game() to restart it before continuing."
            )
        return (
            f"The game process has exited. Could not confirm whether the {button} click on {subject} completed. "
            "Call launch_game() to restart it before continuing."
        )
    if result.get("event") == "external_url":
        urls = "\n".join(result["urls"])
        return (
            f"Clicked {subject} with the {button} mouse button. "
            f"External navigation blocked; no webpage was opened:\n{urls}"
        )
    if not result["ok"]:
        return f"Could not confirm whether the {button} click on {subject} completed."
    return f"Clicked {subject} with the {button} mouse button."
