from fishmip_cesm.write_output import describe_write_failure


def test_a_quota_failure_says_so_and_points_somewhere_with_room():
    error = RuntimeError(
        "NetCDF: HDF error ... errno = 122, error message = 'Disk quota exceeded'"
    )

    message = describe_write_failure(error)

    assert "quota" in message.lower()
    assert "scratch" in message.lower()


def test_a_full_filesystem_is_reported_the_same_way():
    message = describe_write_failure(OSError(28, "No space left on device"))

    assert "space" in message.lower() or "quota" in message.lower()


def test_an_unrelated_failure_is_passed_through_intact():
    message = describe_write_failure(ValueError("something else entirely"))

    assert "something else entirely" in message
    assert "quota" not in message.lower()
