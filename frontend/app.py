import streamlit as st
from streamlit_autorefresh import st_autorefresh
import sqlite3
import pandas as pd
import plotly.express as px
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.progress import get_progress
# Page config
st.set_page_config(
    page_title="Senate Stock Tracker",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium aesthetic
st.markdown("""
<style>
    /* Dark mode optimized premium look */
    .stApp {
        background-color: #0e1117;
        color: #e0e0e0;
    }
    h1, h2, h3 {
        color: #f8f9fa;
        font-family: 'Inter', sans-serif;
    }
    .metric-container {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .senator-card {
        background-color: #1e2530;
        border-left: 5px solid #ff4b4b;
        padding: 15px;
        margin-bottom: 15px;
        border-radius: 5px;
    }
    .insight-box {
        background-color: #2b3340;
        padding: 10px;
        border-radius: 5px;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- Progress Tracking ---
prog = get_progress()
if prog and prog.get("status") not in ("done", "error"):
    # Autorefresh every 2 seconds if still running
    st_autorefresh(interval=2000, limit=None, key="data_refresh")
    
    st.info("🔄 **Aggiornamento dati in corso in background...**")
    status_msg = prog.get("message", "Elaborazione in corso...")
    current = prog.get("current", 0)
    total = prog.get("total", 100)
    
    # Calculate percentage safely
    pct = 0.0
    if total > 0:
        pct = current / total
        pct = min(max(pct, 0.0), 1.0)
        
    st.progress(pct, text=status_msg)

elif prog and prog.get("status") == "error":
    st.error(prog.get("message", "Errore durante l'aggiornamento."))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'senators_trading.db')

@st.cache_data(ttl=3600)
def load_data():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(), pd.DataFrame()
        
    conn = sqlite3.connect(DB_PATH)
    trades_df = pd.read_sql_query("SELECT * FROM trades", conn)
    insights_df = pd.read_sql_query("SELECT * FROM insights", conn)
    conn.close()
    return trades_df, insights_df

st.title("🏛️ US Congress Stock Tracker")
st.markdown("Monitoraggio delle compravendite azionarie dei politici USA e analisi dei conflitti d'interesse.")

trades_df, insights_df = load_data()

if trades_df.empty:
    st.warning("Nessun dato trovato. Esegui il collector per popolare il database.")
else:
    # Convert dates
    trades_df['transaction_date'] = pd.to_datetime(trades_df['transaction_date'])
    
    # Optional filter by chamber
    chambers = trades_df['chamber'].unique()
    selected_chamber = st.selectbox("Filtra per Camera", options=["Tutti"] + list(chambers))
    if selected_chamber != "Tutti":
        trades_df = trades_df[trades_df['chamber'] == selected_chamber]
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("Totale Transazioni", len(trades_df))
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("Politici Coinvolti", trades_df['politician'].nunique())
        st.markdown('</div>', unsafe_allow_html=True)
    with col3:
        avg_roi = trades_df['roi_pct'].mean() if not trades_df.empty else 0
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("ROI Medio (Stimato)", f"{avg_roi:.2f}%", delta=f"{avg_roi:.2f}%")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "📝 Transazioni Recenti", "🤖 Analisi AI (Gemini)"])

    with tab1:
        st.subheader("Politici Più Profittevoli")
        
        # Aggregate by politician
        politician_roi = trades_df.groupby('politician').agg(
            avg_roi=('roi_pct', 'mean'),
            trade_count=('id', 'count')
        ).reset_index().sort_values(by='avg_roi', ascending=False)
        
        # Filter those with at least a few trades for a fair leaderboard
        politician_roi = politician_roi[politician_roi['trade_count'] >= 1]
        
        fig = px.bar(
            politician_roi.head(15), 
            x='avg_roi', 
            y='politician', 
            orientation='h',
            title="Top 15 Politici per Ritorno sull'Investimento (ROI %)",
            color='avg_roi',
            color_continuous_scale="Viridis",
            labels={'avg_roi': 'ROI Medio (%)', 'politician': 'Politico'}
        )
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#e0e0e0')
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Ultime Transazioni")
        recent = trades_df.sort_values(by='transaction_date', ascending=False).head(50)
        
        # Formatting for display
        display_df = recent[['transaction_date', 'politician', 'chamber', 'ticker', 'type', 'amount_range', 'roi_pct']].copy()
        display_df['transaction_date'] = display_df['transaction_date'].dt.strftime('%Y-%m-%d')
        display_df['roi_pct'] = display_df['roi_pct'].apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Possibili Conflitti d'Interesse")
        st.markdown("L'intelligenza artificiale **Gemini** analizza il portafoglio dei politici incrociando i loro ruoli con i settori delle aziende in cui hanno investito.")
        
        if insights_df.empty:
            st.info("Nessuna analisi generata finora. Esegui lo script `llm_analysis.py`.")
        else:
            # Filter insights by available politicians in the filtered trades_df
            valid_politicians = trades_df['politician'].unique()
            filtered_insights = insights_df[insights_df['politician'].isin(valid_politicians)]
            
            for _, row in filtered_insights.iterrows():
                politician = row['politician']
                ticker = row['ticker']
                insight = row['insight_text']
                
                st.markdown(f"""
                <div class="senator-card">
                    <h4>🏛️ {politician} - 📈 {ticker}</h4>
                    <p style="color: #a0a0a0; font-size: 0.9em;">Ultimo aggiornamento analisi: {row['last_updated'][:10]}</p>
                    <div class="insight-box">
                        <strong>Analisi Gemini:</strong><br>
                        {insight}
                    </div>
                </div>
                """, unsafe_allow_html=True)
