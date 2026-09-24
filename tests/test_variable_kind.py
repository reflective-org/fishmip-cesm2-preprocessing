import pytest

from fishmip_cesm.regrid import _VARIABLE_KIND, variable_kind


@pytest.mark.parametrize(
    "fishmip_name, kind",
    [
        # Integrals: a cell that is mostly land contributes proportionally less.
        ("intpp", "flux"),
        ("expc-bot", "flux"),
        ("zoo_loss", "flux"),
        # Averages: must be normalised by the ocean fraction of the cell.
        ("thetao", "concentration"),
        ("tob", "concentration"),
        ("no3", "concentration"),
        ("phyc", "concentration"),
        ("phydiat", "concentration"),
        ("zooc", "concentration"),
        ("deptho", "concentration"),
        ("thkcello", "concentration"),
    ],
)
def test_each_fishmip_variable_is_classified_for_regridding(fishmip_name, kind):
    assert variable_kind(fishmip_name) == kind


def test_an_unclassified_variable_is_refused_rather_than_defaulted():
    # Defaulting would silently apply the wrong regrid to any variable added
    # later, and the output would look plausible either way.
    with pytest.raises(KeyError):
        variable_kind("chl")


def test_every_converted_variable_has_a_regridding_kind():
    # A variable can be converted but not classified, in which case it would
    # reach the regrid and fail there instead of here. areacello is excluded:
    # target cell areas come from the weight file, not from regridding.
    from fishmip_cesm.transform import CONVERSIONS

    converted = {name for name, _, _ in CONVERSIONS.values()} - {"areacello"}
    unclassified = sorted(n for n in converted if n not in _VARIABLE_KIND)

    assert unclassified == []
