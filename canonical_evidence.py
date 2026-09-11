"""Read sealed scanner evidence; downstream readers never refresh market data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def read_evidence(name: str, out: Path = Path('output')) -> dict:
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'PASS' or not manifest.get('run_id'):
        raise RuntimeError('CANONICAL_MANIFEST_NOT_PASS')
    rows = [r for r in manifest.get('authoritative_files', []) if r.get('name') == name]
    path = out / name
    if len(rows) != 1 or not path.is_file():
        raise RuntimeError(f'CANONICAL_EVIDENCE_MISSING:{name}')
    if hashlib.sha256(path.read_bytes()).hexdigest() != rows[0].get('sha256'):
        raise RuntimeError(f'CANONICAL_EVIDENCE_HASH_MISMATCH:{name}')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('source_run_id', payload.get('run_id')) != manifest['run_id']:
        raise RuntimeError(f'CANONICAL_EVIDENCE_RUN_MISMATCH:{name}')
    return payload


def encode_histories(histories: dict[str, pd.DataFrame]) -> dict:
    result = {}
    for ticker, hist in histories.items():
        if hist is None or hist.empty or 'Close' not in hist:
            continue
        h = hist.dropna(subset=['Close']).tail(160).copy()
        h = h[[c for c in ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume'] if c in h]]
        h.index = pd.DatetimeIndex(h.index).strftime('%Y-%m-%d')
        result[ticker] = json.loads(h.to_json(orient='split'))
    return result


def load_histories(tickers: list[str], period: str = '6mo') -> dict[str, pd.DataFrame]:
    payload = read_evidence('market_snapshot.json')
    saved = payload.get('entry_histories')
    if not isinstance(saved, dict):
        raise RuntimeError('CANONICAL_ENTRY_HISTORY_MISSING_RESCAN_REQUIRED')
    cutoff = payload.get('canonical_closed_price_date')
    if not cutoff:
        raise RuntimeError('CANONICAL_ENTRY_CLOSED_DATE_MISSING')
    result = {}
    for ticker in tickers:
        item = saved.get(ticker)
        if item:
            frame = pd.DataFrame(item['data'], columns=item['columns'], index=pd.to_datetime(item['index']))
            if not frame.empty and str(frame.index[-1].date()) == cutoff:
                result[ticker] = frame
    return result


def assert_output_lineage(names: list[str], out: Path = Path('output')) -> str:
    from snapshot_lineage_v2 import assert_decision_snapshot_current
    run_id = assert_decision_snapshot_current(out)['run_id']
    board_path = out / 'decision_board.csv'
    if 'decision_packet.json' in names and board_path.exists():
        board = pd.read_csv(board_path)
        if 'run_id' not in board or set(board['run_id'].dropna().astype(str)) != {run_id}:
            raise RuntimeError('OUTPUT_LINEAGE_MISMATCH:decision_board.csv')
    for name in names:
        p = json.loads((out / name).read_text(encoding='utf-8'))
        if p.get('source_run_id', p.get('run_id')) != run_id:
            raise RuntimeError(f'OUTPUT_LINEAGE_MISMATCH:{name}')
    return run_id
