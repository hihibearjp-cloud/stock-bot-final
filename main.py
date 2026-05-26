
import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime
from ta.volatility import BollingerBands
from ta.trend import PSARIndicator

# 取得環境變數
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
    """取得台灣加權指數大盤狀態，作為濾網"""
    try:
        twii = yf.Ticker("^TWII").history(period="30d")
        if len(twii) < 20: return "⚪ 大盤狀態未知"
        ma20 = twii['Close'].rolling(20).mean().iloc[-1]
        close = twii['Close'].iloc[-1]
        if close > ma20:
            return f"🟢 大盤偏多 (站上月線，順風期)"
        else:
            return f"🔴 大盤偏空 (跌破月線，建議觀望縮手)"
    except:
        return "⚪ 大盤狀態讀取失敗"

def analyze():
    # 觀察名單 (可自由增減)
    targets = {
        "2330": "台積電", "3017": "奇鋐", "2317": "鴻海", "2603": "長榮", 
        "2454": "聯發科", "3231": "緯創", "2382": "廣達"
    }
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    market_trend = get_market_status()
    
    report = f"🎯 紀律戰神雷達 ({today_str})\n"
    report += f"{market_trend}\n"
    report += "="*20 + "\n"
    found = False

    for code, name in targets.items():
        try:
            # 抓取資料
            df = yf.Ticker(f"{code}.TW").history(period="100d")
            if len(df) < 30: continue
            
            # === 計算技術指標 ===
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA10'] = df['Close'].rolling(10).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['VMA20'] = df['Volume'].rolling(20).mean()
            
            indicator_bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
            df['BB_Upper'] = indicator_bb.bollinger_hband()
            
            indicator_psar = PSARIndicator(high=df['High'], low=df['Low'], close=df['Close'], step=0.02, max_step=0.2)
            df['PSAR'] = indicator_psar.psar()
            
            # 尋找前高頸線
            df['Is_Peak'] = (df['High'] > df['High'].shift(1)) & (df['High'] > df['High'].shift(2)) & \
                            (df['High'] >= df['High'].shift(-1)) & (df['High'] >= df['High'].shift(-2))
            
            historical_peaks = df[df['Is_Peak'] & (df.index < df.index[-2])]
            recent_neckline = historical_peaks.iloc[-1]['High'] if not historical_peaks.empty else df['High'].iloc[-20:-3].max()

            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            
            # === 買進條件判斷 ===
            vol_ratio = today['Volume'] / today['VMA20'] if today['VMA20'] > 0 else 0
            is_high_volume = vol_ratio >= 1.0
            
            is_breakout = (today['Close'] > recent_neckline) and (yesterday['Close'] <= recent_neckline)
            is_bullish_ma = (today['MA5'] > today['MA10']) and (today['MA10'] > today['MA20']) and (today['MA5'] > yesterday['MA5'])
            
            ma_max, ma_min = max(today['MA5'], today['MA10'], today['MA20']), min(today['MA5'], today['MA10'], today['MA20'])
            is_tangled = ((ma_max - ma_min) / ma_min) <= 0.03
            
            body_percent = (today['Close'] - today['Open']) / today['Open']
            is_super_red = (body_percent >= 0.03) and (today['Close'] > yesterday['High']) and (today['Open'] <= yesterday['Close'])

            buy_c1, buy_c2, buy_c3, buy_c4 = (is_high_volume and is_breakout), is_bullish_ma, (is_tangled and (today['Close'] > recent_neckline)), (is_high_volume and is_super_red)
            buy_score = sum([buy_c1, buy_c2, buy_c3, buy_c4])

            # === 乖離率與防守點計算 (進階實戰邏輯) ===
            bias_20 = (today['Close'] - today['MA20']) / today['MA20']
            
            # 買進防守點：因為如果處於強勢乖離，用昨低防守最安全
            stop_loss_price = min(today['Low'], yesterday['Low'])

            # === 賣出條件判斷 ===
            is_surging = all(df['Close'].iloc[-i] > df['MA5'].iloc[-i] for i in range(1, 4))
            is_touch_bb = today['High'] >= today['BB_Upper']
            is_sar_dead_cross = (yesterday['Close'] >= yesterday['PSAR']) and (today['Close'] < today['PSAR']) if pd.notna(yesterday['PSAR']) and pd.notna(today['PSAR']) else False

            sell_c1, sell_c2 = (is_surging and is_touch_bb), (is_surging and is_sar_dead_cross)

            # === 輸出報告生成 ===
            if buy_score > 0 or sell_c1 or sell_c2:
                report += f"\n[{code} {name}] 量能 {vol_ratio:.1f}倍\n"
                
                # 處理買方訊號
                if buy_score > 0:
                    report += f" 🟢 買方評分: {'⭐'*buy_score}\n"
                    if buy_c1: report += f"  [✓] 爆量突破頸線\n"
                    if buy_c2: report += f"  [✓] 均線多頭排列\n"
                    if buy_c3: report += f"  [✓] 均線糾結且站穩\n"
                    if buy_c4: report += f"  [✓] 爆量大紅K吞噬\n"
                    
                    report += f"  🛡️ 嚴格防守價: {stop_loss_price:.1f}\n"
                    
                    # 🚀 實戰乖離率邏輯更新
                    if bias_20 > 0.15:
                        report += f"  🔥 [極強勢軋空] 乖離達 {bias_20*100:.1f}%！若要上車請務必「縮小資金部位」！\n"
                    elif bias_20 > 0.08:
                        report += f"  ⚠️ [動能強勁] 乖離達 {bias_20*100:.1f}%，留意短線震盪回踩。\n"
                
                # 處理賣方訊號
                if sell_c1 or sell_c2:
                    report += f" 🔴 【波段賣出警示】\n"
                    if sell_c1: report += f"  [⚠️] 突破布林通道上軌 (短線極度過熱)\n"
                    if sell_c2: report += f"  [⚠️] 股價跌破 SAR 死亡交叉 (趨勢轉弱)\n"
                
                found = True

        except Exception as e:
            print(f"Error {code}: {e}")
            
    if found:
        report += "\n" + "="*20 + "\n💡 觀念提醒：乖離大不是不能買，是資金只能買少一點！"
        send_line_message(report)
    else:
        print("今日盤中無符合條件之股票。")

if __name__ == "__main__":
    analyze()
