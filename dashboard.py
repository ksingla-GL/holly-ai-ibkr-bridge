"""
Streamlit Trading Dashboard for Holly AI to IBKR Bridge
Displays active trades, trade history, and risk parameters
"""

import streamlit as st
import pandas as pd
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Page configuration
st.set_page_config(
    page_title="Holly AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

class TradingDashboard:
    def __init__(self):
        self.config_path = "config/config.json"
        self.risk_state_path = "data/state/risk_state.json"
        self.processed_alerts_path = "data/processed_alerts.json"
        self.trade_logs_dir = "logs/Trade_Logs"
        self.text_logs_dir = "logs/Text_Logs"
        
    def load_config(self):
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Error loading config: {e}")
            return {}
    
    def load_risk_state(self):
        """Load current risk state"""
        try:
            with open(self.risk_state_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Risk state file not found: {e}")
            return {}
    
    def load_processed_alerts(self):
        """Load processed alerts data"""
        try:
            with open(self.processed_alerts_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Processed alerts file not found: {e}")
            return {}
    
    def load_trade_history(self, days=30):
        """Load trade history from CSV files"""
        trade_files = glob.glob(f"{self.trade_logs_dir}/*.csv")
        
        if not trade_files:
            return pd.DataFrame()
        
        all_trades = []
        for file in sorted(trade_files, reverse=True)[:days]:  # Last N days
            try:
                df = pd.read_csv(file)
                if not df.empty:
                    all_trades.append(df)
            except Exception as e:
                st.warning(f"Error reading {file}: {e}")
        
        if all_trades:
            combined_df = pd.concat(all_trades, ignore_index=True)
            combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp'])
            return combined_df.sort_values('timestamp', ascending=False)
        
        return pd.DataFrame()
    
    def calculate_trade_metrics(self, df):
        """Calculate trading performance metrics"""
        if df.empty:
            return {}
        
        # Group trades by symbol to calculate P&L
        trades_by_symbol = df.groupby('symbol')
        pnl_data = []
        
        for symbol, group in trades_by_symbol:
            group = group.sort_values('timestamp')
            position = 0
            total_pnl = 0
            entry_price = 0
            
            for _, trade in group.iterrows():
                if trade['action'] == 'BUY':
                    if position == 0:  # New position
                        entry_price = trade['price']
                        position = trade['shares']
                    else:  # Adding to position
                        entry_price = ((entry_price * position) + (trade['price'] * trade['shares'])) / (position + trade['shares'])
                        position += trade['shares']
                elif trade['action'] == 'SELL' and position > 0:
                    # Calculate P&L for this exit
                    exit_shares = min(trade['shares'], position)
                    pnl = (trade['price'] - entry_price) * exit_shares
                    total_pnl += pnl
                    position -= exit_shares
                    
                    pnl_data.append({
                        'symbol': symbol,
                        'timestamp': trade['timestamp'],
                        'pnl': pnl,
                        'entry_price': entry_price,
                        'exit_price': trade['price'],
                        'shares': exit_shares
                    })
        
        if not pnl_data:
            return {}
        
        pnl_df = pd.DataFrame(pnl_data)
        
        return {
            'total_pnl': pnl_df['pnl'].sum(),
            'total_trades': len(pnl_df),
            'winning_trades': len(pnl_df[pnl_df['pnl'] > 0]),
            'losing_trades': len(pnl_df[pnl_df['pnl'] < 0]),
            'win_rate': (len(pnl_df[pnl_df['pnl'] > 0]) / len(pnl_df) * 100) if len(pnl_df) > 0 else 0,
            'avg_pnl': pnl_df['pnl'].mean(),
            'best_trade': pnl_df['pnl'].max() if not pnl_df.empty else 0,
            'worst_trade': pnl_df['pnl'].min() if not pnl_df.empty else 0,
            'pnl_df': pnl_df
        }
    
    def get_active_positions(self, df):
        """Calculate current active positions from trade history"""
        if df.empty:
            return pd.DataFrame()
        
        # Group by symbol and calculate net position
        positions = {}
        
        for _, trade in df.iterrows():
            symbol = trade['symbol']
            if symbol not in positions:
                positions[symbol] = {'shares': 0, 'total_cost': 0, 'last_trade': trade['timestamp']}
            
            if trade['action'] == 'BUY':
                positions[symbol]['shares'] += trade['shares']
                positions[symbol]['total_cost'] += trade['shares'] * trade['price']
            elif trade['action'] == 'SELL':
                # For sells, we approximate by reducing position
                shares_to_reduce = min(trade['shares'], positions[symbol]['shares'])
                if positions[symbol]['shares'] > 0:
                    avg_cost = positions[symbol]['total_cost'] / positions[symbol]['shares']
                    positions[symbol]['total_cost'] -= shares_to_reduce * avg_cost
                positions[symbol]['shares'] -= shares_to_reduce
            
            positions[symbol]['last_trade'] = max(positions[symbol]['last_trade'], trade['timestamp'])
        
        # Filter only active positions
        active_positions = []
        for symbol, pos in positions.items():
            if pos['shares'] > 0:
                avg_price = pos['total_cost'] / pos['shares'] if pos['shares'] > 0 else 0
                active_positions.append({
                    'symbol': symbol,
                    'shares': pos['shares'],
                    'avg_price': avg_price,
                    'total_value': pos['total_cost'],
                    'last_trade': pos['last_trade']
                })
        
        if active_positions:
            return pd.DataFrame(active_positions).sort_values('last_trade', ascending=False)
        return pd.DataFrame()

def main():
    dashboard = TradingDashboard()
    
    # Sidebar
    st.sidebar.title("📈 Holly AI Trading Dashboard")
    st.sidebar.markdown("---")
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data", type="primary"):
        st.rerun()
    
    # Date range selector for trade history
    days_back = st.sidebar.selectbox(
        "Trade History Period",
        [7, 14, 30, 60, 90],
        index=2,
        help="Number of days of trade history to display"
    )
    
    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
    if auto_refresh:
        st.sidebar.info("Dashboard will refresh every 30 seconds")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Last Updated:** " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Main content
    st.title("🚀 Holly AI to IBKR Trading Dashboard")
    st.markdown("Real-time monitoring of automated trading system")
    
    # Load data
    config = dashboard.load_config()
    risk_state = dashboard.load_risk_state()
    processed_alerts = dashboard.load_processed_alerts()
    trade_history = dashboard.load_trade_history(days_back)
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        daily_trades = risk_state.get('daily_trades', 0)
        max_daily = config.get('risk_management', {}).get('max_daily_trades', 30)
        st.metric(
            "Daily Trades",
            f"{daily_trades}/{max_daily}",
            delta=f"{max_daily - daily_trades} remaining"
        )
    
    with col2:
        current_positions = len(risk_state.get('current_positions', {}))
        max_positions = config.get('risk_management', {}).get('max_concurrent_positions', 3)
        st.metric(
            "Active Positions",
            f"{current_positions}/{max_positions}",
            delta=f"{max_positions - current_positions} available"
        )
    
    with col3:
        if not trade_history.empty:
            today_trades = len(trade_history[trade_history['timestamp'].dt.date == datetime.now().date()])
            st.metric("Today's Trades", today_trades)
        else:
            st.metric("Today's Trades", 0)
    
    with col4:
        total_alerts = sum(len(alerts) for alerts in processed_alerts.values())
        st.metric("Processed Alerts", total_alerts)
    
    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Active Trades", "📈 Trade History", "⚠️ Risk Parameters", "📋 System Status"])
    
    with tab1:
        st.header("Active Positions")
        
        active_positions = dashboard.get_active_positions(trade_history)
        
        if not active_positions.empty:
            # Display active positions
            st.dataframe(
                active_positions.style.format({
                    'avg_price': '${:.2f}',
                    'total_value': '${:.2f}',
                    'last_trade': lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else ''
                }),
                use_container_width=True
            )
            
            # Position value chart
            if len(active_positions) > 1:
                fig = px.pie(
                    active_positions, 
                    values='total_value', 
                    names='symbol',
                    title="Position Distribution by Value"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No active positions currently")
            
            # Show recent closed positions
            if not trade_history.empty:
                st.subheader("Recent Closed Positions")
                recent_closes = trade_history[trade_history['action'] == 'SELL'].head(5)
                if not recent_closes.empty:
                    st.dataframe(
                        recent_closes[['timestamp', 'symbol', 'shares', 'price']].style.format({
                            'price': '${:.2f}',
                            'timestamp': lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else ''
                        }),
                        use_container_width=True
                    )
    
    with tab2:
        st.header("Trade History & Performance")
        
        if not trade_history.empty:
            # Calculate metrics
            metrics = dashboard.calculate_trade_metrics(trade_history)
            
            if metrics:
                # Performance metrics
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total P&L", f"${metrics['total_pnl']:.2f}")
                
                with col2:
                    st.metric("Win Rate", f"{metrics['win_rate']:.1f}%")
                
                with col3:
                    st.metric("Total Trades", metrics['total_trades'])
                
                with col4:
                    st.metric("Avg P&L", f"${metrics['avg_pnl']:.2f}")
                
                # P&L over time
                if not metrics['pnl_df'].empty:
                    pnl_df = metrics['pnl_df'].copy()
                    pnl_df['cumulative_pnl'] = pnl_df['pnl'].cumsum()
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=pnl_df['timestamp'],
                        y=pnl_df['cumulative_pnl'],
                        mode='lines+markers',
                        name='Cumulative P&L',
                        line=dict(color='green' if pnl_df['cumulative_pnl'].iloc[-1] > 0 else 'red')
                    ))
                    fig.update_layout(
                        title="Cumulative P&L Over Time",
                        xaxis_title="Date",
                        yaxis_title="P&L ($)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Trade distribution
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # P&L by symbol
                        symbol_pnl = pnl_df.groupby('symbol')['pnl'].sum().reset_index()
                        fig = px.bar(
                            symbol_pnl,
                            x='symbol',
                            y='pnl',
                            title="P&L by Symbol",
                            color='pnl',
                            color_continuous_scale=['red', 'yellow', 'green']
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        # Trade outcome distribution
                        outcomes = ['Winning', 'Losing']
                        values = [metrics['winning_trades'], metrics['losing_trades']]
                        fig = px.pie(
                            values=values,
                            names=outcomes,
                            title="Trade Outcomes",
                            color_discrete_map={'Winning': 'green', 'Losing': 'red'}
                        )
                        st.plotly_chart(fig, use_container_width=True)
            
            # Recent trades table
            st.subheader("Recent Trades")
            recent_trades = trade_history.head(20)
            st.dataframe(
                recent_trades.style.format({
                    'price': '${:.2f}',
                    'timestamp': lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(x) else ''
                }),
                use_container_width=True
            )
        else:
            st.info("No trade history available")
    
    with tab3:
        st.header("Risk Management Parameters")
        
        if config:
            risk_config = config.get('risk_management', {})
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Position Sizing")
                st.metric("Position Size %", f"{risk_config.get('position_size_pct', 0)}%")
                st.metric("Stop Loss %", f"{risk_config.get('stop_loss_pct', 0)}%")
                st.metric("Time Exit (minutes)", risk_config.get('time_exit_minutes', 0))
                
            with col2:
                st.subheader("Trade Limits")
                st.metric("Max Daily Trades", risk_config.get('max_daily_trades', 0))
                st.metric("Max Concurrent Positions", risk_config.get('max_concurrent_positions', 0))
                
                # Usage visualization
                daily_usage = (daily_trades / max_daily * 100) if max_daily > 0 else 0
                position_usage = (current_positions / max_positions * 100) if max_positions > 0 else 0
                
                st.subheader("Current Usage")
                st.progress(daily_usage / 100, f"Daily Trades: {daily_usage:.1f}%")
                st.progress(position_usage / 100, f"Position Slots: {position_usage:.1f}%")
        
        # System configuration
        st.subheader("System Configuration")
        if config:
            st.json({
                "timezone": config.get('system', {}).get('timezone'),
                "market_timezone": config.get('system', {}).get('market_timezone'),
                "ibkr_port": config.get('ibkr', {}).get('port'),
                "csv_path": config.get('alerts', {}).get('csv_path')
            })
    
    with tab4:
        st.header("System Status")
        
        # File status checks
        st.subheader("Data Files")
        
        files_to_check = [
            ("Configuration", dashboard.config_path),
            ("Risk State", dashboard.risk_state_path),
            ("Processed Alerts", dashboard.processed_alerts_path)
        ]
        
        for name, path in files_to_check:
            if Path(path).exists():
                st.success(f"✅ {name}: Found")
                st.caption(f"Last modified: {datetime.fromtimestamp(Path(path).stat().st_mtime)}")
            else:
                st.error(f"❌ {name}: Not found")
        
        # Log directories
        st.subheader("Log Status")
        
        trade_logs = list(Path(dashboard.trade_logs_dir).glob("*.csv")) if Path(dashboard.trade_logs_dir).exists() else []
        text_logs = list(Path(dashboard.text_logs_dir).glob("*.log")) if Path(dashboard.text_logs_dir).exists() else []
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Trade Log Files", len(trade_logs))
            if trade_logs:
                latest_trade_log = max(trade_logs, key=lambda x: x.stat().st_mtime)
                st.caption(f"Latest: {latest_trade_log.name}")
        
        with col2:
            st.metric("Text Log Files", len(text_logs))
            if text_logs:
                latest_text_log = max(text_logs, key=lambda x: x.stat().st_mtime)
                st.caption(f"Latest: {latest_text_log.name}")
        
        # Alert processing status
        if processed_alerts:
            st.subheader("Alert Processing")
            alerts_by_date = {date: len(alerts) for date, alerts in processed_alerts.items()}
            if alerts_by_date:
                fig = px.bar(
                    x=list(alerts_by_date.keys()),
                    y=list(alerts_by_date.values()),
                    title="Processed Alerts by Date"
                )
                st.plotly_chart(fig, use_container_width=True)
    
    # Auto-refresh functionality
    if auto_refresh:
        time.sleep(30)
        st.rerun()

if __name__ == "__main__":
    main()