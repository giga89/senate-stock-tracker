import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'senators_trading.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table for trades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            senator TEXT,
            transaction_date TEXT,
            owner TEXT,
            ticker TEXT,
            asset_description TEXT,
            asset_type TEXT,
            type TEXT,
            amount_range TEXT,
            transaction_price REAL,
            current_price REAL,
            roi_pct REAL,
            UNIQUE(senator, transaction_date, ticker, type, amount_range)
        )
    ''')
    
    # Table for Gemini insights
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            senator TEXT,
            ticker TEXT,
            insight_text TEXT,
            last_updated TEXT,
            UNIQUE(senator, ticker)
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
