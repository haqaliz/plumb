"""C2 artifact intake: resolve and pin the code/data behind a paper.

The package is built in four slices: tree hashing (I1), source resolution
(I2), manifest scan + environment descriptor (I3), and the public seam +
docs (I4). Nothing here emits a verdict — intake produces pinned records the
run and verdict layers consume.
"""

from __future__ import annotations