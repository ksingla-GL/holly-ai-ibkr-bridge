#!/usr/bin/env python3
"""
Simple runner script for the Holly AI Trading Dashboard
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Run the Streamlit dashboard"""
    dashboard_path = Path(__file__).parent / "dashboard.py"
    
    if not dashboard_path.exists():
        print("Error: dashboard.py not found!")
        sys.exit(1)
    
    print("Starting Holly AI Trading Dashboard...")
    print("Dashboard will open in your browser at http://localhost:8501")
    print("Press Ctrl+C to stop the dashboard")
    
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(dashboard_path),
            "--server.address", "localhost",
            "--server.port", "8501",
            "--browser.gatherUsageStats", "false"
        ])
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    except Exception as e:
        print(f"Error running dashboard: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()