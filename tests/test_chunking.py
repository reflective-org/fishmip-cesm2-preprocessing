from fishmip_cesm.chunking import (
    SOURCE_CELLS,
    TARGET_CHUNK_BYTES,
    time_chunk,
)


def test_a_chunk_stays_under_the_target_size_at_every_depth():
    for levels in (1, 15, 60):
        months = time_chunk(levels)
        assert months * levels * SOURCE_CELLS * 4 <= TARGET_CHUNK_BYTES


def test_deeper_fields_get_fewer_months_per_chunk():
    # A fixed month count means a 60-level chunk is 60x a surface one, which is
    # how a 10 GB machine runs out on thetao but not on intpp.
    assert time_chunk(1) > time_chunk(15) > time_chunk(60)


def test_a_chunk_is_never_less_than_one_month():
    assert time_chunk(10_000) == 1


def test_a_surface_field_is_not_chunked_into_uselessly_small_pieces():
    assert time_chunk(1) <= 120
