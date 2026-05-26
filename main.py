import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime

# 取得環境變數 (從 GitHub Secrets 抓取)
LINE_TOKEN = os.environ.get('LINE_TOKEN')
LINE_USER_ID = os.environ.get('LINE_USER_ID')

def send_line_message(msg):
    if not LINE_TOKEN or not LINE_USER_ID:
        print("測試模式，訊息如下：\n", msg)
        return
    headers = {"Authorization": f"Bearer {LINE_TOKEN}", "Content-Type": "application/json"}
    data = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": msg}]}
    res = requests.post("[https://api.line.me/v2/bot/message/push](https://api.line.me/v2/bot/message/push)", headers=headers, json=data)
    print(f"發送狀態: {res.status_code}")

def analyze():
    # 設定目標股票 (2330台積電, 3017奇鋐)
    targets = {"2330": "台積電", "3017": "奇鋐"}
    report = f"📊 戰情室報告 ({datetime.now().strftime('%Y-%m-%d')})\n"
    found = False

    for code, name in targets.items():
        try:
            df = yf.Ticker(f"{code}.TW").history(period="60d")
            if len(df) < 20: continue
            
            # 計算均線與均量
            df['MA20'] = df['Close'].rolling(20).mean()
            df['VMA20'] = df['Volume'].rolling(20).mean()
            
            last = df.iloc[-1]
            vol_ratio = last['Volume'] / last['VMA20'] if last['VMA20'] > 0 else 0
            
            # 觸發條件 (成交量大於均量 1.5 倍)
            if vol_ratio >= 1.5:
                report += f"\n⚔️ [{code} {name}] 爆量訊號\n ↳ 量能為月均 {vol_ratio:.1f} 倍\n"
                found = True
        except Exception as e:
            print(f"Error {code}: {e}")
            
    if found:
        send_line_message(report)
    else:
        # 測試用：如果沒觸發條件，也會印出這行確認程式有跑完
        print("今日無觸發條件。")

if __name__ == "__main__":
    analyze()
