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
        ticker = ticker.upper()
        if not ticker.endswith('-USD') and ticker in ['BTC', 'ETH', 'DOGE']:
            ticker += '-USD'
        
        data = yf.download(ticker, period='60d', progress=False)
        if data.empty or len(data) < 30:
            return {"error": "No data"}

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
        return {"error": str(e)}

@app.route('/')
def home():
    return "<h1>AI Bot LIVE on Render!</h1>"

@app.route('/signal/<ticker>')
def signal(ticker):
    result = get_signal(ticker)
    print("SIGNAL:", result)
    return jsonify(result)

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
