import sqlite3
import google.generativeai as genai
import logging
from datetime import datetime
from backend.database import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def configure_gemini():
    genai.configure(api_key=GEMINI_API_KEY)
    
def generate_insight(senator, ticker, asset_desc):
    prompt = f"""
Sei un analista finanziario ed esperto di politica americana. 
Il senatore {senator} ha effettuato transazioni sul titolo azionario {ticker} ({asset_desc}).

Cerca di individuare se c'è un legame potenziale tra il lavoro di questo senatore (es. le commissioni di cui fa parte, la sua posizione politica) e il settore in cui opera l'azienda {asset_desc}.
Rispondi in modo conciso, in italiano, evidenziando se ci sono possibili conflitti di interesse o correlazioni rilevanti. Se non ci sono correlazioni evidenti, dillo. Non superare le 4-5 frasi.
"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error generating insight for {senator} - {ticker}: {e}")
        return "Impossibile generare l'analisi al momento."

def update_insights():
    logger.info("Starting LLM insights generation...")
    configure_gemini()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get distinct senator/ticker pairs that don't have an insight yet
    cursor.execute('''
        SELECT DISTINCT senator, ticker, asset_description 
        FROM trades 
        WHERE (senator, ticker) NOT IN (SELECT senator, ticker FROM insights)
        LIMIT 50 -- Limit to 50 per run to avoid rate limits
    ''')
    
    pairs = cursor.fetchall()
    
    for row in pairs:
        senator = row['senator']
        ticker = row['ticker']
        asset_desc = row['asset_description']
        
        logger.info(f"Generating insight for {senator} - {ticker}")
        insight = generate_insight(senator, ticker, asset_desc)
        
        cursor.execute('''
            INSERT INTO insights (senator, ticker, insight_text, last_updated)
            VALUES (?, ?, ?, ?)
        ''', (senator, ticker, insight, datetime.now().isoformat()))
        
    conn.commit()
    conn.close()
    logger.info("LLM insights generation finished.")

if __name__ == '__main__':
    update_insights()
