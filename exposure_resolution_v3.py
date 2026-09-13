from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUT = Path("output")
RAW = OUT / "research_result_v3.raw.txt"
CACHE = OUT / "exposure_resolution_v3.json"
HANDOFF = Path("/tmp/research_handoff.json")
CONTRACT = "ALPHA_HUNTER_V3_EXPOSURE_RESOLUTION_CACHE"
MAX_AGE_DAYS = 120
