"""Windows process discovery, window lookup, and Steam launch."""

import ctypes
import os
from ctypes import wintypes as wt

from ..errors import GameError

GAME = "MessageFromAliens.exe"
STEAM_APP_ID = 1858720


def running_pid() -> int | None:
    # Frida hides inaccessible processes from its enumeration. Use Windows'
    # process snapshot so lack of injection access never triggers Steam launch.
    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", wt.LONG),
            ("dwFlags", wt.DWORD),
            ("szExeFile", wt.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32FirstW.restype = wt.BOOL
    kernel.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.restype = wt.BOOL
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise GameError(
            "PROCESS_QUERY_FAILED", detail=str(ctypes.WinError(ctypes.get_last_error()))
        )
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = []
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            if entry.szExeFile.casefold() == GAME.casefold():
                found.append(entry.th32ProcessID)
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise GameError(
                "PROCESS_QUERY_FAILED",
                detail=str(ctypes.WinError(ctypes.get_last_error())),
            )
        if len(found) > 1:
            raise GameError("MULTIPLE_INSTANCES")
        return found[0] if found else None
    finally:
        kernel.CloseHandle(snapshot)


def request_launch() -> None:
    try:
        os.startfile(f"steam://run/{STEAM_APP_ID}")
    except OSError as error:
        raise GameError("LAUNCH_FAILED", detail=str(error)) from error


def game_window(pid: int) -> tuple[int, int]:
    """Window handle and main thread, without changing window state."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    found: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd, _lparam):
        owner = wt.DWORD()
        thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, 256)
            if name.value.lower() == "unitywndclass":
                found.append((hwnd, thread))
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        raise GameError("WINDOW_UNAVAILABLE")
    return found[0]
