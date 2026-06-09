import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import PSARIndicator
from ta.momentum import RSIIndicator

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
        if close > ma20: return f"🔴 台股偏多 (站上月線)", "#ff4d6d"
        else: return f"🟢 台股偏空 (跌破月線)", "#198754"
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
            # --- 🇹🇼 台股權值山脈 ---
            "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2303.TW": "聯電", 
            "3711.TW": "日月光", "3034.TW": "聯詠", "2379.TW": "瑞昱", "3443.TW": "創意",
            # --- 🇹🇼 AI 伺服器與散熱重兵 ---
            "2382.TW": "廣達", "3231.TW": "緯創", "2376.TW": "技嘉", "2356.TW": "英業達",
            "3017.TW": "奇鋐", "3324.TW": "雙鴻", "2383.TW": "台光電", "3037.TW": "欣興",
            # --- 🇹🇼 重電與核心金融 ---
            "1519.TW": "華城", "1513.TW": "中興電", "1504.TW": "東元", "1514.TW": "亞力",
            "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金",
            # --- 🇹🇼 精選高價與個股期活躍標的 (鴻勁、群聯均完美保留) ---
            "5274.TW": "信驊(股王)", "3008.TW": "大立光(股後)", "3289.TW": "旺矽", 
            "7741.TW": "鴻勁", "3661.TW": "世芯-KY", "6669.TW": "緯穎", 
            "5269.TW": "祥碩", "3529.TW": "力旺", "8299.TW": "群聯", "2337.TW": "旺宏", "8358.TW": "金居",
            # --- 🇺🇸 美股主力戰機 ---
            "QQQM": "納指ETF", "SOXX": "半導體ETF", "TSM": "台積電ADR", 
            "NVDA": "輝達", "AAPL": "蘋果", "MSFT": "微軟", "QLD": "2倍做多納指",
            "USD": "半導體2X(USD)", "MU": "美光", "SNDK": "SanDisk", 
            "AAOI": "應用光電", "LULU": "Lululemon"
        }
    
    signals = {
        'today': {'buy': [], 'sell': []},
        'yesterday': {'buy': [], 'sell': []},
        'day_before': {'buy': [], 'sell': []}
    }

    for code, name in targets.items():
        try:
            df = yf.Ticker(code).history(period="100d")
            if len(df) < 30: continue
            
            display_code = code.replace('.TW', '')
            is_tw = code.endswith('.TW')
            
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['VMA20'] = df['Volume'].rolling(20).mean()
            
            indicator_bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['BB_Upper'] = indicator_bb.bollinger_hband()
            df['BB_Lower'] = indicator_bb.bollinger_lband()
            
            indicator_psar = PSARIndicator(high=df['High'], low=df['Low'], close=df['Close'], step=0.02, max_step=0.2)
            df['PSAR'] = indicator_psar.psar()
            
            indicator_atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=14)
            df['ATR'] = indicator_atr.average_true_range()
            df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
            
            df['Is_Peak'] = (df['High'] > df['High'].shift(1)) & (df['High'] > df['High'].shift(2)) & \
                            (df['High'] >= df['High'].shift(-1)) & (df['High'] >= df['High'].shift(-2))

            for offset, day_label in [(1, 'today'), (2, 'yesterday'), (3, 'day_before')]:
                if len(df) < offset + 20: continue
                
                today_idx = -offset
                yest_idx = -(offset + 1)
                
                today = df.iloc[today_idx]
                yesterday = df.iloc[yest_idx]
                current_atr = df['ATR'].iloc[today_idx]
                current_sar = df['PSAR'].iloc[today_idx]
                
                vol_ratio = today['Volume'] / today['VMA20'] if today['VMA20'] > 0 else 0
                
                historical_peaks = df[df['Is_Peak'] & (df.index < today.name)]
                recent_neckline = historical_peaks.iloc[-1]['High'] if not historical_peaks.empty else df['High'].iloc[-20-offset : -2-offset].max()
                
                is_breakout = (today['Close'] > recent_neckline) and (yesterday['Close'] <= recent_neckline)
                is_bullish_ma = (today['MA5'] > today['MA10']) and (today['MA10'] > today['MA20']) and (today['MA5'] > yesterday['MA5'])
                ma_max, ma_min = max(today['MA5'], today['MA10'], today['MA20']), min(today['MA5'], today['MA10'], today['MA20'])
                is_tangled = ((ma_max - ma_min) / ma_min) <= 0.03 if ma_min > 0 else False
                body_percent = (today['Close'] - today['Open']) / today['Open'] if today['Open'] > 0 else 0
                is_super_red = (body_percent >= 0.03) and (today['Close'] > yesterday['High'])
                
                buy_score = sum([is_breakout and vol_ratio >= 1.0, is_bullish_ma, is_tangled and (today['Close'] > recent_neckline), vol_ratio >= 1.0 and is_super_red])
                is_dip_support = (today['Low'] <= today['BB_Lower']) and (today['Close'] > today['Open'])
                is_v_turn = (yesterday['RSI'] <= 35 or today['RSI'] <= 35) and (today['RSI'] > yesterday['RSI']) and (today['Close'] > today['Open'])

                bias_20 = ((today['Close'] - today['MA20']) / today['MA20']) * 100
                atr_stop_loss = today['Close'] - (1.5 * current_atr)  
                atr_take_profit = today['Close'] + (3.0 * current_atr)
                
                sliced_df = df.iloc[-20-offset+1 : len(df)-offset+1]
                recent_max_high = sliced_df['High'].max()
                chandelier_exit_price = recent_max_high - (2.5 * current_atr)

                stock_info = {
                    "code": display_code, "name": name, "price": today['Close'], "vol_ratio": vol_ratio,
                    "tp": atr_take_profit, "sl": atr_stop_loss, "chandelier": chandelier_exit_price, "psar": current_sar, 
                    "bb_lower": today['BB_Lower'], "bias": bias_20, "rsi": today['RSI'], "mode": "強勢突破", "is_tw": is_tw
                }

                added_to_buy = False
                if is_v_turn:
                    stock_info['mode'] = "⚡ 絕地 V 轉"
                    stock_info['score'] = 3  
                    signals[day_label]['buy'].append(stock_info)
                    added_to_buy = True
                elif buy_score > 0:
                    stock_info['score'] = buy_score 
                    signals[day_label]['buy'].append(stock_info)
                    added_to_buy = True
                elif is_dip_support:
                    stock_info['mode'] = "逢低承接" 
                    stock_info['score'] = 1  
                    signals[day_label]['buy'].append(stock_info)
                    added_to_buy = True

                is_sar_dead_cross = (yesterday['Close'] >= yesterday['PSAR']) and (today['Close'] < today['PSAR'])
                is_touch_bb_upper = today['High'] >= today['BB_Upper']
                is_chandelier_exit = today['Close'] < chandelier_exit_price
                
                if is_sar_dead_cross:
                    stock_info['reason'] = "短線極速反轉 (SAR死叉)"
                    signals[day_label]['sell'].append(stock_info)
                elif is_chandelier_exit:
                    stock_info['reason'] = "波段趨勢破線 (吊燈停損)"
                    signals[day_label]['sell'].append(stock_info)
                elif is_touch_bb_upper and today['Close'] > today['MA5']:
                    stock_info['reason'] = "技術指標過熱 (布林上軌)"
                    signals[day_label]['sell'].append(stock_info)

                if offset == 1 and temp_stock:
                    trend_status = stock_info['mode'] if added_to_buy else "無特別訊號"
                    report = f"🔍 【{display_code} 戰情回報】\n"
                    report += f"──────────────\n"
                    report += f"現價: {today['Close']:.2f}\n"
                    report += f"空方防守(破必補): {current_sar:.2f}\n"
                    report += f"空方收割(布林下): {today['BB_Lower']:.2f}\n"
                    report += f"──────────────\n"
                    report += f"📊 訊號狀態: {trend_status}\n"
                    send_line_message(report)
                    return

        except Exception as e:
            print(f"Error {code}: {e}")

    # 交叉比對：多轉空
    yest_buy_codes = {s['code'] for s in signals['yesterday']['buy']}
    db_buy_codes = {s['code'] for s in signals['day_before']['buy']}
    today_turn_sells = [s for s in signals['today']['sell'] if s['code'] in yest_buy_codes]
    yest_turn_sells = [s for s in signals['yesterday']['sell'] if s['code'] in db_buy_codes]

    # === 生成 HTML 🚀 ===
    html_tabs = ""
    html_contents = ""
    labels = [('today', '今日戰情', 'active'), ('yesterday', '昨日回顧', ''), ('day_before', '前日歷史', '')]
    
    for day_id, day_name, active_class in labels:
        html_tabs += f'<button class="tab-btn {active_class}" onclick="showTab(\'{day_id}\', event)">{day_name}</button>\n'
        
        tw_buys = [s for s in signals[day_id]['buy'] if s['is_tw']]
        us_buys = [s for s in signals[day_id]['buy'] if not s['is_tw']]
        tw_sells = [s for s in signals[day_id]['sell'] if s['is_tw']]
        us_sells = [s for s in signals[day_id]['sell'] if not s['is_tw']]

        turn_tw = [s for s in today_turn_sells if s['is_tw']] if day_id == 'today' else ([s for s in yest_turn_sells if s['is_tw']] if day_id == 'yesterday' else [])
        turn_us = [s for s in today_turn_sells if not s['is_tw']] if day_id == 'today' else ([s for s in yest_turn_sells if not s['is_tw']] if day_id == 'yesterday' else [])
        
        tw_sells_clean = [s for s in tw_sells if s['code'] not in {x['code'] for x in turn_tw}]
        us_sells_clean = [s for s in us_sells if s['code'] not in {x['code'] for x in turn_us}]

        html_contents += f'<div id="{day_id}" class="tab-content {active_class}">\n'
        
        # --- 🚨 逆轉警戒區 (新增空方回補雙指標) ---
        if turn_tw or turn_us:
            html_contents += '<h2 class="section-title turn-title">⚠️ 🚨 逆轉警戒：多方轉空方專區</h2>\n'
            if turn_tw:
                html_contents += f'<h3 class="market-sub-title">🇹🇼 台股多轉空標的 ({len(turn_tw)})</h3>\n'
                html_contents += '<div class="grid-container">\n'
                for s in turn_tw:
                    html_contents += f"""
                        <div class="card turn">
                            <div class="card-header">
                                <div class="stock-name">{s['code']} {s['name']}<span class="badge bg-orange">昨日多 ➔ 今日空</span></div>
                                <div class="stock-price">{s['price']:.2f}</div>
                            </div>
                            <div class="data-row"><span class="label">量能放大倍數</span><span class="val-box color-main">{s['vol_ratio']:.1f}x</span></div>
                            <div class="data-row"><span class="label">轉空核心主因</span><span class="val-box color-green">{s['reason']}</span></div>
                            <div class="data-row"><span class="label">空方回補防守 (突破必補)</span><span class="val-box color-green">{s['psar']:.2f}</span></div>
                            <div class="data-row"><span class="label">空方收割目標 (布林下軌)</span><span class="val-box color-pink">{s['bb_lower']:.2f}</span></div>
                        </div>
                    """
                html_contents += '</div>\n'
            if turn_us:
                html_contents += f'<h3 class="market-sub-title" style="margin-top:20px;">🇺🇸 美股多轉空標的 ({len(turn_us)})</h3>\n'
                html_contents += '<div class="grid-container">\n'
                for s in turn_us:
                    html_contents += f"""
                        <div class="card turn">
                            <div class="card-header">
                                <div class="stock-name">{s['code']} {s['name']}<span class="badge bg-orange">昨日多 ➔ 今日空</span></div>
                                <div class="stock-price">{s['price']:.2f}</div>
                            </div>
                            <div class="data-row"><span class="label">量能放大</span><span class="val-box color-main">{s['vol_ratio']:.1f}x</span></div>
                            <div class="data-row"><span class="label">轉空核心主因</span><span class="val-box color-green">{s['reason']}</span></div>
                            <div class="data-row"><span class="label">空方回補防守 (突破必補)</span><span class="val-box color-green">{s['psar']:.2f}</span></div>
                            <div class="data-row"><span class="label">空方收割目標 (布林下軌)</span><span class="val-box color-pink">{s['bb_lower']:.2f}</span></div>
                        </div>
                    """
                html_contents += '</div>\n'

        # --- 🟢 多方區塊 ---
        html_contents += '<h2 class="section-title buy-title">🟢 多方觀測名單</h2>\n'
        
        def generate_buy_card(s):
            c_class = "card vturn" if s['mode'] == "⚡ 絕地 V 轉" else ("card dip" if s['mode'] == "逢低承接" else "card")
            b_class = "badge bg-yellow" if s['mode'] == "⚡ 絕地 V 轉" else ("badge bg-blue" if s['mode'] == "逢低承接" else "badge bg-pink")
            v_style = "color-yellow" if s['mode'] == "⚡ 絕地 V 轉" else "color-pink"
            stars_html = f'<span class="stars">{"★"*s.get("score", 1)}</span>'
            
            return f"""
                <div class="{c_class}">
                    <div class="card-header">
                        <div class="stock-name">{s['code']} {s['name']}<br>{stars_html}<span class="{b_class}">{s['mode']}</span></div>
                        <div class="stock-price">{s['price']:.2f}</div>
                    </div>
                    <div class="data-row"><span class="label">量能放大倍數</span><span class="val-box color-pink">{s['vol_ratio']:.1f}x</span></div>
                    <div class="data-row"><span class="label">RSI 相對強弱</span><span class="val-box {v_style}">{s['rsi']:.1f}</span></div>
                    <div class="data-row"><span class="label">月線乖離率</span><span class="val-box color-sub">{s['bias']:.1f}%</span></div>
                    <div class="data-row"><span class="label">ATR 停損 (防守)</span><span class="val-box color-green">{s['sl']:.2f}</span></div>
                    <div class="data-row"><span class="label">SAR 點位 (極速)</span><span class="val-box color-green">{s['psar']:.2f}</span></div>
                    <div class="data-row"><span class="label">ATR 停利 (攻擊)</span><span class="val-box color-pink">{s['tp']:.2f}</span></div>
                </div>
            """

        html_contents += f'<h3 class="market-sub-title">🇹🇼 台股市場 ({len(tw_buys)})</h3>\n'
        html_contents += '<div class="grid-container">\n'
        for s in tw_buys: html_contents += generate_buy_card(s)
        html_contents += '</div>\n'

        html_contents += f'<h3 class="market-sub-title" style="margin-top:25px;">🇺🇸 美股市場 ({len(us_buys)})</h3>\n'
        html_contents += '<div class="grid-container">\n'
        for s in us_buys: html_contents += generate_buy_card(s)
        html_contents += '</div>\n'
        
        # --- 🔴 空方區塊 (導入回補雙指標) ---
        html_contents += '<h2 class="section-title sell-title" style="margin-top: 50px;">🔴 空方風險警示</h2>\n'
        
        html_contents += f'<h3 class="market-sub-title">🇹🇼 台股市場 ({len(tw_sells_clean)})</h3>\n'
        html_contents += '<div class="grid-container">\n'
        for s in tw_sells_clean:
            html_contents += f"""
                <div class="card sell">
                    <div class="card-header">
                        <div class="stock-name">{s['code']} {s['name']}<span class="badge bg-green">空方</span></div>
                        <div class="stock-price">{s['price']:.2f}</div>
                    </div>
                    <div class="data-row"><span class="label">月線乖離率</span><span class="val-box color-sub">{s['bias']:.1f}%</span></div>
                    <div class="data-row"><span class="label">觸發警報</span><span class="val-box color-green">{s['reason']}</span></div>
                    <div class="data-row"><span class="label">空方回補防守 (突破必補)</span><span class="val-box color-green">{s['psar']:.2f}</span></div>
                    <div class="data-row"><span class="label">空方收割目標 (布林下軌)</span><span class="val-box color-pink">{s['bb_lower']:.2f}</span></div>
                </div>
            """
        html_contents += '</div>\n'

        html_contents += f'<h3 class="market-sub-title" style="margin-top:25px;">🇺🇸 美股市場 ({len(us_sells_clean)})</h3>\n'
        html_contents += '<div class="grid-container">\n'
        for s in us_sells_clean:
            html_contents += f"""
                <div class="card sell">
                    <div class="card-header">
                        <div class="stock-name">{s['code']} {s['name']}<span class="badge bg-green">空方</span></div>
                        <div class="stock-price">{s['price']:.2f}</div>
                    </div>
                    <div class="data-row"><span class="label">月線乖離率</span><span class="val-box color-sub">{s['bias']:.1f}%</span></div>
                    <div class="data-row"><span class="label">觸發警報</span><span class="val-box color-green">{s['reason']}</span></div>
                    <div class="data-row"><span class="label">空方回補防守 (突破必補)</span><span class="val-box color-green">{s['psar']:.2f}</span></div>
                    <div class="data-row"><span class="label">空方收割目標 (布林下軌)</span><span class="val-box color-pink">{s['bb_lower']:.2f}</span></div>
                </div>
            """
        html_contents += '</div>\n</div>\n'

    html_full = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="大富翁戰情室">
        <title>大富翁戰情室 | 數據滿載版</title>
        <style>
            :root {{ 
                --bg-color: #ffffff; 
                --card-bg: #f8f9fa; 
                --text-main: #212529; 
                --text-sub: #6c757d; 
                --accent-up: #ff4d6d;    
                --accent-down: #198754;  
                --accent-blue: #0ea5e9; 
                --accent-yellow: #f59e0b; 
                --accent-orange: #fd7e14; 
                --border-radius: 12px; 
            }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 40px 20px 20px 20px; -webkit-user-select: none; }}
            .header {{ text-align: center; margin-bottom: 25px; }}
            .market-status {{ display: inline-block; padding: 10px 20px; border-radius: 30px; background-color: #f1f3f5; border: 1px solid {market_color}; color: {market_color}; font-weight: bold; margin-top: 5px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }}
            
            .tabs {{ display: flex; justify-content: center; margin-bottom: 25px; gap: 10px; }}
            .tab-btn {{ background-color: #f1f3f5; color: var(--text-sub); border: 1px solid #dee2e6; padding: 10px 18px; border-radius: 20px; cursor: pointer; font-weight: bold; font-size: 0.9em; transition: all 0.3s; }}
            .tab-btn.active {{ background-color: var(--accent-up); color: #fff; border-color: var(--accent-up); box-shadow: 0 4px 10px rgba(255,77,109,0.3); }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; animation: fadeIn 0.4s; }}
            @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            
            .section-title {{ font-size: 1.4em; border-bottom: 2px solid #dee2e6; padding-bottom: 8px; margin-top: 25px; font-weight: 800; color: var(--text-main); }}
            .buy-title {{ border-bottom-color: var(--accent-up); }}
            .turn-title {{ border-bottom-color: var(--accent-orange); }}
            .sell-title {{ border-bottom-color: var(--accent-down); }}
            .market-sub-title {{ font-size: 1.1em; color: var(--text-sub); margin: 15px 0 10px 5px; font-weight: bold; letter-spacing: 0.5px; }}

            .grid-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }}
            
            .card {{ background-color: #ffffff; border-radius: var(--border-radius); padding: 16px; box-shadow: 0 4px 12px rgba(0,0,0,0.04); border: 1px solid #e9ecef; border-left: 5px solid var(--accent-up); }}
            .card.dip {{ border-left-color: var(--accent-blue); border-color: #e0f2fe; }}
            .card.vturn {{ border-left-color: var(--accent-yellow); border-color: #fef3c7; }}
            .card.turn {{ border-left-color: var(--accent-orange); border-color: #ffedd5; }}
            .card.sell {{ border-left-color: var(--accent-down); border-color: #d1e7dd; }}
            
            .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; border-bottom: 1px solid #f1f3f5; padding-bottom: 8px; }}
            .stock-name {{ font-size: 1.15em; font-weight: bold; line-height: 1.4; }}
            .stock-price {{ font-size: 1.35em; color: #111; font-weight: bold; }}
            
            .data-row {{ display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 0.85em; align-items: center; border-bottom: 1px dashed #f1f3f5; padding-bottom: 4px; }}
            .data-row:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
            .label {{ color: var(--text-sub); }}
            
            .val-box {{ padding: 3px 6px; border-radius: 4px; font-weight: bold; background: #f8f9fa; font-family: monospace; font-size: 1.05em; }}
            .color-main {{ color: var(--text-main); }}
            .color-sub {{ color: var(--text-sub); }}
            .color-pink {{ color: var(--accent-up); }}
            .color-green {{ color: var(--accent-down); }}
            .color-blue {{ color: var(--accent-blue); }}
            .color-yellow {{ color: var(--accent-yellow); }}
            .color-orange {{ color: var(--accent-orange); }}
            
            .badge {{ font-size: 0.7em; padding: 3px 6px; border-radius: 6px; color: #fff; margin-left: 6px; font-weight: bold; vertical-align: middle; }}
            .bg-pink {{ background-color: var(--accent-up); }}
            .bg-blue {{ background-color: var(--accent-blue); }}
            .bg-yellow {{ background-color: var(--accent-yellow); color: #000; }}
            .bg-orange {{ background-color: var(--accent-orange); }}
            .bg-green {{ background-color: var(--accent-down); }}
            
            .stars {{ color: #f59e0b; font-size: 0.9em; letter-spacing: 1px; margin-right: 4px; }}
        </style>
        <script>
            function showTab(tabId, event) {{
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                event.currentTarget.classList.add('active');
            }}
        </script>
    </head>
    <body>
        <div class="header">
            <h2 style="color: #00704A; font-weight:900; letter-spacing:1px;">大富翁戰情室</h2>
            <div class="market-status">{market_text}</div>
        </div>
        
        <div class="tabs">
            {html_tabs}
        </div>

        {html_contents}
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_full)

    timestamp = datetime.now().strftime('%m%d%H%M')
    dashboard_url = f"https://hihibearjp.github.io/stock-bot-final/?v={timestamp}"

    turn_count = len(today_turn_sells)
    msg_lines = [
        f"🎯 戰情摘要 ({today_str})", market_text, "--------------------",
        f"🟢 今日多方: 台股 {len(tw_buys)} / 美股 {len(us_buys)} 檔", 
        f"🔴 今日空方: 台股 {len(tw_sells_clean)} / 美股 {len(us_sells_clean)} 檔",
    ]
    if turn_count > 0:
        msg_lines.append(f"⚠️ 🚨 注意：今日出現 {turn_count} 檔【多轉空】極速轉折標的！")
        
    msg_lines.extend(["--------------------", "📊 點擊進入大富翁白底高密度版：", dashboard_url])
    line_msg = "\n".join(msg_lines)
    
    total_signals = sum(len(signals[day]['buy']) + len(signals[day]['sell']) for day in signals)
    if total_signals > 0: 
        send_line_message(line_msg)

if __name__ == "__main__":
    analyze()
