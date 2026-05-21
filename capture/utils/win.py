import subprocess
import signal
import os
from pathlib import Path

def get_python_executable() -> str:
    """Returns the path to the virtual environment python executable on Windows."""
    return str(Path("capture") / ".venv" / "Scripts" / "python.exe")

def stop_process(process: subprocess.Popen):
    """Sends a graceful CTRL_C_EVENT to the capture process on Windows."""
    if process:
        try:
            # Note: CTRL_C_EVENT requires the process to be created with creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            os.kill(process.pid, signal.CTRL_C_EVENT)
        except (ProcessLookupError, AttributeError, OSError):
            # Fallback if standard signal fails
<<<<<<< HEAD
            process.terminate()
=======
            process.terminate()
>>>>>>> step-1-terminal-stt
