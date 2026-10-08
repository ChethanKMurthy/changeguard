from audit.stamp import audit_timestamp


def test_timestamp_is_utc():
    assert audit_timestamp().endswith("+00:00")
