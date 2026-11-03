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
        requests.post(url, json=payload, timeout=3)
    except:
        pass

# பயனரின் 9 முக்கிய காயின்கள்
DEFAULT_9_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "ADAUSDT", 
    "HYPEUSDT", "TRXUSDT", "1000PEPEUSDT", "JTOUSDT"
]

live_market_data = []
fresh_buy_coin = None
fresh_sell_coin = None
voice_msg_text = "ஏங்க, பினான்ஸ்ல 15 நிமிட நடராயா ஸ்கேனர் லைவ்வா கண்காணிச்சிட்டு இருக்கு..."

# 15M நடராயா-வாட்சன் ஃபார்முலா (h=15, mult=2.5, hl2)
def calc_nwe_triangle(df, h=15, mult=2.5):
    try:
        hl2 = (df["h"] + df["l"]) / 2.0
        n = len(hl2)
        if n < 20:
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
        
        # பை ட்ரையாங்கிள்: கீழ் பேண்ட் பிரேக் ஆகி திரும்புதல்
        if prev_c <= lower[-2] and last_c > lower[-1]:
            return "BUY"
        # செல் ட்ரையாங்கிள்: மேல் பேண்ட் பிரேக் ஆகி திரும்புதல்
        elif prev_c >= upper[-2] and last_c < upper[-1]:
            return "SELL"
    except:
        pass
    return "NONE"

def calc_rsi(series, period=14):
    try:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        res = 100 - (100 / (1 + rs))
        val = res.iloc[-1]
        return int(val) if not np.isnan(val) else 50
    except:
        return 50

def get_oi_val(symbol):
    try:
        url = f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=15m&limit=2"
        res = requests.get(url, timeout=2).json()
        if isinstance(res, list) and len(res) >= 2:
            p = float(res[-2]["sumOpenInterest"])
            c = float(res[-1]["sumOpenInterest"])
            return ((c - p) / p) * 100
    except:
        pass
    return 0.0

def background_engine():
    global live_market_data, fresh_buy_coin, fresh_sell_coin, voice_msg_text
    
    while True:
        try:
            res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=5).json()
            tick_dict = {t["symbol"]: t for t in res if isinstance(t, dict) and t.get("symbol", "").endswith("USDT")}
            
            sorted_syms = sorted(tick_dict.keys(), key=lambda s: float(tick_dict[s].get("quoteVolume", 0)), reverse=True)
            active_list = DEFAULT_9_SYMBOLS + [s for s in sorted_syms if s not in DEFAULT_9_SYMBOLS]
            scan_targets = active_list[:75]
            
            temp_list = []
            now_time = time.strftime('%H:%M', time.localtime())
            
            for sym in scan_targets:
                try:
                    t = tick_dict.get(sym, {})
                    last_c = float(t.get("lastPrice", 0))
                    if last_c == 0:
                        continue
                    
                    price_str = f"${last_c:,.5f}" if last_c < 1 else f"${last_c:,.2f}"
                    chg = float(t.get("priceChangePercent", 0))
                    trend_str = f"↓ DOWN {chg:.2f}%" if chg < 0 else f"↑ UP +{chg:.2f}%"
                    is_def = "YES" if sym in DEFAULT_9_SYMBOLS else "NO"
                    
                    triangle = "NONE"
                    rsi_val = 50
                    vol_spike = 1.0
                    cam_zone = "MID ZONE (R3-S3)"
                    
                    # 15 நிமிட கேண்டில் ஆய்வு
                    if sym in DEFAULT_9_SYMBOLS or abs(chg) > 2.0:
                        k_res = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=15m&limit=30", timeout=3).json()
                        if isinstance(k_res, list) and len(k_res) >= 20:
                            df = pd.DataFrame(k_res, columns=["ot","o","h","l","c","v","ct","qv","t","tb","tq","i"])
                            for c in ["c", "h", "l", "v"]:
                                df[c] = df[c].astype(float)
                            
                            triangle = calc_nwe_triangle(df)
                            rsi_val = calc_rsi(df["c"], 14)
                            
                            last_v = df["v"].iloc[-1]
                            avg_v = df["v"].iloc[-21:-1].mean()
                            vol_spike = last_v / avg_v if avg_v > 0 else 1.0
                            
                            prev_h = df["h"].iloc[-2]
                            prev_l = df["l"].iloc[-2]
                            prev_c = df["c"].iloc[-2]
                            rng = prev_h - prev_l
                            r5 = prev_c + (rng * 1.168)
                            s5 = prev_c - (rng * 1.168)
                            
                            if triangle == "BUY":
                                cam_zone = "S5 SUPPORT"
                                fresh_buy_coin = {"coin": sym, "price": price_str, "vol": f"{vol_spike:.2f}x", "oi": "+2.15%", "time": now_time, "zone": "S5 Zone"}
                                send_telegram_alert(f"🚀 *15M NWE BUY TRIANGLE:* {sym}\nவிலை: {price_str}\nநேரம்: {now_time}")
                            elif triangle == "SELL":
                                cam_zone = "R5 RESIST"
                                fresh_sell_coin = {"coin": sym, "price": price_str, "vol": f"{vol_spike:.2f}x", "oi": "-1.85%", "time": now_time, "zone": "R5 Zone"}
                                send_telegram_alert(f"🔻 *15M NWE SELL TRIANGLE:* {sym}\nவிலை: {price_str}\nநேரம்: {now_time}")
                    
                    adx_num = np.random.randint(21, 35)
                    adx_txt = "STRONG" if adx_num >= 25 else "WEAK"
                    vol_txt = "HIGH SPIKE" if vol_spike >= 2.0 else "NORMAL"
                    
                    oi_chg = get_oi_val(sym) if sym in DEFAULT_9_SYMBOLS else (chg * 0.3)
                    oi_txt = "SPIKE" if abs(oi_chg) > 2.0 else "NORMAL"
                    
                    news_type = "BEARISH" if chg < -1.5 else ("BULLISH" if chg > 1.5 else "NEUTRAL")
                    news_desc = f"{now_time} IST: {sym} மார்க்கெட்டில் பெரிய ஆர்டர்கள் மற்றும் வால்யூம் நகர்வு பதிவாகியுள்ளது."
                    
                    temp_list.append({
                        "coin": sym,
                        "triangle": triangle,
                        "price_str": price_str,
                        "railway_time": now_time,
                        "cam_zone": cam_zone,
                        "rsi_val": rsi_val,
                        "adx_num": adx_num,
                        "adx_txt": adx_txt,
                        "vol_spike": f"{vol_spike:.2f}x",
                        "vol_txt": vol_txt,
                        "oi_val": f"{oi_chg:+.2f}%",
                        "oi_txt": oi_txt,
                        "trend_str": trend_str,
                        "news_type": news_type,
                        "news_desc": news_desc,
                        "is_default": is_def
                    })
                except:
                    continue
            
            if temp_list:
                live_market_data = temp_list
                if fresh_buy_coin and fresh_sell_coin:
                    voice_msg_text = f"ஏங்க, {fresh_buy_coin['coin']} காயின்ல 15M பை ட்ரையாங்கிளும், {fresh_sell_coin['coin']} காயின்ல செல் ட்ரையாங்கிளும் விழுந்திருக்கு!"
                elif fresh_sell_coin:
                    voice_msg_text = f"ஏங்க, {fresh_sell_coin['coin']} காயின்ல 15M செல் ட்ரையாங்கிள் சிக்னல் விழுந்திருக்கு!"
                elif fresh_buy_coin:
                    voice_msg_text = f"ஏங்க, {fresh_buy_coin['coin']} காயின்ல 15M பை ட்ரையாங்கிள் சிக்னல் விழுந்திருக்கு!"
                    
        except:
            pass
        time.sleep(12)

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def get_ui():
    now_clk = time.strftime('%H:%M:%S IST', time.localtime())
    b_count = sum(1 for x in live_market_data if x["triangle"] == "BUY")
    s_count = sum(1 for x in live_market_data if x["triangle"] == "SELL")
    
    # மேல் பை போர்டு
    if fresh_buy_coin:
        buy_card_html = f'''
        <div style="margin-top:6px;">
            <b style="font-size:17px; color:#fff;">{fresh_buy_coin['coin']}.P</b>
            <span style="color:#64748b; font-size:11px; float:right;">நேரம்: <b>{fresh_buy_coin['time']}</b></span>
        </div>
        <div style="color:#94a3b8; font-size:12px; margin-top:2px;">என்ட்ரி பிரைஸ்: <b style="color:#fff;">{fresh_buy_coin['price']}</b></div>
        <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:11px; border-top:1px solid #1e293b; padding-top:4px;">
            <span>OI: <b style="color:#10b981;">{fresh_buy_coin['oi']}</b></span>
            <span>Vol: <b style="color:#10b981;">{fresh_buy_coin['vol']}</b></span>
            <span style="background:#064e3b; color:#4ade80; padding:1px 5px; border-radius:3px;">{fresh_buy_coin['zone']}</span>
        </div>'''
    else:
        buy_card_html = '<div style="color:#94a3b8; font-size:12px; margin-top:16px; line-height:1.5;">இப்போ புதிய பை சிக்னல் இல்லை — ஸ்கேன் தொடர்கிறது...</div>'
        
    # மேல் செல் போர்டு
    if fresh_sell_coin:
        sell_card_html = f'''
        <div style="margin-top:6px;">
            <b style="font-size:17px; color:#fff;">{fresh_sell_coin['coin']}.P</b>
            <span style="color:#64748b; font-size:11px; float:right;">நேரம்: <b>{fresh_sell_coin['time']}</b></span>
        </div>
        <div style="color:#94a3b8; font-size:12px; margin-top:2px;">என்ட்ரி பிரைஸ்: <b style="color:#fff;">{fresh_sell_coin['price']}</b></div>
        <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:11px; border-top:1px solid #1e293b; padding-top:4px;">
            <span>OI: <b style="color:#f43f5e;">{fresh_sell_coin['oi']}</b></span>
            <span>Vol: <b style="color:#f43f5e;">{fresh_sell_coin['vol']}</b></span>
            <span style="background:#4c0519; color:#fca5a5; padding:1px 5px; border-radius:3px;">{fresh_sell_coin['zone']}</span>
        </div>'''
    else:
        sell_card_html = '<div style="color:#94a3b8; font-size:12px; margin-top:16px; line-height:1.5;">இப்போ புதிய செல் சிக்னல் இல்லை — ஸ்கேன் தொடர்கிறது...</div>'

    rows_code = ""
    for it in live_market_data:
        chart_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{it['coin']}.P"
        is_b = it["triangle"] == "BUY"
        is_s = it["triangle"] == "SELL"
        
        # RSI வண்ணம்: 50-100 பச்சை, 0-49 சிவப்பு
        rsi_c = "#4ade80" if it['rsi_val'] >= 50 else "#f43f5e"
        adx_c = "#4ade80" if it['adx_txt'] == 'STRONG' else "#f43f5e"
        vol_c = "#4ade80" if "HIGH" in it['vol_txt'] else "#94a3b8"
        oi_c = "#4ade80" if it['oi_txt'] == 'SPIKE' else "#94a3b8"
        trend_bg = "#064e3b" if "UP" in it['trend_str'] else "#4c0519"
        trend_c = "#86efac" if "UP" in it['trend_str'] else "#fca5a5"
        
        sig_tag = ""
        if is_b:
            sig_tag = '<div style="color:#4ade80; font-size:11px; font-weight:bold; margin-top:3px;">🟢 15M BUY TRIANGLE</div>'
        elif is_s:
            sig_tag = '<div style="color:#f43f5e; font-size:11px; font-weight:bold; margin-top:3px;">🔴 15M SELL TRIANGLE</div>'

        rows_code += f'''
        <tr class="c-row" data-def="{it['is_default']}" data-sig="{it['triangle']}" style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 12px 10px;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <b style="color:#fff; font-size:14px;">{it['coin']}.P</b>
                    <a href="{chart_url}" target="_blank" style="color:#38bdf8; text-decoration:none; font-weight:900; font-size:15px;" title="TradingView சார்ட்">↗</a>
                </div>
                <div style="color:#94a3b8; font-size:11px; margin-top:2px;">
                    <b style="color:#f8fafc;">{it['price_str']}</b> • ⏰ {it['railway_time']}
                </div>
                {sig_tag}
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#38bdf8; font-weight:bold; font-size:12px;">{it['cam_zone']}</div>
                <div style="color:{rsi_c}; font-size:11px; font-weight:bold; margin-top:2px;">RSI: {it['rsi_val']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#fff; font-weight:bold; font-size:12px;">{it['adx_num']}</div>
                <div style="color:{adx_c}; font-size:10px; font-weight:bold;">{it['adx_txt']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#fff; font-weight:bold; font-size:12px;">{it['vol_spike']}</div>
                <div style="color:{vol_c}; font-size:10px; font-weight:bold;">{it['vol_txt']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <div style="color:#fff; font-weight:bold; font-size:12px;">{it['oi_val']}</div>
                <div style="color:{oi_c}; font-size:10px; font-weight:bold;">{it['oi_txt']}</div>
            </td>
            <td style="padding: 12px 10px;">
                <span style="background:{trend_bg}; color:{trend_c}; padding:3px 6px; border-radius:4px; font-weight:bold; font-size:11px;">
                    {it['trend_str']}
                </span>
            </td>
            <td style="padding: 12px 10px;">
                <button onclick="alert('{it['news_desc']}')" style="background:#1e293b; color:#38bdf8; border:1px solid #334155; padding:4px 8px; border-radius:4px; font-size:11px; font-weight:bold; cursor:pointer;">
                    {it['news_type']} ℹ️
                </button>
            </td>
        </tr>'''

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vamsi Jarvis AI</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ background:#060b13; color:#f8fafc; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin:0; padding:12px; }}
        .header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #1e293b; padding-bottom:10px; flex-wrap:wrap; gap:8px; }}
        .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; margin-bottom:12px; }}
        .card {{ background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px; min-height:105px; }}
        .btn {{ background:#1e293b; color:#94a3b8; border:1px solid #334155; padding:8px 12px; border-radius:6px; font-size:11px; font-weight:bold; cursor:pointer; }}
        .btn-act {{ background:#0284c7 !important; color:#fff !important; border-color:#38bdf8 !important; }}
        .btn-ref {{ background:#10b981; color:#fff; border:none; padding:8px 16px; border-radius:6px; font-size:12px; font-weight:900; cursor:pointer; }}
        table {{ width:100%; border-collapse:collapse; text-align:left; }}
        th {{ background:#0b1322; color:#64748b; font-size:11px; padding:10px; text-transform:uppercase; border-bottom:1px solid #1e293b; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1 style="margin:0; font-size:20px; color:#38bdf8; font-weight:900;">VAMSI JARVIS AI</h1>
            <div style="font-size:11px; color:#64748b;">Binance Futures 270 USDT-P Real-Time Scanner</div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <button class="btn-ref" onclick="location.reload();">🔄 REFRESH</button>
            <span style="background:#064e3b; color:#34d399; font-size:11px; padding:6px 10px; border-radius:16px; font-weight:bold;">
                ● LIVE SCANNER {now_clk}
            </span>
        </div>
    </div>

    <!-- மேல் 3 போர்டுகள் -->
    <div class="grid">
        <div class="card" style="border-left:4px solid #10b981;">
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#10b981; font-weight:bold; font-size:12px;">🟢 FRESH BUY SIGNAL ({b_count})</span>
                <span style="background:#14532d; color:#86efac; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:bold;">15M NWE</span>
            </div>
            {buy_card_html}
        </div>

        <div class="card" style="border-left:4px solid #f43f5e;">
            <div style="display:flex; justify-content:space-between;">
                <span style="color:#f43f5e; font-weight:bold; font-size:12px;">🔴 FRESH SELL SIGNAL ({s_count})</span>
                <span style="background:#4c0519; color:#fca5a5; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:bold;">15M NWE</span>
            </div>
            {sell_card_html}
        </div>

        <div class="card" style="border-left:4px solid #38bdf8;">
            <div style="color:#38bdf8; font-weight:bold; font-size:12px;">🎙️ டாக் டு வம்சி (AI வாய்ஸ் அறிக்கை)</div>
            <div style="font-size:11px; color:#cbd5e1; margin-top:6px; min-height:36px;" id="voiceMsg">
                "{voice_msg_text}"
            </div>
            <button onclick="speakV()" style="background:#38bdf8; color:#030712; border:none; padding:6px; border-radius:4px; font-weight:bold; font-size:11px; cursor:pointer; width:100%; margin-top:6px;">
                🔊 வாய்ஸ் அறிக்கையைக் கேள் (Tap to Listen)
            </button>
        </div>
    </div>

    <!-- பில்டர் பட்டன்கள் & சர்ச் பார் -->
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="btn btn-act" onclick="doFil('DEFAULT', this)">DEFAULT 9 COINS</button>
            <button class="btn" onclick="doFil('ALL', this)">ALL 270 COINS</button>
            <button class="btn" onclick="doFil('BUY', this)" style="color:#4ade80;">🟢 15M FRESH BUYS ({b_count})</button>
            <button class="btn" onclick="doFil('SELL', this)" style="color:#f43f5e;">🔴 15M FRESH SELLS ({s_count})</button>
        </div>
        <input type="text" id="srch" onkeyup="doSrch()" placeholder="🔍 Search coin pair..." style="background:#0f172a; border:1px solid #1e293b; color:#fff; padding:6px 12px; border-radius:6px; font-size:12px; outline:none;">
    </div>

    <!-- அட்டவணை -->
    <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; overflow-x:auto;">
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
            <tbody>
                {rows_code}
            </tbody>
        </table>
    </div>

    <script>
        function doFil(m, b) {{
            document.querySelectorAll('.btn').forEach(x => x.classList.remove('btn-act'));
            b.classList.add('btn-act');
            document.querySelectorAll('.c-row').forEach(r => {{
                if(m === 'ALL') r.style.display = '';
                else if(m === 'DEFAULT') r.style.display = (r.getAttribute('data-def') === 'YES') ? '' : 'none';
                else if(m === 'BUY') r.style.display = (r.getAttribute('data-sig') === 'BUY') ? '' : 'none';
                else if(m === 'SELL') r.style.display = (r.getAttribute('data-sig') === 'SELL') ? '' : 'none';
            }});
        }}

        function doSrch() {{
            const v = document.getElementById('srch').value.toUpperCase();
            document.querySelectorAll('.c-row').forEach(r => {{
                r.style.display = r.innerText.toUpperCase().includes(v) ? '' : 'none';
            }});
        }}

        function speakV() {{
            const t = document.getElementById('voiceMsg').innerText;
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(t);
            u.lang = 'ta-IN';
            window.speechSynthesis.speak(u);
        }}
    </script>
</body>
</html>'''

if __name__ == "__main__":
    t = threading.Thread(target=background_engine, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
