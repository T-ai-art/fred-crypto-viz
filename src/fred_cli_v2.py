#!/usr/bin/env python3
"""
FRED Crypto Viz v2 — CLI for fetching data and generating
live-refresh HTML visualization page.

Changes from v1:
- Uses html_builder_v2 (live-refresh, updated colors, refresh button)
- 3 Polymarket markets: Hormuz, Ceasefire, Regime
- SPYx removed (low liquidity)
- Same fetch logic as v1; v2 features are in the HTML/JS layer

Usage:
  # Auto mode: fetch all granularities
  python3 fred_cli_v2.py --auto --outdir ../docs/ --cdn --no-open --password "xxx"

  # Quick test
  python3 fred_cli_v2.py --assets xaut,btc --xaut-sources bitfinex --days 7 --granularities 1H --cdn --no-open
"""

import argparse
import datetime
import json
import os
import sys
import time

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetchers import okx, bitfinex, binance, polymarket
import html_builder_v2 as html_builder


# ========== DEFAULTS ==========

AUTO_FETCH_PLAN = {
    # granularity: days_to_fetch
    '1m':  7,
    '5m':  30,
    '15m': 30,
    '1H':  90,
    '4H':  180,
    '1D':  365,
}

ALL_GRANULARITIES = ['1m', '5m', '15m', '1H', '4H', '1D']


def parse_args():
    p = argparse.ArgumentParser(
        description='FRED Crypto Viz v2 — Data Fetcher & HTML Generator')

    p.add_argument('--auto', action='store_true',
                   help='Auto mode: fetch all granularities with default periods')
    p.add_argument('--assets', default='xaut,btc,iran,hormuz,ceasefire,regime',
                   help='Comma-separated assets: xaut,btc,iran,hormuz,ceasefire,regime (default: all)')
    p.add_argument('--xaut-sources', default='okx,bitfinex',
                   help='Comma-separated XAUt sources: okx,bitfinex (default: both)')
    p.add_argument('--days', type=int, default=None,
                   help='Days to fetch (overrides auto plan)')
    p.add_argument('--start', default=None,
                   help='Start date: YYYY-MM-DD')
    p.add_argument('--end', default=None,
                   help='End date: YYYY-MM-DD (default: now)')
    p.add_argument('--granularities', default=None,
                   help='Comma-separated: 1m,5m,15m,1H,4H,1D')
    p.add_argument('--outdir', default='.',
                   help='Output directory (default: current dir)')
    p.add_argument('--cdn', action='store_true',
                   help='Use CDN for Chart.js (for GitHub Pages)')
    p.add_argument('--no-open', action='store_true',
                   help='Do not open browser after generation')
    p.add_argument('--password', default=None,
                   help='Password to encrypt the HTML data (AES-256-GCM).')
    p.add_argument('--verbose', action='store_true', default=True,
                   help='Verbose output')

    return p.parse_args()


def main():
    args = parse_args()
    now = int(time.time())

    assets = [a.strip().lower() for a in args.assets.split(',')]
    xaut_sources = [s.strip().lower() for s in args.xaut_sources.split(',')]

    if args.granularities:
        granularities = [g.strip() for g in args.granularities.split(',')]
    elif args.auto:
        granularities = ALL_GRANULARITIES
    else:
        granularities = ['1H']

    # Determine time ranges per granularity
    fetch_plan = {}
    for gran in granularities:
        if args.start:
            start_ts = _parse_date(args.start)
        elif args.days:
            start_ts = now - args.days * 86400
        elif args.auto:
            days = AUTO_FETCH_PLAN.get(gran, 30)
            start_ts = now - days * 86400
        else:
            start_ts = now - 30 * 86400

        if args.end:
            end_ts = _parse_date(args.end) + 86400
        else:
            end_ts = now

        fetch_plan[gran] = (start_ts, end_ts)

    # ========== FETCH DATA ==========
    all_data = {}
    total_candles = 0

    for gran in granularities:
        start_ts, end_ts = fetch_plan[gran]
        print(f'\n=== Granularity: {gran} ({_fmt_ts(start_ts)} → {_fmt_ts(end_ts)}) ===')

        # XAUt sources
        if 'xaut' in assets:
            if 'okx' in xaut_sources:
                print(f'  Fetching XAUt from OKX...')
                try:
                    data = okx.fetch(start_ts, end_ts, gran, verbose=args.verbose)
                    all_data[f'xaut_okx_{gran}'] = data
                    total_candles += len(data)
                except Exception as e:
                    print(f'  [ERROR] OKX fetch failed: {e}')
                    all_data[f'xaut_okx_{gran}'] = []

            if 'bitfinex' in xaut_sources:
                print(f'  Fetching XAUt from Bitfinex...')
                try:
                    data = bitfinex.fetch(start_ts, end_ts, gran, verbose=args.verbose)
                    all_data[f'xaut_bitfinex_{gran}'] = data
                    total_candles += len(data)
                except Exception as e:
                    print(f'  [ERROR] Bitfinex fetch failed: {e}')
                    all_data[f'xaut_bitfinex_{gran}'] = []

        # BTC
        if 'btc' in assets:
            print(f'  Fetching BTC from Binance...')
            try:
                data = binance.fetch(start_ts, end_ts, gran, verbose=args.verbose)
                all_data[f'btc_binance_{gran}'] = data
                total_candles += len(data)
            except Exception as e:
                print(f'  [ERROR] Binance fetch failed: {e}')
                all_data[f'btc_binance_{gran}'] = []

        # US Strikes Iran Probability (Polymarket — resolved)
        if 'iran' in assets:
            print(f'  Fetching Iran Strike prob from Polymarket...')
            try:
                data = polymarket.fetch(start_ts, end_ts, gran,
                                        market_key='iran_legacy',
                                        verbose=args.verbose)
                all_data[f'iran_polymarket_{gran}'] = data
                total_candles += len(data)
            except Exception as e:
                print(f'  [ERROR] Polymarket Iran fetch failed: {e}')
                all_data[f'iran_polymarket_{gran}'] = []

        # Hormuz Strait Closure Probability (Polymarket)
        if 'hormuz' in assets:
            print(f'  Fetching Hormuz prob from Polymarket...')
            try:
                data = polymarket.fetch(start_ts, end_ts, gran,
                                        market_key='hormuz',
                                        verbose=args.verbose)
                all_data[f'hormuz_polymarket_{gran}'] = data
                total_candles += len(data)
            except Exception as e:
                print(f'  [ERROR] Polymarket Hormuz fetch failed: {e}')
                all_data[f'hormuz_polymarket_{gran}'] = []

        # US x Iran Ceasefire Probability (Polymarket)
        if 'ceasefire' in assets:
            print(f'  Fetching Ceasefire prob from Polymarket...')
            try:
                data = polymarket.fetch(start_ts, end_ts, gran,
                                        market_key='ceasefire',
                                        verbose=args.verbose)
                all_data[f'ceasefire_polymarket_{gran}'] = data
                total_candles += len(data)
            except Exception as e:
                print(f'  [ERROR] Polymarket Ceasefire fetch failed: {e}')
                all_data[f'ceasefire_polymarket_{gran}'] = []

        # Iranian Regime Fall Probability (Polymarket)
        if 'regime' in assets:
            print(f'  Fetching Regime prob from Polymarket...')
            try:
                data = polymarket.fetch(start_ts, end_ts, gran,
                                        market_key='regime',
                                        verbose=args.verbose)
                all_data[f'regime_polymarket_{gran}'] = data
                total_candles += len(data)
            except Exception as e:
                print(f'  [ERROR] Polymarket Regime fetch failed: {e}')
                all_data[f'regime_polymarket_{gran}'] = []

    print(f'\n=== Total: {total_candles} candles across {len(all_data)} series ===')

    # ========== GENERATE HTML ==========
    meta = {
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'assets': assets,
        'xaut_sources': xaut_sources,
        'granularities': granularities,
        'total_candles': total_candles,
        'version': 'v2',
    }

    html = html_builder.build_html(all_data, meta, cdn=args.cdn, password=args.password)

    # Write output
    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = len(html.encode('utf-8')) / 1024
    print(f'\nHTML v2 generated: {out_path} ({size_kb:.0f} KB)')
    if args.password:
        print(f'  🔒 Password protection: ENABLED (AES-256-GCM encrypted)')

    # Timestamped archive copy
    ts_str = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M')
    archive_path = os.path.join(args.outdir, f'crypto_data_v2_{ts_str}.html')
    with open(archive_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Archive copy: {archive_path}')

    # Open in browser
    if not args.no_open:
        import webbrowser
        webbrowser.open('file://' + os.path.abspath(out_path))

    return 0


def _parse_date(s):
    parts = s.split('-')
    dt = datetime.datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    return int(dt.timestamp())


def _fmt_ts(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')


if __name__ == '__main__':
    sys.exit(main())
