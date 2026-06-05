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
    temp_stock = os.environ.get('TEMP_STOCK', '').strip().upper()
    today_str = datetime.now().strftime('%Y-%m-%d')
    market_text, market_color = get_market_status()

    if temp_stock:
        targets = {temp_stock: "臨時查詢"}
    else:
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
            if len(df) < 30: continue
            
            display_code = code.replace('.TW', '')
            
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['VMA20'] = df['Volume'].rolling(20).mean()
            
            indicator_bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['BB_Upper'] = indicator_bb.bollinger_hband()
            df['BB_Lower'] = indicator_bb.bollinger_lband()
            
            # SAR 指標
            indicator_psar = PSARIndicator(high=df['High'], low=df['Low'], close=df['Close'], step=0.02, max_step=0.2)
            df['PSAR'] = indicator_psar.psar()
            current_sar = df['PSAR'].iloc[-1]
            
            # ATR 指標
            indicator_atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            current_atr = indicator_atr.average_true_range().iloc[-1]
            
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            
            vol_ratio = today['Volume'] / today['VMA20'] if today['VMA20'] > 0 else 0
            
            # 策略 A：強勢突破 (右側)
            df['Is_Peak'] = (df['High'] > df['High'].shift(1)) & (df['High'] > df['High'].shift(2)) & \
                            (df['High'] >= df['High'].shift(-1)) & (df['High'] >= df['High'].shift(-2))
            historical_peaks = df[df['Is_Peak'] & (df.index < df.index[-2])]
            recent_neckline = historical_peaks.iloc[-1]['High'] if not historical_peaks.empty else df['High'].iloc[-20:-3].max()
            
            is_breakout = (today['Close'] > recent_neckline) and (yesterday['Close'] <= recent_neckline)
            is_bullish_ma = (today['MA5'] > today['MA10']) and (today['MA10'] > today['MA20']) and (today['MA5'] > yesterday['MA5'])
            ma_max, ma_min = max(today['MA5'], today['MA10'], today['MA20']), min(today['MA5'], today['MA10'], today['MA20'])
            is_tangled = ((ma_max - ma_min) / ma_min) <= 0.03
            body_percent = (today['Close'] - today['Open']) / today['Open'] if today['Open'] > 0 else 0
            is_super_red = (body_percent >= 0.03) and (today['Close'] > yesterday['High'])
            
            buy_score = sum([is_breakout and vol_ratio >= 1.0, is_bullish_ma, is_tangled and (today['Close'] > recent_neckline), vol_ratio >= 1.0 and is_super_red])
            
            # 策略 B：跌深反彈承接雷達 (左側)
            is_dip_support = (today['Low'] <= today['BB_Lower']) and (today['Close'] > today['Open'])

            bias_20 = ((today['Close'] - today['MA20']) / today['MA20']) * 100
            atr_stop_loss = today['Close'] - (1.5 * current_atr)
            atr_take_profit = today['Close'] + (3.0 * current_atr)
            
            # 吊燈停損價
            recent_max_high = df['High'].iloc[-20:].max()
            chandelier_exit_price = recent_max_high - (2.5 * current_atr)

            # 將 SAR 加入傳遞給 UI 的資料中
            stock_info = {
                "code": display_code, "name": name, "price": today['Close'], "vol_ratio": vol_ratio,
                "sl": atr_stop_loss, "tp": atr_take_profit, "chandelier": chandelier_exit_price, 
                "psar": current_sar, "bias": bias_20, "mode": "強勢突破"
            }

            if buy_score > 0:
                stock_info['score'] = buy_score
                buy_signals.append(stock_info)
            elif is_dip_support:
                stock_info['score'] = 1
                stock_info['mode'] = "逢低承接" 
                buy_signals.append(stock_info)

            # 賣出策略
            is_sar_dead_cross = (yesterday['Close'] >= yesterday['PSAR']) and (today['Close'] < today['PSAR'])
            is_touch_bb_upper = today['High'] >= today['BB_Upper']
            is_chandelier_exit = today['Close'] < chandelier_exit_price
            
            if is_sar_dead_cross:
                stock_info['reason'] = "短線極速反轉 (SAR死叉)"
                sell_signals.append(stock_info)
            elif is_chandelier_exit:
                stock_info['reason'] = "波段趨勢破線 (吊燈停損)"
                sell_signals.append(stock_info)
            elif is_touch_bb_upper and today['Close'] > today['MA5']:
                stock_info['reason'] = "技術指標過熱 (布林上軌)"
                sell_signals.append(stock_info)

            if temp_stock:
                trend_status = "強勢突破 ✅" if buy_score > 1 else ("逢低止跌 🔵" if is_dip_support else "空頭排列 ❌")
                report = f"🔍 【{display_code} 戰情回報】\n"
                report += f"──────────────\n"
                report += f"現價: {today['Close']:.2f}\n"
                report += f"短線 SAR 防守: {current_sar:.2f}\n"
                report += f"波段 吊燈防守: {chandelier_exit_price:.2f}\n"
                report += f"──────────────\n"
                report += f"📊 訊號: {trend_status}\n"
                report += f"🚨 警報: {'👉 建議出場' if (is_sar_dead_cross or is_chandelier_exit) else '正常抱股'}\n"
                send_line_message(report)
                return

        except Exception as e:
            print(f"Error {code}: {e}")

    # === 生成 HTML 儀表板 (工業極簡 3D 風格) ===
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="大富翁戰情室">
        <link rel="apple-touch-icon" href="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?q=80&w=256&auto=format&fit=crop">
        <title>大富翁戰情室 | {today_str}</title>
        <style>
            :root {{ 
                --bg-color: #121212; 
                --card-bg: #1e1e1e; 
                --text-main: #e0e0e0; 
                --text-sub: #888888; 
                --accent-green: #00704A; /* 星巴克綠 */
                --accent-red: #d9534f; 
                --accent-blue: #3498db; 
                --border-radius: 12px; 
            }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 40px 20px 20px 20px; -webkit-user-select: none; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .market-status {{ display: inline-block; padding: 10px 20px; border-radius: 30px; background-color: #111; border: 1px solid {market_color}; color: {market_color}; font-weight: bold; margin-top: 10px; box-shadow: inset 2px 2px 5px rgba(0,0,0,0.5), inset -2px -2px 5px rgba(255,255,255,0.05); }}
            .grid-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
            
            /* 3D 質感卡片設計 */
            .card {{ 
                background-color: var(--card-bg); 
                border-radius: var(--border-radius); 
                padding: 20px; 
                box-shadow: 6px 6px 12px rgba(0,0,0,0.6), -4px -4px 10px rgba(255,255,255,0.05); 
                border-left: 5px solid var(--accent-green); 
            }}
            .card.dip {{ border-left-color: var(--accent-blue); }}
            .card.sell {{ border-left-color: var(--accent-red); }}
            
            .card-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 10px; }}
            .stock-name {{ font-size: 1.3em; font-weight: bold; letter-spacing: 1px; }}
            .stock-price {{ font-size: 1.4em; color: #fff; text-shadow: 1px 1px 2px rgba(0,0,0,0.8); }}
            .data-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.95em; align-items: center; }}
            .label {{ color: var(--text-sub); }}
            
            /* 數值立體化標籤 */
            .val-box {{ padding: 4px 8px; border-radius: 6px; font-weight: bold; background: #2a2a2a; box-shadow: inset 1px 1px 3px rgba(0,0,0,0.8); }}
            .value-green {{ color: var(--accent-green); }}
            .value-red {{ color: var(--accent-red); }}
            
            .badge {{ font-size: 0.7em; padding: 4px 8px; border-radius: 6px; color: #fff; margin-left: 8px; box-shadow: 2px 2px 5px rgba(0,0,0,0.3); }}
            .bg-green {{ background-color: var(--accent-green); }}
            .bg-blue {{ background-color: var(--accent-blue); }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="color: var(--accent-green);">大富翁戰情室</h2>
            <p style="color: var(--text-sub);">{today_str}</p>
            <div class="market-status">{market_text}</div>
        </div>
        <h3 style="color: var(--text-main);">🟢 多方觀測名單 ({len(buy_signals)})</h3>
        <div class="grid-container">
    """
    
    for s in buy_signals:
        card_class = "card dip" if s['mode'] == "逢低承接" else "card"
        badge_class = "badge bg-blue" if s['mode'] == "逢低承接" else "badge bg-green"
        html_content += f"""
            <div class="{card_class}">
                <div class="card-header">
                    <div class="stock-name">{s['code']} {s['name']}<span class="{badge_class}">{s['mode']}</span></div>
                    <div class="stock-price">{s['price']:.2f}</div>
                </div>
                <div class="data-row"><span class="label">短線 SAR 防守線</span><span class="val-box value-red">{s['psar']:.2f}</span></div>
                <div class="data-row"><span class="label">波段 吊燈防守線</span><span class="val-box value-red">{s['chandelier']:.2f}</span></div>
                <div class="data-row"><span class="label">ATR 波段攻擊目標</span><span class="val-box value-green">{s['tp']:.2f}</span></div>
            </div>
        """
        
    html_content += f"""
        </div>
        <h3 style="color: var(--accent-red); margin-top: 40px;">🔴 空方風險警示 ({len(sell_signals)})</h3>
        <div class="grid-container">
    """
    
    for s in sell_signals:
        html_content += f"""
            <div class="card sell">
                <div class="card-header">
                    <div class="stock-name">{s['code']} {s['name']}</div>
                    <div class="stock-price">{s['price']:.2f}</div>
                </div>
                <div class="data-row"><span class="label">觸發警報</span><span class="val-box value-red">{s['reason']}</span></div>
                <div class="data-row"><span class="label">當前 SAR 點位</span><span class="val-box value-red">{s['psar']:.2f}</span></div>
            </div>
        """
        
    html_content += """
        </div>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    timestamp = datetime.now().strftime('%m%d%H%M')
    dashboard_url = f"https://hihibearjp.github.io/stock-bot-final/?v={timestamp}"

    msg_lines = [
        f"🎯 戰情摘要 ({today_str})", market_text, "--------------------",
        f"🟢 多方訊號: {len(buy_signals)} 檔", 
        f"🔴 風險警示: {len(sell_signals)} 檔",
        "--------------------", "📊 點擊查看大富翁戰情：", dashboard_url
    ]
    line_msg = "\n".join(msg_lines)
    if len(buy_signals) > 0 or len(sell_signals) > 0: send_line_message(line_msg)

if __name__ == "__main__":
    analyze()
