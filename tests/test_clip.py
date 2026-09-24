import numpy as np
import pytest
import xarray as xr

from fishmip_cesm.validate import clip_negatives


def test_clipping_replaces_negatives_with_zero_and_leaves_the_rest_alone():
    no3 = xr.DataArray([-0.001, 0.02, 0.03], dims="cell")

    clipped, _ = clip_negatives("no3", no3)

    np.testing.assert_allclose(clipped.values, [0.0, 0.02, 0.03])


def test_clipping_preserves_land_rather_than_flooding_it_with_zeros():
    # NaN is land. Turning it into zero would claim there is ocean there.
    no3 = xr.DataArray([np.nan, -0.001, 0.02], dims="cell")

    clipped, _ = clip_negatives("no3", no3)

    assert np.isnan(clipped.values[0])


def test_the_clip_report_counts_the_cells_and_records_the_worst_value():
    no3 = xr.DataArray([-0.001, -0.002, 0.02], dims="cell")

    _, report = clip_negatives("no3", no3)

    assert report.cells == 2
    assert report.most_negative == pytest.approx(-0.002)


def test_the_clip_report_gives_what_was_removed_relative_to_what_remains():
    # 0.003 removed against 0.3 kept: one percent of the field.
    no3 = xr.DataArray([-0.001, -0.002, 0.3], dims="cell")

    _, report = clip_negatives("no3", no3)

    assert report.removed_fraction == pytest.approx(0.01)


def test_clipping_a_clean_field_reports_nothing_removed():
    no3 = xr.DataArray([0.01, 0.02], dims="cell")

    _, report = clip_negatives("no3", no3)

    assert report.cells == 0
    assert report.removed_fraction == 0.0


def test_clipping_is_refused_for_a_variable_that_may_legitimately_be_negative():
    # Sea water reaches -1.9 degC. Clipping temperature would be a disaster,
    # and a silent one.
    thetao = xr.DataArray([-1.9, 12.0], dims="cell")

    with pytest.raises(ValueError, match="thetao"):
        clip_negatives("thetao", thetao)
