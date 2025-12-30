from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import os
import hashlib
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
import json

app = Flask(__name__)

# Получаем строку подключения из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Создает соединение с PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    """Инициализирует базу данных"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Создаем таблицу лицензий
    cur.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id SERIAL PRIMARY KEY,
            license_key VARCHAR(100) UNIQUE NOT NULL,
            hwid VARCHAR(100),
            activated_at TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            customer_name VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем таблицу активаций
    cur.execute('''
        CREATE TABLE IF NOT EXISTS activations (
            id SERIAL PRIMARY KEY,
            license_key VARCHAR(100) REFERENCES licenses(license_key),
            hwid VARCHAR(100),
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address VARCHAR(50)
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

@app.route('/api/validate', methods=['POST'])
def validate_license():
    try:
        data = request.json
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        if not license_key:
            return jsonify({'valid': False, 'message': 'No license key provided'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем лицензию
        cur.execute('''
            SELECT * FROM licenses 
            WHERE license_key = %s AND is_active = TRUE
        ''', (license_key,))
        
        license_data = cur.fetchone()
        
        if not license_data:
            cur.close()
            conn.close()
            return jsonify({'valid': False, 'message': 'Invalid license'}), 403
        
        # Проверяем срок действия
        if license_data['expires_at'] < datetime.now():
            cur.close()
            conn.close()
            return jsonify({
                'valid': False, 
                'message': 'License has expired',
                'expired': True
            }), 403
        
        # Если лицензия без HWID - привязываем к первому устройству
        if not license_data['hwid'] and hwid:
            cur.execute('''
                UPDATE licenses SET hwid = %s 
                WHERE license_key = %s
            ''', (hwid, license_key))
            conn.commit()
            
            # Записываем активацию
            cur.execute('''
                INSERT INTO activations (license_key, hwid, ip_address)
                VALUES (%s, %s, %s)
            ''', (license_key, hwid, request.remote_addr))
            conn.commit()
        
        # Проверяем привязку к HWID
        elif license_data['hwid'] and license_data['hwid'] != hwid:
            cur.close()
            conn.close()
            return jsonify({
                'valid': False, 
                'message': 'License is bound to another device'
            }), 403
        
        cur.close()
        conn.close()
        
        return jsonify({
            'valid': True,
            'expiry': license_data['expires_at'].isoformat(),
            'message': 'License is valid'
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)}), 500

@app.route('/api/activate', methods=['POST'])
def activate_license():
    try:
        data = request.json
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        if not license_key or not hwid:
            return jsonify({'success': False, 'message': 'Missing data'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем существование лицензии
        cur.execute('SELECT * FROM licenses WHERE license_key = %s', (license_key,))
        license_data = cur.fetchone()
        
        if license_data:
            # Лицензия уже существует
            if license_data['hwid'] and license_data['hwid'] != hwid:
                cur.close()
                conn.close()
                return jsonify({
                    'success': False, 
                    'message': 'License already activated on another device'
                }), 403
            
            # Обновляем HWID если нужно
            if not license_data['hwid']:
                cur.execute('''
                    UPDATE licenses 
                    SET hwid = %s, activated_at = CURRENT_TIMESTAMP 
                    WHERE license_key = %s
                ''', (hwid, license_key))
        else:
            # Создаем новую лицензию (для демо)
            expires_at = datetime.now() + timedelta(days=30)
            cur.execute('''
                INSERT INTO licenses (license_key, hwid, expires_at)
                VALUES (%s, %s, %s)
            ''', (license_key, hwid, expires_at))
            
            license_data = {
                'expires_at': expires_at,
                'license_key': license_key
            }
        
        # Записываем активацию
        cur.execute('''
            INSERT INTO activations (license_key, hwid, ip_address)
            VALUES (%s, %s, %s)
        ''', (license_key, hwid, request.remote_addr))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'expiry': license_data['expires_at'].isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def generate_license():
    """Генерирует новую лицензию (требуется секретный ключ)"""
    try:
        auth_key = request.headers.get('X-API-Key')
        if auth_key != os.environ.get('ADMIN_KEY', 'default-secret-key'):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        data = request.json
        days = data.get('days', 30)
        customer = data.get('customer', 'Anonymous')
        
        # Генерация ключа
        key = f"SNOS-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:4].upper()}"
        expires_at = datetime.now() + timedelta(days=days)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO licenses (license_key, expires_at, customer_name)
            VALUES (%s, %s, %s)
        ''', (key, expires_at, customer))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'license_key': key,
            'expiry': expires_at.isoformat(),
            'customer': customer
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/renew', methods=['POST'])
def renew_license():
    try:
        data = request.json
        license_key = data.get('key')
        days = data.get('days', 30)
        
        if not license_key:
            return jsonify({'success': False, 'message': 'No license key'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Находим лицензию
        cur.execute('SELECT expires_at FROM licenses WHERE license_key = %s', (license_key,))
        result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': 'License not found'}), 404
        
        # Обновляем срок
        current_expiry = result['expires_at']
        if current_expiry < datetime.now():
            new_expiry = datetime.now() + timedelta(days=days)
        else:
            new_expiry = current_expiry + timedelta(days=days)
        
        cur.execute('''
            UPDATE licenses 
            SET expires_at = %s, is_active = TRUE 
            WHERE license_key = %s
        ''', (new_expiry, license_key))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'License renewed for {days} days',
            'new_expiry': new_expiry.isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """Получает статистику (админ)"""
    try:
        auth_key = request.headers.get('X-API-Key')
        if auth_key != os.environ.get('ADMIN_KEY', 'default-secret-key'):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Общая статистика
        cur.execute('SELECT COUNT(*) as total, COUNT(CASE WHEN is_active THEN 1 END) as active FROM licenses')
        license_stats = cur.fetchone()
        
        cur.execute('SELECT COUNT(*) as total FROM activations')
        activation_stats = cur.fetchone()
        
        # Последние активации
        cur.execute('''
            SELECT license_key, hwid, activated_at 
            FROM activations 
            ORDER BY activated_at DESC 
            LIMIT 10
        ''')
        recent_activations = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'licenses': {
                'total': license_stats['total'],
                'active': license_stats['active']
            },
            'activations': {
                'total': activation_stats['total']
            },
            'recent_activations': recent_activations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/')
def home():
    return '''
    <html>
        <head>
            <title>Snos Tool License Server</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { 
                    background: #000; 
                    color: #0f0; 
                    font-family: 'Courier New', monospace; 
                    padding: 20px; 
                    max-width: 800px; 
                    margin: 0 auto;
                }
                .container { 
                    border: 2px solid #0f0; 
                    padding: 30px; 
                    margin: 20px 0; 
                    border-radius: 10px;
                }
                h1 { 
                    color: #0f0; 
                    text-align: center;
                    margin-bottom: 30px;
                }
                .status { 
                    background: #0a0a0a; 
                    padding: 15px; 
                    border-radius: 5px;
                    margin: 15px 0;
                }
                .endpoint { 
                    background: #111; 
                    padding: 10px; 
                    margin: 5px 0; 
                    border-left: 3px solid #0f0;
                }
                code { 
                    background: #222; 
                    padding: 2px 5px; 
                    border-radius: 3px;
                }
                .demo { 
                    background: #1a1a1a; 
                    padding: 20px; 
                    margin: 20px 0; 
                    border-radius: 5px;
                }
            </style>
        </head>
        <body>
            <h1>⚡ Snos Tool License Server</h1>
            
            <div class="container">
                <div class="status">
                    <h2>Status: <span style="color:#0f0">ONLINE</span></h2>
                    <p>Server is running and ready to handle license requests.</p>
                </div>
                
                <h3>API Endpoints:</h3>
                <div class="endpoint">
                    <strong>POST /api/validate</strong><br>
                    Validate license key. Requires JSON: <code>{"license_key": "KEY", "hwid": "HWID"}</code>
                </div>
                
                <div class="endpoint">
                    <strong>POST /api/activate</strong><br>
                    Activate license key. Same parameters as validate.
                </div>
                
                <div class="endpoint">
                    <strong>POST /api/generate</strong><br>
                    Generate new license (admin). Requires <code>X-API-Key</code> header.
                </div>
                
                <div class="endpoint">
                    <strong>POST /api/renew</strong><br>
                    Renew existing license. Requires JSON: <code>{"key": "LICENSE_KEY", "days": 30}</code>
                </div>
                
                <div class="demo">
                    <h3>Quick Test:</h3>
                    <p>Try demo license: <code>DEMO-20251230-1234</code></p>
                    <p>Use any HWID for testing.</p>
                </div>
            </div>
        </body>
    </html>
    '''

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'snos-license-server'
    })

# Инициализация базы данных при запуске
@app.before_first_request
def initialize():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
