frfrom flask import Flask, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
import time

app = Flask(__name__)

# GLOBAL CACHE
signal_cache = {
    "BTC-USD": {"signal": "HOLD", "price": 0, "timestamp": 0},
    "ETH-USD": {"signal": "HOLD", "price": 0, "timestamp": 0},
    "AAPL": {"signal": "HOLD", "price": 0, "timestamp": 0},
}

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
    if request.method == 'OPTIONS':
        return '', 200
    return response

def get_signal(ticker):
    ticker = ticker.upper().strip()
    if ticker in ['BTC', 'ETH', 'DOGE']:
        ticker += '-USD'

    # Use cache if fresh (< 5 min)
    if ticker in signal_cache and time.time() - signal_cache[ticker]["timestamp"] < 300:
        print(f"Using cache for {ticker}")
        return {**signal_cache[ticker], "ticker": ticker, "cached": True}

    for attempt in range(3):
        try:
            print(f"Fetching {ticker} (attempt {attempt+1})")
            data = yf.download(ticker, period='1y', progress=False)
            if not data.empty and len(data) >= 30:
                close = data['Close']
                ma10 = float(close.rolling(10).mean().iloc[-1])
                ma30 = float(close.rolling(30).mean().iloc[-1])
                
                delta = close.diff()
                gain = float(delta.where(delta > 0, 0).rolling(14).mean().iloc[-1])
                loss = float((-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1])
                
                gain = 0.0 if pd.isna(gain) else gain
                loss = 0.0 if pd.isna(loss) else loss
                rsi = 100 if loss == 0 else 100 - (100 / (1 + gain / loss))
                
                price = round(float(close.iloc[-1]), 2)
                signal = "BUY" if ma10 > ma30 and rsi < 70 else "SELL" if ma10 < ma30 and rsi > 30 else "HOLD"

                # SAVE TO CACHE
                result = {
                    "ticker": ticker,
                    "signal": signal,
                    "price": price,
                    "ma10": round(ma10, 2),
                    "ma30": round(ma30, 2),
                    "rsi": round(rsi, 2),
                    "timestamp": int(time.time()),
                    "cached": False
                }
                signal_cache[ticker] = result
                return result
        except Exception as e:
            print(f"Error: {e}")

    # RETURN CACHED OR FALLBACK
    if ticker in signal_cache:
        print(f"Using stale cache for {ticker}")
        return {**signal_cache[ticker], "ticker": ticker, "cached": True}
    
    return {"error": "No data — try again", "ticker": ticker}

@app.route('/')
def home():
    return "<h1>SP4CEBOT API LIVE</h1>"

@app.route('/api/signal')
def signal():
    ticker = request.args.get('ticker', 'BTC-USD')
    result = get_signal(ticker)
    return jsonify(result)

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
