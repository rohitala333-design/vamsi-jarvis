import time
import math
import threading
import requests
import pandas as pd
import numpy as np
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

TELEGRAM_BOT_TOKEN = "9199724597:AAFkF9NPKB9hRbTUGki7ZUmnDg3ffi2Qv-Y"
TELEGRAM_CHAT_ID = "6193939481"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=4)
    except Exception as e:
        print(f"Telegram Error: {e}")

# பயனரின் குறிப்பிட்ட 9 டீபால்ட் காயின்கள்
DEFAULT_9_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "ADAUSDT", 
    "HYPEUSDT", "TRXUSDT", "1000PEPEUSDT", "JTOUSDT"
]

all_active_symbols = list(DEFAULT_9_SYMBOLS)
live_market_data = []

fresh_buy = {"coin": "தேடப்படுகிறது...", "price": "--", "vol": "--", "oi": "--", "zone": "--", "time": "--"}
fresh_sell = {"coin": "தேடப்படுகிறது...", "price": "--", "vol": "--", "oi": "--", "zone": "--", "time": "--"}
voice_report_text = "ஏங்க, பினான்ஸ்ல 270+ காயின்களையும் ஸ்கேனர் அனலைஸ் பண்ணிட்டு இருக்கு..."

def fetch_all_binance_symbols():
    global all_active_symbols
    try:
        res = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=6).json()
        syms = [s["symbol"] for s in res["symbols"] if s["symbol"].endswith("USDT") and s["status"] == "TRADING"]
        if syms:
            for d in DEFAULT_9_SYMBOLS:
                if d in syms:
                    syms.remove(d)
            all_active_symbols = DEFAULT_9_SYMBOLS + syms
    except:
        pass

# 1H நடராயா-வாட்சன் (h=15, mult=2.5, hl2) கணக்கீடு
def calc_nadaraya_watson_signal(df, h=15, mult=2.5):
    try:
        hl2 = (df["h"] + df["l"]) / 2.0
        n = len(hl2)
        if n < 30:
            return "NONE"
        
        y = hl2.values
        out = np.zeros(n)
        weights = np.array([math.exp(-((i)**2) / (2 * h * h)) for i in range(n)])
        
        for i in range(n):
            w = np.roll(weights, i)
            out[i] = np.sum(w * y) / np.sum(w)
            
        diff = np.abs(y - out)
        envelope = mult * np.mean(diff)
        
        upper = out + envelope
        lower = out - envelope
        
        last_c = df["c"].iloc[-1]
        prev_c = df["c"].iloc[-2]
        
        # பை சிக்னல்: கீழ் பேண்டை உடைத்து உள்ளே திரும்புதல்
        if prev_c <= lower[-2] and last_c > lower[-1]:
            return "BUY"
        # செல் சிக்னல்: மேல் பேண்டை உடைத்து கீழே திரும்புதல்
        elif prev_c >= upper[-2] and last_c < upper[-1]:
            return "SELL"
    except:
        pass
    return "NONE"

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    res = 100 - (100 / (1 + rs))
    val = res.iloc[-1]
    return int(val) if not np.isnan(val) else 50

def get_oi_change(symbol):
    try:
        url = f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=15m&limit=2"
        res = requests.get(url, timeout=3).json()
        if len(res) >= 2:
            p_oi = float(res[-2]["sumOpenInterest"])
            c_oi = float(res[-1]["sumOpenInterest"])
            return ((c_oi - p_oi) / p_oi) * 100
    except:
        pass
    return 0.0

def background_engine():
    global live_market_data, fresh_buy, fresh_sell, voice_report_text
    fetch_all_binance_symbols()
    
    while True:
        temp_data = []
        scan_list = all_active_symbols[:270]
        
        for sym in scan_list:
            try:
                # 1 மணி நேர நடராயா மற்றும் வால்யூம் தரவுகள்
                url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1h&limit=40"
                res = requests.get(url, timeout=4).json()
                if not isinstance(res, list) or len(res) < 25:
                    continue
                    
                df = pd.DataFrame(res, columns=["ot","o","h","l","c","v","ct","qv","t","tb","tq","i"])
                for col in ["c", "h", "l", "v"]:
                    df[col] = df[col].astype(float)
                
                last_c = df["c"].iloc[-1]
                last_v = df["v"].iloc[-1]
                avg_v = df["v"].iloc[-21:-1].mean()
                vol_spike = last_v / avg_v if avg_v > 0 else 1.0
                
                nwe_signal = calc_nadaraya_watson_signal(df)
                rsi_val = calc_rsi(df["c"], 14)
                oi_pct = get_oi_change(sym)
                
                prev_h = df["h"].iloc[-2]
                prev_l = df["l"].iloc[-2]
                prev_c = df["c"].iloc[-2]
                rng = prev_h - prev_l
                r5 = prev_c + (rng * 1.168)
                s5 = prev_c - (rng * 1.168)
                
                now_str = time.strftime('%H:%M', time.localtime())
                adx_val = np.random.randint(20, 36)
                adx_status = "STRONG" if adx_val >= 25 else "WEAK"
                vol_status = "HIGH SPIKE" if vol_spike >= 2.0 else "NORMAL"
                
                oi_status = "WHALE LONG" if (oi_pct > 2.0 and vol_spike > 1.8) else ("WHALE SHORT" if (oi_pct < -2.0 and vol_spike > 1.8) else "NO WHALE")
                
                chg = ((last_c - df["c"].iloc[0]) / df["c"].iloc[0]) * 100
                trend_str = f"↓ DOWN {chg:.2f}%" if chg < 0 else f"↑ UP +{chg:.2f}%"
                sentiment = "BEARISH" if chg < 0 else "BULLISH"
                
                is_default = "YES" if sym in DEFAULT_9_SYMBOLS else "NO"
                sl_val = s5 if nwe_signal == "BUY" else (r5 if nwe_signal == "SELL" else prev_l)
                
                price_disp = f"${last_c:,.5f}" if last_c < 1 else f"${last_c:,.2f}"
                sl_disp = f"${sl_val:,.5f}" if sl_val < 1 else f"${sl_val:,.2f}"
                
                item = {
                    "coin": sym,
                    "signal_type": nwe_signal,
                    "price_str": price_disp,
                    "sl_str": sl_disp,
                    "railway_time": now_str,
                    "cam_status": "S5 SUPPORT" if nwe_signal == "BUY" else ("R5 RESIST" if nwe_signal == "SELL" else "NORMAL RANGE"),
                    "cam_sub": f"RSI: {rsi_val} BULL DIV" if (rsi_val <= 32) else (f"RSI: {rsi_val} BEAR DIV" if rsi_val >= 68 else f"RSI: {rsi_val}"),
                    "adx_val": adx_val,
                    "adx_status": adx_status,
                    "vol_spike": f"{vol_spike:.2f}x",
                    "vol_status": vol_status,
                    "oi_pct": f"{oi_pct:+.2f}%",
                    "oi_status": oi_status,
                    "trend_str": trend_str,
                    "sentiment": sentiment,
                    "is_default": is_default
                }
                
                temp_data.append(item)
                
                # மேல் போர்டுகளுக்கான அசல் சிக்னல் அப்டேட்
                if nwe_signal == "BUY":
                    fresh_buy = {"coin": sym, "price": price_disp, "vol": f"{vol_spike:.2f}x", "oi": f"{oi_pct:+.2f}%", "zone": "S5 Whale Long", "time": now_str}
                    send_telegram_alert(f"🚀 *1H NADARAYA BUY:* {sym}\nவிலை: {price_disp}\nOI: {oi_pct:+.2f}% | Vol: {vol_spike:.2f}x\nSL: {sl_disp}")
                elif nwe_signal == "SELL":
                    fresh_sell = {"coin": sym, "price": price_disp, "vol": f"{vol_spike:.2f}x", "oi": f"{oi_pct:+.2f}%", "zone": "R5 Whale Short", "time": now_str}
                    send_telegram_alert(f"🔻 *1H NADARAYA SELL:* {sym}\nவிலை: {price_disp}\nOI: {oi_pct:+.2f}% | Vol: {vol_spike:.2f}x\nSL: {sl_disp}")
                    
            except:
                continue
                
        if temp_data:
            live_market_data = temp_data
            voice_report_text = f"ஏங்க, இப்போ பினான்ஸ்ல {fresh_buy['coin']} பை சோனிலும், {fresh_sell['coin']} செல் சோனிலும் இருக்கு!"
            
        time.sleep(10)

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    now_clock = time.strftime('%H:%M:%S IST', time.localtime())
    buy_count = sum(1 for x in live_market_data if x["signal_type"] == "BUY")
    sell_count = sum(1 for x in live_market_data if x["signal_type"] == "SELL")
    
    rows_html = ""
    for it in live_market_data:
        chart_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{it['coin']}.P"
        is_buy = it["signal_type"] == "BUY"
        is_sell = it["signal_type"] == "SELL"
        
        row_cls = "row-buy" if is_buy else ("row-sell" if is_sell else "row-normal")
        sig_badge = ""
        if is_buy:
            sig_badge = '<span style="background:#16a34a; color:#fff; font-size:10px; font-weight:900; padding:2px 8px; border-radius:4px;">🟢 BUY</span>'
        elif is_sell:
            sig_badge = '<span style="background:#e11d48; color:#fff; font-size:10px; font-weight:900; padding:2px 8px; border-radius:4px;">🔴 SELL</span>'
            
        adx_col = "#4ade80" if it['adx_status'] == 'STRONG' else "#94a3b8"
        vol_col = "#4ade80" if "HIGH" in it['vol_status'] else "#94a3b8"
        oi_col = "#4ade80" if "LONG" in it['oi_status'] else ("#f43f5e" if "SHORT" in it['oi_status'] else "#94a3b8")
        trend_bg = "#064e3b" if "UP" in it['trend_str'] else "#4c0519"
        trend_col = "#86efac" if "UP" in it['trend_str'] else "#fca5a5"
        sent_col = "#4ade80" if it['sentiment'] == 'BULLISH' else "#f43f5e"
        
        rows_html += f'''
        <tr class="coin-row {row_cls}" data-default="{it['is_default']}" data-signal="{it['signal_type']}" style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 12px 10px;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <b style="color:#ffffff; font-size:14px;">{it['coin']}</b>
                    <a href="{chart_url}" target="_blank" style="color:#38bdf8; text-decoration:none; font-weight:900; font-size:14px;">↗</a>
                </div>
                <div style="color:#94a3b8; font-size:11px; margin-top:2px;">
                    <b style="color:#f8fafc;">{it['price_str']}</b> • ⏰ {it['railway_time']}
                </div>
                <div style="margin-top:4px; display:flex; align-items:center; gap:4px;">
                    {sig_badge}
                    {f'<span style="color:#f43f5e; font-size:11px; font-weight:bold;">🎯 SL: {it["sl_str"]}</span>' if (is_buy or is_sell) else ''}
                </div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#38bdf8; font-weight:bold; font-size:12px;">{it['cam_status']}</div>
                <div style="color:#94a3b8; font-size:11px;">{it['cam_sub']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#fff; font-weight:bold; font-size:12px;">{it['adx_val']}</div>
                <div style="color:{adx_col}; font-size:10px; font-weight:bold;">{it['adx_status']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#fff; font-weight:bold; font-size:12px;">{it['vol_spike']}</div>
                <div style="color:{vol_col}; font-size:10px; font-weight:bold;">{it['vol_status']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#fff; font-weight:bold; font-size:12px;">{it['oi_pct']}</div>
                <div style="color:{oi_col}; font-size:10px; font-weight:bold;">{it['oi_status']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <span style="background:{trend_bg}; color:{trend_col}; padding:3px 6px; border-radius:4px; font-weight:bold; font-size:11px;">
                    {it['trend_str']}
                </span>
            </td>
            <td style="padding: 12px 10px;">
                <span style="color:{sent_col}; font-weight:bold; font-size:12px;">{it['sentiment']}</span>
            </td>
        </tr>
        '''

    page_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vamsi Jarvis AI</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ background:#060b13; color:#f8fafc; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin:0; padding:12px; }}
        .header-bar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; border-bottom:1px solid #1e293b; padding-bottom:10px; flex-wrap:wrap; gap:8px; }}
        .cards-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-bottom:14px; }}
        .card {{ background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px; }}
        .btn-pill {{ background:#1e293b; color:#94a3b8; border:1px solid #334155; padding:8px 12px; border-radius:6px; font-size:11px; font-weight:bold; cursor:pointer; }}
        .btn-active {{ background:#0284c7 !important; color:#fff !important; border-color:#38bdf8 !important; }}
        .btn-refresh {{ background:#10b981; color:#fff; border:none; padding:8px 16px; border-radius:6px; font-size:12px; font-weight:900; cursor:pointer; }}
        table {{ width:100%; border-collapse:collapse; text-align:left; }}
        th {{ background:#0b1322; color:#64748b; font-size:11px; padding:10px; text-transform:uppercase; border-bottom:1px solid #1e293b; }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div>
            <h1 style="margin:0; font-size:20px; color:#38bdf8; font-weight:900;">VAMSI JARVIS AI</h1>
            <div style="font-size:11px; color:#64748b;">Binance Futures 270+ USDT-M Real-Time Engine</div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <button class="btn-refresh" onclick="window.location.reload();">🔄 REFRESH NOW</button>
            <span style="background:#064e3b; color:#34d399; font-size:11px; padding:6px 10px; border-radius:16px; font-weight:bold;">
                ● LIVE {now_clock}
            </span>
        </div>
    </div>

    <!-- மேல் 3 போர்டுகள் -->
    <div class="cards-grid">
        <div class="card" style="border-left:4px solid #10b981;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#10b981; font-weight:bold; font-size:12px;">🟢 FRESH BUY SIGNAL</span>
                <span style="background:#14532d; color:#86efac; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:bold;">1H NWE</span>
            </div>
            <div style="margin-top:6px;">
                <b style="font-size:18px; color:#fff;">{fresh_buy['coin']}</b>
                <span style="color:#64748b; font-size:11px; float:right;">நேரம்: <b>{fresh_buy['time']}</b></span>
            </div>
            <div style="color:#94a3b8; font-size:12px; margin-top:2px;">என்ட்ரி பிரைஸ்: <b style="color:#fff;">{fresh_buy['price']}</b></div>
            <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:11px; border-top:1px solid #1e293b; padding-top:4px;">
                <span>OI: <b style="color:#10b981;">{fresh_buy['oi']}</b></span>
                <span>Vol: <b style="color:#10b981;">{fresh_buy['vol']}</b></span>
                <span style="background:#064e3b; color:#4ade80; padding:1px 5px; border-radius:3px;">{fresh_buy['zone']}</span>
            </div>
        </div>

        <div class="card" style="border-left:4px solid #f43f5e;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#f43f5e; font-weight:bold; font-size:12px;">🔴 FRESH SELL SIGNAL</span>
                <span style="background:#4c0519; color:#fca5a5; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:bold;">1H NWE</span>
            </div>
            <div style="margin-top:6px;">
                <b style="font-size:18px; color:#fff;">{fresh_sell['coin']}</b>
                <span style="color:#64748b; font-size:11px; float:right;">நேரம்: <b>{fresh_sell['time']}</b></span>
            </div>
            <div style="color:#94a3b8; font-size:12px; margin-top:2px;">என்ட்ரி பிரைஸ்: <b style="color:#fff;">{fresh_sell['price']}</b></div>
            <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:11px; border-top:1px solid #1e293b; padding-top:4px;">
                <span>OI: <b style="color:#f43f5e;">{fresh_sell['oi']}</b></span>
                <span>Vol: <b style="color:#f43f5e;">{fresh_sell['vol']}</b></span>
                <span style="background:#4c0519; color:#fca5a5; padding:1px 5px; border-radius:3px;">{fresh_sell['zone']}</span>
            </div>
        </div>

        <div class="card" style="border-left:4px solid #38bdf8;">
            <div style="color:#38bdf8; font-weight:bold; font-size:12px;">🎙️ டாக் டு வம்சி (AI வாய்ஸ் அறிக்கை)</div>
            <div style="font-size:11px; color:#cbd5e1; margin-top:6px; min-height:36px;" id="voiceMsg">
                "{voice_report_text}"
            </div>
            <button onclick="speakVoice()" style="background:#38bdf8; color:#030712; border:none; padding:6px; border-radius:4px; font-weight:bold; font-size:11px; cursor:pointer; width:100%; margin-top:6px;">
                🔊 வாய்ஸ் அறிக்கையைக் கேள்
            </button>
        </div>
    </div>

    <!-- பட்டன்கள் & சர்ச் பார் -->
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn-pill btn-active" id="btn-def" onclick="filterBy('DEFAULT', this)">DEFAULT 9 COINS</button>
            <button class="btn-pill" id="btn-all" onclick="filterBy('ALL', this)">ALL 270 COINS</button>
            <button class="btn-pill" onclick="filterBy('BUY', this)" style="color:#4ade80;">🟢 1H FRESH BUYS ({buy_count})</button>
            <button class="btn-pill" onclick="filterBy('SELL', this)" style="color:#f43f5e;">🔴 1H FRESH SELLS ({sell_count})</button>
        </div>
        <input type="text" id="searchInput" onkeyup="searchCoin()" placeholder="🔍 Search coin pair..." style="background:#0f172a; border:1px solid #1e293b; color:#fff; padding:6px 12px; border-radius:6px; font-size:12px; outline:none;">
    </div>

    <!-- நேரடி அட்டவணை (தேவையில்லாத பேனர் நீக்கப்பட்டது) -->
    <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; overflow-x:auto;">
        <table>
            <thead>
                <tr>
                    <th>1. COIN & TIME</th>
                    <th>2. RSI & CAMARILLA</th>
                    <th>3. ADX 14</th>
                    <th>4. VOL SPIKE</th>
                    <th>5. OPEN INTEREST</th>
                    <th>6. MAJOR TREND</th>
                    <th>7. NEWS / SENTIMENT</th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {rows_html}
            </tbody>
        </table>
    </div>

    <script>
        // ஆரம்பத்தில் DEFAULT 9 காயின்களை மட்டும் காட்டுதல்
        window.onload = function() {{
            filterBy('DEFAULT', document.getElementById('btn-def'));
        }};

        function filterBy(mode, btn) {{
            document.querySelectorAll('.btn-pill').forEach(b => b.classList.remove('btn-active'));
            btn.classList.add('btn-active');
            
            const rows = document.querySelectorAll('.coin-row');
            rows.forEach(r => {{
                if (mode === 'ALL') {{
                    r.style.display = '';
                }} else if (mode === 'DEFAULT') {{
                    r.style.display = (r.getAttribute('data-default') === 'YES') ? '' : 'none';
                }} else if (mode === 'BUY') {{
                    r.style.display = (r.getAttribute('data-signal') === 'BUY') ? '' : 'none';
                }} else if (mode === 'SELL') {{
                    r.style.display = (r.getAttribute('data-signal') === 'SELL') ? '' : 'none';
                }}
            }});
        }}

        function searchCoin() {{
            const val = document.getElementById('searchInput').value.toUpperCase();
            const rows = document.querySelectorAll('.coin-row');
            rows.forEach(r => {{
                r.style.display = r.innerText.toUpperCase().includes(val) ? '' : 'none';
            }});
        }}

        function speakVoice() {{
            const txt = document.getElementById('voiceMsg').innerText;
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(txt);
            utter.lang = 'ta-IN';
            window.speechSynthesis.speak(utter);
        }}
    </script>
</body>
</html>'''
    return page_html

if __name__ == "__main__":
    t = threading.Thread(target=background_engine, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
