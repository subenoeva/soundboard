import struct
import subprocess
import sys
from pathlib import Path


def test_make_icon_writes_a_valid_png(tmp_path: Path) -> None:
    output = tmp_path / "icon.png"

    subprocess.run(
        [sys.executable, "packaging/linux/make_icon.py", str(output), "--size", "32"],
        check=True,
    )

    data = output.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (32, 32)
