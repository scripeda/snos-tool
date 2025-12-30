from flask import Flask, request, jsonify
import sqlite3
import datetime
from datetime import timedelta
import secrets
import os

app = Flask(__name__)

# Конфигурация из переменных окружения
API_KEY = os.environ.get('API_KEY', 'SECRET_KEY_123')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'ADMIN_KEY_456')
DATABASE_URL = os.environ.get('DATABASE_URL', 'licenses.db')

class LicenseDatabase:
    def __init__(self, db_path=DATABASE_URL):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT UNIQUE NOT NULL,
                hwid TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                max_activations INTEGER DEFAULT 1,
                current_activations INTEGER DEFAULT 0,
                product TEXT DEFAULT 'SnosByDrxe'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key TEXT,
                hwid TEXT,
                activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                FOREIGN KEY (license_key) REFERENCES licenses (license_key)
            )
        ''')
        
        # Тестовые ключи
        test_keys = [
            ("SNOS-TEST-7D3F9A2B5C8E", 30, 999),
            ("SNOS-ETERNAL-ABCDEF123456", 0, 1),
            ("SNOS-DEMO-123456789ABC", 7, 3),
        ]
        
        for key, days, activations in test_keys:
            cursor.execute('SELECT 1 FROM licenses WHERE license_key = ?', (key,))
            if not cursor.fetchone():
                expires_at = None
                if days > 0:
                    expires_at = datetime.datetime.now() + timedelta(days=days)
                
                cursor.execute('''
                    INSERT INTO licenses (license_key, expires_at, max_activations)
                    VALUES (?, ?, ?)
                ''', (key, expires_at, activations))
        
        conn.commit()
        conn.close()
    
    def generate_license_key(self, days=30, max_activations=1):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        while True:
            key = f"SNOS-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            cursor.execute('SELECT 1 FROM licenses WHERE license_key = ?', (key,))
            if not cursor.fetchone():
                break
        
        expires_at = None
        if days > 0:
            expires_at = datetime.datetime.now() + timedelta(days=days)
        
        cursor.execute('''
            INSERT INTO licenses (license_key, expires_at, max_activations)
            VALUES (?, ?, ?)
        ''', (key, expires_at, max_activations))
        
        conn.commit()
        conn.close()
        return key
    
    def activate_license(self, license_key, hwid, ip_address):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT is_active, expires_at, max_activations, current_activations
            FROM licenses WHERE license_key = ?
        ''', (license_key,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False, "Лицензия не найдена"
        
        is_active = bool(result['is_active'])
        expires_at = result['expires_at']
        max_activations = result['max_activations']
        current_activations = result['current_activations']
        
        if not is_active:
            conn.close()
            return False, "Лицензия заблокирована"
        
        if expires_at:
            expires_date = datetime.datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
            if datetime.datetime.now() > expires_date:
                conn.close()
                return False, "Срок действия лицензии истек"
        
        if current_activations >= max_activations:
            cursor.execute('SELECT 1 FROM activations WHERE license_key = ? AND hwid = ?', (license_key, hwid))
            if cursor.fetchone():
                conn.close()
                return True, "Лицензия уже активирована на этом устройстве"
            else:
                conn.close()
                return False, "Достигнут лимит активаций"
        
        cursor.execute('UPDATE licenses SET current_activations = current_activations + 1 WHERE license_key = ?', (license_key,))
        cursor.execute('INSERT INTO activations (license_key, hwid, ip_address) VALUES (?, ?, ?)', 
                      (license_key, hwid, ip_address))
        
        conn.commit()
        conn.close()
        return True, "Лицензия успешно активирована"
    
    def check_license(self, license_key, hwid):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT l.is_active, l.expires_at, l.max_activations, l.current_activations,
                   a.hwid, a.activated_at
            FROM licenses l
            LEFT JOIN activations a ON l.license_key = a.license_key AND a.hwid = ?
            WHERE l.license_key = ?
        ''', (hwid, license_key))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return False, "Лицензия не найдена"
        
        response = {
            'is_active': bool(result['is_active']),
            'is_expired': False,
            'expires_at': result['expires_at'],
            'max_activations': result['max_activations'],
            'current_activations': result['current_activations'],
            'is_activated_on_hwid': result['hwid'] is not None,
            'activated_at': result['activated_at']
        }
        
        if result['expires_at']:
            expires_date = datetime.datetime.fromisoformat(result['expires_at']) if isinstance(result['expires_at'], str) else result['expires_at']
            response['is_expired'] = datetime.datetime.now() > expires_date
        
        return True, response
    
    def get_all_licenses(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT license_key, hwid, created_at, expires_at, 
                   is_active, max_activations, current_activations
            FROM licenses
            ORDER BY created_at DESC
        ''')
        
        licenses = []
        for row in cursor.fetchall():
            licenses.append({
                'license_key': row['license_key'],
                'hwid': row['hwid'],
                'created_at': row['created_at'],
                'expires_at': row['expires_at'],
                'is_active': bool(row['is_active']),
                'max_activations': row['max_activations'],
                'current_activations': row['current_activations']
            })
        
        conn.close()
        return licenses
    
    def reset_license(self, license_key):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT 1 FROM licenses WHERE license_key = ?', (license_key,))
        if not cursor.fetchone():
            conn.close()
            return False, "Лицензия не найдена"
        
        cursor.execute('UPDATE licenses SET current_activations = 0 WHERE license_key = ?', (license_key,))
        cursor.execute('DELETE FROM activations WHERE license_key = ?', (license_key,))
        
        conn.commit()
        conn.close()
        return True, "Лицензия успешно сброшена"

# Инициализация базы данных
db = LicenseDatabase()

# ==================== API ЭНДПОЙНТЫ ====================

@app.route('/')
def home():
    return jsonify({
        'service': 'SnosByDrxe License Server',
        'status': 'running',
        'endpoints': {
            'test': '/api/test',
            'activate': '/api/activate',
            'check': '/api/check',
            'generate': '/api/generate (requires API_KEY)',
            'licenses': '/api/licenses (requires ADMIN_KEY)',
            'reset': '/api/reset (requires ADMIN_KEY)',
            'revoke': '/api/revoke (requires ADMIN_KEY)',
            'update': '/api/update (requires ADMIN_KEY)'
        },
        'test_keys': [
            'SNOS-TEST-7D3F9A2B5C8E (30 дней, много активаций)',
            'SNOS-ETERNAL-ABCDEF123456 (вечная, 1 активация)',
            'SNOS-DEMO-123456789ABC (7 дней, 3 активации)'
        ]
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    return jsonify({
        'status': 'ok',
        'server_time': datetime.datetime.now().isoformat(),
        'message': 'SnosByDrxe License Server is running',
        'version': '1.0.0'
    })

@app.route('/api/activate', methods=['POST'])
def activate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No JSON data provided'}), 400
        
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        ip_address = request.remote_addr
        
        if not license_key or not hwid:
            return jsonify({'success': False, 'message': 'Missing license_key or hwid'}), 400
        
        success, message = db.activate_license(license_key, hwid, ip_address)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/check', methods=['POST'])
def check():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
        
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        if not license_key or not hwid:
            return jsonify({'success': False, 'error': 'Missing license_key or hwid'}), 400
        
        success, result = db.check_license(license_key, hwid)
        
        if success:
            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'error': result
            })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500

@app.route('/api/generate', methods=['POST'])
def generate():
    """Генерация нового ключа (требует API ключ)"""
    auth_key = request.headers.get('X-Auth-Key')
    if auth_key != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        days = data.get('days', 30)
        max_activations = data.get('max_activations', 1)
        
        license_key = db.generate_license_key(days, max_activations)
        
        return jsonify({
            'success': True,
            'license_key': license_key,
            'days': days,
            'max_activations': max_activations,
            'created_at': datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/licenses', methods=['GET'])
def list_licenses():
    """Список всех лицензий (требует админский ключ)"""
    auth_key = request.headers.get('X-Auth-Key')
    if auth_key != ADMIN_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    licenses = db.get_all_licenses()
    return jsonify({
        'success': True,
        'count': len(licenses),
        'licenses': licenses
    })

@app.route('/api/reset', methods=['POST'])
def reset():
    """Сброс лицензии (требует админский ключ)"""
    auth_key = request.headers.get('X-Auth-Key')
    if auth_key != ADMIN_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data предоставлен'}), 400
        
        license_key = data.get('license_key')
        if not license_key:
            return jsonify({'error': 'Missing license_key'}), 400
        
        success, message = db.reset_license(license_key)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/revoke', methods=['POST'])
def revoke():
    """Отзыв лицензии (требует админский ключ)"""
    auth_key = request.headers.get('X-Auth-Key')
    if auth_key != ADMIN_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        license_key = data.get('license_key')
        if not license_key:
            return jsonify({'error': 'Missing license_key'}), 400
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE licenses SET is_active = 0 WHERE license_key = ?', (license_key,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        
        return jsonify({
            'success': success,
            'message': 'License revoked' if success else 'License not found'
        })
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/update', methods=['POST'])
def update():
    """Обновление параметров лицензии (требует админский ключ)"""
    auth_key = request.headers.get('X-Auth-Key')
    if auth_key != ADMIN_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        data = request.get_json()
        license_key = data.get('license_key')
        days = data.get('days')
        max_activations = data.get('max_activations')
        
        if not license_key:
            return jsonify({'error': 'Missing license_key'}), 400
        
        if days is None and max_activations is None:
            return jsonify({'error': 'No parameters to update'}), 400
        
        updates = []
        params = []
        
        if days is not None:
            if days == 0:
                updates.append("expires_at = NULL")
            else:
                expires_at = datetime.datetime.now() + timedelta(days=days)
                updates.append("expires_at = ?")
                params.append(expires_at)
        
        if max_activations is not None:
            updates.append("max_activations = ?")
            params.append(max_activations)
        
        if not updates:
            return jsonify({'error': 'No parameters to update'}), 400
        
        params.append(license_key)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        sql = f"UPDATE licenses SET {', '.join(updates)} WHERE license_key = ?"
        cursor.execute(sql, params)
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        
        return jsonify({
            'success': updated,
            'message': 'License updated' if updated else 'License not found'
        })
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
