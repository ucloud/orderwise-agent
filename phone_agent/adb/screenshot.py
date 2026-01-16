"""Screenshot utilities for Android device."""

import base64
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class Screenshot:
    """Screenshot data structure."""
    base64_data: str
    width: int
    height: int


def _get_adb_prefix(device_id: Optional[str] = None) -> list[str]:
    """Get ADB command prefix with optional device ID."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def get_screenshot(device_id: Optional[str] = None) -> Screenshot:
    """
    Capture screenshot from Android device.
    
    Args:
        device_id: Optional ADB device ID for multi-device setups.
    
    Returns:
        Screenshot object with base64_data, width, and height.
    """
    adb_prefix = _get_adb_prefix(device_id)
    
    # Capture screenshot directly to memory (avoiding file I/O)
    result = subprocess.run(
        adb_prefix + ["exec-out", "screencap", "-p"],
        capture_output=True,
        check=True,
    )
    
    # Convert to base64
    base64_data = base64.b64encode(result.stdout).decode("utf-8")
    
    # Get image dimensions using PIL (if available) or default values
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(result.stdout))
        width, height = img.size
    except ImportError:
        # Fallback: assume common screen size if PIL not available
        width, height = 1080, 1920
    
    return Screenshot(base64_data=base64_data, width=width, height=height)
