"""
Bitfinex Fetcher — XAUt/USD candle data (NEW)

API: https://api-pub.bitfinex.com/v2/candles/trade:{timeframe}:{symbol}/hist
  - symbol: tXAUT:USD (NOTE: colon required for tokenized assets!)
  - timeframe: 1m|5m|15m|30m|1h|3h|6h|12h|1D|1W|14D|1M
  - limit: up to 10000 per request
  - start: ms timestamp (oldest boundary)
  - end: ms timestamp (newest boundary)
  - sort: 1 = oldest first, -1 = newest first

Response: [[MTS, OPEN, CLOSE, HIGH, LOW, VOLUME], ...]
  NOTE: Bitfinex order is O,C,H,L — NOT O,H,L,C like OKX/Binance!

Returns: List of [timestamp_sec, open, high, low, close, volume]
         (normalized to standard OHLCV order)
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

TIMEFRAME_MAP = {
    '1m': '1m', '5m': '5m', '15m': '15m',
    '1H': '1h', '4H': '4h', '1D': '1D',
}


def fetch(start_ts, end_ts, granularity='1H', symbol='tXAUT:USD',
          rate_limit=1.0, max_pages=100, verbose=True):
    """
    Fetch OHLCV candles from Bitfinex.

    Args:
        start_ts: Unix timestamp (seconds), start of range
        end_ts:   Unix timestamp (seconds), end of range
        granularity: '1m','5m','15m','1H','4H','1D'
        symbol:  Bitfinex symbol (e.g. 'tXAUTUSD')
        rate_limit: delay between requests (seconds) — Bitfinex is strict
        max_pages: safety limit on pagination
        verbose: print progress

    Returns:
        List of [timestamp_sec, open, high, low, close, volume]
        sorted by timestamp ascending
    """
    tf = TIMEFRAME_MAP.get(granularity, '1h')
    ctx = ssl.create_default_context()
    all_candles = {}  # ts -> candle, for dedup

    current_start_ms = start_ts * 1000
    end_ms = end_ts * 1000

    for page in range(max_pages):
        # URL-encode the symbol (colon → %3A) for tokenized assets like tXAUT:USD
        sym_encoded = symbol.replace(':', '%3A')
        url = (f'https://api-pub.bitfinex.com/v2/candles'
               f'/trade:{tf}:{sym_encoded}/hist'
               f'?limit=10000&start={current_start_ms}&end={end_ms}&sort=1')

        try:
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                rows = json.loads(resp.read().decode())
        except Exception as e:
            if verbose:
                print(f'  [Bitfinex] Page {page} error: {e}')
            break

        if not rows or not isinstance(rows, list):
            break
        if isinstance(rows[0], dict):
            # Error response
            if verbose:
                print(f'  [Bitfinex] API error: {rows}')
            break

        for row in rows:
            # Bitfinex: [MTS, OPEN, CLOSE, HIGH, LOW, VOLUME]
            mts = int(row[0])
            ts = mts // 1000
            if ts < start_ts or ts > end_ts:
                continue
            # Normalize to standard OHLCV: open, HIGH, LOW, close, volume
            all_candles[ts] = [
                ts,
                float(row[1]),  # open
                float(row[3]),  # high  (index 3 in Bitfinex!)
                float(row[4]),  # low   (index 4 in Bitfinex!)
                float(row[2]),  # close (index 2 in Bitfinex!)
                float(row[5]) if row[5] else 0.0,  # volume
            ]

        if len(rows) < 10000:
            # Last page
            break

        # Paginate forward: start after last timestamp
        last_mts = int(rows[-1][0])
        current_start_ms = last_mts + 1
        if current_start_ms >= end_ms:
            break

        time.sleep(rate_limit)

    result = sorted(all_candles.values(), key=lambda x: x[0])
    if verbose:
        print(f'  [Bitfinex] {symbol} {granularity}: {len(result)} candles '
              f'({_fmt_ts(result[0][0]) if result else "N/A"} → '
              f'{_fmt_ts(result[-1][0]) if result else "N/A"})')
    return result


def _fmt_ts(ts):
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
