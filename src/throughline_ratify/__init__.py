# Copyright (c) 2026 Henry J Grech-Cini
# SPDX-License-Identifier: Apache-2.0
"""throughline-ratify — a full-screen terminal companion for
working through the throughline items that await human ratification."""
from __future__ import annotations

from throughline.version import distribution_version

# Read from the installed distribution, and marked when that install is a working
# tree rather than the release it derives from (SR-0031). The header shows this
# value, so a pipx build and a checkout that would otherwise print the same string
# are told apart at a glance — which is the failure that wrote the requirement.
__version__ = distribution_version("throughline-ratify")

__all__ = ["__version__"]
