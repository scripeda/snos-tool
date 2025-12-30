from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import sqlite3
import hashlib
import uuid
import json

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            hwid TEXT,
            activated_at DATETIME,
            expires_at DATETIME,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/api/validate', methods=['POST'])
def validate_license():
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM licenses WHERE license_key = ? AND is_active = 1', (license_key,))
    license_data = c.fetchone()
    
    if license_data:
        expires_at = datetime.fromisoformat(license_data[4])
        if datetime.now() < expires_at:
            if not license_data[2]:
                c.execute('UPDATE licenses SET hwid = ? WHERE license_key = ?', (hwid, license_key))
                conn.commit()
            
            if license_data[2] and license_data[2] != hwid:
                conn.close()
                return jsonify({'valid': False, 'message': 'License is bound to another device'})
            
            conn.close()
            return jsonify({
                'valid': True,
                'expiry': expires_at.isoformat(),
                'message': 'License is valid'
            })
    
    conn.close()
    return jsonify({'valid': False, 'message': 'Invalid license'})

@app.route('/api/activate', methods=['POST'])
def activate_license():
    data = request.json
    license_key = data.get('license_key')
    hwid = data.get('hwid')
    
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
    license_data = c.fetchone()
    
    if license_data:
        if license_data[2] and license_data[2] != hwid:
            conn.close()
            return jsonify({'success': False, 'message': 'License already activated on another device'})
        
        c.execute('UPDATE licenses SET hwid = ?, is_active = 1 WHERE license_key = ?', (hwid, license_key))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'expiry': license_data[4]
        })
    else:
        expires_at = datetime.now() + timedelta(days=30)
        c.execute('INSERT INTO licenses (license_key, hwid, activated_at, expires_at) VALUES (?, ?, ?, ?)',
                 (license_key, hwid, datetime.now().isoformat(), expires_at.isoformat()))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'expiry': expires_at.isoformat()
        })

@app.route('/api/generate', methods=['POST'])
def generate_license():
    days = request.json.get('days', 30)
    key = f"SNOS-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:4].upper()}"
    
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    expires_at = datetime.now() + timedelta(days=days)
    c.execute('INSERT INTO licenses (license_key, expires_at) VALUES (?, ?)', (key, expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'license_key': key,
        'expiry': expires_at.isoformat()
    })

@app.route('/api/renew', methods=['POST'])
def renew_license():
    data = request.json
    license_key = data.get('key')
    days = data.get('days', 30)
    
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    
    c.execute('SELECT expires_at FROM licenses WHERE license_key = ?', (license_key,))
    result = c.fetchone()
    
    if result:
        current_expiry = datetime.fromisoformat(result[0])
        if current_expiry < datetime.now():
            new_expiry = datetime.now() + timedelta(days=days)
        else:
            new_expiry = current_expiry + timedelta(days=days)
        
        c.execute('UPDATE licenses SET expires_at = ? WHERE license_key = ?', 
                 (new_expiry.isoformat(), license_key))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'License renewed for {days} days',
            'new_expiry': new_expiry.isoformat()
        })
    
    conn.close()
    return jsonify({'success': False, 'message': 'License not found'})

@app.route('/')
def home():
    return '''
    <html>
        <head>
            <title>Snos Tool License Server</title>
            <style>
                body { background: #000; color: #0f0; font-family: monospace; padding: 50px; }
                .container { max-width: 800px; margin: 0 auto; }
                h1 { color: #0f0; }
                .status { border: 2px solid #0f0; padding: 20px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⚡ Snos Tool License Server</h1>
                <div class="status">
                    <h2>Status: ONLINE</h2>
                    <p>Server is running and ready to handle license requests.</p>
                    <p>API Endpoints:</p>
                    <ul>
                        <li>POST /api/validate - Validate license key</li>
                        <li>POST /api/activate - Activate license key</li>
                        <li>POST /api/generate - Generate new license (admin)</li>
                        <li>POST /api/renew - Renew existing license</li>
                    </ul>
                </div>
            </div>
        </body>
    </html>
    '''

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)