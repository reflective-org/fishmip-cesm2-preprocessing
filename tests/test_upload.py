import pytest

from fishmip_cesm.upload import credentials_from_env, needs_upload, plan_upload


def test_a_file_that_is_not_in_the_bucket_needs_uploading():
    assert needs_upload(local_size=100, remote_size=None)


def test_a_file_already_there_at_the_same_size_does_not():
    assert not needs_upload(local_size=100, remote_size=100)


def test_a_file_there_at_a_different_size_does():
    # A truncated or superseded object must not be left in place.
    assert needs_upload(local_size=100, remote_size=99)


def test_the_upload_plan_maps_a_filename_to_its_scenario_prefix():
    plan = plan_upload("cesm2-cam6_g6-1p5k-mcb_001_intpp_onedeg_global_monthly_2035_2069.nc")

    assert plan == "fishmip/g6-1p5k-mcb/cesm2-cam6_g6-1p5k-mcb_001_intpp_onedeg_global_monthly_2035_2069.nc"


def test_a_filename_that_does_not_parse_is_refused():
    # Guessing a prefix would scatter files across the bucket under names
    # nobody can find, and a published key is hard to take back.
    with pytest.raises(ValueError):
        plan_upload("something-else.nc")


def test_missing_credentials_are_reported_not_guessed(monkeypatch):
    for name in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="R2_ACCESS_KEY_ID"):
        credentials_from_env()


def test_credentials_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_ACCOUNT_ID", "account")

    creds = credentials_from_env()

    assert creds.endpoint == "https://account.r2.cloudflarestorage.com"
    # The secret must never appear in a repr that could reach a log.
    assert "secret" not in repr(creds)
