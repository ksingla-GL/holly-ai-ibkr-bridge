# Holly AI to IBKR Bridge

Automated trading system that reads Holly AI alerts from CSV and executes trades through Interactive Brokers TWS API.

## Features
- Real-time CSV alert monitoring
- Automated order execution via IBKR TWS API
- Paper trading mode

## Setup
1. Install Python 3.8 or higher
2. Install dependencies: `pip install -r requirements.txt`
3. Configure IBKR TWS:
   - Enable API connections in File > Global Configuration > API > Settings
   - Check "Enable ActiveX and Socket Clients"
   - Uncheck "Read-Only API" button
   - Set Socket port to 7497 (paper trading)
4. Update `config/config.json` with your settings
5. Change csv path in "alerts" in `config/config.json` to where your Holly AI alerts file is located
6. Run: `python src/main.py` or use `run.bat` (Windows) / `run.sh` (Mac/Linux)

## CSV Format
The Holly AI CSV must have these columns:
- TimeStamp
- Symbol
- Type
- Description (containing "New High" triggers)
- Price
- Relative Volume

## Project Structure
- `src/core/`: Core trading logic and IBKR integration
- `src/utils/`: Utility functions
- `config/`: Configuration files
- `data/`: Alert files and trade logs

IMPORTANT: Trading Mode Configuration

Paper Trading (SAFE):
- Set port to 7497 in config.json
- Uses virtual money
- No real trades

Live Trading (REAL MONEY):
- Set port to 7496 in config.json  
- Uses real money
- Real trades executed

The system will REFUSE to connect if port 7496 (live) is detected.
To enable live trading, remove the safety check in ibkr_connector.py