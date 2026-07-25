# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""throughline-ratify — a full-screen terminal companion for
working through the throughline items that await human ratification."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("throughline-ratify")
except PackageNotFoundError:  # running from a source tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
