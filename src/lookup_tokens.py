#!/usr/bin/env python3
"""
Polymarket Token ID Lookup Tool

Queries the Gamma API via curl (bypasses Python SSL issues on macOS)
to find clobTokenIds for specific markets.

Usage:
    cd fred_crypto_viz/src
    python3 lookup_tokens.py
"""

import json
import subprocess

SLUGS = [
    # Hormuz Strait closure - End of March
    'will-iran-close-the-strait-of-hormuz-by-2027',
    # US x Iran ceasefire - End of March
    'us-x-iran-ceasefire-by',
    # Iranian regime fall
    'will-the-iranian-regime-fall-by-june-30',
]


def fetch_event(slug):
    url = f'https://gamma-api.polymarket.com/events?slug={slug}'
    result = subprocess.run(
        ['curl', '-s', '-H', 'Accept: application/json', url],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    return json.loads(result.stdout)


def main():
    print("=" * 70)
    print("Polymarket Token ID Lookup (curl version)")
    print("=" * 70)

    for slug in SLUGS:
        print(f"\n--- Event slug: {slug} ---")
        try:
            events = fetch_event(slug)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        for ev in events:
            title = ev.get('title', 'N/A')
            print(f"  Event: {title}")
            markets = ev.get('markets', [])
            print(f"  Markets count: {len(markets)}")

            for m in markets:
                q = m.get('question', '')
                vol = m.get('volume', 0)
                active = m.get('active')
                closed = m.get('closed')

                clob_ids = m.get('clobTokenIds')
                if isinstance(clob_ids, str):
                    clob_ids = json.loads(clob_ids)

                outcomes = m.get('outcomes')
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)

                prices = m.get('outcomePrices')
                if isinstance(prices, str):
                    prices = json.loads(prices)

                cond_id = m.get('conditionId', '')

                print(f"\n    Q: {q}")
                print(f"    Volume: ${vol:,.2f}" if vol else "    Volume: N/A")
                print(f"    Active: {active}, Closed: {closed}")
                print(f"    Outcomes: {outcomes}")
                print(f"    Prices: {prices}")
                print(f"    conditionId: {cond_id}")
                if clob_ids:
                    for i, tid in enumerate(clob_ids):
                        outcome_name = outcomes[i] if outcomes and i < len(outcomes) else f"Outcome {i}"
                        print(f"    Token[{outcome_name}]: {tid}")
                print()

    print("=" * 70)
    print("DONE. Copy the Yes token IDs above into polymarket.py")
    print("=" * 70)


if __name__ == '__main__':
    main()
