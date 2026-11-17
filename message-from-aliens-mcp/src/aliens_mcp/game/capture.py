"""Background game-window capture using Windows.Graphics.Capture."""

import ctypes
import threading
from ctypes import wintypes as wt
from io import BytesIO

from ..errors import GameError
from ..models import Screenshot
from .windows import game_window


def _window_info(hwnd: int) -> tuple[int, int, bool]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsIconic.restype = wt.BOOL
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsWindowVisible.restype = wt.BOOL
    if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
        raise GameError("WINDOW_HIDDEN")
    user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetClientRect.restype = wt.BOOL
    user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    # A thread-local override avoids changing the host's process DPI configuration.
    previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous:
        raise GameError("DPI_QUERY_FAILED")
    try:
        rect = wt.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise GameError("DIMENSIONS_UNAVAILABLE")
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise GameError("EMPTY_CLIENT_AREA")
        bordered = bool(user32.GetWindowLongPtrW(hwnd, -16) & 0x00C00000)  # WS_CAPTION
        return width, height, bordered
    finally:
        user32.SetThreadDpiAwarenessContext(previous)


def capture(pid: int) -> Screenshot:
    """One fresh window frame, with an 8-second timeout and no desktop fallback."""
    from PIL import Image
    from windows_capture import WindowsCapture

    hwnd, _ = game_window(pid)
    client_width, client_height, bordered = _window_info(hwnd)
    ready = threading.Event()
    frames: list[tuple[int, int, bytes]] = []
    errors: list[Exception] = []
    session = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=False)

    @session.event
    def on_frame_arrived(frame, control):
        try:
            # The mapped D3D buffer is valid only during this callback. Copy it
            # before signalling the caller or stopping capture.
            if not ready.is_set():
                frames.append((frame.width, frame.height, frame.frame_buffer.tobytes()))
        except Exception as error:
            errors.append(error)
        finally:
            control.stop()
            ready.set()

    @session.event
    def on_closed():
        ready.set()

    try:
        control = session.start_free_threaded()
        try:
            if not ready.wait(8):
                raise GameError("CAPTURE_TIMEOUT")
        finally:
            control.stop()
        if errors:
            raise errors[0]
        if not frames:
            raise GameError("CAPTURE_CLOSED")
        width, height, buffer = frames[0]
        picture = Image.frombytes("RGB", (width, height), buffer, "raw", "BGRX")
        output = BytesIO()
        picture.save(output, format="PNG")
        return Screenshot(
            output.getvalue(), width, height, client_width, client_height, bordered
        )
    except GameError:
        raise
    except Exception as error:
        raise GameError("CAPTURE_FAILED", detail=str(error)) from error
