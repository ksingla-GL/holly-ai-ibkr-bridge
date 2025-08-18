# Holly AI to IBKR Bridge

Automated trading system that reads Holly AI breakout signals and executes trades through Interactive Brokers.

## Features

- **Timezone-Aware**: Uses your configured local timezone while trading US markets
- **State Persistence**: Maintains state across restarts, preventing duplicate trades
- **Position Sync**: Regularly syncs with IBKR to ensure position accuracy
- **Time-Based Exits**: Automatically exits positions after 10 minutes
- **Risk Management**: 3% position sizing, max 3 concurrent positions, 30 daily trades
- **Real-time Dashboard**: Streamlit-based monitoring interface for trades and performance

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure TWS/IB Gateway:
   - Enable API connections
   - Set socket port to 7497 for paper trading
   - Disable read-only API mode

3. Edit `config/config.json`:
   - Set `system.timezone` to your local timezone (e.g. `Australia/Sydney`)
   - Keep `system.market_timezone` as `US/Eastern` for U.S. market hours
   - Verify `alerts.csv_path` points to the folder where Holly AI drops CSVs
   - Adjust risk parameters if needed

4. Run the system:
   ```bash
   python main.py
   ```

## Dashboard Monitoring

Launch the real-time monitoring dashboard to track trades and performance:

```bash
python run_dashboard.py
```

The dashboard provides:
- **Active Trades**: Current open positions and recent activity
- **Trade History**: Performance metrics, P&L charts, and trade analysis
- **Risk Parameters**: Current risk settings and usage monitoring
- **System Status**: File status checks and alert processing statistics

Access the dashboard at `http://localhost:8501` after starting.

## State Management

The system maintains state in `data/state/trading_state.json` which includes:
- Processed alerts (prevents duplicates)
- Open positions
- Pending exits
- Daily statistics

This ensures the system can be safely restarted without:
- Processing the same alerts multiple times
- Losing track of open positions
- Missing scheduled exits

## Monitoring

### Dashboard (Recommended)
Use the Streamlit dashboard for real-time monitoring:
```bash
python run_dashboard.py
```

### Log Files
Check the logs in the `logs/Text_Logs` directory for runtime details such as:
- Trade execution messages
- Position sync results
- Risk rule violations
- System errors

Daily trade summaries are written to CSV files in `logs/Trade_Logs`.

## Safety Features

- Port 7496 (live trading) is blocked
- Automatic position sync with IBKR
- Graceful shutdown closes all positions
- State backup prevents data loss
