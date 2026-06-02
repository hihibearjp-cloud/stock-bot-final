import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import PSARIndicator

LINE_TOKEN = os.environ.get('LINE_TOKEN')
LINE_USER_ID = os.environ.get('LINE_USER_ID')

def send_line_message(msg):
    if not LINE_TOKEN or not LINE_USER_ID:
        print("測試模式，訊息如下：\n", msg)
        return
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)

def get_market_status():
    try:
        twii = yf.Ticker("^TWII").history(period="30d")
        if len(twii) < 20: return "大盤狀態未知", "#555"
        ma20 = twii['Close'].rolling(20).mean().iloc[-1]
        close = twii['Close'].iloc[-1]
        if close > ma20: return f"🟢 台股偏多 (站上月線)", "#00704A"
        else: return f"🔴 台股偏空 (跌破月線)", "#d9534f"
    except:
        return "大盤狀態讀取失敗", "#555"

def analyze():
    # 💡 抓取從 GitHub 輸入框傳來的「臨時股票代號」
    temp_stock = os.environ.get('TEMP_STOCK', '').strip().upper()
    today_str = datetime.now().strftime('%Y-%m-%d')
    market_text, market_color = get_market_status()

    # --- 判斷執行模式 ---
    if temp_stock:
        print(f"啟動單檔臨時查詢模式：{temp_stock}")
        targets = {temp_stock: "臨時查詢"}
    else:
        print("啟動每日完整雷達模式")
        targets = {
            "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2303.TW": "聯電", 
            "3711.TW": "日月光", "3034.TW": "聯詠", "2379.TW": "瑞昱", "3443.TW": "創意",
            "2382.TW": "廣達", "3231.TW": "緯創", "2376.TW": "技嘉", "2356.TW": "英業達",
            "3017.TW": "奇鋐", "3324.TW": "雙鴻", "2383.TW": "台光電", "3037.TW": "欣興",
            "1519.TW": "華城", "1513.TW": "中興電", "1504.TW": "東元", "1514.TW": "亞力",
            "8299.TW": "群聯", "2337.TW": "旺宏", "8358.TW": "金居",
            "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金",
            "QQQM": "納指ETF", "SOXX": "半導體ETF", "TSM": "台積電ADR", 
            "NVDA": "輝達", "AAPL": "蘋果", "MSFT": "微軟", "QLD": "2倍做多納指"
        }
    
    buy_signals, sell_signals = [], []

    for code, name in targets.items():
        try:
            df = yf.Ticker(code).history(period="100d")
            if len(df) < 30: 
                if temp_stock: send_line_message(f"⚠️ 找不到代號 {code} 的資料。")
                continue
            
            display_code = code.replace('.TW', '')
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['VMA20'] = df['Volume'].rolling(20).mean()
            
            indicator_bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['BB_Upper'] = indicator_bb.bollinger_hband()
            
            indicator_psar = PSARIndicator(high=df['High'], low=df['Low'], close=df['Close'], step=0.02, max_step=0.2)
            df['PSAR'] = indicator_psar.psar()
            
            indicator_atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            df['ATR'] = indicator_atr.average_true_range()
            
            df['Is_Peak'] = (df['High'] > df['High'].shift(1)) & (df['High'] > df['High'].shift(2)) & \
                            (df['High'] >= df['High'].shift(-1)) & (df['High'] >= df['High'].shift(-2))
            historical_peaks = df[df['Is_Peak'] & (df.index < df.index[-2])]
            recent_neckline = historical_peaks.iloc[-1]['High'] if not historical_peaks.empty else df['High'].iloc[-20:-3].max()

            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            
            vol_ratio = today['Volume'] / today['VMA20'] if today['VMA20'] > 0 else 0
            is_high_volume = vol_ratio >= 1.0
            
            is_breakout = (today['Close'] > recent_neckline) and (yesterday['Close'] <= recent_neckline)
            is_bullish_ma = (today['MA5'] > today['MA10']) and (today['MA10'] > today['MA20']) and (today['MA5'] > yesterday['MA5'])
            
            ma_max, ma_min = max(today['MA5'], today['MA10'], today['MA20']), min(today['MA5'], today['MA10'], today['MA20'])
            is_tangled = ((ma_max - ma_min) / ma_min) <= 0.03
            
            body_percent = (today['Close'] - today['Open']) / today['Open']
            is_super_red = (body_percent >= 0.03) and (today['Close'] > yesterday['High']) and (today['Open'] <= yesterday['Close'])

            buy_c1 = is_high_volume and is_breakout
            buy_c2 = is_bullish_ma
            buy_c3 = is_tangled and (today['Close'] > recent_neckline)
            buy_c4 = is_high_volume and is_super_red
            buy_score = sum([buy_c1, buy_c2, buy_c3, buy_c4])

            bias_20 = (today['Close'] - today['MA20']) / today['MA20']
            current_atr = today['ATR']
            atr_stop_loss = today['Close'] - (1.5 * current_atr)
            atr_take_profit = today['Close'] + (3.0 * current_atr)

            # === 💡 如果是臨時查詢，發送專屬的詳細戰情後直接結束 ===
            if temp_stock:
                report = f"🔍 【{display_code} 臨時戰情回報】\n"
                report += f"──────────────\n"
                report += f"現價: {today['Close']:.2f}\n"
                report += f"防守(停損): {atr_stop_loss:.2f}\n"
                report += f"攻擊(停利): {atr_take_profit:.2f}\n"
                report += f"──────────────\n"
                report += f"📈 趨勢: {'多方排列 ✅' if is_bullish_ma else '偏弱/震盪 ❌'}\n"
                report += f"📊 乖離: 月線 {bias_20*100:.1f}%\n"
                report += f"🔥 量能: {vol_ratio:.1f} 倍"
                send_line_message(report)
                return # 👈 重要：傳完 LINE 就結束，保護你的網頁不被覆蓋

            # (以下是原本的陣列紀錄)
            is_surging = all(df['Close'].iloc[-i] > df['MA5'].iloc[-i] for i in range(1, 4))
            is_touch_bb = today['High'] >= today['BB_Upper']
            is_sar_dead_cross = (yesterday['Close'] >= yesterday['PSAR']) and (today['Close'] < today['PSAR']) if pd.notna(yesterday['PSAR']) and pd.notna(today['PSAR']) else False

            stock_info = {
                "code": display_code, "name": name, "price": today['Close'], "vol_ratio": vol_ratio,
                "atr": current_atr, "sl": atr_stop_loss, "tp": atr_take_profit, "bias": bias_20 * 100
            }

            if buy_score > 0:
                stock_info['score'] = buy_score
                buy_signals.append(stock_info)
            if (is_surging and is_touch_bb) or (is_surging and is_sar_dead_cross):
                sell_signals.append(stock_info)

        except Exception as e:
            print(f"Error {code}: {e}")

    # === 生成 HTML 儀表板 (只有在沒有臨時查詢時才會執行到這) ===
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="AI 戰情室">
        <link rel="apple-touch-icon" href="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?q=80&w=256&auto=format&fit=crop">
        <title>戰情儀表板 | {today_str}</title>
        <style>
            :root {{ --bg-color: #121212; --card-bg: #1e1e1e; --text-main: #e0e0e0; --text-sub: #a0a0a0; --accent-green: #00704A; --accent-red: #d9534f; --border-radius: 12px; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 40px 20px 20px 20px; -webkit-user-select: none; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .market-status {{ display: inline-block; padding: 10px 20px; border-radius: 30px; background-color: var(--card-bg); border: 1px solid {market_color}; color: {market_color}; font-weight: bold; margin-top: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .grid-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
            .card {{ background-color: var(--card-bg); border-radius: var(--border-radius); padding: 20px; box-shadow: 0 8px 16px rgba(0,0,0,0.4); border-top: 4px solid var(--accent-green); transition: transform 0.2s; }}
            .card.sell {{ border-top-color: var(--accent-red); }}
            .card-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 10px; }}
            .stock-name {{ font-size: 1.4em; font-weight: bold; }}
            .stock-price {{ font-size: 1.2em; color: #fff; }}
            .data-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.95em; }}
            .label {{ color: var(--text-sub); }}
            .value-green {{ color: var(--accent-green); font-weight: bold; }}
            .value-red {{ color: var(--accent-red); font-weight: bold; }}
            .stars {{ color: #FFD700; font-size: 1.2em; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>AI 戰情儀表板</h2>
            <p style="color: var(--text-sub);">{today_str}</p>
            <div class="market-status">{market_text}</div>
        </div>
        <h3 style="color: var(--accent-green);">🟢 多方突破訊號 ({len(buy_signals)})</h3>
        <div class="grid-container">
    """
    
    for s in buy_signals:
        html_content += f"""
            <div class="card">
                <div class="card-header">
                    <div class="stock-name">{s['code']} {s['name']} <span class="stars">{"★"*s['score']}</span></div>
                    <div class="stock-price">{s['price']:.2f}</div>
                </div>
                <div class="data-row"><span class="label">量能放大</span><span class="value-green">{s['vol_ratio']:.1f}x</span></div>
                <div class="data-row"><span class="label">ATR 停損價 (防守)</span><span class="value-red">{s['sl']:.2f}</span></div>
                <div class="data-row"><span class="label">ATR 停利價 (攻擊)</span><span class="value-green">{s['tp']:.2f}</span></div>
                <div class="data-row"><span class="label">月線乖離率</span><span>{s['bias']:.1f}%</span></div>
            </div>
        """
        
    html_content += f"""
        </div>
        <h3 style="color: var(--accent-red); margin-top: 40px;">🔴 空方過熱警示 ({len(sell_signals)})</h3>
        <div class="grid-container">
    """
    
    for s in sell_signals:
        html_content += f"""
            <div class="card sell">
                <div class="card-header">
                    <div class="stock-name">{s['code']} {s['name']}</div>
                    <div class="stock-price">{s['price']:.2f}</div>
                </div>
                <div class="data-row"><span class="label">狀態</span><span class="value-red">技術指標過熱 / 趨勢轉弱</span></div>
            </div>
        """
        
    html_content += """
        </div>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

        # === 💡 破解 LINE 快取的終極武器 ===
    timestamp = datetime.now().strftime('%m%d%H%M')
    dashboard_url = f"https://hihibearjp.github.io/stock-bot-final/?v={timestamp}"

    msg_lines = [
        f"🎯 戰情摘要 ({today_str})", 
        market_text, 
        "--------------------",
        f"🟢 買進標的: {len(buy_signals)} 檔", 
        f"🔴 停利警示: {len(sell_signals)} 檔",
        "--------------------", 
        "📊 點擊查看最新戰情：",
        dashboard_url,
        "",
        "📱 (也可直接開啟手機桌面 APP)"
    ]
    
    line_msg = "\n".join(msg_lines)

    if len(buy_signals) > 0 or len(sell_signals) > 0: 
        send_line_message(line_msg)
    else:
        print("今日無訊號，但仍會更新網頁。")

