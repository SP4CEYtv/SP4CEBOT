from flask import Flask, jsonify, request
import time

app = Flask(__name__)

# CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
    if request.method == 'OPTIONS':
        return '', 200
    return response

# HARDCODED FALLBACK (updated daily)
FALLBACK = {
    "BTC-USD": {"signal": "SELL", "price": 67234, "ma10": 68120, "ma30": 69890, "rsi": 58},
    "ETH-USD": {"signal": "BUY", "price": 2456, "ma10": 2420, "ma30": 2380, "rsi": 62},
    "AAPL": {"signal": "BUY", "price": 195, "ma10": 194, "ma30": 192, "rsi": 62},
    "DOGE-USD": {"signal": "HOLD", "price": 0.14, "ma10": 0.145, "ma30": 0.142, "rsi": 48}
}

# CACHE
signal_cache = {}

def get_signal(ticker):
    ticker = ticker.upper().strip()
    if ticker in ['BTC', 'ETH', 'DOGE']:
        ticker += '-USD'

    # Use cache if fresh
    if ticker in signal_cache and time.time() - signal_cache[ticker]["timestamp"] < 300:
        return {**signal_cache[ticker], "ticker": ticker, "cached": True}

    # Try yfinance
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

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
        print(f"yfinance failed: {e}")

    # FALLBACK
    if ticker in FALLBACK:
        print(f"Using fallback for {ticker}")
        result = {**FALLBACK[ticker], "ticker": ticker, "cached": True, "fallback": True}
        signal_cache[ticker] = result
        return result

    return {"error": "No data", "ticker": ticker}

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

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
