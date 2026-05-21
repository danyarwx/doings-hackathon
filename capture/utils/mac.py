import subprocess
import signal
import os
from pathlib import Path

def get_python_executable() -> str:
    """Returns the path to the virtual environment python executable on macOS/Linux."""
    return str(Path("capture") / ".venv" / "bin" / "python")

def stop_process(process: subprocess.Popen):
    """Sends a graceful SIGINT to the capture process on macOS/Linux."""
    if process:
        try:
            os.kill(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass