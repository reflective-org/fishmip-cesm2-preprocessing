import pytest

from fishmip_cesm.plan import plan_output


def test_plan_names_the_file_and_the_object_key():
    plan = plan_output(
        model="CESM2-WACCM6",
        scenario="G6-1.5K-SAI",
        member="001",
        variable="intpp",
        window=((2035, 1), (2069, 12)),
        levels=1,
    )

    assert plan.filename == (
        "cesm2-waccm6_g6-1p5k-sai_001_intpp_onedeg_global_monthly_2035_2069.nc"
    )
    assert plan.key == f"fishmip/g6-1p5k-sai/{plan.filename}"


def test_plan_counts_the_months_in_the_window_inclusively():
    plan = plan_output(
        model="CESM2-WACCM6",
        scenario="G6-1.5K-SAI",
        member="001",
        variable="intpp",
        window=((2035, 1), (2069, 12)),
        levels=1,
    )

    assert plan.months == 420


def test_plan_estimates_size_from_months_levels_and_grid():
    flat = plan_output(
        model="m", scenario="s", member="001", variable="intpp",
        window=((2035, 1), (2069, 12)), levels=1,
    )
    deep = plan_output(
        model="m", scenario="s", member="001", variable="no3",
        window=((2035, 1), (2069, 12)), levels=60,
    )

    # 420 months x 64800 cells x 4 bytes
    assert flat.gigabytes == pytest.approx(0.1089, rel=0.01)
    assert deep.gigabytes == pytest.approx(flat.gigabytes * 60, rel=0.01)
