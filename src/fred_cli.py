#!/usr/bin/env python3
"""
FRED Crypto Viz — CLI for fetching XAUt & BTC data and generating
an interactive FRED-like HTML visualization page.

Usage:
  # Auto mode (GitHub Actions): fetch all granularities
  python3 fred_cli.py --auto --outdir docs/

  # Manual: specific assets/sources/period
  python3 fred_cli.py --assets xaut,btc --xaut-sources okx,bitfinex \\
      --days 30 --granularities 1H,1D --outdir docs/

  # Minimal: just XAUt from OKX, 7 days, 1H
  python3 fred_cli.py --assets xaut --xaut-sources okx --days 7 \\
      --granularities 1H
"""

import argparse
import datetime
import json
import os
import sys
import time

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetchers import okx, bitfinex, binance, mexc
import html_builder


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
        description='FRED Crypto Viz — Data Fetcher & HTML Generator')

    p.add_argument('--auto', action='store_true',
                   help='Auto mode: fetch all granularities with default periods')
    p.add_argument('--assets', default='xaut,btc,spyx',
                   help='Comma-separated assets: xaut,btc,spyx (default: xaut,btc,spyx)')
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
                   help='Password to encrypt the HTML data (AES-256-GCM). '
                        'If set, viewers must enter this password to see charts/data.')
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
            start_ts = now - 30 * 86400  # default 30 days

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

        # SPYx (SP500 xStock)
        if 'spyx' in assets:
            print(f'  Fetching SPYx from MEXC...')
            try:
                data = mexc.fetch(start_ts, end_ts, gran,
                                  symbol='SPYXUSDT', verbose=args.verbose)
                all_data[f'spyx_mexc_{gran}'] = data
                total_candles += len(data)
            except Exception as e:
                print(f'  [ERROR] MEXC SPYx fetch failed: {e}')
                all_data[f'spyx_mexc_{gran}'] = []

    print(f'\n=== Total: {total_candles} candles across {len(all_data)} series ===')

    # ========== GENERATE HTML ==========
    meta = {
        'generated_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'assets': assets,
        'xaut_sources': xaut_sources,
        'granularities': granularities,
        'total_candles': total_candles,
    }

    html = html_builder.build_html(all_data, meta, cdn=args.cdn, password=args.password)

    # Write output
    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, 'index.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = len(html.encode('utf-8')) / 1024
    print(f'\nHTML generated: {out_path} ({size_kb:.0f} KB)')
    if args.password:
        print(f'  🔒 Password protection: ENABLED (AES-256-GCM encrypted)')

    # Also generate a timestamped archive copy
    ts_str = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M')
    archive_path = os.path.join(args.outdir, f'crypto_data_{ts_str}.html')
    with open(archive_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Archive copy: {archive_path}')

    # Open in browser
    if not args.no_open:
        import webbrowser
        webbrowser.open('file://' + os.path.abspath(out_path))

    return 0


def _parse_date(s):
    """Parse YYYY-MM-DD to unix timestamp."""
    parts = s.split('-')
    dt = datetime.datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    return int(dt.timestamp())


def _fmt_ts(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M')


if __name__ == '__main__':
    sys.exit(main())
