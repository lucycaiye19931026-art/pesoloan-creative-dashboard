"""Pesoloan双端素材表现看板独立服务。
Usage: python app.py --port 5050
参数：--port HTTP监听端口；生产环境使用PORT环境变量。
Example: python app.py --port 5050
"""
import argparse
import os
from flask import Flask, jsonify, redirect
from creative_dashboard_module import register_creative_dashboard

app = Flask(__name__)
register_creative_dashboard(app)

@app.route('/')
def index():
    return redirect('/creative-dashboard')

@app.route('/health')
def health():
    return jsonify({'ok': True, 'service': 'pesoloan-creative-dashboard'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pesoloan素材表现看板')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '5050')))
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port, debug=False)
