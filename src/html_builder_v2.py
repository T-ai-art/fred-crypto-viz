"""
HTML Builder v2 — Live-refresh FRED-like interactive data visualization.

Changes from v1:
- Default: 1H granularity, 1-week period, Bitfinex only, BTC right axis
- Auto-refresh every 1 hour + manual refresh button
- Browser-side API fetching for live data updates
- Download fetches all granularities including 1m with latest data
- Updated colors: Linen (Bitfinex), Violet (BTC), Neutral Alt (OKX)
- Gray/inactive CSV/Excel buttons
"""

import json
import datetime
import os
import hashlib
import base64


def _encrypt_data(plaintext, password):
    """Encrypt plaintext with AES-256-GCM (same as v1)."""
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext.encode('utf-8'), None)
    except ImportError:
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f_in:
            f_in.write(plaintext.encode('utf-8'))
            in_path = f_in.name
        out_path = in_path + '.enc'
        try:
            subprocess.run([
                'openssl', 'enc', '-aes-256-gcm',
                '-in', in_path, '-out', out_path,
                '-K', key.hex(), '-iv', iv.hex(),
            ], check=True, capture_output=True)
            with open(out_path, 'rb') as f_out:
                ciphertext = f_out.read()
        finally:
            os.unlink(in_path)
            if os.path.exists(out_path):
                os.unlink(out_path)
    return {
        'salt': base64.b64encode(salt).decode(),
        'iv': base64.b64encode(iv).decode(),
        'ct': base64.b64encode(ciphertext).decode(),
    }


# =========================================================================
# CSS
# =========================================================================
_CSS = """
:root {
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #c9d1d9; --text-dim: #8b949e; --accent: #58a6ff;
  --gold-bfx: #CCB58A; --gold-okx: #DB7600;
  --btc: #834C82; --spyx: #a855f7; --iran: #ef4444;
  --green: #3fb950; --red: #f85149;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
.container { max-width:1400px; margin:0 auto; padding:16px; }
header { padding:24px 0 16px; border-bottom:1px solid var(--border); margin-bottom:16px; }
header h1 { font-size:24px; font-weight:600; color:#f0f6fc; }
header p { color:var(--text-dim); font-size:14px; margin-top:4px; }
.controls { display:flex; flex-wrap:wrap; gap:12px; padding:16px; background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:16px; align-items:center; }
.ctrl-group { display:flex; align-items:center; gap:8px; }
.ctrl-group label { font-size:13px; color:var(--text-dim); font-weight:600; text-transform:uppercase; letter-spacing:0.5px; white-space:nowrap; }
.ctrl-group input[type="checkbox"], .ctrl-group input[type="radio"] { accent-color:var(--accent); width:16px; height:16px; }
.ctrl-group .cb-label { font-size:14px; cursor:pointer; user-select:none; }
.ctrl-group .cb-label.disabled { color:var(--text-dim); opacity:0.4; cursor:not-allowed; }
.ctrl-group select, .ctrl-group input[type="date"] { background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:4px; padding:4px 8px; font-size:13px; }
.btn { background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:4px; padding:4px 12px; font-size:13px; cursor:pointer; transition:0.15s; }
.btn:hover { background:var(--border); }
.btn.active { background:var(--accent); color:#0d1117; border-color:var(--accent); }
.btn-refresh { background:#1f6feb; color:#fff; border-color:#1f6feb; font-weight:600; }
.btn-refresh:hover { background:#388bfd; }
.btn-refresh.loading { opacity:0.6; pointer-events:none; }
.btn-dl { background:#2d333b; color:#8b949e; border:1px solid #444c56; }
.btn-dl:hover { background:#444c56; color:#c9d1d9; }
.sep { width:1px; height:28px; background:var(--border); }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:16px; }
.stat-card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px; }
.stat-card .label { font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; }
.stat-card .value { font-size:22px; font-weight:600; margin-top:4px; }
.stat-card .change { font-size:13px; margin-top:2px; }
.stat-card .change.up { color:var(--green); }
.stat-card .change.down { color:var(--red); }
.chart-box { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:16px; }
.chart-box h3 { font-size:14px; color:var(--text-dim); margin-bottom:12px; }
.chart-wrap { position:relative; height:500px; width:100%; }
.data-info { font-size:12px; color:var(--text-dim); padding:8px 0; display:flex; justify-content:space-between; align-items:center; }
footer { border-top:1px solid var(--border); padding:16px 0; margin-top:16px; font-size:12px; color:var(--text-dim); display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }
footer a { color:var(--accent); text-decoration:none; }
@media (max-width:768px) {
  .controls { flex-direction:column; align-items:stretch; }
  .sep { display:none; }
  .chart-wrap { height:350px; }
}
"""

# =========================================================================
# HTML BODY (placeholder: __GENERATED_AT__)
# =========================================================================
_HTML_BODY = """
  <header>
    <h1>Crypto Asset Data Explorer <span style="font-size:14px;color:var(--text-dim)">v2</span></h1>
    <p>Tokenized Gold (XAUt) &amp; Right-Axis Asset &mdash; Live Refresh</p>
  </header>

  <div class="controls">
    <div class="ctrl-group">
      <label>Left Axis:</label>
      <input type="checkbox" id="cb-xaut" checked><span class="cb-label" onclick="document.getElementById('cb-xaut').click()"> XAUt</span>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <label>Source:</label>
      <input type="checkbox" id="cb-okx"><span class="cb-label" onclick="document.getElementById('cb-okx').click()"> OKX</span>
      <input type="checkbox" id="cb-bitfinex" checked><span class="cb-label" onclick="document.getElementById('cb-bitfinex').click()"> Bitfinex</span>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <label>Right Axis:</label>
      <input type="radio" name="right-axis" id="rb-btc" value="btc" checked onchange="render()"><span class="cb-label" onclick="document.getElementById('rb-btc').click()"> BTC</span>
      <input type="radio" name="right-axis" id="rb-spyx" value="spyx" onchange="render()"><span class="cb-label" onclick="document.getElementById('rb-spyx').click()"> SPYx</span>
      <input type="radio" name="right-axis" id="rb-iran" value="iran" onchange="render()"><span class="cb-label" onclick="document.getElementById('rb-iran').click()"> Iran %</span>
      <input type="radio" name="right-axis" id="rb-none" value="none" onchange="render()"><span class="cb-label" onclick="document.getElementById('rb-none').click()"> None</span>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <label>Period:</label>
      <input type="date" id="date-start">
      <span style="color:var(--text-dim)">to</span>
      <input type="date" id="date-end">
      <button class="btn period-btn active" onclick="setPeriod(7,this)">1W</button>
      <button class="btn period-btn" onclick="setPeriod(30,this)">1M</button>
      <button class="btn period-btn" onclick="setPeriod(90,this)">3M</button>
      <button class="btn period-btn" onclick="setPeriod(0,this)">ALL</button>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <label>Granularity:</label>
      <select id="sel-gran" onchange="render()">
        <option value="1m" selected>1 min</option>
        <option value="5m">5 min</option>
        <option value="15m">15 min</option>
        <option value="1H">1 hour</option>
        <option value="4H">4 hours</option>
        <option value="1D">1 day</option>
      </select>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <button class="btn btn-refresh" id="btn-refresh" onclick="refreshData()">&#8635; Refresh</button>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <button class="btn btn-dl" onclick="guardedExport('csv')">CSV</button>
      <button class="btn btn-dl" onclick="guardedExport('xlsx')">Excel</button>
    </div>
  </div>

  <div class="stats" id="stats-container"></div>

  <div class="chart-box">
    <h3 id="chart-title">Price Chart</h3>
    <div class="chart-wrap"><canvas id="main-chart"></canvas></div>
  </div>

  <div class="data-info">
    <span id="data-info-text"></span>
    <span id="last-update" style="color:var(--accent)">Built: __GENERATED_AT__</span>
  </div>

  <footer>
    <div>Sources: <a href="https://www.okx.com" target="_blank">OKX</a> | <a href="https://www.bitfinex.com" target="_blank">Bitfinex</a> | <a href="https://www.binance.com" target="_blank">Binance</a> | <a href="https://www.mexc.com" target="_blank">MEXC</a> | <a href="https://polymarket.com/event/us-strikes-iran-by" target="_blank">Polymarket</a></div>
    <div>Auto-refresh: 1h</div>
  </footer>

  <!-- Fetch Progress Modal -->
  <div id="fetch-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9998;align-items:center;justify-content:center;">
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:32px;max-width:400px;width:90%;text-align:center;">
      <div style="font-size:36px;margin-bottom:12px;">&#128202;</div>
      <h3 style="color:#f0f6fc;margin-bottom:6px;">Fetching Latest Data</h3>
      <p id="fetch-progress-text" style="color:var(--text-dim);font-size:13px;margin-bottom:16px;">Preparing...</p>
      <div style="background:#30363d;border-radius:4px;height:8px;overflow:hidden;">
        <div id="fetch-progress-bar" style="background:var(--accent);height:100%;border-radius:4px;width:0%;transition:width 0.3s;"></div>
      </div>
    </div>
  </div>

  <!-- Download Password Modal -->
  <div id="dl-modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:9999;align-items:center;justify-content:center;">
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:32px;max-width:380px;width:90%;text-align:center;">
      <div style="font-size:36px;margin-bottom:12px;">&#128274;</div>
      <h3 style="color:#f0f6fc;margin-bottom:6px;">Download Protected</h3>
      <p style="color:var(--text-dim);font-size:13px;margin-bottom:20px;">Enter the password to download data files.</p>
      <input type="password" id="dl-pw-input" placeholder="Password"
        style="width:100%;padding:10px 14px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;font-size:15px;margin-bottom:10px;outline:none;"
        onkeydown="if(event.key==='Enter')unlockDownload()">
      <div style="display:flex;gap:8px;">
        <button onclick="closeDownloadModal()"
          style="flex:1;padding:10px;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;font-size:14px;cursor:pointer;">Cancel</button>
        <button onclick="unlockDownload()"
          style="flex:1;padding:10px;background:var(--accent);color:#0d1117;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;">Unlock</button>
      </div>
      <div id="dl-pw-error" style="color:var(--red);font-size:13px;margin-top:10px;display:none;">Incorrect password.</div>
    </div>
  </div>
"""

# =========================================================================
# JAVASCRIPT APPLICATION CODE (regular string — no f-string escaping needed)
# =========================================================================
_JS_APP = r"""
// ========== CONFIG ==========
var chart = null;
var _refreshing = false;
var _autoRefreshInterval = null;

var COLORS = {
  xaut_okx:       {line:'#DB7600',fill:'rgba(219,118,0,0.10)',label:'XAUt (OKX)'},
  xaut_bitfinex:  {line:'#CCB58A',fill:'rgba(204,181,138,0.15)',label:'XAUt (Bitfinex)'},
  btc_binance:    {line:'#834C82',fill:'rgba(131,76,130,0.12)',label:'BTC (Binance)'},
  spyx_mexc:      {line:'#a855f7',fill:'rgba(168,85,247,0.08)',label:'SPYx (MEXC)'},
  iran_polymarket:{line:'#ef4444',fill:'rgba(239,68,68,0.12)',label:'Iran Strike % (Polymarket)'}
};

var RIGHT_AXIS_LABELS = {
  btc: 'BTC (USD)',
  spyx: 'SPYx (USD)',
  iran: 'Strike Probability (%)'
};
var PERCENT_ASSETS = ['iran'];

// Timeframe mappings per exchange
var TF = {
  bitfinex:  {'1m':'1m','5m':'5m','15m':'15m','1H':'1h','4H':'4h','1D':'1D'},
  binance:   {'1m':'1m','5m':'5m','15m':'15m','1H':'1h','4H':'4h','1D':'1d'},
  mexc:      {'1m':'1m','5m':'5m','15m':'15m','1H':'1h','4H':'4h','1D':'1d'},
  polymarket:{'1m':1,'5m':5,'15m':15,'1H':60,'4H':240,'1D':1440},
  okx:       {'1m':'1m','5m':'5m','15m':'15m','1H':'1H','4H':'4Hutc','1D':'1Dutc'}
};

var POLY_TOKEN = '110790003121442365126855864076707686014650523258783405996925622264696084778807';

// ========== UTILITY ==========
function sleep(ms) { return new Promise(function(r){setTimeout(r,ms);}); }
function tsToDate(ts) { var d=new Date(ts*1000); return d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate()); }
function dateToTs(str) { if(!str)return 0; var p=str.split('-'); return Math.floor(new Date(Date.UTC(+p[0],+p[1]-1,+p[2])).getTime()/1000); }
function pad2(n) { return n<10?'0'+n:''+n; }
function nowSec() { return Math.floor(Date.now()/1000); }

function getSelectedRight() {
  var radios = document.getElementsByName('right-axis');
  for (var i = 0; i < radios.length; i++) {
    if (radios[i].checked) return radios[i].value;
  }
  return 'btc';
}

// ========== API FETCHERS ==========
async function apiFetchBitfinex(startSec, endSec, gran) {
  var tf = TF.bitfinex[gran] || '1h';
  var results = {};
  var cursor = startSec * 1000;
  var endMs = endSec * 1000;
  for (var page = 0; page < 50; page++) {
    if (cursor >= endMs) break;
    try {
      var url = 'https://api-pub.bitfinex.com/v2/candles/trade:'+tf+':tXAUT%3AUSD/hist?limit=10000&start='+cursor+'&end='+endMs+'&sort=1';
      var resp = await fetch(url);
      var rows = await resp.json();
      if (!Array.isArray(rows) || rows.length === 0) break;
      rows.forEach(function(r) {
        var ts = Math.floor(r[0] / 1000);
        if (ts >= startSec && ts <= endSec) results[ts] = [ts, r[1], r[3], r[4], r[2], r[5]||0];
      });
      if (rows.length < 10000) break;
      cursor = rows[rows.length-1][0] + 1;
      await sleep(1000);
    } catch(e) { console.warn('Bitfinex fetch error:', e); break; }
  }
  return Object.values(results).sort(function(a,b){return a[0]-b[0];});
}

async function apiFetchBinance(startSec, endSec, gran) {
  var interval = TF.binance[gran] || '1h';
  var results = {};
  var cursor = startSec * 1000;
  var endMs = endSec * 1000;
  for (var page = 0; page < 200; page++) {
    if (cursor >= endMs) break;
    try {
      var url = 'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval='+interval+'&startTime='+cursor+'&endTime='+endMs+'&limit=1000';
      var resp = await fetch(url);
      var rows = await resp.json();
      if (!Array.isArray(rows) || rows.length === 0) break;
      rows.forEach(function(r) {
        var ts = Math.floor(r[0] / 1000);
        if (ts >= startSec && ts <= endSec) results[ts] = [ts, +r[1], +r[2], +r[3], +r[4], +r[5]||0];
      });
      if (rows.length < 1000) break;
      cursor = rows[rows.length-1][0] + 1;
      await sleep(100);
    } catch(e) { console.warn('Binance fetch error:', e); break; }
  }
  return Object.values(results).sort(function(a,b){return a[0]-b[0];});
}

async function apiFetchMEXC(startSec, endSec, gran) {
  var interval = TF.mexc[gran] || '1h';
  var results = {};
  var cursor = startSec * 1000;
  var endMs = endSec * 1000;
  for (var page = 0; page < 200; page++) {
    if (cursor >= endMs) break;
    try {
      var url = 'https://api.mexc.com/api/v3/klines?symbol=SPYXUSDT&interval='+interval+'&startTime='+cursor+'&endTime='+endMs+'&limit=1000';
      var resp = await fetch(url);
      var rows = await resp.json();
      if (!Array.isArray(rows) || rows.length === 0) break;
      rows.forEach(function(r) {
        var ts = Math.floor(r[0] / 1000);
        if (ts >= startSec && ts <= endSec) results[ts] = [ts, +r[1], +r[2], +r[3], +r[4], +r[5]||0];
      });
      if (rows.length < 500) break;
      cursor = rows[rows.length-1][0] + 1;
      await sleep(150);
    } catch(e) { console.warn('MEXC fetch error:', e); break; }
  }
  return Object.values(results).sort(function(a,b){return a[0]-b[0];});
}

async function apiFetchOKX(startSec, endSec, gran) {
  var bar = TF.okx[gran] || '1H';
  var results = {};
  var afterParam = '';
  for (var page = 0; page < 200; page++) {
    try {
      var url = 'https://www.okx.com/api/v5/market/history-candles?instId=XAUT-USDT&bar='+bar+'&limit=100';
      if (afterParam) url += '&after=' + afterParam;
      var resp = await fetch(url);
      var body = await resp.json();
      var rows = body.data || [];
      if (rows.length === 0) break;
      var reachedStart = false;
      rows.forEach(function(r) {
        var ts = Math.floor(+r[0] / 1000);
        if (ts < startSec) { reachedStart = true; return; }
        if (ts > endSec) return;
        results[ts] = [ts, +r[1], +r[2], +r[3], +r[4], +r[5]||0];
      });
      if (reachedStart) break;
      afterParam = rows[rows.length - 1][0];
      await sleep(100);
    } catch(e) { console.warn('OKX fetch error:', e); break; }
  }
  return Object.values(results).sort(function(a,b){return a[0]-b[0];});
}

async function apiFetchPolymarket(startSec, endSec, gran) {
  var fidelity = TF.polymarket[gran] || 60;
  var results = {};
  var chunkSize = 86400 * 7;
  var cursor = startSec;
  while (cursor < endSec) {
    var chunkEnd = Math.min(cursor + chunkSize, endSec);
    try {
      var url = 'https://clob.polymarket.com/prices-history?market='+POLY_TOKEN+'&startTs='+cursor+'&endTs='+chunkEnd+'&fidelity='+fidelity;
      var resp = await fetch(url);
      var data = await resp.json();
      var history = data.history || [];
      history.forEach(function(pt) {
        var ts = +pt.t;
        var pct = Math.round(pt.p * 10000) / 100;
        if (ts >= startSec && ts <= endSec) results[ts] = [ts, pct, pct, pct, pct, 0];
      });
    } catch(e) { console.warn('Polymarket fetch error:', e); }
    cursor = chunkEnd;
    await sleep(200);
  }
  return Object.values(results).sort(function(a,b){return a[0]-b[0];});
}

// ========== REFRESH ==========
async function refreshData() {
  if (_refreshing) return;
  _refreshing = true;
  var btn = document.getElementById('btn-refresh');
  btn.innerHTML = '&#8987; Loading...';
  btn.classList.add('loading');

  try {
    var gran = document.getElementById('sel-gran').value;
    var now = nowSec();
    var startSec = dateToTs(document.getElementById('date-start').value);
    // Always update end date to now
    document.getElementById('date-end').value = tsToDate(now);

    var showOkx = document.getElementById('cb-okx').checked;
    var showBfx = document.getElementById('cb-bitfinex').checked;
    var rightAsset = getSelectedRight();

    var promises = [];
    var keys = [];

    if (showBfx) {
      promises.push(apiFetchBitfinex(startSec, now, gran));
      keys.push('xaut_bitfinex_'+gran);
    }
    if (showOkx) {
      promises.push(apiFetchOKX(startSec, now, gran));
      keys.push('xaut_okx_'+gran);
    }
    // Always fetch BTC
    promises.push(apiFetchBinance(startSec, now, gran));
    keys.push('btc_binance_'+gran);

    if (rightAsset === 'spyx') {
      promises.push(apiFetchMEXC(startSec, now, gran));
      keys.push('spyx_mexc_'+gran);
    }
    // Iran/Polymarket: resolved contract — skip live fetch

    var results = await Promise.allSettled(promises);
    results.forEach(function(r, i) {
      if (r.status === 'fulfilled' && r.value && r.value.length > 0) {
        DATA[keys[i]] = r.value;
      }
    });

    document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    render();
  } catch(e) {
    console.error('Refresh error:', e);
  } finally {
    _refreshing = false;
    btn.innerHTML = '&#8635; Refresh';
    btn.classList.remove('loading');
  }
}

// ========== DOWNLOAD WITH LIVE FETCH ==========
function showFetchProgress(pct, text) {
  document.getElementById('fetch-modal').style.display = 'flex';
  document.getElementById('fetch-progress-bar').style.width = pct + '%';
  document.getElementById('fetch-progress-text').textContent = text;
}
function hideFetchProgress() {
  document.getElementById('fetch-modal').style.display = 'none';
}

async function fetchAllForExport() {
  var grans = ['1m','5m','15m','1H','4H','1D'];
  var dlData = {};
  var startSec = dateToTs(document.getElementById('date-start').value);
  var endSec = nowSec();
  var showOkx = document.getElementById('cb-okx').checked;

  for (var gi = 0; gi < grans.length; gi++) {
    var gran = grans[gi];
    var pct = Math.round((gi / grans.length) * 100);
    showFetchProgress(pct, 'Fetching ' + gran + ' data...');

    var promises = [];
    var pKeys = [];

    // Bitfinex (always)
    promises.push(apiFetchBitfinex(startSec, endSec, gran).catch(function(){return [];}));
    pKeys.push('xaut_bitfinex_'+gran);

    // OKX (if enabled) — skip 1m for OKX (too slow with 100/page limit)
    if (showOkx && gran !== '1m') {
      promises.push(apiFetchOKX(startSec, endSec, gran).catch(function(){return [];}));
      pKeys.push('xaut_okx_'+gran);
    }

    // Binance (always)
    promises.push(apiFetchBinance(startSec, endSec, gran).catch(function(){return [];}));
    pKeys.push('btc_binance_'+gran);

    // MEXC (if SPYx data exists)
    var hasSpyx = false;
    for (var k in DATA) { if (k.indexOf('spyx_') === 0 && DATA[k] && DATA[k].length > 0) { hasSpyx = true; break; } }
    if (hasSpyx) {
      promises.push(apiFetchMEXC(startSec, endSec, gran).catch(function(){return [];}));
      pKeys.push('spyx_mexc_'+gran);
    }

    // Polymarket (use embedded — resolved contract)
    var iranKey = 'iran_polymarket_'+gran;
    if (DATA[iranKey] && DATA[iranKey].length > 0) dlData[iranKey] = DATA[iranKey];

    var results = await Promise.all(promises);
    results.forEach(function(data, i) {
      if (data && data.length > 0) {
        dlData[pKeys[i]] = data;
      } else if (DATA[pKeys[i]] && DATA[pKeys[i]].length > 0) {
        dlData[pKeys[i]] = DATA[pKeys[i]]; // fallback to embedded
      }
    });
  }

  showFetchProgress(100, 'Building file...');
  await sleep(300);
  return dlData;
}

// ========== INIT ==========
function initApp() {
  // Default: end=now, start=now-7days
  var now = nowSec();
  document.getElementById('date-end').value = tsToDate(now);
  document.getElementById('date-start').value = tsToDate(now - 7 * 86400);

  ['cb-xaut','cb-okx','cb-bitfinex'].forEach(function(id) {
    document.getElementById(id).addEventListener('change', render);
  });
  document.getElementById('date-start').addEventListener('change', render);
  document.getElementById('date-end').addEventListener('change', render);

  // Disable unavailable granularities
  var selGran = document.getElementById('sel-gran');
  for (var i = 0; i < selGran.options.length; i++) {
    var g = selGran.options[i].value;
    var hasData = false;
    for (var k in DATA) { if (k.endsWith('_'+g) && DATA[k] && DATA[k].length > 0) { hasData = true; break; } }
    if (!hasData) { selGran.options[i].disabled = true; selGran.options[i].text += ' (no data)'; }
  }

  // Disable radio buttons for missing assets
  var hasSpyx = false;
  for (var k in DATA) { if (k.indexOf('spyx_') === 0 && DATA[k] && DATA[k].length > 0) { hasSpyx = true; break; } }
  if (!hasSpyx) {
    document.getElementById('rb-spyx').disabled = true;
    document.getElementById('rb-spyx').nextElementSibling.className = 'cb-label disabled';
  }
  var hasIran = false;
  for (var k in DATA) { if (k.indexOf('iran_') === 0 && DATA[k] && DATA[k].length > 0) { hasIran = true; break; } }
  if (!hasIran) {
    document.getElementById('rb-iran').disabled = true;
    document.getElementById('rb-iran').nextElementSibling.className = 'cb-label disabled';
  }

  render();

  // Auto-refresh every 1 hour
  _autoRefreshInterval = setInterval(refreshData, 3600000);
}

document.addEventListener('DOMContentLoaded', function() { initApp(); });

// ========== PERIOD PRESETS ==========
function setPeriod(days, btn) {
  var now = nowSec();
  document.getElementById('date-end').value = tsToDate(now);
  if (days === 0) {
    var minTs = Infinity;
    for (var k in DATA) {
      var arr = DATA[k];
      if (arr && arr.length > 0 && arr[0][0] < minTs) minTs = arr[0][0];
    }
    document.getElementById('date-start').value = tsToDate(minTs);
  } else {
    document.getElementById('date-start').value = tsToDate(now - days * 86400);
  }
  // Highlight active period button
  document.querySelectorAll('.period-btn').forEach(function(b) { b.classList.remove('active'); });
  if (btn) btn.classList.add('active');
  render();
}

// ========== MAIN RENDER ==========
function render() {
  var gran = document.getElementById('sel-gran').value;
  var startTs = dateToTs(document.getElementById('date-start').value);
  var endTs = dateToTs(document.getElementById('date-end').value) + 86400;
  var showXaut = document.getElementById('cb-xaut').checked;
  var showOkx = document.getElementById('cb-okx').checked;
  var showBfx = document.getElementById('cb-bitfinex').checked;
  var rightAsset = getSelectedRight();

  var datasets = [];
  var hasLeftAxis = false;
  var hasRightAxis = false;

  // Left axis: XAUt
  if (showXaut && showOkx) {
    var d = getFiltered('xaut_okx_' + gran, startTs, endTs);
    if (d.length > 0) { datasets.push(makeDataset('xaut_okx', d, 'y', false)); hasLeftAxis = true; }
  }
  if (showXaut && showBfx) {
    var d = getFiltered('xaut_bitfinex_' + gran, startTs, endTs);
    if (d.length > 0) { datasets.push(makeDataset('xaut_bitfinex', d, 'y', showOkx)); hasLeftAxis = true; }
  }

  // Right axis
  if (rightAsset === 'btc') {
    var d = getFiltered('btc_binance_' + gran, startTs, endTs);
    if (d.length > 0) {
      var axisId = hasLeftAxis ? 'y1' : 'y';
      datasets.push(makeDataset('btc_binance', d, axisId, false));
      if (axisId === 'y1') hasRightAxis = true; else hasLeftAxis = true;
    }
  } else if (rightAsset === 'spyx') {
    var d = getFiltered('spyx_mexc_' + gran, startTs, endTs);
    if (d.length > 0) {
      var axisId = hasLeftAxis ? 'y1' : 'y';
      datasets.push(makeDataset('spyx_mexc', d, axisId, false));
      if (axisId === 'y1') hasRightAxis = true; else hasLeftAxis = true;
    }
  } else if (rightAsset === 'iran') {
    var d = getFiltered('iran_polymarket_' + gran, startTs, endTs);
    if (d.length > 0) {
      var axisId = hasLeftAxis ? 'y1' : 'y';
      datasets.push(makeDataset('iran_polymarket', d, axisId, false));
      if (axisId === 'y1') hasRightAxis = true; else hasLeftAxis = true;
    }
  }

  if (chart) chart.destroy();
  var ctx = document.getElementById('main-chart').getContext('2d');
  var totalDays = (endTs - startTs) / 86400;
  var timeUnit = totalDays > 90 ? 'week' : (totalDays > 7 ? 'day' : 'hour');

  var leftLabel = 'XAUt (USD)';
  var rightLabel = RIGHT_AXIS_LABELS[rightAsset] || 'USD';

  var scales = {
    x: { type:'time', time:{unit:timeUnit}, grid:{color:'rgba(48,54,61,0.6)'}, ticks:{color:'#8b949e',maxTicksLimit:12} }
  };
  if (hasLeftAxis || !hasRightAxis) {
    scales.y = { position:'left', title:{display:true,text:showXaut?leftLabel:rightLabel,color:'#8b949e'}, grid:{color:'rgba(48,54,61,0.6)'}, ticks:{color:'#8b949e',callback:function(v){return '$'+v.toLocaleString();}} };
  }
  if (hasRightAxis) {
    var isPercent = PERCENT_ASSETS.indexOf(rightAsset) >= 0;
    var rightTickFn = isPercent ? function(v){return v.toFixed(1)+'%';} : function(v){return '$'+v.toLocaleString();};
    var rightAxisOpts = { position:'right', title:{display:true,text:rightLabel,color:'#8b949e'}, grid:{drawOnChartArea:false}, ticks:{color:'#8b949e',callback:rightTickFn} };
    if (isPercent) { rightAxisOpts.min = 0; rightAxisOpts.max = 100; }
    scales.y1 = rightAxisOpts;
  }

  chart = new Chart(ctx, {
    type:'line', data:{datasets:datasets},
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins: {
        tooltip:{callbacks:{label:function(ctx){
          if(ctx.dataset.label&&ctx.dataset.label.indexOf('%')>=0){return ctx.dataset.label+': '+ctx.parsed.y.toFixed(1)+'%';}
          return ctx.dataset.label+': $'+ctx.parsed.y.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
        }}},
        legend:{labels:{color:'#c9d1d9',usePointStyle:true,pointStyle:'line'}}
      },
      scales:scales,
      elements:{point:{radius:0,hoverRadius:4},line:{tension:0,borderWidth:1.5}}
    }
  });

  updateStats(gran, startTs, endTs, showXaut, showOkx, showBfx, rightAsset);

  var totalPoints = datasets.reduce(function(s,d){return s+d.data.length;},0);
  document.getElementById('data-info-text').textContent = 'Showing '+totalPoints+' data points | Granularity: '+gran+' | Period: '+document.getElementById('date-start').value+' to '+document.getElementById('date-end').value;

  var parts = [];
  if (showXaut) parts.push('XAUt');
  if (rightAsset === 'btc') parts.push('BTC');
  else if (rightAsset === 'spyx') parts.push('SPYx');
  else if (rightAsset === 'iran') parts.push('Iran Strike %');
  document.getElementById('chart-title').textContent = parts.join(' & ') + ' \u2014 ' + gran + ' Chart';
}

function makeDataset(key, data, yAxisID, dashed) {
  var c = COLORS[key]||{line:'#888',fill:'rgba(128,128,128,0.1)',label:key};
  return { label:c.label, data:data.map(function(d){return {x:new Date(d[0]*1000),y:d[4]};}), borderColor:c.line, backgroundColor:c.fill, borderDash:dashed?[6,3]:[], fill:false, yAxisID:yAxisID, pointRadius:0, pointHoverRadius:4, borderWidth:1.5 };
}

function updateStats(gran, startTs, endTs, showXaut, showOkx, showBfx, rightAsset) {
  var container = document.getElementById('stats-container');
  container.innerHTML = '';
  var cards = [];
  if (showXaut && showOkx) cards.push({key:'xaut_okx_'+gran,name:'XAUt (OKX)',color:'var(--gold-okx)'});
  if (showXaut && showBfx) cards.push({key:'xaut_bitfinex_'+gran,name:'XAUt (Bitfinex)',color:'var(--gold-bfx)'});
  if (rightAsset === 'btc') cards.push({key:'btc_binance_'+gran,name:'BTC (Binance)',color:'var(--btc)'});
  if (rightAsset === 'spyx') cards.push({key:'spyx_mexc_'+gran,name:'SPYx (MEXC)',color:'var(--spyx)'});
  if (rightAsset === 'iran') cards.push({key:'iran_polymarket_'+gran,name:'Iran Strike % (Polymarket)',color:'var(--iran)',isPercent:true});

  cards.forEach(function(c) {
    var d = getFiltered(c.key, startTs, endTs);
    if (d.length === 0) return;
    var first=d[0][4],last=d[d.length-1][4];
    var high=Math.max.apply(null,d.map(function(x){return x[2];}));
    var low=Math.min.apply(null,d.map(function(x){return x[3];}));
    var chg=first!==0?((last-first)/first*100):0;
    var chgClass=chg>=0?'up':'down', chgSign=chg>=0?'+':'';
    var isPct = c.isPercent;
    var valStr = isPct ? last.toFixed(1)+'%' : '$'+last.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
    var hiStr = isPct ? high.toFixed(1)+'%' : '$'+high.toLocaleString(undefined,{maximumFractionDigits:2});
    var loStr = isPct ? low.toFixed(1)+'%' : '$'+low.toLocaleString(undefined,{maximumFractionDigits:2});
    container.innerHTML += '<div class="stat-card" style="border-top:3px solid '+c.color+'"><div class="label">'+c.name+'</div><div class="value">'+valStr+'</div><div class="change '+chgClass+'">'+chgSign+chg.toFixed(2)+'% &nbsp; H:'+hiStr+' L:'+loStr+'</div><div class="label" style="margin-top:6px">'+d.length+(isPct?' points':' candles')+'</div></div>';
  });
}

function getFiltered(key, startTs, endTs) {
  var arr = DATA[key]; if (!arr) return [];
  return arr.filter(function(d){return d[0]>=startTs&&d[0]<=endTs;});
}

// ========== DOWNLOAD GUARD & EXPORT ==========
var _pendingExportFormat = null;

function guardedExport(format) {
  if (DOWNLOAD_UNLOCKED || !DOWNLOAD_ENCRYPTED) {
    doExport(format);
  } else {
    _pendingExportFormat = format;
    document.getElementById('dl-modal').style.display = 'flex';
    document.getElementById('dl-pw-input').value = '';
    document.getElementById('dl-pw-error').style.display = 'none';
    document.getElementById('dl-pw-input').focus();
  }
}
function closeDownloadModal() {
  document.getElementById('dl-modal').style.display = 'none';
  _pendingExportFormat = null;
}

async function doExport(format) {
  var dlData = await fetchAllForExport();
  hideFetchProgress();
  if (format === 'csv') exportCSV(dlData);
  else if (format === 'xlsx') exportXLSX(dlData);
}

function exportCSV(dlData) {
  var grans = ['1m','5m','15m','1H','4H','1D'];
  var allLines = [];

  grans.forEach(function(gran) {
    var series = [];
    var allKeys = ['xaut_okx_'+gran,'xaut_bitfinex_'+gran,'btc_binance_'+gran,'spyx_mexc_'+gran,'iran_polymarket_'+gran];
    allKeys.forEach(function(key){ if(dlData[key] && dlData[key].length > 0) series.push(key); });
    if (series.length === 0) return;

    var tsMap = {};
    series.forEach(function(key){ dlData[key].forEach(function(row){ if(!tsMap[row[0]])tsMap[row[0]]={}; tsMap[row[0]][key]=row; }); });
    var timestamps = Object.keys(tsMap).map(Number).sort(function(a,b){return a-b;});

    var headers = ['timestamp','datetime'];
    series.forEach(function(key){ var base=key.replace('_'+gran,''); headers.push(base+'_open',base+'_high',base+'_low',base+'_close',base+'_volume'); });

    if (allLines.length > 0) allLines.push('');
    allLines.push('# Granularity: ' + gran);
    allLines.push(headers.join(','));
    timestamps.forEach(function(ts){
      var row = [ts, new Date(ts*1000).toISOString()];
      series.forEach(function(key){ var d=tsMap[ts][key]; if(d){row.push(d[1],d[2],d[3],d[4],d[5]);}else{row.push('','','','','');} });
      allLines.push(row.join(','));
    });
  });

  downloadFile(allLines.join('\n'), 'crypto_all_data.csv', 'text/csv');
}

function exportXLSX(dlData) {
  if (typeof XLSX === 'undefined') { alert('SheetJS library not loaded.'); return; }
  var wb = XLSX.utils.book_new();
  var grans = ['1m','5m','15m','1H','4H','1D'];

  grans.forEach(function(gran) {
    var sheetConfigs = [];
    if(dlData['xaut_okx_'+gran] && dlData['xaut_okx_'+gran].length>0) sheetConfigs.push({key:'xaut_okx_'+gran,name:'XAUt_OKX_'+gran});
    if(dlData['xaut_bitfinex_'+gran] && dlData['xaut_bitfinex_'+gran].length>0) sheetConfigs.push({key:'xaut_bitfinex_'+gran,name:'XAUt_BFX_'+gran});
    if(dlData['btc_binance_'+gran] && dlData['btc_binance_'+gran].length>0) sheetConfigs.push({key:'btc_binance_'+gran,name:'BTC_'+gran});
    if(dlData['spyx_mexc_'+gran] && dlData['spyx_mexc_'+gran].length>0) sheetConfigs.push({key:'spyx_mexc_'+gran,name:'SPYx_'+gran});
    if(dlData['iran_polymarket_'+gran] && dlData['iran_polymarket_'+gran].length>0) sheetConfigs.push({key:'iran_polymarket_'+gran,name:'Iran_'+gran});

    sheetConfigs.forEach(function(cfg) {
      var d = dlData[cfg.key];
      var rows = [['Timestamp','DateTime','Open','High','Low','Close','Volume']];
      d.forEach(function(r){ rows.push([r[0], new Date(r[0]*1000).toISOString(), r[1], r[2], r[3], r[4], r[5]]); });
      var ws = XLSX.utils.aoa_to_sheet(rows);
      ws['!cols'] = [{wch:12},{wch:24},{wch:12},{wch:12},{wch:12},{wch:12},{wch:14}];
      XLSX.utils.book_append_sheet(wb, ws, cfg.name);
    });
  });

  XLSX.writeFile(wb, 'crypto_all_data.xlsx');
}

function downloadFile(content, filename, mime) {
  var blob = new Blob([content], {type: mime});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
"""

# =========================================================================
# DECRYPT JS (only included when password is set)
# =========================================================================
_JS_DECRYPT = r"""
// ========== DOWNLOAD PASSWORD MODAL ==========
async function unlockDownload() {
  var pw = document.getElementById('dl-pw-input').value;
  if (!pw) return;
  document.getElementById('dl-pw-error').style.display = 'none';

  try {
    var saltBuf = Uint8Array.from(atob(DOWNLOAD_ENCRYPTED.salt), function(c){return c.charCodeAt(0);});
    var ivBuf   = Uint8Array.from(atob(DOWNLOAD_ENCRYPTED.iv),   function(c){return c.charCodeAt(0);});
    var ctBuf   = Uint8Array.from(atob(DOWNLOAD_ENCRYPTED.ct),    function(c){return c.charCodeAt(0);});

    var keyMaterial = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]
    );
    var aesKey = await crypto.subtle.deriveKey(
      {name: "PBKDF2", salt: saltBuf, iterations: 100000, hash: "SHA-256"},
      keyMaterial,
      {name: "AES-GCM", length: 256},
      false,
      ["decrypt"]
    );
    await crypto.subtle.decrypt({name: "AES-GCM", iv: ivBuf}, aesKey, ctBuf);

    DOWNLOAD_UNLOCKED = true;
    closeDownloadModal();
    if (_pendingExportFormat) { doExport(_pendingExportFormat); _pendingExportFormat = null; }
  } catch(e) {
    document.getElementById('dl-pw-error').style.display = 'block';
    document.getElementById('dl-pw-input').value = '';
    document.getElementById('dl-pw-input').focus();
  }
}
"""


# =========================================================================
# BUILD HTML
# =========================================================================
def build_html(all_data, meta, cdn=True, password=None):
    """
    Generate self-contained HTML v2 with live-refresh capability.

    Args:
        all_data: dict of data series
        meta: dict with metadata
        cdn: if True, load Chart.js from CDN
        password: if set, encrypt data with this password (AES-256-GCM)

    Returns:
        str: complete HTML document
    """
    data_json = json.dumps(all_data, separators=(',', ':'))
    meta_json = json.dumps(meta, separators=(',', ':'))
    gen_at = meta.get('generated_at',
                      datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'))

    # CDN script tags
    cdn_tags = ''
    if cdn:
        cdn_tags = (
            '    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>\n'
            '    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>\n'
            '    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>'
        )

    # JS data section
    js_data = 'var DATA = ' + data_json + ';\nvar META = ' + meta_json + ';\n'

    if password:
        enc = _encrypt_data(data_json, password)
        js_data += ('var DOWNLOAD_ENCRYPTED = {salt:"' + enc['salt']
                    + '",iv:"' + enc['iv'] + '",ct:"' + enc['ct'] + '"};\n'
                    'var DOWNLOAD_UNLOCKED = false;\n')
    else:
        js_data += 'var DOWNLOAD_ENCRYPTED = null;\nvar DOWNLOAD_UNLOCKED = true;\n'

    # Assemble HTML
    html = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<meta name="theme-color" content="#0d1117">\n'
        '<title>Crypto Asset Data Explorer v2 | Tokenized Assets</title>\n'
        + cdn_tags + '\n<style>\n' + _CSS + '\n</style>\n</head>\n<body>\n'
        '<div class="container">\n'
        + _HTML_BODY.replace('__GENERATED_AT__', gen_at)
        + '\n</div>\n<script>\n'
        '// ========== EMBEDDED DATA ==========\n'
        + js_data + '\n'
        + _JS_APP + '\n'
        + (_JS_DECRYPT if password else '') + '\n'
        + '</script>\n</body>\n</html>'
    )

    return html
