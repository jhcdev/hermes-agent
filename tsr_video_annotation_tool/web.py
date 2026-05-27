from __future__ import annotations

from importlib import resources
from pathlib import Path


def get_browser_bundle_root() -> Path:
    """Return the packaged static browser bundle directory."""

    bundle_root = resources.files("tsr_video_annotation_tool").joinpath("web_dist")
    return Path(str(bundle_root))
