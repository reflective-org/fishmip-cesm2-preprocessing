"""How much of a field to hold in memory at once.

Chunking by a fixed number of months ignores depth, so a 60-level field asks for
sixty times the memory of a surface one. That is the difference between a job
that fits in 10 GB and one that does not.
"""

# POP gx1v7 horizontal size.
SOURCE_CELLS = 384 * 320

# Per chunk, before dask runs several concurrently.
#
# Too small is its own failure mode: dask chunks smaller than the netCDF file's
# internal chunks make the same compressed blocks decompress repeatedly, and the
# job becomes I/O bound on data it has already read. This was set to 64 MB while
# chasing a memory problem whose real cause was elsewhere (unflatten
# materialising the whole variable), and the small chunks then became the
# bottleneck.
TARGET_CHUNK_BYTES = 256 * 1024 * 1024

# More months than this buys nothing and makes the graph coarse.
MAX_MONTHS = 60


def time_chunk(levels: int) -> int:
    """Months per chunk for a field with this many depth levels."""
    per_month = max(1, levels) * SOURCE_CELLS * 4
    return max(1, min(MAX_MONTHS, TARGET_CHUNK_BYTES // per_month))
