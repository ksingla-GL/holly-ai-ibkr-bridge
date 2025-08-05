# Holly AI to IBKR Bridge

Automated trading system that reads Holly AI breakout signals and executes trades through Interactive Brokers.

## Features

- **Timezone-Aware**: Correctly handles Australian timezone for US market trading
- **State Persistence**: Maintains state across restarts, preventing duplicate trades
- **Position Sync**: Regularly syncs with IBKR to ensure position accuracy
- **Time-Based Exits**: Automatically exits positions after 10 minutes
- **Risk Management**: 3% position sizing, max 3 concurrent positions, 30 daily trades

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
   - Set your timezone
   - Adjust risk parameters if needed
   - Verify CSV path settings

4. Run the system:
   ```bash
   python main.py
   ```

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

Check the logs in `logs/` directory for:
- Trade execution details
- Position sync results
- Risk rule violations
- System errors

## Safety Features

- Port 7496 (live trading) is blocked
- Automatic position sync with IBKR
- Graceful shutdown closes all positions
- State backup prevents data loss
