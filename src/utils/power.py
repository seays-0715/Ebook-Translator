"""Prevent system sleep during active translation (spec §38).

After-completion actions (spec §39): nothing / sleep / shutdown / open_folder.
Sleep/Shutdown only after successful job completion (caller decides).
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class SleepPreventer:
    def __init__(self) -> None:
        self._active = False
        self._es_continuous = 0x80000000
        self._es_system = 0x00000001

    def prevent(self) -> None:
        if self._active:
            return
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(
                    self._es_continuous | self._es_system
                )
                self._active = True
            except Exception:
                pass
        else:
            self._active = True

    def restore(self) -> None:
        if not self._active:
            return
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(self._es_continuous)
            except Exception:
                pass
        self._active = False

    def __enter__(self) -> "SleepPreventer":
        self.prevent()
        return self

    def __exit__(self, *args) -> None:
        self.restore()


@contextmanager
def prevent_sleep() -> Generator[SleepPreventer, None, None]:
    p = SleepPreventer()
    p.prevent()
    try:
        yield p
    finally:
        p.restore()


def after_completion_action(
    action: str,
    *,
    output_folder: str | Path | None = None,
) -> None:
    """Run post-completion action. Unknown values treated as nothing."""
    action = (action or "nothing").strip().lower()
    if action == "open_folder" and output_folder:
        folder = Path(output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)
        return
    if action == "sleep":
        _system_sleep()
        return
    if action == "shutdown":
        _system_shutdown()
        return
    # nothing


def _open_folder(path: Path) -> None:
    path = path.resolve()
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def _system_sleep() -> None:
    try:
        if sys.platform == "win32":
            # Hibernate/sleep via rundll32
            subprocess.Popen(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"]
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["pmset", "sleepnow"])
        else:
            subprocess.Popen(["systemctl", "suspend"])
    except Exception:
        pass


def _system_shutdown() -> None:
    try:
        if sys.platform == "win32":
            subprocess.Popen(["shutdown", "/s", "/t", "60"])
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
        else:
            subprocess.Popen(["shutdown", "-h", "+1"])
    except Exception:
        pass
