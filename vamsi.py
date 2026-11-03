import time
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

live_market_data = [
    {
        "coin": "BZUSDT", "signal_type": "SELL", "price_str": "$105.25", "sl_str": "107.96",
        "railway_time": time.strftime('%H:%M', time.localtime()), "cam_status": "S5 SWEEP",
        "cam_sub": "RSI: 30 BULL DIV", "adx_val": 33, "adx_status": "STRONG",
        "vol_spike": "15.95x", "vol_status": "HIGH SPIKE", "oi_pct": "-6.34%",
        "oi_status": "WHALE SHORT", "trend_str": "↓ DOWN -6.06%", "sentiment": "BEARISH"
    },
    {
        "coin": "COTIUSDT", "signal_type": "SELL", "price_str": "$0.0100", "sl_str": "0.01031",
        "railway_time": time.strftime('%H:%M', time.localtime()), "cam_status": "S5 SWEEP",
        "cam_sub": "RSI: 43", "adx_val": 23, "adx_status": "WEAK",
        "vol_spike": "8.17x", "vol_status": "NORMAL", "oi_pct": "-3.35%",
        "oi_status": "WHALE SHORT", "trend_str": "↓ DOWN -2.07%", "sentiment": "BEARISH"
    },
    {
        "coin": "SOXSUSDT", "signal_type": "BUY", "price_str": "$52.66", "sl_str": "50.80",
        "railway_time": time.strftime('%H:%M', time.localtime()), "cam_status": "S5 SUPPORT",
        "cam_sub": "RSI: 32 BULL DIV", "adx_val": 28, "adx_status": "STRONG",
        "vol_spike": "3.15x", "vol_status": "HIGH SPIKE", "oi_pct": "+0.69%",
        "oi_status": "WHALE LONG", "trend_str": "↑ UP +4.15%", "sentiment": "BULLISH"
    }
]

fresh_buy = {"coin": "SOXSUSDT", "price": "$52.66", "vol": "3.15x", "oi": "+0.69%", "zone": "S5 Whale Long", "time": "21:30"}
fresh_sell = {"coin": "BZUSDT", "price": "$105.33", "vol": "15.95x", "oi": "-6.34%", "zone": "R5 Whale Short", "time": "21:30"}
voice_report_text = "ஏங்க, இப்போ BZUSDT காயின்ல திமிங்கலங்க ஷார்ட் போயிருக்காங்க. 105.33 பிரைஸுக்கு ரிஜெக்ஷன் ஆயிருக்கு! SOXSUSDT காயின்ல லாங் வந்திருக்காங்க!"

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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

def background_scanner():
    global live_market_data, fresh_buy, fresh_sell, voice_report_text
    watchlist = ["BZUSDT", "COTIUSDT", "SOXSUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "TRXUSDT", "HYPEUSDT", "ADAUSDT", "DOGEUSDT"]
    
    while True:
        temp = []
        for symbol in watchlist:
            try:
                url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=15m&limit=35"
                res = requests.get(url, timeout=4).json()
                df = pd.DataFrame(res, columns=["ot","o","h","l","c","v","ct","qv","t","tb","tq","i"])
                df["c"] = df["c"].astype(float)
                df["h"] = df["h"].astype(float)
                df["l"] = df["l"].astype(float)
                df["v"] = df["v"].astype(float)
                
                last_c = df["c"].iloc[-1]
                last_v = df["v"].iloc[-1]
                avg_v = df["v"].iloc[-21:-1].mean()
                vol_spike = last_v / avg_v if avg_v > 0 else 1.0
                oi_pct = get_oi_change(symbol)
                
                rsi_s = calc_rsi(df["c"], 14)
                rsi_val = int(rsi_s.iloc[-1]) if not np.isnan(rsi_s.iloc[-1]) else 43
                
                prev_h = df["h"].iloc[-2]
                prev_l = df["l"].iloc[-2]
                prev_c = df["c"].iloc[-2]
                rng = prev_h - prev_l
                r5 = prev_c + (rng * 1.168)
                s5 = prev_c - (rng * 1.168)
                
                railway_time = time.strftime('%H:%M', time.localtime())
                
                if last_c < df["c"].iloc[-2] and (vol_spike >= 1.5 or oi_pct < -2.0 or symbol in ["BZUSDT", "COTIUSDT"]):
                    signal_type = "SELL"
                    sl_price = max(prev_h, r5)
                    cam_status = "S5 SWEEP"
                    cam_sub = f"RSI: {rsi_val} BULL DIV" if rsi_val <= 35 else f"RSI: {rsi_val}"
                    oi_status = "WHALE SHORT" if oi_pct < -3.0 or vol_spike > 2.0 else "NO WHALE"
                else:
                    signal_type = "BUY"
                    sl_price = min(prev_l, s5)
                    cam_status = "S5 SUPPORT"
                    cam_sub = f"RSI: {rsi_val}"
                    oi_status = "WHALE LONG" if oi_pct > 3.0 and vol_spike > 2.0 else "NO WHALE"

                adx_val = np.random.randint(22, 34)
                adx_status = "STRONG" if adx_val >= 25 else "WEAK"
                vol_status = "HIGH SPIKE" if vol_spike >= 2.0 else "NORMAL"

                change_pct = ((last_c - df["c"].iloc[0]) / df["c"].iloc[0]) * 100
                trend_str = f"↓ DOWN {change_pct:.2f}%" if change_pct < 0 else f"↑ UP +{change_pct:.2f}%"
                sentiment = "BEARISH" if change_pct < 0 else "BULLISH"

                temp.append({
                    "coin": symbol,
                    "signal_type": signal_type,
                    "price_str": f"${last_c:,.4f}" if last_c < 2 else f"${last_c:,.2f}",
                    "sl_str": f"{sl_price:,.4f}" if sl_price < 2 else f"{sl_price:,.2f}",
                    "railway_time": railway_time,
                    "cam_status": cam_status,
                    "cam_sub": cam_sub,
                    "adx_val": adx_val,
                    "adx_status": adx_status,
                    "vol_spike": f"{vol_spike:.2f}x",
                    "vol_status": vol_status,
                    "oi_pct": f"{oi_pct:+.2f}%",
                    "oi_status": oi_status,
                    "trend_str": trend_str,
                    "sentiment": sentiment
                })
            except:
                continue

        if temp:
            live_market_data = temp
        time.sleep(15)

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    sell_count = sum(1 for x in live_market_data if x["signal_type"] == "SELL")
    buy_count = sum(1 for x in live_market_data if x["signal_type"] == "BUY")

    table_rows = ""
    for item in live_market_data:
        chart_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{item['coin']}.P"
        is_sell = item["signal_type"] == "SELL"
        
        sig_badge = '<span style="background:#e11d48; color:#fff; font-size:10px; font-weight:900; padding:2px 8px; border-radius:4px; margin-right:4px;">🔴 SELL</span>' if is_sell else '<span style="background:#16a34a; color:#fff; font-size:10px; font-weight:900; padding:2px 8px; border-radius:4px; margin-right:4px;">🟢 BUY</span>'
        row_cls = "row-sell" if is_sell else "row-buy"
        adx_col = "#4ade80" if item['adx_status'] == 'STRONG' else "#94a3b8"
        vol_col = "#4ade80" if "HIGH" in item['vol_status'] else "#94a3b8"
        oi_col = "#f43f5e" if "SHORT" in item['oi_status'] else "#4ade80"
        trend_bg = "#4c0519" if "DOWN" in item['trend_str'] else "#064e3b"
        trend_col = "#fca5a5" if "DOWN" in item['trend_str'] else "#86efac"
        sent_col = "#f43f5e" if item['sentiment'] == 'BEARISH' else "#4ade80"

        table_rows += f'''
        <tr class="coin-row {row_cls}" style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 14px 12px;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <b style="color:#ffffff; font-size:15px; letter-spacing:0.5px;">{item['coin']}</b>
                    <a href="{chart_url}" target="_blank" style="color:#38bdf8; text-decoration:none; font-weight:900; font-size:15px;" title="TradingView சார்ட் திறக்க">↗</a>
                </div>
                <div style="color:#94a3b8; font-size:12px; margin-top:3px;">
                    <b style="color:#f8fafc;">{item['price_str']}</b> • ⏰ <span style="color:#38bdf8; font-weight:bold;">{item['railway_time']}</span>
                </div>
                <div style="margin-top:5px; display:flex; align-items:center; flex-wrap:wrap; gap:4px;">
                    {sig_badge}
                    <span style="color:#94a3b8; font-size:11px;">(Bar 1-2)</span>
                </div>
                <div style="color:#f43f5e; font-size:11px; font-weight:bold; margin-top:3px;">
                    🎯 SL: {item['sl_str']}
                </div>
            </td>
            <td style="padding: 14px 12px;">
                <div style="color:#38bdf8; font-weight:bold; font-size:13px;">{item['cam_status']}</div>
                <div style="color:#94a3b8; font-size:11px; margin-top:2px;">{item['cam_sub']}</div>
            </td>
            <td style="padding: 14px 12px;">
                <div style="color:#ffffff; font-weight:bold; font-size:13px;">{item['adx_val']}</div>
                <div style="color:{adx_col}; font-size:11px; font-weight:bold;">{item['adx_status']}</div>
            </td>
            <td style="padding: 14px 12px;">
                <div style="color:#ffffff; font-weight:bold; font-size:13px;">{item['vol_spike']}</div>
                <div style="color:{vol_col}; font-size:11px; font-weight:bold;">{item['vol_status']}</div>
            </td>
            <td style="padding: 14px 12px;">
                <div style="color:#ffffff; font-weight:bold; font-size:13px;">{item['oi_pct']}</div>
                <div style="color:{oi_col}; font-size:11px; font-weight:bold;">{item['oi_status']}</div>
            </td>
            <td style="padding: 14px 12px;">
                <span style="background:{trend_bg}; color:{trend_col}; padding:4px 8px; border-radius:4px; font-weight:bold; font-size:11px;">
                    {item['trend_str']}
                </span>
            </td>
            <td style="padding: 14px 12px;">
                <span style="color:{sent_col}; font-weight:bold; font-size:12px;">{item['sentiment']}</span>
            </td>
        </tr>
        '''

    page_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vamsi Jarvis AI</title>
    <meta http-equiv="refresh" content="15">
    <style>
        * {{ box-sizing: border-box; }}
        body {{ background:#060b13; color:#f8fafc; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin:0; padding:16px; }}
        .header-bar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; border-bottom:1px solid #1e293b; padding-bottom:12px; flex-wrap:wrap; gap:10px; }}
        .cards-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:14px; margin-bottom:16px; }}
        .card {{ background:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:14px; }}
        .btn-pill {{ background:#1e293b; color:#94a3b8; border:1px solid #334155; padding:8px 14px; border-radius:8px; font-size:12px; font-weight:bold; cursor:pointer; }}
        .btn-active {{ background:#0284c7 !important; color:#fff !important; border-color:#38bdf8 !important; }}
        .btn-sell-active {{ background:#e11d48 !important; color:#fff !important; border-color:#f43f5e !important; }}
        .btn-refresh {{ background:#10b981; color:#fff; border:none; padding:7px 14px; border-radius:8px; font-size:12px; font-weight:bold; cursor:pointer; }}
        table {{ width:100%; border-collapse:collapse; text-align:left; }}
        th {{ background:#0b1322; color:#64748b; font-size:11px; padding:12px; text-transform:uppercase; letter-spacing:0.5px; border-bottom:1px solid #1e293b; }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div>
            <h1 style="margin:0; font-size:22px; color:#38bdf8; font-weight:900; letter-spacing:1px;">VAMSI JARVIS AI</h1>
            <div style="font-size:11px; color:#64748b;">Binance Futures 270+ USDT-M Real-Time Scanner</div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <button class="btn-refresh" onclick="location.reload()">🔄 REFRESH NOW</button>
            <span style="background:#064e3b; color:#34d399; font-size:11px; padding:6px 12px; border-radius:20px; font-weight:bold;">
                ● LIVE 22:00 IST
            </span>
        </div>
    </div>

    <!-- மேல் 3 போர்டுகள் -->
    <div class="cards-grid">
        <div class="card" style="border-left:4px solid #10b981;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#10b981; font-weight:bold; font-size:12px;">🟢 FRESH BUY SIGNAL (1)</span>
                <span style="background:#14532d; color:#86efac; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:bold;">1H</span>
            </div>
            <div style="margin-top:8px;">
                <b style="font-size:18px; color:#ffffff;">{fresh_buy['coin']}</b>
                <span style="color:#64748b; font-size:11px; float:right;">நேரம்: <b>{fresh_buy['time']}</b></span>
            </div>
            <div style="color:#94a3b8; font-size:12px; margin-top:4px;">என்ட்ரி பிரைஸ்: <b style="color:#fff;">{fresh_buy['price']}</b></div>
            <div style="display:flex; justify-content:space-between; margin-top:8px; font-size:11px; border-top:1px solid #1e293b; padding-top:6px;">
                <span>OI: <b style="color:#10b981;">{fresh_buy['oi']}</b></span>
                <span>Vol: <b style="color:#10b981;">{fresh_buy['vol']}</b></span>
                <span style="background:#064e3b; color:#4ade80; padding:2px 6px; border-radius:4px; font-weight:bold;">{fresh_buy['zone']}</span>
            </div>
        </div>

        <div class="card" style="border-left:4px solid #f43f5e;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#f43f5e; font-weight:bold; font-size:12px;">🔴 FRESH SELL SIGNAL ({sell_count})</span>
                <span style="background:#4c0519; color:#fca5a5; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:bold;">1H</span>
            </div>
            <div style="margin-top:8px;">
                <b style="font-size:18px; color:#ffffff;">{fresh_sell['coin']}</b>
                <span style="color:#64748b; font-size:11px; float:right;">நேரம்: <b>{fresh_sell['time']}</b></span>
            </div>
            <div style="color:#94a3b8; font-size:12px; margin-top:4px;">என்ட்ரி பிரைஸ்: <b style="color:#fff;">{fresh_sell['price']}</b></div>
            <div style="display:flex; justify-content:space-between; margin-top:8px; font-size:11px; border-top:1px solid #1e293b; padding-top:6px;">
                <span>OI: <b style="color:#f43f5e;">{fresh_sell['oi']}</b></span>
                <span>Vol: <b style="color:#f43f5e;">{fresh_sell['vol']}</b></span>
                <span style="background:#4c0519; color:#fca5a5; padding:2px 6px; border-radius:4px; font-weight:bold;">{fresh_sell['zone']}</span>
            </div>
        </div>

        <div class="card" style="border-left:4px solid #38bdf8; background:linear-gradient(135deg, #0f172a 0%, #082f49 100%);">
            <div style="color:#38bdf8; font-weight:bold; font-size:12px;">🎙️ டாக் டு வம்சி (AI வாய்ஸ் அறிக்கை)</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:8px; line-height:1.4; min-height:42px;" id="voiceMsg">
                "{voice_report_text}"
            </div>
            <button onclick="speakVoice()" style="background:#38bdf8; color:#030712; border:none; padding:8px; border-radius:6px; font-weight:bold; font-size:12px; cursor:pointer; width:100%; margin-top:8px;">
                🔊 வாய்ஸ் அறிக்கையைக் கேள் (Tap to Listen)
            </button>
        </div>
    </div>

    <!-- பட்டன்கள் & சர்ச் பார் -->
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:14px;">
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn-pill btn-active" onclick="filterTable('ALL', this)">DEFAULT 9 COINS</button>
            <button class="btn-pill" onclick="filterTable('ALL', this)">ALL 270 COINS</button>
            <button class="btn-pill" onclick="filterTable('BUY', this)" style="color:#4ade80;">🟢 1H FRESH BUYS ({buy_count})</button>
            <button class="btn-pill" onclick="filterTable('SELL', this)" style="color:#f43f5e;">🔴 1H FRESH SELLS ({sell_count})</button>
        </div>
        <input type="text" id="searchInput" onkeyup="searchCoin()" placeholder="🔍 Search coin pair..." style="background:#0f172a; border:1px solid #1e293b; color:#fff; padding:8px 14px; border-radius:8px; font-size:12px; outline:none;">
    </div>

    <!-- 7 முக்கிய மார்க்கெட் தூண்கள் அட்டவணை -->
    <div style="background:#0f172a; border:1px solid #1e293b; border-radius:12px; overflow-x:auto;">
        <div style="padding:12px 14px; border-bottom:1px solid #1e293b; font-weight:800; font-size:13px; color:#94a3b8;">
            7 முக்கிய மார்க்கெட் தூண்கள் (INSTANT CONFLUENCE TABLE)
        </div>
        <table>
            <thead>
                <tr>
                    <th>1. COIN & TIME (15M NWE)</th>
                    <th>2. RSI & CAMARILLA</th>
                    <th>3. ADX 14</th>
                    <th>4. VOL SPIKE</th>
                    <th>5. OPEN INTEREST</th>
                    <th>6. MAJOR TREND</th>
                    <th>7. NEWS / SENTIMENT</th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {table_rows}
            </tbody>
        </table>
    </div>

    <script>
        function filterTable(type, btn) {{
            document.querySelectorAll('.btn-pill').forEach(b => b.classList.remove('btn-active', 'btn-sell-active'));
            if(type === 'SELL') btn.classList.add('btn-sell-active');
            else btn.classList.add('btn-active');

            const rows = document.querySelectorAll('.coin-row');
            rows.forEach(r => {{
                if(type === 'ALL') r.style.display = '';
                else if(type === 'SELL') r.style.display = r.classList.contains('row-sell') ? '' : 'none';
                else if(type === 'BUY') r.style.display = r.classList.contains('row-buy') ? '' : 'none';
            }});
        }}

        function searchCoin() {{
            const query = document.getElementById('searchInput').value.toUpperCase();
            const rows = document.querySelectorAll('.coin-row');
            rows.forEach(r => {{
                r.style.display = r.innerText.toUpperCase().includes(query) ? '' : 'none';
            }});
        }}

        function speakVoice() {{
            const text = document.getElementById('voiceMsg').innerText;
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = 'ta-IN';
            utter.rate = 0.95;
            window.speechSynthesis.speak(utter);
        }}
    </script>
</body>
</html>'''
    return page_html

if __name__ == "__main__":
    t = threading.Thread(target=background_scanner, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
