import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import os

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
        backdrop-filter: blur(10px);
    }
    .senator-card {
        background: linear-gradient(145deg, #1e2128, #15171c);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        border: 1px solid #2d313a;
    }
    .insight-box {
        border-left: 4px solid #4CAF50;
        background-color: rgba(76, 175, 80, 0.1);
        padding: 15px;
        border-radius: 0 8px 8px 0;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

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

st.title("🏛️ US Senate Stock Tracker")
st.markdown("Monitoraggio delle compravendite azionarie dei senatori USA e analisi dei conflitti d'interesse.")

trades_df, insights_df = load_data()

if trades_df.empty:
    st.warning("Nessun dato trovato. Esegui il collector per popolare il database.")
else:
    # Convert dates
    trades_df['transaction_date'] = pd.to_datetime(trades_df['transaction_date'])
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("Totale Transazioni", len(trades_df))
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("Senatori Coinvolti", trades_df['senator'].nunique())
        st.markdown('</div>', unsafe_allow_html=True)
    with col3:
        avg_roi = trades_df['roi_pct'].mean()
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric("ROI Medio (Stimato)", f"{avg_roi:.2f}%", delta=f"{avg_roi:.2f}%")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📊 Leaderboard", "📝 Transazioni Recenti", "🤖 Analisi AI (Gemini)"])

    with tab1:
        st.subheader("Senatori Più Profittevoli")
        
        # Aggregate by senator
        senator_roi = trades_df.groupby('senator').agg(
            avg_roi=('roi_pct', 'mean'),
            trade_count=('id', 'count')
        ).reset_index().sort_values(by='avg_roi', ascending=False)
        
        # Filter those with at least a few trades for a fair leaderboard
        senator_roi = senator_roi[senator_roi['trade_count'] >= 1]
        
        fig = px.bar(
            senator_roi.head(15), 
            x='avg_roi', 
            y='senator', 
            orientation='h',
            title="Top 15 Senatori per Ritorno sull'Investimento (ROI %)",
            color='avg_roi',
            color_continuous_scale="Viridis",
            labels={'avg_roi': 'ROI Medio (%)', 'senator': 'Senatore'}
        )
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color='#e0e0e0')
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Ultime Transazioni")
        recent = trades_df.sort_values(by='transaction_date', ascending=False).head(50)
        
        # Formatting for display
        display_df = recent[['transaction_date', 'senator', 'ticker', 'type', 'amount_range', 'roi_pct']].copy()
        display_df['transaction_date'] = display_df['transaction_date'].dt.strftime('%Y-%m-%d')
        display_df['roi_pct'] = display_df['roi_pct'].apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Possibili Conflitti d'Interesse")
        st.markdown("L'intelligenza artificiale **Gemini** analizza il portafoglio dei senatori incrociando i loro ruoli politici con i settori delle aziende in cui hanno investito.")
        
        if insights_df.empty:
            st.info("Nessuna analisi generata finora. Esegui lo script `llm_analysis.py`.")
        else:
            # Join trades with insights
            for _, row in insights_df.iterrows():
                senator = row['senator']
                ticker = row['ticker']
                insight = row['insight_text']
                
                # Get the latest trade details for this pair
                trade_info = trades_df[(trades_df['senator'] == senator) & (trades_df['ticker'] == ticker)]
                
                st.markdown(f"""
                <div class="senator-card">
                    <h4>🏛️ {senator} - 📈 {ticker}</h4>
                    <p style="color: #a0a0a0; font-size: 0.9em;">Ultimo aggiornamento analisi: {row['last_updated'][:10]}</p>
                    <div class="insight-box">
                        <strong>Analisi Gemini:</strong><br>
                        {insight}
                    </div>
                </div>
                """, unsafe_allow_html=True)
