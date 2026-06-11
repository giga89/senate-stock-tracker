import requests
import json
import sqlite3
import yfinance as yf
from datetime import datetime, timedelta
import time
import logging
from backend.database import get_connection, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENATE_DATA_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"

def get_stock_prices(ticker, transaction_date_str):
    """
    Returns (transaction_date_price, current_price) using yfinance.
    transaction_date_str is usually in MM/DD/YYYY format.
    """
    try:
        if not ticker or ticker == '--' or ticker == 'Unknown':
            return None, None
            
        # Parse date
        try:
            tx_date = datetime.strptime(transaction_date_str, "%m/%d/%Y")
        except ValueError:
            try:
                tx_date = datetime.strptime(transaction_date_str, "%Y-%m-%d")
            except:
                return None, None

        # Clean ticker (e.g. if there is a stock exchange prefix or suffix)
        ticker = ticker.strip().upper().replace('<br>', '')
        if len(ticker) > 5 or not ticker.isalpha():
            return None, None
            
        stock = yf.Ticker(ticker)
        
        # Get historical data around the transaction date
        start_date = tx_date.strftime("%Y-%m-%d")
        end_date = (tx_date + timedelta(days=5)).strftime("%Y-%m-%d")
        
        hist = stock.history(start=start_date, end=end_date)
        if hist.empty:
            return None, None
            
        tx_price = float(hist['Close'].iloc[0])
        
        # Get current price
        curr_hist = stock.history(period="1d")
        if curr_hist.empty:
            return tx_price, tx_price # Fallback
            
        curr_price = float(curr_hist['Close'].iloc[-1])
        
        return tx_price, curr_price
    except Exception as e:
        logger.error(f"Error fetching price for {ticker}: {e}")
        return None, None

def calculate_roi(tx_type, tx_price, curr_price):
    if not tx_price or not curr_price or tx_price == 0:
        return 0.0
    
    perf = (curr_price - tx_price) / tx_price * 100
    
    if "Purchase" in tx_type:
        return perf
    elif "Sale" in tx_type:
        # If they sold, their 'gain' compared to holding is avoiding the drop.
        # Negative performance means they saved money. 
        return -perf
    return 0.0

def collect_data(days_back=180):
    logger.info("Starting data collection...")
    init_db()
    
    response = requests.get(SENATE_DATA_URL)
    if response.status_code != 200:
        logger.error("Failed to fetch senate data.")
        return
        
    data = response.json()
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    processed_count = 0
    added_count = 0
    
    # Sort data by transaction date, newest first
    # Dates are in MM/DD/YYYY format usually
    def safe_parse_date(d):
        try:
            return datetime.strptime(d['transaction_date'], "%m/%d/%Y")
        except:
            return datetime.min
            
    data.sort(key=safe_parse_date, reverse=True)
    
    for row in data:
        tx_date_str = row.get("transaction_date", "")
        tx_date = safe_parse_date(row)
        
        if tx_date < cutoff_date:
            continue
            
        senator = row.get("senator", "Unknown")
        ticker = row.get("ticker", "").strip()
        
        # Skip useless tickers
        if not ticker or ticker == '--' or ticker == 'Unknown' or len(ticker) > 5 or '<' in ticker:
            continue
            
        owner = row.get("owner", "Unknown")
        asset_desc = row.get("asset_description", "")
        asset_type = row.get("asset_type", "")
        tx_type = row.get("type", "")
        amount_range = row.get("amount", "")
        
        # Check if already in DB
        cursor.execute('''
            SELECT id FROM trades 
            WHERE senator=? AND transaction_date=? AND ticker=? AND type=? AND amount_range=?
        ''', (senator, tx_date_str, ticker, tx_type, amount_range))
        
        if cursor.fetchone():
            continue # Already processed
            
        # Get prices
        tx_price, curr_price = get_stock_prices(ticker, tx_date_str)
        
        if tx_price is None:
            continue
            
        roi = calculate_roi(tx_type, tx_price, curr_price)
        
        try:
            cursor.execute('''
                INSERT INTO trades (senator, transaction_date, owner, ticker, asset_description, asset_type, type, amount_range, transaction_price, current_price, roi_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (senator, tx_date_str, owner, ticker, asset_desc, asset_type, tx_type, amount_range, tx_price, curr_price, roi))
            added_count += 1
            logger.info(f"Added trade: {senator} - {ticker} ({tx_type}) ROI: {roi:.2f}%")
        except sqlite3.IntegrityError:
            pass # duplicate
            
        processed_count += 1
        
        # Sleep to respect yfinance rate limits
        if processed_count % 10 == 0:
            conn.commit()
            time.sleep(1)
            
    conn.commit()
    conn.close()
    logger.info(f"Collection finished. Added {added_count} new trades.")

if __name__ == '__main__':
    collect_data(days_back=90) # Default to last 90 days for quick run
