"""
Binance Fetcher — BTCUSDT candle data
Refactored from geopolitical_risk_analyzer.py fetch_btc()

API: https://api.binance.com/api/v3/klines
  - symbol: BTCUSDT
  - interval: 1m|5m|15m|1h|4h|1d
  - startTime: ms
  - endTime: ms
  - limit: 1000 (max per request)

Response: [[openTime, O, H, L, C, V, closeTime, ...], ...]

Returns: List of [timestamp_sec, open, high, low, close, volume]
"""

import json
import ssl
import time
import urllib.request

INTERVAL_MAP = {
    '1m': '1m', '5m': '5m', '15m': '15m',
    '1H': '1h', '4H': '4h', '1D': '1d',
}


def fetch(start_ts, end_ts, granularity='1H', symbol='BTCUSDT',
          rate_limit=0.1, max_pages=100, verbose=True):
    """
    Fetch OHLCV candles from Binance.

    Args:
        start_ts: Unix timestamp (seconds), start of range
        end_ts:   Unix timestamp (seconds), end of range
        granularity: '1m','5m','15m','1H','4H','1D'
        symbol:  Binance symbol (e.g. 'BTCUSDT')
        rate_limit: delay between requests (seconds)
        max_pages: safety limit on pagination
        verbose: print progress

    Returns:
        List of [timestamp_sec, open, high, low, close, volume]
        sorted by timestamp ascending
    """
    interval = INTERVAL_MAP.get(granularity, '1h')
    ctx = ssl.create_default_context()
    all_candles = {}  # ts -> candle, for dedup

    current_start_ms = start_ts * 1000
    end_ms = end_ts * 1000

    for page in range(max_pages):
        url = (f'https://api.binance.com/api/v3/klines'
               f'?symbol={symbol}&interval={interval}'
               f'&startTime={current_start_ms}&endTime={end_ms}&limit=1000')

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                rows = json.loads(resp.read().decode())
        except Exception as e:
            if verbose:
                print(f'  [Binance] Page {page} error: {e}')
            break

        if not rows:
            break

        for row in rows:
            # Binance: [openTime_ms, O, H, L, C, V, closeTime, ...]
            ts = int(row[0]) // 1000
            if ts < start_ts or ts > end_ts:
                continue
            all_candles[ts] = [
                ts,
                float(row[1]),  # open
                float(row[2]),  # high
                float(row[3]),  # low
                float(row[4]),  # close
                float(row[5]) if row[5] else 0.0,  # volume
            ]

        if len(rows) < 1000:
            # Last page
            break

        # Paginate forward
        last_ms = int(rows[-1][0])
        current_start_ms = last_ms + 1
        if current_start_ms >= end_ms:
            break

        time.sleep(rate_limit)

    result = sorted(all_candles.values(), key=lambda x: x[0])
    if verbose:
        print(f'  [Binance] {symbol} {granularity}: {len(result)} candles '
              f'({_fmt_ts(result[0][0]) if result else "N/A"} → '
              f'{_fmt_ts(result[-1][0]) if result else "N/A"})')
    return result


def _fmt_ts(ts):
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
