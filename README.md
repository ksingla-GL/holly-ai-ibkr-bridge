# Holly AI to IBKR Bridge

Automated trading system that reads Holly AI alerts from CSV and executes trades through Interactive Brokers TWS API.

## Features
- Real-time CSV alert monitoring
- Automated order execution via IBKR TWS API
- Risk management controls
- Web-based monitoring dashboard
- Paper trading mode

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Configure IBKR credentials in `config/config.json`
3. Place Holly AI alerts CSV in `data/alerts/`
4. Run: `python src/main.py`

## Project Structure
- `src/core/`: Core trading logic and IBKR integration
- `src/risk/`: Risk management modules
- `src/dashboard/`: Flask web dashboard
- `src/utils/`: Utility functions
- `config/`: Configuration files
- `data/`: Alert files and trade logs
