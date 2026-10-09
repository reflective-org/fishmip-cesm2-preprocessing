import pytest

from fishmip_cesm.naming import object_key, output_filename


def test_filename_follows_the_fishmip_forcing_convention():
    name = output_filename(
        model="CESM2-WACCM6",
        scenario="G6-1.5K-SAI",
        member="001",
        variable="intpp",
        start_year=2035,
        end_year=2069,
    )

    assert name == (
        "cesm2-waccm6_g6-1p5k-sai_001_intpp_onedeg_global_monthly_2035_2069.nc"
    )


def test_filename_is_lowercase_with_no_characters_that_need_escaping():
    name = output_filename(
        model="CESM2.1-CAM6",
        scenario="G6-1.5K-MCB",
        member="003",
        variable="expc-bot",
        start_year=2035,
        end_year=2069,
    )

    assert name == name.lower()
    assert " " not in name
    # Dots separate the extension only; they must not appear in the tokens.
    assert name.count(".") == 1


def test_object_key_sits_under_the_fishmip_prefix():
    key = object_key(
        scenario="G6-1.5K-MCB", filename="cesm2-1-cam6_g6-1p5k-mcb_001_intpp.nc"
    )

    assert key.startswith("fishmip/")
    assert key.endswith("cesm2-1-cam6_g6-1p5k-mcb_001_intpp.nc")


def test_object_key_refuses_a_path_that_would_escape_the_prefix():
    with pytest.raises(ValueError):
        object_key(scenario="G6-1.5K-MCB", filename="../../etc/passwd")


def test_model_years_are_padded_to_four_digits():
    # piControl years are three digits or fewer. Unpadded they sort wrongly
    # against four-digit years and do not match the cftime stamps in the file.
    name = output_filename(
        model="cesm2-waccm6",
        scenario="picontrol",
        member="001",
        variable="intpp",
        start_year=300,
        end_year=499,
    )

    assert name.endswith("_0300_0499.nc")


def test_a_padded_window_reads_back_correctly():
    from fishmip_cesm.naming import window_from_filename

    name = output_filename(
        model="cesm2-waccm6",
        scenario="picontrol",
        member="001",
        variable="intpp",
        start_year=300,
        end_year=499,
    )

    assert window_from_filename(name) == ((300, 1), (499, 12))
