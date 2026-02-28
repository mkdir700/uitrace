"""Platform abstraction for uitrace."""
import sys

from uitrace.platform.base import Platform


def get_platform() -> Platform:
    """Get platform implementation for current OS."""
    if sys.platform == "darwin":
        # Lazy import to avoid pyobjc on non-macOS
        from uitrace.platform.macos import MacOSPlatform

        return MacOSPlatform()
    from uitrace.platform.unsupported import UnsupportedPlatform

    return UnsupportedPlatform()
