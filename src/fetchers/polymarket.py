"""
Polymarket Fetcher — US strikes Iran by Feb 28, 2026 (implied probability)

API: https://clob.polymarket.com/prices-history
  - market: token_id (Yes outcome)
  - startTs: unix timestamp (seconds)
  - endTs: unix timestamp (seconds)
  - fidelity: accuracy in minutes (1, 5, 15, 60, 240, 1440)

Response format:
  {"history": [{"t": unix_ts, "p": price_0_to_1}, ...]}

Returns: List of [timestamp_sec, prob_pct, prob_pct, prob_pct, prob_pct, 0]
  where prob_pct = probability * 100 (0-100 range)
  OHLCV-compatible format: O=H=L=C=probability, V=0
"""

import json
import ssl
import time
import urllib.request

# "US strikes Iran by February 28, 2026?" — Yes token
TOKEN_IRAN_FEB28_YES = (
    "110790003121442365126855864076707686014650523258783405996925622264696084778807"
)

# Market metadata
MARKET_INFO = {
    'id': '1198423',
    'question': 'US strikes Iran by February 28, 2026?',
    'slug': 'us-strikes-iran-by-february-28-2026',
    'volume': 89652867.36,
    'conditionId': '0x3488f31e6449f9803f99a8b5dd232c7ad883637f1c86e6953305a2ef19c77f20',
    'resolved': True,
    'outcome': 'Yes',
    'event_date': '2026-02-28T06:15:00Z',  # Operation Epic Fury start (UTC)
}

FIDELITY_MAP = {
    '1m': 1, '5m': 5, '15m': 15,
    '1H': 60, '4H': 240, '1D': 1440,
}


def fetch(start_ts, end_ts, granularity='1H', token_id=None,
          rate_limit=0.2, verbose=True):
    """
    Fetch implied probability history from Polymarket CLOB API.

    Args:
        start_ts: Unix timestamp (seconds), start of range
        end_ts:   Unix timestamp (seconds), end of range
        granularity: '1m','5m','15m','1H','4H','1D'
        token_id: Polymarket token ID (default: Iran Feb 28 Yes)
        rate_limit: delay between requests (seconds)
        verbose: print progress

    Returns:
        List of [timestamp_sec, prob_pct, prob_pct, prob_pct, prob_pct, 0]
        sorted by timestamp ascending.
        prob_pct = probability * 100 (0 = 0%, 100 = 100%)
    """
    if token_id is None:
        token_id = TOKEN_IRAN_FEB28_YES

    fidelity = FIDELITY_MAP.get(granularity, 60)
    ctx = ssl.create_default_context()
    all_points = {}

    # Polymarket API can return a lot of data in one call,
    # but for long ranges we may need to paginate by chunks
    chunk_size = 86400 * 7  # 7 days per chunk
    current_start = start_ts

    page = 0
    while current_start < end_ts:
        chunk_end = min(current_start + chunk_size, end_ts)

        url = (f'https://clob.polymarket.com/prices-history'
               f'?market={token_id}'
               f'&startTs={current_start}'
               f'&endTs={chunk_end}'
               f'&fidelity={fidelity}')

        try:
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                                  'Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json',
                }
            )
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            if verbose:
                print(f'  [Polymarket] Chunk {page} error: {e}')
            current_start = chunk_end
            page += 1
            continue

        history = data.get('history', [])
        for point in history:
            ts = int(point['t'])
            p = float(point['p'])
            prob_pct = round(p * 100, 2)
            if start_ts <= ts <= end_ts:
                all_points[ts] = [
                    ts,
                    prob_pct,  # open
                    prob_pct,  # high
                    prob_pct,  # low
                    prob_pct,  # close
                    0.0,       # volume (not applicable)
                ]

        if verbose and history:
            print(f'  [Polymarket] Chunk {page}: {len(history)} points '
                  f'({_fmt_ts(current_start)} -> {_fmt_ts(chunk_end)})')

        current_start = chunk_end
        page += 1
        if page > 1:
            time.sleep(rate_limit)

    result = sorted(all_points.values(), key=lambda x: x[0])
    if verbose:
        print(f'  [Polymarket] Iran Feb28 {granularity}: {len(result)} points '
              f'({_fmt_ts(result[0][0]) if result else "N/A"} -> '
              f'{_fmt_ts(result[-1][0]) if result else "N/A"})')
    return result


def _fmt_ts(ts):
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
