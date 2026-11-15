"""One-off model and data acquisition.

This is the **only** code that may use the network, and only while
``APERTURE_ALLOW_NETWORK=1`` (set by ``aperture fetch-models``).  Before
downloading anything it tries to *import* a copy you already have on this Mac
(e.g. ``~/.insightface`` or the Hugging Face cache), so a machine that already
ran these models needs no download at all.
"""

from __future__ import annotations
