from pathlib import Path

from fishmip_cesm.make_weights import weight_generation_command


def test_weight_generation_command_asks_for_a_conservative_regrid():
    # The one flag that must never silently drift: bilinear would not preserve
    # the global integral of the flux variables.
    command = weight_generation_command(
        source=Path("gx1v7.nc"), destination=Path("fishmip.nc"), weight=Path("w.nc")
    )

    assert command[0] == "ESMF_RegridWeightGen"
    assert command[command.index("--method") + 1] == "conserve"


def test_weight_generation_command_passes_all_three_paths():
    command = weight_generation_command(
        source=Path("gx1v7.nc"), destination=Path("fishmip.nc"), weight=Path("w.nc")
    )

    assert command[command.index("--source") + 1] == "gx1v7.nc"
    assert command[command.index("--destination") + 1] == "fishmip.nc"
    assert command[command.index("--weight") + 1] == "w.nc"
