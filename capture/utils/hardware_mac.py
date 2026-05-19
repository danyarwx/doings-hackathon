import platform

def check_hardware_warnings():
    if platform.machine() in ["arm64", "aarch64"]:
        print("🎙️  [Capture] Apple Silicon detected. pywhispercpp will use Metal acceleration.")
    else:
        print("🎙️  [Capture] Intel Mac detected. Running on CPU.")
