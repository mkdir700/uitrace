import pytest

from uitrace.errors import ErrorCode, UitError
from uitrace.platform.unsupported import UnsupportedPlatform


def test_unsupported_platform_list_windows():
    p = UnsupportedPlatform()
    with pytest.raises(UitError) as exc:
        p.list_windows()
    assert exc.value.code == ErrorCode.UNSUPPORTED_PLATFORM


def test_unsupported_platform_check_permissions():
    p = UnsupportedPlatform()
    with pytest.raises(UitError) as exc:
        p.check_permissions()
    assert exc.value.code == ErrorCode.UNSUPPORTED_PLATFORM
