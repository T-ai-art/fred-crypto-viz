"""
Multi-source data merger
Merges candle data from multiple exchanges, handling timestamp alignment and dedup.
"""


def merge_sources(series_dict):
    """
    Merge multiple source series into a unified timeline.
    Each source keeps its own column; timestamps are unioned.

    Args:
        series_dict: dict of {source_key: candle_list}
            source_key: e.g. 'xaut_okx', 'xaut_bitfinex', 'btc_binance'
            candle_list: [[ts, o, h, l, c, v], ...]

    Returns:
        dict: {
            'timestamps': [ts1, ts2, ...],
            'series': {
                'xaut_okx': {ts1: [o,h,l,c,v], ts2: None, ...},
                ...
            }
        }
    """
    # Collect all unique timestamps
    all_ts = set()
    indexed = {}
    for key, candles in series_dict.items():
        ts_map = {}
        for c in candles:
            ts_map[c[0]] = c[1:]  # [o, h, l, c, v]
            all_ts.add(c[0])
        indexed[key] = ts_map

    timestamps = sorted(all_ts)

    return {
        'timestamps': timestamps,
        'series': indexed,
    }


def to_csv_rows(merged, series_keys=None):
    """
    Convert merged data to CSV rows.

    Args:
        merged: output of merge_sources()
        series_keys: list of keys to include (default: all)

    Returns:
        list of dicts (one per timestamp)
    """
    import datetime
    if series_keys is None:
        series_keys = list(merged['series'].keys())

    rows = []
    for ts in merged['timestamps']:
        row = {
            'timestamp': ts,
            'datetime': datetime.datetime.utcfromtimestamp(ts).strftime(
                '%Y-%m-%dT%H:%M:%SZ'),
        }
        for key in series_keys:
            vals = merged['series'][key].get(ts)
            if vals:
                row[f'{key}_open'] = vals[0]
                row[f'{key}_high'] = vals[1]
                row[f'{key}_low'] = vals[2]
                row[f'{key}_close'] = vals[3]
                row[f'{key}_volume'] = vals[4]
            else:
                row[f'{key}_open'] = ''
                row[f'{key}_high'] = ''
                row[f'{key}_low'] = ''
                row[f'{key}_close'] = ''
                row[f'{key}_volume'] = ''
        rows.append(row)
    return rows
