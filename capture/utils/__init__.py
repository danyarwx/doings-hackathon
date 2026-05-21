import sys

if sys.platform == "win32":
    from .hardware_win import check_hardware_warnings
else:
    from .hardware_mac import check_hardware_warnings

__all__ = ["check_hardware_warnings"]