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

SENATE_DATA_URL = "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json"
HOUSE_DATA_URL = "https://raw.githubusercontent.com/timothycarambat/house-stock-watcher-data/master/data/all_transactions.json"

_price_cache = {}

def get_stock_prices(ticker, transaction_date_str):
    """
    Returns (transaction_date_price, current_price) using yfinance.
    transaction_date_str is usually in MM/DD/YYYY format.
    """
    cache_key = f"{ticker}_{transaction_date_str}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]

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
            _price_cache[cache_key] = (None, None)
            return None, None
            
        tx_price = float(hist['Close'].iloc[0])
        
        # Get current price
        curr_hist = stock.history(period="1d")
        if curr_hist.empty:
            _price_cache[cache_key] = (tx_price, tx_price)
            return tx_price, tx_price # Fallback
            
        curr_price = float(curr_hist['Close'].iloc[-1])
        
        _price_cache[cache_key] = (tx_price, curr_price)
        return tx_price, curr_price
    except Exception as e:
        logger.error(f"Error fetching price for {ticker}: {e}")
        _price_cache[cache_key] = (None, None)
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

def fetch_data_from_url(url, chamber):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            for row in data:
                row['chamber_assigned'] = chamber
            return data
        else:
            logger.warning(f"Failed to fetch {chamber} data. HTTP {response.status_code} (Probably dead API)")
            return []
    except Exception as e:
        logger.warning(f"Error fetching {chamber} data: {e}")
        return []

def collect_data(days_back=180):
    logger.info("Starting data collection...")
    init_db()
    
    from backend.progress import update_progress
    update_progress("collecting", 0, 100, "Inizializzazione collector e download sorgenti...")
    
    all_data = []
    
    # Fetch Senate
    senate_data = fetch_data_from_url(SENATE_DATA_URL, "Senate")
    all_data.extend(senate_data)
    
    # Fetch House (Currently the repository/API is down, but we try anyway just in case it comes back)
    # house_data = fetch_data_from_url(HOUSE_DATA_URL, "House")
    # all_data.extend(house_data)
    
    if not all_data:
        logger.error("No data fetched from any source.")
        update_progress("error", 0, 100, "Nessun dato trovato dai sorgenti.")
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Dates are in MM/DD/YYYY format usually
    def safe_parse_date(d):
        try:
            return datetime.strptime(d.get('transaction_date', ''), "%m/%d/%Y")
        except:
            try:
                return datetime.strptime(d.get('transaction_date', ''), "%Y-%m-%d")
            except:
                return datetime.min
            
    all_data.sort(key=safe_parse_date, reverse=True)
    
    # Calculate cutoff date relative to today
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    # Pre-filter all_data so we know the exact total
    filtered_data = []
    for row in all_data:
        tx_date = safe_parse_date(row)
        if tx_date >= cutoff_date:
            filtered_data.append(row)
            
    total_records = len(filtered_data)
    
    processed_count = 0
    added_count = 0
    
    for i, row in enumerate(filtered_data):
        tx_date_str = row.get("transaction_date", "")
        tx_date = safe_parse_date(row)
        
        # Determine politician name (House uses 'representative', Senate uses 'senator')
        politician = row.get("representative") or row.get("senator") or "Unknown"
        chamber = row.get("chamber_assigned", "Unknown")
        ticker = row.get("ticker", "").strip()
        tx_type = row.get("type", "")
        amount_range = row.get("amount", "")
        asset_desc = row.get("asset_description", "")
        owner = row.get("owner", "Unknown")
        asset_type = row.get("asset_type", "")
        
        if i % 10 == 0 or i == total_records - 1:
            update_progress("collecting", i + 1, total_records, f"Elaborazione transazione {i+1}/{total_records}: {politician} - {ticker}")
        
        # Skip useless tickers
        if not ticker or ticker == '--' or ticker == 'Unknown' or len(ticker) > 5 or '<' in ticker:
            continue
            
        # Check if already in DB
        cursor.execute('''
            SELECT id FROM trades 
            WHERE politician=? AND transaction_date=? AND ticker=? AND type=? AND amount_range=?
        ''', (politician, tx_date_str, ticker, tx_type, amount_range))
        
        if cursor.fetchone():
            continue # Already processed
            
        # Get prices
        tx_price, curr_price = get_stock_prices(ticker, tx_date_str)
        
        if tx_price is None:
            continue
            
        roi = calculate_roi(tx_type, tx_price, curr_price)
        
        try:
            cursor.execute('''
                INSERT INTO trades (politician, chamber, transaction_date, owner, ticker, asset_description, asset_type, type, amount_range, transaction_price, current_price, roi_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (politician, chamber, tx_date_str, owner, ticker, asset_desc, asset_type, tx_type, amount_range, tx_price, curr_price, roi))
            added_count += 1
            logger.info(f"Added trade: {politician} ({chamber}) - {ticker} ({tx_type}) ROI: {roi:.2f}%")
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
    update_progress("collecting", total_records, total_records, f"Raccolta completata. Aggiunte {added_count} nuove transazioni.")

if __name__ == '__main__':
    collect_data(days_back=730)
