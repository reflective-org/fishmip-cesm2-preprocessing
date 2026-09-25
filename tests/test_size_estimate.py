import numpy as np

from fishmip_cesm.plan import BYTES_PER_VALUE
from fishmip_cesm.write_output import COMPRESSION


def test_the_size_estimate_matches_the_dtype_the_writer_actually_uses():
    # The plan assumes float32. The regrid produces float64, so unless the
    # encoding says otherwise every file is twice the size the plan reported --
    # and the plan is what the storage decision is made on.
    assert np.dtype(COMPRESSION["dtype"]).itemsize == BYTES_PER_VALUE
