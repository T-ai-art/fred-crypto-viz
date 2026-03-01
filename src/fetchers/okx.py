"""
OKX Fetcher — XAUt-USDT candle data
Refactored from geopolitical_risk_analyzer.py fetch_xaut()

API: https://www.okx.com/api/v5/market/history-candles
  - instId: XAUT-USDT
  - bar: 1m|5m|15m|1H|4H|1D
  - limit: 100 (max per request)
  - after: oldest_timestamp_ms (pagination, goes backwards in time)

Returns: List of [timestamp_sec, open, high, low, close, volume]
"""

import json
import ssl
import time
import urllib.request

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

BAR_MAP = {
    '1m': '1m', '5m': '5m', '15m': '15m',
    '1H': '1H', '4H': '4Hutc', '1D': '1Dutc',
}


def fetch(start_ts, end_ts, granularity='1H', inst_id='XAUT-USDT',
          rate_limit=0.1, max_pages=200, verbose=True):
    """
    Fetch OHLCV candles from OKX.

    Args:
        start_ts: Unix timestamp (seconds), start of range
        end_ts:   Unix timestamp (seconds), end of range
        granularity: '1m','5m','15m','1H','4H','1D'
        inst_id:  OKX instrument ID
        rate_limit: delay between requests (seconds)
        max_pages: safety limit on pagination
        verbose: print progress

    Returns:
        List of [timestamp_sec, open, high, low, close, volume]
        sorted by timestamp ascending
    """
    bar = BAR_MAP.get(granularity, '1H')
    ctx = ssl.create_default_context()
    all_candles = {}  # ts -> candle, for dedup

    after_param = ''
    for page in range(max_pages):
        url = (f'https://www.okx.com/api/v5/market/history-candles'
               f'?instId={inst_id}&bar={bar}&limit=100')
        if after_param:
            url += f'&after={after_param}'

        try:
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                body = json.loads(resp.read().decode())
        except Exception as e:
            if verbose:
                print(f'  [OKX] Page {page} error: {e}')
            break

        rows = body.get('data', [])
        if not rows:
            break

        reached_start = False
        for row in rows:
            ts_ms = int(row[0])
            ts = ts_ms // 1000
            if ts < start_ts:
                reached_start = True
                continue
            if ts > end_ts:
                continue
            all_candles[ts] = [
                ts,
                float(row[1]),  # open
                float(row[2]),  # high
                float(row[3]),  # low
                float(row[4]),  # close
                float(row[5]) if row[5] else 0.0,  # volume
            ]

        if reached_start:
            break

        # Paginate: OKX returns newest first, last row is oldest
        after_param = str(rows[-1][0])
        time.sleep(rate_limit)

    result = sorted(all_candles.values(), key=lambda x: x[0])
    if verbose:
        print(f'  [OKX] {inst_id} {granularity}: {len(result)} candles '
              f'({_fmt_ts(result[0][0]) if result else "N/A"} → '
              f'{_fmt_ts(result[-1][0]) if result else "N/A"})')
    return result


def _fmt_ts(ts):
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
