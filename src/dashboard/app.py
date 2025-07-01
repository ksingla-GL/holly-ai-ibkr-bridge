"""Flask Web Dashboard"""
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Shared state (in production, use Redis or database)
dashboard_data = {
    'active_trades': [],
    'trade_history': [],
    'account_info': {},
    'risk_metrics': {},
    'system_status': 'Running'
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        'status': dashboard_data['system_status'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/trades/active')
def get_active_trades():
    return jsonify(dashboard_data['active_trades'])

@app.route('/api/trades/history')
def get_trade_history():
    return jsonify(dashboard_data['trade_history'])

@app.route('/api/account')
def get_account_info():
    return jsonify(dashboard_data['account_info'])

@app.route('/api/risk')
def get_risk_metrics():
    return jsonify(dashboard_data['risk_metrics'])

def update_dashboard_data(key: str, data):
    """Update dashboard data (called from main trading loop)"""
    dashboard_data[key] = data

def run_dashboard(config):
    """Run Flask dashboard"""
    app.run(
        host=config['dashboard']['host'],
        port=config['dashboard']['port'],
        debug=config['dashboard']['debug']
    )
