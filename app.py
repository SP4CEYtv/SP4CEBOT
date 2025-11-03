from flask import Flask, jsonify, request
import time
import os
import threading
from datetime import datetime

app = Flask(__name__)

# ============================================
# ENVIRONMENT VARIABLES (SET IN RENDER)
# ============================================
ALPACA_API_KEY = os.environ.get('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = 'https://paper-api.alpaca.markets'  # Paper trading

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# ============================================
# IMPORTS (ADD TO requirements.txt)
# ============================================
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from supabase import create_client, Client
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install yfinance pandas numpy alpaca-py supabase")

# Initialize Alpaca client
alpaca = None
if ALPACA_API_KEY and ALPACA_SECRET_KEY:
    alpaca = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

# Initialize Supabase client
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# CORS
# ============================================
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
    if request.method == 'OPTIONS':
        return '', 200
    return response

# ============================================
# HARDCODED FALLBACK
# ============================================
FALLBACK = {
    "BTC-USD": {"signal": "SELL", "price": 67234, "ma10": 68120, "ma30": 69890, "rsi": 58},
    "ETH-USD": {"signal": "BUY", "price": 2456, "ma10": 2420, "ma30": 2380, "rsi": 62},
    "AAPL": {"signal": "BUY", "price": 195, "ma10": 194, "ma30": 192, "rsi": 62},
    "DOGE-USD": {"signal": "HOLD", "price": 0.14, "ma10": 0.145, "ma30": 0.142, "rsi": 48}
}

# CACHE
signal_cache = {}

# ============================================
# SIGNAL GENERATION (YOUR ORIGINAL CODE)
# ============================================
def get_signal(ticker):
    ticker = ticker.upper().strip()
    if ticker in ['BTC', 'ETH', 'DOGE']:
        ticker += '-USD'
    
    # Use cache
    if ticker in signal_cache and time.time() - signal_cache[ticker]["timestamp"] < 300:
        return {**signal_cache[ticker], "ticker": ticker, "cached": True}
    
    try:
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
        print(f"Error fetching {ticker}: {e}")
    
    # FALLBACK
    if ticker in FALLBACK:
        result = {**FALLBACK[ticker], "ticker": ticker, "cached": True, "fallback": True}
        signal_cache[ticker] = result
        return result
    return {"error": "No data", "ticker": ticker}

# ============================================
# LOG TRADE TO SUPABASE
# ============================================
def log_trade(ticker, action, quantity, price, total_cost, strategy="manual"):
    """Log trade to Supabase database"""
    if not supabase:
        print("⚠️ Supabase not configured")
        return
    
    try:
        supabase.table('trades').insert({
            'ticker': ticker,
            'action': action,
            'quantity': float(quantity),
            'price': float(price),
            'total_cost': float(total_cost),
            'timestamp': datetime.now().isoformat(),
            'strategy': strategy,
            'status': 'filled'
        }).execute()
        print(f"✅ Logged {action} {ticker} to Supabase")
    except Exception as e:
        print(f"❌ Failed to log trade: {e}")

# ============================================
# TRADING ENDPOINTS
# ============================================
@app.route('/api/trade/buy', methods=['POST'])
def buy_trade():
    """Execute BUY order on Alpaca + log to Supabase"""
    if not alpaca:
        return jsonify({"error": "Alpaca not configured"}), 500
    
    data = request.json
    ticker = data.get('ticker', 'BTC-USD').upper()
    amount = float(data.get('amount', 500))  # Dollar amount
    
    try:
        # Convert crypto tickers for Alpaca format
        if '-USD' in ticker:
            ticker = ticker.replace('-USD', 'USD')  # BTC-USD -> BTCUSD
        
        # Get current price
        signal_data = get_signal(ticker)
        price = signal_data.get('price', 0)
        
        # Calculate quantity
        quantity = amount / price if price > 0 else 0
        
        # Submit market order to Alpaca
        market_order = MarketOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        )
        
        order = alpaca.submit_order(order_data=market_order)
        
        # Log to Supabase
        log_trade(ticker, 'BUY', quantity, price, amount, strategy='manual')
        
        return jsonify({
            "status": "success",
            "order_id": str(order.id),
            "ticker": ticker,
            "quantity": quantity,
            "price": price,
            "total": amount
        })
        
    except Exception as e:
        print(f"❌ Buy error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/trade/sell', methods=['POST'])
def sell_trade():
    """Execute SELL order on Alpaca + log to Supabase"""
    if not alpaca:
        return jsonify({"error": "Alpaca not configured"}), 500
    
    data = request.json
    ticker = data.get('ticker', 'BTC-USD').upper()
    
    try:
        # Convert crypto tickers
        if '-USD' in ticker:
            ticker = ticker.replace('-USD', 'USD')
        
        # Get position
        position = alpaca.get_open_position(ticker)
        quantity = float(position.qty)
        current_price = float(position.current_price)
        total_value = quantity * current_price
        
        # Submit sell order
        market_order = MarketOrderRequest(
            symbol=ticker,
            qty=quantity,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        )
        
        order = alpaca.submit_order(order_data=market_order)
        
        # Log to Supabase
        log_trade(ticker, 'SELL', quantity, current_price, total_value, strategy='manual')
        
        return jsonify({
            "status": "success",
            "order_id": str(order.id),
            "ticker": ticker,
            "quantity": quantity,
            "price": current_price,
            "total": total_value
        })
        
    except Exception as e:
        print(f"❌ Sell error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/trade/sell-all', methods=['POST'])
def sell_all():
    """Close all positions"""
    if not alpaca:
        return jsonify({"error": "Alpaca not configured"}), 500
    
    try:
        positions = alpaca.get_all_positions()
        closed = []
        
        for position in positions:
            ticker = position.symbol
            quantity = float(position.qty)
            current_price = float(position.current_price)
            
            alpaca.close_position(ticker)
            log_trade(ticker, 'SELL', quantity, current_price, quantity * current_price, strategy='manual')
            closed.append(ticker)
        
        return jsonify({"status": "success", "closed": closed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# AUTO-TRADING LOOP
# ============================================
auto_trading_active = False
trading_thread = None

@app.route('/api/auto-trade/start', methods=['POST'])
def start_auto_trading():
    global auto_trading_active, trading_thread
    
    auto_trading_active = True
    
    if trading_thread is None or not trading_thread.is_alive():
        trading_thread = threading.Thread(target=auto_trading_loop, daemon=True)
        trading_thread.start()
        print("🚀 Auto-trading started")
    
    return jsonify({"status": "started", "active": True})

@app.route('/api/auto-trade/stop', methods=['POST'])
def stop_auto_trading():
    global auto_trading_active
    auto_trading_active = False
    print("🛑 Auto-trading stopped")
    return jsonify({"status": "stopped", "active": False})

@app.route('/api/auto-trade/status', methods=['GET'])
def auto_trade_status():
    return jsonify({
        "active": auto_trading_active,
        "last_check": datetime.now().isoformat()
    })

def auto_trading_loop():
    """Main trading loop - runs every 5 minutes"""
    global auto_trading_active
    
    tickers = ["BTCUSD", "ETHUSD", "SOLUSD"]
    
    while auto_trading_active:
        try:
            print(f"[AUTO-TRADE] Checking at {datetime.now()}")
            
            for ticker in tickers:
                signal_data = get_signal(ticker)
                
                if signal_data.get('signal') == 'BUY':
                    # Check if we already have a position
                    try:
                        alpaca.get_open_position(ticker)
                        print(f"Already holding {ticker}, skip")
                    except:
                        # No position, buy
                        print(f"🟢 BUY signal for {ticker}")
                        # Execute small test trade: $100
                        # In production, use Kelly Criterion
                        # For now: skip auto-buy until you confirm manual works
                
                elif signal_data.get('signal') == 'SELL':
                    try:
                        position = alpaca.get_open_position(ticker)
                        print(f"🔴 SELL signal for {ticker}, closing position")
                        # alpaca.close_position(ticker)  # Uncomment when ready
                    except:
                        print(f"No position to sell for {ticker}")
            
            time.sleep(300)  # 5 minutes
            
        except Exception as e:
            print(f"[AUTO-TRADE] Error: {e}")
            time.sleep(60)

# ============================================
# ORIGINAL ENDPOINTS
# ============================================
@app.route('/')
def home():
    return "<h1>SP4CEBOT API LIVE ✅</h1><p>Endpoints: /api/signal, /api/trade/buy, /api/trade/sell</p>"

@app.route('/api/signal')
def signal():
    ticker = request.args.get('ticker', 'BTC-USD')
    result = get_signal(ticker)
    return jsonify(result)

# ============================================
# RUN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Starting SP4CEBOT on port {port}")
    app.run(host='0.0.0.0', port=port)
if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
