
import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime
import time

LINE_TOKEN = os.environ.get('LINE_TOKEN')
LINE_USER_ID = os.environ.get('LINE_USER_ID')

def send_line_message(msg):
    if not LINE_TOKEN or not LINE_USER_ID:
        print("測試模式，訊息如下：\n", msg)
        return
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)

def analyze():
    # 擴充為台灣 50 大權值股 (部分示意，可自行增減)
    targets = {
        "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達", "2308": "台達電",
        "2881": "富邦金", "2882": "國泰金", "2412": "中華電", "2891": "中信金", "3231": "緯創",
        "3017": "奇鋐", "2303": "聯電", "2886": "兆豐金", "3711": "日月光", "2603": "長榮",
        "2884": "玉山金", "2892": "第一金", "2885": "元大金", "2357": "華碩", "3034": "聯詠",
        "2345": "智邦", "2395": "研華", "2880": "華南金", "2618": "長榮航", "2883": "開發金"
    }
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    report = f"📡 台灣大金剛雷達 ({today_str})\n"
    report += "正在從 25 檔大型權值股中尋找爆量訊號...\n"
    report += "-"*20 + "\n"
    
    found_count = 0

    for code, name in targets.items():
        try:
            # 加上微小的延遲，避免被 Yahoo 封鎖
            time.sleep(0.5) 
            
            df = yf.Ticker(f"{code}.TW").history(period="60d")
            if len(df) < 20: continue
            
            df['VMA20'] = df['Volume'].rolling(20).mean()
            last = df.iloc[-1]
            vol_ratio = last['Volume'] / last['VMA20'] if last['VMA20'] > 0 else 0
            
            if vol_ratio >= 1.5:
                report += f"🔥 [{code} {name}] 爆量 {vol_ratio:.1f} 倍\n"
                found_count += 1
                
        except Exception as e:
            print(f"Error {code}: {e}")
            
    if found_count > 0:
        report += f"-"*20 + f"\n總共抓到 {found_count} 檔大人氣股票！"
        send_line_message(report)
    else:
        # 如果你想確認程式有活著，可以改成發送 "今日大型股無爆量訊號"
        print("今日大型股無爆量訊號。")

if __name__ == "__main__":
    analyze()

