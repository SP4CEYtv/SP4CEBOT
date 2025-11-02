from flask import Flask, jsonify, request
import yfinance as yf
import pandas as pd
import numpy as np

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

def get_signal(ticker):
    try:
        ticker = ticker.upper().strip()
        if not ticker.endswith('-USD') and ticker in ['BTC', 'ETH', 'DOGE', 'SOL']:
            ticker += '-USD'
        
        print(f"Fetching: {ticker}")

        # Longer period for reliability
        data = yf.download(ticker, period='1y', progress=False)
        if data.empty or len(data) < 30:
            print(f"No data for {ticker}")
            return {"error": "No data for " + ticker}

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

        return {
            "ticker": ticker,
            "signal": signal,
            "price": price,
            "ma10": round(ma10, 2),
            "ma30": round(ma30, 2),
            "rsi": round(rsi, 2)
        }
    except Exception as e:
        print(f"Error: {e}")
        return {"error": str(e)}

@app.route('/')
def home():
    return "<h1>SP4CEBOT API LIVE</h1><p>Use /api/signal?ticker=BTC-USD</p>"

# QUERY PARAM ENDPOINT — NO DASH ISSUES
@app.route('/api/signal')
def signal():
    ticker = request.args.get('ticker', 'BTC-USD')
    result = get_signal(ticker)
    return jsonify(result)

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
