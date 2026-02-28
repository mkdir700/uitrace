from uitrace.errors import ErrorCode, UitError, format_error


def test_format_error_includes_code_message_and_hint():
    error = UitError(code=ErrorCode.SCHEMA_INVALID, message="bad", hint="do x")

    formatted = format_error(error)

    assert "SCHEMA_INVALID" in formatted
    assert "bad" in formatted
    assert "do x" in formatted
