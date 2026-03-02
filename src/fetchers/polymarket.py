"""
Polymarket Fetcher — Multiple Iran-related prediction markets (implied probability)

Supports 3 active markets:
  1. Hormuz: Will Iran close the Strait of Hormuz by March 31?
  2. Ceasefire: US x Iran ceasefire by End of March?
  3. Regime: Will the Iranian regime fall by June 30?

API: https://clob.polymarket.com/prices-history
  - market: token_id (Yes outcome)
  - startTs: unix timestamp (seconds)
  - endTs: unix timestamp (seconds)
  - fidelity: accuracy in minutes (1, 5, 15, 60, 240, 1440)

Returns: List of [timestamp_sec, prob_pct, prob_pct, prob_pct, prob_pct, 0]
  where prob_pct = probability * 100 (0-100 range)
  OHLCV-compatible format: O=H=L=C=probability, V=0
"""

import json
import ssl
import time
import urllib.request

# ========== TOKEN IDs (Yes outcomes) ==========
# To obtain these, run: python3 lookup_tokens.py on your Mac
# and copy the Yes token IDs here.

# "Will Iran close the Strait of Hormuz by March 31, 2026?" — Yes token
TOKEN_HORMUZ = "11259214629259962188961658360673801608680858594287954976598964541495296876564"

# "US x Iran ceasefire by End of March?" — Yes token
TOKEN_CEASEFIRE = "5708561660601459805512817131601230493971589760294984590237789749933853841330"

# "Will the Iranian regime fall by June 30, 2026?" — Yes token
TOKEN_REGIME = "38397507750621893057346880033441136112987238933685677349709401910643842844855"

# Legacy: "US strikes Iran by February 28, 2026?" — Yes token (resolved)
TOKEN_IRAN_FEB28_YES = (
    "110790003121442365126855864076707686014650523258783405996925622264696084778807"
)

# ========== MARKET REGISTRY ==========
MARKETS = {
    'hormuz': {
        'token_id': TOKEN_HORMUZ,
        'question': 'Will Iran close the Strait of Hormuz by March 31, 2026?',
        'label': 'Hormuz Closure %',
        'active': True,
    },
    'ceasefire': {
        'token_id': TOKEN_CEASEFIRE,
        'question': 'US x Iran ceasefire by End of March?',
        'label': 'Ceasefire %',
        'active': True,
    },
    'regime': {
        'token_id': TOKEN_REGIME,
        'question': 'Will the Iranian regime fall by June 30, 2026?',
        'label': 'Regime Fall %',
        'active': True,
    },
    'iran_legacy': {
        'token_id': TOKEN_IRAN_FEB28_YES,
        'question': 'US strikes Iran by February 28, 2026?',
        'label': 'Iran Strike % (resolved)',
        'active': False,
    },
}

FIDELITY_MAP = {
    '1m': 1, '5m': 5, '15m': 15,
    '1H': 60, '4H': 240, '1D': 1440,
}


def fetch(start_ts, end_ts, granularity='1H', token_id=None,
          market_key=None, rate_limit=0.2, verbose=True):
    """
    Fetch implied probability history from Polymarket CLOB API.

    Args:
        start_ts: Unix timestamp (seconds), start of range
        end_ts:   Unix timestamp (seconds), end of range
        granularity: '1m','5m','15m','1H','4H','1D'
        token_id: Polymarket token ID (overrides market_key)
        market_key: Key from MARKETS dict ('hormuz','ceasefire','regime')
        rate_limit: delay between requests (seconds)
        verbose: print progress

    Returns:
        List of [timestamp_sec, prob_pct, prob_pct, prob_pct, prob_pct, 0]
        sorted by timestamp ascending.
        prob_pct = probability * 100 (0 = 0%, 100 = 100%)
    """
    if token_id is None:
        if market_key and market_key in MARKETS:
            token_id = MARKETS[market_key]['token_id']
        else:
            token_id = TOKEN_IRAN_FEB28_YES

    # Determine label for verbose output
    label = market_key or 'unknown'
    for k, v in MARKETS.items():
        if v['token_id'] == token_id:
            label = k
            break

    fidelity = FIDELITY_MAP.get(granularity, 60)
    ctx = ssl.create_default_context()
    all_points = {}

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
                print(f'  [Polymarket/{label}] Chunk {page} error: {e}')
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
            print(f'  [Polymarket/{label}] Chunk {page}: {len(history)} points '
                  f'({_fmt_ts(current_start)} -> {_fmt_ts(chunk_end)})')

        current_start = chunk_end
        page += 1
        if page > 1:
            time.sleep(rate_limit)

    result = sorted(all_points.values(), key=lambda x: x[0])
    if verbose:
        print(f'  [Polymarket/{label}] {granularity}: {len(result)} points '
              f'({_fmt_ts(result[0][0]) if result else "N/A"} -> '
              f'{_fmt_ts(result[-1][0]) if result else "N/A"})')
    return result


def _fmt_ts(ts):
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
