"""
HTML Builder — Generates FRED-like interactive data visualization page.
All data is embedded as JSON; Chart.js + SheetJS loaded from CDN.
Optional AES-256-GCM encryption: password is NOT stored in HTML.
"""

import json
import datetime
import os
import hashlib
import base64


def _encrypt_data(plaintext, password):
    """
    Encrypt plaintext with AES-256-GCM using password.
    Uses PBKDF2 key derivation (same as Web Crypto API on client side).

    Returns: dict with base64-encoded salt, iv, ciphertext
    """
    import struct

    salt = os.urandom(16)
    iv = os.urandom(12)

    # Derive key using PBKDF2-SHA256, 100000 iterations, 32 bytes
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)

    # AES-256-GCM encryption using Python's cryptography or fallback
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext.encode('utf-8'), None)
    except ImportError:
        # Fallback: use OpenSSL via subprocess
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


def build_html(all_data, meta, cdn=True, password=None):
    """
    Generate self-contained HTML with FRED-like UI.

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
    generated_at = meta.get('generated_at',
                            datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'))

    chartjs_tag = ''
    if cdn:
        chartjs_tag = '''
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>'''

    # ===== Data embedding strategy =====
    data_embed = f'''
var DATA = {data_json};
var META = {meta_json};'''

    if password:
        encrypted = _encrypt_data(data_json, password)
        data_embed += f'''
var DOWNLOAD_ENCRYPTED = {{
  salt: "{encrypted['salt']}",
  iv: "{encrypted['iv']}",
  ct: "{encrypted['ct']}"
}};
var DOWNLOAD_UNLOCKED = false;'''
    else:
        data_embed += '''
var DOWNLOAD_ENCRYPTED = null;
var DOWNLOAD_UNLOCKED = true;'''

    password_screen = ''
    main_display = ''

    # ===== Download password modal (only if encrypted) =====
    if password:
        decrypt_js = '''
// ========== DOWNLOAD PASSWORD MODAL ==========
var _pendingExportFn = null;

function showDownloadModal(exportFn) {
  _pendingExportFn = exportFn;
  document.getElementById("dl-modal").style.display = "flex";
  document.getElementById("dl-pw-input").value = "";
  document.getElementById("dl-pw-error").style.display = "none";
  document.getElementById("dl-pw-input").focus();
}

function closeDownloadModal() {
  document.getElementById("dl-modal").style.display = "none";
  _pendingExportFn = null;
}

async function unlockDownload() {
  var pw = document.getElementById("dl-pw-input").value;
  if (!pw) return;
  document.getElementById("dl-pw-error").style.display = "none";

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
    var decrypted = await crypto.subtle.decrypt(
      {name: "AES-GCM", iv: ivBuf}, aesKey, ctBuf
    );

    DOWNLOAD_UNLOCKED = true;
    closeDownloadModal();
    if (_pendingExportFn) { _pendingExportFn(); _pendingExportFn = null; }

  } catch(e) {
    document.getElementById("dl-pw-error").style.display = "block";
    document.getElementById("dl-pw-input").value = "";
    document.getElementById("dl-pw-input").focus();
  }
}
'''
    else:
        decrypt_js = ''

    init_call = '''
document.addEventListener('DOMContentLoaded', function() { initApp(); });
'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CryptoExplorer">
<meta name="theme-color" content="#0d1117">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="icon-192.png">
<title>Crypto Asset Data Explorer | Tokenized Assets</title>
{chartjs_tag}
<style>
:root {{
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #c9d1d9; --text-dim: #8b949e; --accent: #58a6ff;
  --gold: #f0b90b; --gold-dim: #f0b90b80; --btc: #f7931a; --btc-dim: #f7931a80;
  --bitfinex: #16b979; --bitfinex-dim: #16b97980;
  --spyx: #a855f7; --spyx-dim: #a855f780;
  --iran: #ef4444; --iran-dim: #ef444480;
  --green: #3fb950; --red: #f85149;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
.container {{ max-width:1400px; margin:0 auto; padding:16px; }}
header {{ padding:24px 0 16px; border-bottom:1px solid var(--border); margin-bottom:16px; }}
header h1 {{ font-size:24px; font-weight:600; color:#f0f6fc; }}
header p {{ color:var(--text-dim); font-size:14px; margin-top:4px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:12px; padding:16px; background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:16px; align-items:center; }}
.ctrl-group {{ display:flex; align-items:center; gap:8px; }}
.ctrl-group label {{ font-size:13px; color:var(--text-dim); font-weight:600; text-transform:uppercase; letter-spacing:0.5px; white-space:nowrap; }}
.ctrl-group input[type="checkbox"], .ctrl-group input[type="radio"] {{ accent-color:var(--accent); width:16px; height:16px; }}
.ctrl-group .cb-label {{ font-size:14px; cursor:pointer; user-select:none; }}
.ctrl-group .cb-label.disabled {{ color:var(--text-dim); opacity:0.4; cursor:not-allowed; }}
.ctrl-group select, .ctrl-group input[type="date"] {{
  background:var(--bg); color:var(--text); border:1px solid var(--border);
  border-radius:4px; padding:4px 8px; font-size:13px;
}}
.btn {{ background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:4px; padding:4px 12px; font-size:13px; cursor:pointer; transition:0.15s; }}
.btn:hover {{ background:var(--border); }}
.btn.active {{ background:var(--accent); color:#0d1117; border-color:var(--accent); }}
.btn-export {{ background:#238636; color:#fff; border-color:#238636; }}
.btn-export:hover {{ background:#2ea043; }}
.sep {{ width:1px; height:28px; background:var(--border); }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:16px; }}
.stat-card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:14px; }}
.stat-card .label {{ font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; }}
.stat-card .value {{ font-size:22px; font-weight:600; margin-top:4px; }}
.stat-card .change {{ font-size:13px; margin-top:2px; }}
.stat-card .change.up {{ color:var(--green); }}
.stat-card .change.down {{ color:var(--red); }}
.chart-box {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:16px; }}
.chart-box h3 {{ font-size:14px; color:var(--text-dim); margin-bottom:12px; }}
.chart-wrap {{ position:relative; height:500px; width:100%; }}
.data-info {{ font-size:12px; color:var(--text-dim); padding:8px 0; }}
footer {{ border-top:1px solid var(--border); padding:16px 0; margin-top:16px; font-size:12px; color:var(--text-dim); display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
footer a {{ color:var(--accent); text-decoration:none; }}
@media (max-width:768px) {{
  .controls {{ flex-direction:column; align-items:stretch; }}
  .sep {{ display:none; }}
  .chart-wrap {{ height:350px; }}
}}
</style>
</head>
<body>
<div class="container">
{password_screen}
  <div id="main-content" {main_display}>
  <header>
    <h1>Crypto Asset Data Explorer</h1>
    <p>Tokenized Gold (XAUt) &amp; Right-Axis Asset &mdash; Multi-Source Historical Data</p>
  </header>

  <div class="controls">
    <div class="ctrl-group">
      <label>Left Axis:</label>
      <input type="checkbox" id="cb-xaut" checked><span class="cb-label" onclick="document.getElementById('cb-xaut').click()"> XAUt</span>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <label>XAUt Source:</label>
      <input type="checkbox" id="cb-okx" checked><span class="cb-label" onclick="document.getElementById('cb-okx').click()"> OKX</span>
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
      <button class="btn" onclick="setPeriod(7)">1W</button>
      <button class="btn" onclick="setPeriod(30)">1M</button>
      <button class="btn" onclick="setPeriod(90)">3M</button>
      <button class="btn" onclick="setPeriod(0)">ALL</button>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <label>Granularity:</label>
      <select id="sel-gran" onchange="render()">
        <option value="1m">1 min</option>
        <option value="5m">5 min</option>
        <option value="15m">15 min</option>
        <option value="1H" selected>1 hour</option>
        <option value="4H">4 hours</option>
        <option value="1D">1 day</option>
      </select>
    </div>
    <div class="sep"></div>
    <div class="ctrl-group">
      <button class="btn btn-export" onclick="guardedExport(exportCSV)">CSV (All)</button>
      <button class="btn btn-export" onclick="guardedExport(exportXLSX)">Excel (All)</button>
    </div>
  </div>

  <div class="stats" id="stats-container"></div>

  <div class="chart-box">
    <h3 id="chart-title">Price Chart</h3>
    <div class="chart-wrap"><canvas id="main-chart"></canvas></div>
  </div>

  <div class="data-info" id="data-info"></div>

  <footer>
    <div>Sources: <a href="https://www.okx.com" target="_blank">OKX</a> | <a href="https://www.bitfinex.com" target="_blank">Bitfinex</a> | <a href="https://www.binance.com" target="_blank">Binance</a> | <a href="https://www.mexc.com" target="_blank">MEXC</a> | <a href="https://polymarket.com/event/us-strikes-iran-by" target="_blank">Polymarket</a></div>
    <div>Last updated: {generated_at}</div>
  </footer>
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
</div>

<script>
// ========== EMBEDDED DATA ==========
{data_embed}

// ========== APP STATE ==========
var chart = null;
var COLORS = {{
  xaut_okx:      {{line:'#f0b90b',fill:'rgba(240,185,11,0.08)',label:'XAUt (OKX)'}},
  xaut_bitfinex: {{line:'#16b979',fill:'rgba(22,185,121,0.08)',label:'XAUt (Bitfinex)'}},
  btc_binance:   {{line:'#f7931a',fill:'rgba(247,147,26,0.08)',label:'BTC (Binance)'}},
  spyx_mexc:     {{line:'#a855f7',fill:'rgba(168,85,247,0.08)',label:'SPYx (MEXC)'}},
  iran_polymarket:{{line:'#ef4444',fill:'rgba(239,68,68,0.12)',label:'Iran Strike % (Polymarket)'}},
}};

// Right-axis asset labels for Y-axis title
var RIGHT_AXIS_LABELS = {{
  btc: 'BTC (USD)',
  spyx: 'SPYx (USD)',
  iran: 'Strike Probability (%)',
}};
var PERCENT_ASSETS = ['iran'];

{decrypt_js}

// ========== HELPER: get selected right-axis asset ==========
function getSelectedRight() {{
  var radios = document.getElementsByName('right-axis');
  for (var i = 0; i < radios.length; i++) {{
    if (radios[i].checked) return radios[i].value;
  }}
  return 'btc';
}}

// ========== INIT APP ==========
function initApp() {{
  var allTs = [];
  for (var k in DATA) {{
    var arr = DATA[k];
    if (arr && arr.length > 0) {{
      allTs.push(arr[0][0], arr[arr.length-1][0]);
    }}
  }}
  if (allTs.length > 0) {{
    var minTs = Math.min.apply(null, allTs);
    var maxTs = Math.max.apply(null, allTs);
    document.getElementById('date-start').value = tsToDate(minTs);
    document.getElementById('date-end').value = tsToDate(maxTs);
  }}

  ['cb-xaut','cb-okx','cb-bitfinex'].forEach(function(id) {{
    document.getElementById(id).addEventListener('change', render);
  }});
  document.getElementById('date-start').addEventListener('change', render);
  document.getElementById('date-end').addEventListener('change', render);

  // Disable radio buttons for assets without data
  var selGran = document.getElementById('sel-gran');
  var opts = selGran.options;
  for (var i = 0; i < opts.length; i++) {{
    var g = opts[i].value;
    var hasData = false;
    for (var k in DATA) {{
      if (k.endsWith('_' + g) && DATA[k] && DATA[k].length > 0) {{
        hasData = true; break;
      }}
    }}
    if (!hasData) {{ opts[i].disabled = true; opts[i].text += ' (no data)'; }}
  }}

  // Check if SPYx data exists for any granularity
  var hasSpyx = false;
  for (var k in DATA) {{
    if (k.indexOf('spyx_') === 0 && DATA[k] && DATA[k].length > 0) {{ hasSpyx = true; break; }}
  }}
  if (!hasSpyx) {{
    document.getElementById('rb-spyx').disabled = true;
    var lbl = document.getElementById('rb-spyx').nextElementSibling;
    if (lbl) lbl.className = 'cb-label disabled';
  }}

  // Check if Iran data exists for any granularity
  var hasIran = false;
  for (var k in DATA) {{
    if (k.indexOf('iran_') === 0 && DATA[k] && DATA[k].length > 0) {{ hasIran = true; break; }}
  }}
  if (!hasIran) {{
    document.getElementById('rb-iran').disabled = true;
    var lbl2 = document.getElementById('rb-iran').nextElementSibling;
    if (lbl2) lbl2.className = 'cb-label disabled';
  }}

  render();
}}

{init_call}

// ========== PERIOD PRESETS ==========
function setPeriod(days) {{
  var allTs = [];
  for (var k in DATA) {{
    var arr = DATA[k];
    if (arr && arr.length > 0) allTs.push(arr[arr.length-1][0]);
  }}
  if (allTs.length === 0) return;
  var maxTs = Math.max.apply(null, allTs);
  document.getElementById('date-end').value = tsToDate(maxTs);
  if (days === 0) {{
    var minTs = Infinity;
    for (var k in DATA) {{
      var arr = DATA[k];
      if (arr && arr.length > 0 && arr[0][0] < minTs) minTs = arr[0][0];
    }}
    document.getElementById('date-start').value = tsToDate(minTs);
  }} else {{
    document.getElementById('date-start').value = tsToDate(maxTs - days * 86400);
  }}
  render();
}}

// ========== MAIN RENDER ==========
function render() {{
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
  if (showXaut && showOkx) {{
    var d = getFiltered('xaut_okx_' + gran, startTs, endTs);
    if (d.length > 0) {{ datasets.push(makeDataset('xaut_okx', d, 'y', false)); hasLeftAxis = true; }}
  }}
  if (showXaut && showBfx) {{
    var d = getFiltered('xaut_bitfinex_' + gran, startTs, endTs);
    if (d.length > 0) {{ datasets.push(makeDataset('xaut_bitfinex', d, 'y', showOkx)); hasLeftAxis = true; }}
  }}

  // Right axis: BTC or SPYx (exclusive)
  if (rightAsset === 'btc') {{
    var d = getFiltered('btc_binance_' + gran, startTs, endTs);
    if (d.length > 0) {{
      var axisId = hasLeftAxis ? 'y1' : 'y';
      datasets.push(makeDataset('btc_binance', d, axisId, false));
      if (axisId === 'y1') hasRightAxis = true; else hasLeftAxis = true;
    }}
  }} else if (rightAsset === 'spyx') {{
    var d = getFiltered('spyx_mexc_' + gran, startTs, endTs);
    if (d.length > 0) {{
      var axisId = hasLeftAxis ? 'y1' : 'y';
      datasets.push(makeDataset('spyx_mexc', d, axisId, false));
      if (axisId === 'y1') hasRightAxis = true; else hasLeftAxis = true;
    }}
  }} else if (rightAsset === 'iran') {{
    var d = getFiltered('iran_polymarket_' + gran, startTs, endTs);
    if (d.length > 0) {{
      var axisId = hasLeftAxis ? 'y1' : 'y';
      datasets.push(makeDataset('iran_polymarket', d, axisId, false));
      if (axisId === 'y1') hasRightAxis = true; else hasLeftAxis = true;
    }}
  }}

  if (chart) chart.destroy();
  var ctx = document.getElementById('main-chart').getContext('2d');
  var totalDays = (endTs - startTs) / 86400;
  var timeUnit = totalDays > 90 ? 'week' : (totalDays > 7 ? 'day' : 'hour');

  var leftLabel = 'XAUt (USD)';
  var rightLabel = RIGHT_AXIS_LABELS[rightAsset] || 'USD';

  var scales = {{
    x: {{ type:'time', time:{{unit:timeUnit}}, grid:{{color:'rgba(48,54,61,0.6)'}}, ticks:{{color:'#8b949e',maxTicksLimit:12}} }}
  }};
  if (hasLeftAxis || !hasRightAxis) {{
    scales.y = {{ position:'left', title:{{display:true,text:showXaut ? leftLabel : rightLabel,color:'#8b949e'}}, grid:{{color:'rgba(48,54,61,0.6)'}}, ticks:{{color:'#8b949e',callback:function(v){{return '$'+v.toLocaleString();}}}} }};
  }}
  if (hasRightAxis) {{
    var isPercent = PERCENT_ASSETS.indexOf(rightAsset) >= 0;
    var rightTickFn = isPercent
      ? function(v){{return v.toFixed(1)+'%';}}
      : function(v){{return '$'+v.toLocaleString();}};
    var rightAxisOpts = {{ position:'right', title:{{display:true,text:rightLabel,color:'#8b949e'}}, grid:{{drawOnChartArea:false}}, ticks:{{color:'#8b949e',callback:rightTickFn}} }};
    if (isPercent) {{ rightAxisOpts.min = 0; rightAxisOpts.max = 100; }}
    scales.y1 = rightAxisOpts;
  }}

  chart = new Chart(ctx, {{
    type:'line', data:{{datasets:datasets}},
    options: {{
      responsive:true, maintainAspectRatio:false,
      interaction:{{mode:'index',intersect:false}},
      plugins: {{
        tooltip:{{callbacks:{{label:function(ctx){{
          if(ctx.dataset.label&&ctx.dataset.label.indexOf('%')>=0){{return ctx.dataset.label+': '+ctx.parsed.y.toFixed(1)+'%';}}
          return ctx.dataset.label+': $'+ctx.parsed.y.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
        }}}}}},
        legend:{{labels:{{color:'#c9d1d9',usePointStyle:true,pointStyle:'line'}}}}
      }},
      scales:scales,
      elements:{{point:{{radius:0,hoverRadius:4}},line:{{tension:0,borderWidth:1.5}}}}
    }}
  }});

  updateStats(gran, startTs, endTs, showXaut, showOkx, showBfx, rightAsset);
  var totalPoints = datasets.reduce(function(s,d){{return s+d.data.length;}},0);
  document.getElementById('data-info').textContent = 'Showing '+totalPoints+' data points | Granularity: '+gran+' | Period: '+document.getElementById('date-start').value+' to '+document.getElementById('date-end').value;
  var parts = [];
  if (showXaut) parts.push('XAUt');
  if (rightAsset === 'btc') parts.push('BTC');
  else if (rightAsset === 'spyx') parts.push('SPYx');
  else if (rightAsset === 'iran') parts.push('Iran Strike %');
  document.getElementById('chart-title').textContent = parts.join(' & ')+' \\u2014 '+gran+' Chart';
}}

function makeDataset(key, data, yAxisID, dashed) {{
  var c = COLORS[key]||{{line:'#888',fill:'rgba(128,128,128,0.1)',label:key}};
  return {{ label:c.label, data:data.map(function(d){{return {{x:new Date(d[0]*1000),y:d[4]}}; }}), borderColor:c.line, backgroundColor:c.fill, borderDash:dashed?[6,3]:[], fill:false, yAxisID:yAxisID, pointRadius:0, pointHoverRadius:4, borderWidth:1.5 }};
}}

function updateStats(gran, startTs, endTs, showXaut, showOkx, showBfx, rightAsset) {{
  var container = document.getElementById('stats-container');
  container.innerHTML = '';
  var cards = [];
  if (showXaut && showOkx) cards.push({{key:'xaut_okx_'+gran,name:'XAUt (OKX)',color:'var(--gold)'}});
  if (showXaut && showBfx) cards.push({{key:'xaut_bitfinex_'+gran,name:'XAUt (Bitfinex)',color:'var(--bitfinex)'}});
  if (rightAsset === 'btc') cards.push({{key:'btc_binance_'+gran,name:'BTC (Binance)',color:'var(--btc)'}});
  if (rightAsset === 'spyx') cards.push({{key:'spyx_mexc_'+gran,name:'SPYx (MEXC)',color:'var(--spyx)'}});
  if (rightAsset === 'iran') cards.push({{key:'iran_polymarket_'+gran,name:'Iran Strike % (Polymarket)',color:'var(--iran)',isPercent:true}});
  cards.forEach(function(c) {{
    var d = getFiltered(c.key, startTs, endTs);
    if (d.length === 0) return;
    var first=d[0][4],last=d[d.length-1][4];
    var high=Math.max.apply(null,d.map(function(x){{return x[2];}}));
    var low=Math.min.apply(null,d.map(function(x){{return x[3];}}));
    var chg=first!==0?((last-first)/first*100):0;
    var chgClass=chg>=0?'up':'down', chgSign=chg>=0?'+':'';
    var isPct = c.isPercent;
    var valStr = isPct ? last.toFixed(1)+'%' : '$'+last.toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
    var hiStr = isPct ? high.toFixed(1)+'%' : '$'+high.toLocaleString(undefined,{{maximumFractionDigits:2}});
    var loStr = isPct ? low.toFixed(1)+'%' : '$'+low.toLocaleString(undefined,{{maximumFractionDigits:2}});
    container.innerHTML += '<div class="stat-card" style="border-top:3px solid '+c.color+'"><div class="label">'+c.name+'</div><div class="value">'+valStr+'</div><div class="change '+chgClass+'">'+chgSign+chg.toFixed(2)+'% &nbsp; H:'+hiStr+' L:'+loStr+'</div><div class="label" style="margin-top:6px">'+d.length+(isPct?' points':' candles')+'</div></div>';
  }});
}}

function getFiltered(key, startTs, endTs) {{
  var arr = DATA[key]; if (!arr) return [];
  return arr.filter(function(d){{return d[0]>=startTs&&d[0]<=endTs;}});
}}
function tsToDate(ts) {{ var d=new Date(ts*1000); return d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate()); }}
function dateToTs(str) {{ if(!str)return 0; var p=str.split('-'); return Math.floor(new Date(Date.UTC(parseInt(p[0]),parseInt(p[1])-1,parseInt(p[2]))).getTime()/1000); }}
function pad2(n) {{ return n<10?'0'+n:''+n; }}

// ========== DOWNLOAD GUARD ==========
function guardedExport(exportFn) {{
  if (DOWNLOAD_UNLOCKED || !DOWNLOAD_ENCRYPTED) {{
    exportFn();
  }} else {{
    showDownloadModal(exportFn);
  }}
}}

// ========== CSV EXPORT (ALL series) ==========
function exportCSV() {{
  var gran=document.getElementById('sel-gran').value;
  var startTs=dateToTs(document.getElementById('date-start').value);
  var endTs=dateToTs(document.getElementById('date-end').value)+86400;
  // Export ALL series for this granularity, regardless of UI selection
  var series=[];
  var allKeys=['xaut_okx_'+gran,'xaut_bitfinex_'+gran,'btc_binance_'+gran,'spyx_mexc_'+gran,'iran_polymarket_'+gran];
  allKeys.forEach(function(key){{ if(DATA[key]&&DATA[key].length>0) series.push(key); }});
  var tsMap={{}};
  series.forEach(function(key){{ var d=getFiltered(key,startTs,endTs); d.forEach(function(row){{ if(!tsMap[row[0]])tsMap[row[0]]={{}}; tsMap[row[0]][key]=row; }}); }});
  var timestamps=Object.keys(tsMap).map(Number).sort(function(a,b){{return a-b;}});
  var headers=['timestamp','datetime'];
  series.forEach(function(key){{ var base=key.replace('_'+gran,''); headers.push(base+'_open',base+'_high',base+'_low',base+'_close',base+'_volume'); }});
  var lines=[headers.join(',')];
  timestamps.forEach(function(ts){{ var row=[ts,new Date(ts*1000).toISOString()]; series.forEach(function(key){{ var d=tsMap[ts][key]; if(d){{row.push(d[1],d[2],d[3],d[4],d[5]);}}else{{row.push('','','','','');}} }}); lines.push(row.join(',')); }});
  downloadFile(lines.join('\\n'),'crypto_all_data_'+gran+'.csv','text/csv');
}}

// ========== XLSX EXPORT (ALL series) ==========
function exportXLSX() {{
  if(typeof XLSX==='undefined'){{alert('SheetJS library not loaded.');return;}}
  var gran=document.getElementById('sel-gran').value;
  var startTs=dateToTs(document.getElementById('date-start').value);
  var endTs=dateToTs(document.getElementById('date-end').value)+86400;
  var wb=XLSX.utils.book_new();
  // Export ALL series regardless of UI selection
  var sheetConfigs=[];
  if(DATA['xaut_okx_'+gran]&&DATA['xaut_okx_'+gran].length>0) sheetConfigs.push({{key:'xaut_okx_'+gran,name:'XAUt_OKX'}});
  if(DATA['xaut_bitfinex_'+gran]&&DATA['xaut_bitfinex_'+gran].length>0) sheetConfigs.push({{key:'xaut_bitfinex_'+gran,name:'XAUt_Bitfinex'}});
  if(DATA['btc_binance_'+gran]&&DATA['btc_binance_'+gran].length>0) sheetConfigs.push({{key:'btc_binance_'+gran,name:'BTC_Binance'}});
  if(DATA['spyx_mexc_'+gran]&&DATA['spyx_mexc_'+gran].length>0) sheetConfigs.push({{key:'spyx_mexc_'+gran,name:'SPYx_MEXC'}});
  if(DATA['iran_polymarket_'+gran]&&DATA['iran_polymarket_'+gran].length>0) sheetConfigs.push({{key:'iran_polymarket_'+gran,name:'Iran_Polymarket'}});
  sheetConfigs.forEach(function(cfg){{
    var d=getFiltered(cfg.key,startTs,endTs);
    var rows=[['Timestamp','DateTime','Open','High','Low','Close','Volume']];
    d.forEach(function(r){{rows.push([r[0],new Date(r[0]*1000).toISOString(),r[1],r[2],r[3],r[4],r[5]]);}});
    var ws=XLSX.utils.aoa_to_sheet(rows);
    ws['!cols']=[{{wch:12}},{{wch:24}},{{wch:12}},{{wch:12}},{{wch:12}},{{wch:12}},{{wch:14}}];
    XLSX.utils.book_append_sheet(wb,ws,cfg.name);
  }});
  var series=sheetConfigs.map(function(c){{return c.key;}});
  var tsMap={{}};
  series.forEach(function(key){{var d=getFiltered(key,startTs,endTs);d.forEach(function(row){{if(!tsMap[row[0]])tsMap[row[0]]={{}};tsMap[row[0]][key]=row;}});}});
  var timestamps=Object.keys(tsMap).map(Number).sort(function(a,b){{return a-b;}});
  var mH=['Timestamp','DateTime'];
  sheetConfigs.forEach(function(c){{var b=c.name;mH.push(b+'_Open',b+'_High',b+'_Low',b+'_Close',b+'_Volume');}});
  var mR=[mH];
  timestamps.forEach(function(ts){{var row=[ts,new Date(ts*1000).toISOString()];series.forEach(function(key){{var d=tsMap[ts][key];if(d){{row.push(d[1],d[2],d[3],d[4],d[5]);}}else{{row.push('','','','','');}}}});mR.push(row);}});
  var mWs=XLSX.utils.aoa_to_sheet(mR);
  XLSX.utils.book_append_sheet(wb,mWs,'Merged');
  XLSX.writeFile(wb,'crypto_all_data_'+gran+'.xlsx');
}}

function downloadFile(content,filename,mime) {{
  var blob=new Blob([content],{{type:mime}});
  var url=URL.createObjectURL(blob);
  var a=document.createElement('a');
  a.href=url;a.download=filename;
  document.body.appendChild(a);a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}
// ========== SERVICE WORKER REGISTRATION ==========
if ('serviceWorker' in navigator) {{
  navigator.serviceWorker.register('sw.js').then(function(reg) {{
    console.log('SW registered:', reg.scope);
  }}).catch(function(err) {{
    console.log('SW registration failed:', err);
  }});
}}
</script>
</body>
</html>'''

    return html
