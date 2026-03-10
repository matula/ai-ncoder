"""PyInstaller runtime hook: ensure ffmpeg/ffprobe are executable after unpack
and set LLAMA_CPP_LIB_PATH so llama_cpp finds its native libraries."""

import os
import stat
import sys

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # Ensure ffmpeg/ffprobe binaries are executable
    for binary in ("bin/ffmpeg", "bin/ffprobe"):
        path = os.path.join(sys._MEIPASS, binary)
        if os.path.isfile(path):
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Point llama_cpp to its native libraries inside the bundle
    llama_lib = os.path.join(sys._MEIPASS, "llama_cpp", "lib")
    if os.path.isdir(llama_lib):
        os.environ["LLAMA_CPP_LIB_PATH"] = llama_lib
