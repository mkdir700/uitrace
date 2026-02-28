"""Pure unit tests for validate_record_permissions."""

import pytest

from uitrace.errors import ErrorCode, UitError
from uitrace.platform.base import PermissionReport, PermissionStatus
from uitrace.recorder.recorder import validate_record_permissions


def _make_report(
    accessibility: PermissionStatus = PermissionStatus.granted,
    input_monitoring: PermissionStatus = PermissionStatus.granted,
    screen_recording: PermissionStatus = PermissionStatus.granted,
) -> PermissionReport:
    return PermissionReport(
        accessibility=accessibility,
        input_monitoring=input_monitoring,
        screen_recording=screen_recording,
    )


def test_all_granted_no_raise():
    """All permissions granted -> no exception."""
    perms = _make_report()
    validate_record_permissions(perms, require_screen_recording=True)


def test_accessibility_denied_raises():
    """Accessibility denied -> raises UitError with PERMISSION_DENIED."""
    perms = _make_report(accessibility=PermissionStatus.denied)
    with pytest.raises(UitError) as exc_info:
        validate_record_permissions(perms, require_screen_recording=True)
    assert exc_info.value.code == ErrorCode.PERMISSION_DENIED
    assert "Accessibility" in exc_info.value.message


def test_input_monitoring_denied_raises():
    """Input monitoring denied -> raises UitError with PERMISSION_DENIED and correct message."""
    perms = _make_report(input_monitoring=PermissionStatus.denied)
    with pytest.raises(UitError) as exc_info:
        validate_record_permissions(perms, require_screen_recording=True)
    assert exc_info.value.code == ErrorCode.PERMISSION_DENIED
    assert "Input Monitoring" in exc_info.value.message


def test_screen_recording_denied_raises():
    """Screen recording denied with require_screen_recording=True -> raises."""
    perms = _make_report(screen_recording=PermissionStatus.denied)
    with pytest.raises(UitError) as exc_info:
        validate_record_permissions(perms, require_screen_recording=True)
    assert exc_info.value.code == ErrorCode.PERMISSION_DENIED
    assert "Screen Recording" in exc_info.value.message


def test_screen_recording_denied_not_required_no_raise():
    """Screen recording denied but require_screen_recording=False -> no raise."""
    perms = _make_report(screen_recording=PermissionStatus.denied)
    validate_record_permissions(perms, require_screen_recording=False)
