import hashlib
import json
from pathlib import Path

def test_all_frozen_v1_sha256_hashes_match():
    root=Path(__file__).resolve().parents[1]
    registry=json.loads((root/'config/frozen_strategy_v1.json').read_text())
    assert len(registry['file_hashes'])==14
    for name,expected in registry['file_hashes'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
