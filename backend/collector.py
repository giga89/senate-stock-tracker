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

KADOA_TRADES_URL = "https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/trades.json"
FMP_API_KEY = "QPNreVEDlsaLlSuEG3ZUYOb02Yz7odKs"
FMP_API_URL = f"https://financialmodelingprep.com/stable/senate-latest?apikey={FMP_API_KEY}"

_price_cache = {}

def get_stock_prices(ticker, transaction_date_str):
    """
    Returns (transaction_date_price, current_price) using yfinance.
    transaction_date_str is usually in MM/DD/YYYY or YYYY-MM-DD format.
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

def collect_data(days_back=730):
    logger.info("Starting data collection...")
    init_db()
    
    from backend.progress import update_progress
    update_progress("collecting", 0, 100, "Inizializzazione collector e download sorgenti FMP/Kadoa...")
    
    all_data = []
    
    # Fetch Kadoa historical data
    try:
        logger.info("Fetching Kadoa historical data...")
        kadoa_resp = requests.get(KADOA_TRADES_URL)
        if kadoa_resp.status_code == 200:
            for r in kadoa_resp.json():
                chamber_str = r.get("chamber") or "Unknown"
                ticker_str = r.get("ticker") or ""
                all_data.append({
                    "transaction_date": r.get("transaction_date", ""),
                    "politician": r.get("filer_name", "Unknown"),
                    "chamber_assigned": chamber_str.title(),
                    "ticker": ticker_str,
                    "type": r.get("transaction_type", ""),
                    "amount": r.get("amount_range_label", ""),
                    "asset_description": r.get("asset_name", ""),
                    "owner": r.get("owner", "Unknown"),
                    "asset_type": r.get("asset_type", "")
                })
        else:
            logger.warning(f"Failed to fetch Kadoa data. HTTP {kadoa_resp.status_code}")
    except Exception as e:
        logger.error(f"Error fetching Kadoa data: {e}")

    # Fetch FMP real-time data
    try:
        logger.info("Fetching FMP real-time data...")
        fmp_resp = requests.get(FMP_API_URL)
        if fmp_resp.status_code == 200:
            for r in fmp_resp.json():
                first = r.get("firstName") or ""
                last = r.get("lastName") or ""
                politician = f"{first} {last}".strip() or "Unknown"
                
                district = r.get("district", "")
                chamber = "House" if district and len(district) > 2 and any(c.isdigit() for c in district) else "Senate"
                
                ticker_str = r.get("symbol") or ""
                all_data.append({
                    "transaction_date": r.get("transactionDate", ""),
                    "politician": politician,
                    "chamber_assigned": chamber,
                    "ticker": ticker_str,
                    "type": r.get("type", ""),
                    "amount": r.get("amount", ""),
                    "asset_description": r.get("assetDescription", ""),
                    "owner": r.get("owner", "Unknown"),
                    "asset_type": r.get("assetType", "")
                })
        else:
            logger.warning(f"Failed to fetch FMP data. HTTP {fmp_resp.status_code}")
    except Exception as e:
        logger.error(f"Error fetching FMP data: {e}")
    
    if not all_data:
        logger.error("No data fetched from any source.")
        update_progress("error", 0, 100, "Nessun dato trovato dai sorgenti FMP/Kadoa.")
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Dates are in MM/DD/YYYY or YYYY-MM-DD format
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
    logger.info(f"Filtered {total_records} records within the last {days_back} days.")
    
    added_count = 0
    processed_count = 0
    
    for i, row in enumerate(filtered_data):
        if i % 10 == 0:
            update_progress("collecting", i, total_records, f"Elaborazione transazione {i}/{total_records}...")
            
        politician = (row.get("politician") or "Unknown").strip()
        chamber = (row.get("chamber_assigned") or "Unknown").strip()
        tx_date_str = (row.get("transaction_date") or "").strip()
        owner = (row.get("owner") or "Unknown").strip()
        ticker = (row.get("ticker") or "").strip()
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
