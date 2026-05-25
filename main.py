
檔案一：main.py請在 GitHub 根目錄新增 main.py，並貼上以下全部內容：import yfinance as yf
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
檔案二：requirements.txt請在 GitHub 根目錄新增 requirements.txt，並貼上以下這 3 行：yfinance
pandas
requests
檔案三：schedule.yml請在 GitHub 新增檔案，名稱連同資料夾輸入 .github/workflows/schedule.yml，並貼上以下內容：name: Daily Stock Schedule
on:
  schedule:
    - cron: '30 6 * * *'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install yfinance pandas requests

      - name: Find and Run script
        env:
          LINE_TOKEN: ${{ secrets.LINE_TOKEN }}
          LINE_USER_ID: ${{ secrets.LINE_USER_ID }}
        run: |
          TARGET=$(find . -name "main.py" | head -n 1)
          echo "找到的執行路徑: $TARGET"
          python "$TARGET"
