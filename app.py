from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import uuid
import hashlib
import json
import os
import sqlite3
from functools import wraps

app = Flask(__name__)
CORS(app)

# Конфигурация
ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'BYDSQ123')
SERVER_SECRET = os.environ.get('SERVER_SECRET', 'BYDSQ123')
DATABASE_URL = os.environ.get('DATABASE_URL', 'licenses.db')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DATABASE_URL)
    c = conn.cursor()
    
    # Таблица лицензий
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id TEXT PRIMARY KEY,
            license_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            max_activations INTEGER DEFAULT 1,
            current_activations INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            notes TEXT,
            created_by TEXT,
            source TEXT DEFAULT 'server'
        )
    ''')
    
    # Таблица активаций
    c.execute('''
        CREATE TABLE IF NOT EXISTS activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT NOT NULL,
            hwid TEXT NOT NULL,
            device_name TEXT,
            platform TEXT,
            activation_time TIMESTAMP NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (license_key) REFERENCES licenses (license_key)
        )
    ''')
    
    # Таблица администраторов (для будущего использования)
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            api_key TEXT UNIQUE,
            permissions TEXT DEFAULT 'read,write'
        )
    ''')
    
    # Таблица статистики
    c.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            licenses_generated INTEGER DEFAULT 0,
            licenses_activated INTEGER DEFAULT 0,
            unique_hwids INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    return conn

# Декоратор для проверки API ключа
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != ADMIN_API_KEY:
            return jsonify({
                'success': False,
                'message': 'Invalid or missing API key',
                'error_code': 'INVALID_API_KEY'
            }), 401
        return f(*args, **kwargs)
    return decorated_function

# Декоратор для логирования
def log_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        endpoint = request.path
        method = request.method
        user_agent = request.headers.get('User-Agent', 'Unknown')
        
        print(f"[{datetime.now()}] {method} {endpoint} - IP: {ip} - UA: {user_agent[:50]}...")
        return f(*args, **kwargs)
    return decorated_function

# Вспомогательные функции
def generate_license_key():
    """Генерирует уникальный лицензионный ключ"""
    key_base = hashlib.sha256(f"{uuid.uuid4()}{SERVER_SECRET}{datetime.now()}".encode()).hexdigest().upper()
    return f"SNOS-{key_base[:4]}-{key_base[4:8]}-{key_base[8:12]}-{key_base[12:16]}-{key_base[16:20]}"

def update_stats(action, license_key=None, hwid=None):
    """Обновляет статистику"""
    try:
        conn = get_db()
        c = conn.cursor()
        today = datetime.now().date().isoformat()
        
        # Получаем текущую статистику за сегодня
        c.execute("SELECT * FROM stats WHERE date = ?", (today,))
        stats = c.fetchone()
        
        if not stats:
            # Создаем новую запись
            c.execute('''
                INSERT INTO stats (date, licenses_generated, licenses_activated, unique_hwids)
                VALUES (?, 0, 0, 0)
            ''', (today,))
        
        if action == 'generate':
            c.execute("UPDATE stats SET licenses_generated = licenses_generated + 1 WHERE date = ?", (today,))
        elif action == 'activate':
            c.execute("UPDATE stats SET licenses_activated = licenses_activated + 1 WHERE date = ?", (today,))
            
            # Проверяем уникальность HWID
            if hwid:
                c.execute('''
                    SELECT COUNT(DISTINCT hwid) as unique_count 
                    FROM activations 
                    WHERE date(activation_time) = ?
                ''', (today,))
                unique_count = c.fetchone()['unique_count']
                c.execute("UPDATE stats SET unique_hwids = ? WHERE date = ?", (unique_count, today))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Stats update error: {e}")

# API Endpoints

@app.route('/')
@log_request
def index():
    return jsonify({
        'service': 'Snos Tool License Server',
        'version': '2.0.0',
        'status': 'online',
        'endpoints': {
            'GET /api/test': 'Test server connection',
            'POST /api/generate': 'Generate new license key',
            'POST /api/activate': 'Activate license',
            'POST /api/validate': 'Validate license',
            'GET /api/licenses': 'Get all licenses (admin)',
            'GET /api/stats': 'Get server statistics',
            'GET /api/license/<key>': 'Get license details'
        }
    })

@app.route('/api/test', methods=['GET'])
@log_request
def test():
    return jsonify({
        'success': True,
        'message': 'Server is online and responding',
        'server_time': datetime.now().isoformat(),
        'server_version': '2.0.0',
        'uptime': '24/7'
    })

@app.route('/api/generate', methods=['POST'])
@require_api_key
@log_request
def generate_license():
    try:
        data = request.json or {}
        
        # Параметры генерации
        days_valid = int(data.get('days_valid', 30))
        max_activations = int(data.get('max_activations', 1))
        notes = data.get('notes', '')
        created_by = data.get('created_by', 'admin_panel')
        
        if days_valid <= 0 or max_activations <= 0:
            return jsonify({
                'success': False,
                'message': 'Invalid parameters: days_valid and max_activations must be positive'
            }), 400
        
        # Генерируем ключ
        license_key = generate_license_key()
        license_id = str(uuid.uuid4())
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=days_valid)
        
        # Сохраняем в базу
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO licenses (id, license_key, created_at, expires_at, max_activations, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (license_id, license_key, created_at, expires_at, max_activations, notes, created_by))
        
        conn.commit()
        conn.close()
        
        # Обновляем статистику
        update_stats('generate')
        
        return jsonify({
            'success': True,
            'license_key': license_key,
            'license_id': license_id,
            'created_at': created_at.isoformat(),
            'expires_at': expires_at.isoformat(),
            'max_activations': max_activations,
            'message': f'License generated successfully. Valid for {days_valid} days.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}',
            'error_code': 'GENERATION_ERROR'
        }), 500

@app.route('/api/activate', methods=['POST'])
@log_request
def activate_license():
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        if not license_key or not hwid:
            return jsonify({
                'success': False,
                'message': 'Missing required fields: license_key and hwid',
                'error_code': 'MISSING_FIELDS'
            }), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаем информацию о лицензии
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        license_data = c.fetchone()
        
        if not license_data:
            return jsonify({
                'success': False,
                'message': 'License key not found',
                'error_code': 'LICENSE_NOT_FOUND'
            }), 404
        
        # Проверяем активна ли лицензия
        if not license_data['is_active']:
            return jsonify({
                'success': False,
                'message': 'License has been revoked',
                'error_code': 'LICENSE_REVOKED'
            }), 400
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(license_data['expires_at'])
        if expires_at < datetime.now():
            return jsonify({
                'success': False,
                'message': 'License has expired',
                'expired_at': expires_at.isoformat(),
                'error_code': 'LICENSE_EXPIRED'
            }), 400
        
        # Проверяем количество активаций
        c.execute('SELECT COUNT(*) as count FROM activations WHERE license_key = ?', (license_key,))
        activation_count = c.fetchone()['count']
        
        if activation_count >= license_data['max_activations']:
            return jsonify({
                'success': False,
                'message': f'Maximum activations reached ({license_data["max_activations"]})',
                'max_activations': license_data['max_activations'],
                'current_activations': activation_count,
                'error_code': 'MAX_ACTIVATIONS'
            }), 400
        
        # Проверяем, активирована ли уже на этом HWID
        c.execute('SELECT * FROM activations WHERE license_key = ? AND hwid = ?', (license_key, hwid))
        existing_activation = c.fetchone()
        
        if existing_activation:
            return jsonify({
                'success': True,
                'message': 'License already activated on this device',
                'already_activated': True,
                'activation_time': existing_activation['activation_time'],
                'expires_at': license_data['expires_at']
            })
        
        # Активируем лицензию
        activation_time = datetime.now()
        device_info = data.get('device_info', {})
        
        c.execute('''
            INSERT INTO activations (license_key, hwid, device_name, platform, activation_time, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            license_key,
            hwid,
            device_info.get('device_name'),
            device_info.get('platform'),
            activation_time,
            request.remote_addr,
            request.headers.get('User-Agent')
        ))
        
        # Обновляем счетчик активаций
        c.execute('''
            UPDATE licenses 
            SET current_activations = current_activations + 1 
            WHERE license_key = ?
        ''', (license_key,))
        
        conn.commit()
        conn.close()
        
        # Обновляем статистику
        update_stats('activate', license_key, hwid)
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'license_key': license_key,
            'hwid': hwid,
            'activation_time': activation_time.isoformat(),
            'expires_at': license_data['expires_at'],
            'max_activations': license_data['max_activations'],
            'current_activations': activation_count + 1,
            'already_activated': False
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Activation error: {str(e)}',
            'error_code': 'ACTIVATION_ERROR'
        }), 500

@app.route('/api/validate', methods=['POST'])
@log_request
def validate_license():
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        if not license_key:
            return jsonify({
                'valid': False,
                'message': 'License key is required',
                'error_code': 'MISSING_KEY'
            }), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаем информацию о лицензии
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        license_data = c.fetchone()
        
        if not license_data:
            return jsonify({
                'valid': False,
                'message': 'License key not found',
                'error_code': 'LICENSE_NOT_FOUND'
            })
        
        # Проверяем активна ли лицензия
        if not license_data['is_active']:
            return jsonify({
                'valid': False,
                'message': 'License has been revoked',
                'error_code': 'LICENSE_REVOKED'
            })
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(license_data['expires_at'])
        if expires_at < datetime.now():
            return jsonify({
                'valid': False,
                'message': 'License has expired',
                'expired_at': expires_at.isoformat(),
                'error_code': 'LICENSE_EXPIRED'
            })
        
        # Если передан HWID, проверяем активацию
        if hwid:
            c.execute('SELECT * FROM activations WHERE license_key = ? AND hwid = ?', (license_key, hwid))
            activation = c.fetchone()
            
            if not activation:
                return jsonify({
                    'valid': False,
                    'message': 'License not activated on this device',
                    'error_code': 'NOT_ACTIVATED'
                })
        
        conn.close()
        
        return jsonify({
            'valid': True,
            'message': 'License is valid',
            'license_key': license_key,
            'expires_at': license_data['expires_at'],
            'max_activations': license_data['max_activations'],
            'current_activations': license_data['current_activations'],
            'is_active': bool(license_data['is_active'])
        })
        
    except Exception as e:
        return jsonify({
            'valid': False,
            'message': f'Validation error: {str(e)}',
            'error_code': 'VALIDATION_ERROR'
        }), 500

@app.route('/api/licenses', methods=['GET'])
@require_api_key
@log_request
def get_all_licenses():
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаем все лицензии с информацией об активациях
        c.execute('''
            SELECT 
                l.*,
                GROUP_CONCAT(a.hwid) as activated_hwids,
                COUNT(a.id) as activation_count,
                MAX(a.activation_time) as last_activation
            FROM licenses l
            LEFT JOIN activations a ON l.license_key = a.license_key
            GROUP BY l.id
            ORDER BY l.created_at DESC
        ''')
        
        licenses = []
        for row in c.fetchall():
            license_data = dict(row)
            
            # Преобразуем даты
            license_data['created_at'] = license_data['created_at']
            license_data['expires_at'] = license_data['expires_at']
            
            # Статус лицензии
            expires_at = datetime.fromisoformat(license_data['expires_at'])
            is_expired = expires_at < datetime.now()
            
            license_data['status'] = 'active'
            if is_expired:
                license_data['status'] = 'expired'
            elif not license_data['is_active']:
                license_data['status'] = 'revoked'
            
            # Форматируем HWID
            if license_data['activated_hwids']:
                license_data['activated_hwids'] = license_data['activated_hwids'].split(',')
            else:
                license_data['activated_hwids'] = []
            
            licenses.append(license_data)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(licenses),
            'licenses': licenses
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving licenses: {str(e)}'
        }), 500

@app.route('/api/license/<license_key>', methods=['GET'])
@log_request
def get_license_details(license_key):
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Получаем информацию о лицензии
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        license_data = c.fetchone()
        
        if not license_data:
            return jsonify({
                'success': False,
                'message': 'License not found'
            }), 404
        
        # Получаем активации для этой лицензии
        c.execute('''
            SELECT * FROM activations 
            WHERE license_key = ? 
            ORDER BY activation_time DESC
        ''', (license_key,))
        
        activations = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        license_dict = dict(license_data)
        
        # Определяем статус
        expires_at = datetime.fromisoformat(license_dict['expires_at'])
        is_expired = expires_at < datetime.now()
        
        license_dict['status'] = 'active'
        if is_expired:
            license_dict['status'] = 'expired'
        elif not license_dict['is_active']:
            license_dict['status'] = 'revoked'
        
        return jsonify({
            'success': True,
            'license': license_dict,
            'activations': activations,
            'activation_count': len(activations)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving license: {str(e)}'
        }), 500

@app.route('/api/stats', methods=['GET'])
@require_api_key
def get_stats():
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Общая статистика
        c.execute('SELECT COUNT(*) as total FROM licenses')
        total_licenses = c.fetchone()['total']
        
        c.execute('SELECT COUNT(*) as active FROM licenses WHERE is_active = 1 AND expires_at > ?', (datetime.now().isoformat(),))
        active_licenses = c.fetchone()['active']
        
        c.execute('SELECT COUNT(*) as expired FROM licenses WHERE expires_at <= ?', (datetime.now().isoformat(),))
        expired_licenses = c.fetchone()['expired']
        
        c.execute('SELECT COUNT(*) as total_activations FROM activations')
        total_activations = c.fetchone()['total_activations']
        
        c.execute('SELECT COUNT(DISTINCT hwid) as unique_devices FROM activations')
        unique_devices = c.fetchone()['unique_devices']
        
        # Статистика за последние 7 дней
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        c.execute('''
            SELECT 
                date,
                licenses_generated,
                licenses_activated,
                unique_hwids
            FROM stats 
            WHERE date >= ?
            ORDER BY date DESC
            LIMIT 7
        ''', (week_ago,))
        
        weekly_stats = [dict(row) for row in c.fetchall()]
        
        # Самые активные лицензии
        c.execute('''
            SELECT 
                l.license_key,
                COUNT(a.id) as activation_count,
                l.created_at,
                l.expires_at
            FROM licenses l
            LEFT JOIN activations a ON l.license_key = a.license_key
            GROUP BY l.license_key
            ORDER BY activation_count DESC
            LIMIT 10
        ''')
        
        top_licenses = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'overall': {
                'total_licenses': total_licenses,
                'active_licenses': active_licenses,
                'expired_licenses': expired_licenses,
                'total_activations': total_activations,
                'unique_devices': unique_devices
            },
            'weekly_stats': weekly_stats,
            'top_licenses': top_licenses,
            'server_time': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving stats: {str(e)}'
        }), 500

@app.route('/api/revoke/<license_key>', methods=['POST'])
@require_api_key
def revoke_license(license_key):
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Проверяем существование лицензии
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        if not c.fetchone():
            return jsonify({
                'success': False,
                'message': 'License not found'
            }), 404
        
        # Отзываем лицензию
        c.execute('UPDATE licenses SET is_active = 0 WHERE license_key = ?', (license_key,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'License {license_key} has been revoked'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error revoking license: {str(e)}'
        }), 500

@app.route('/api/extend/<license_key>', methods=['POST'])
@require_api_key
def extend_license(license_key):
    try:
        data = request.json or {}
        days = int(data.get('days', 30))
        
        if days <= 0:
            return jsonify({
                'success': False,
                'message': 'Days must be positive'
            }), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаем текущую лицензию
        c.execute('SELECT expires_at FROM licenses WHERE license_key = ?', (license_key,))
        row = c.fetchone()
        
        if not row:
            return jsonify({
                'success': False,
                'message': 'License not found'
            }), 404
        
        # Продлеваем срок
        current_expiry = datetime.fromisoformat(row['expires_at'])
        new_expiry = current_expiry + timedelta(days=days)
        
        c.execute('''
            UPDATE licenses 
            SET expires_at = ?, is_active = 1 
            WHERE license_key = ?
        ''', (new_expiry.isoformat(), license_key))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'License extended by {days} days',
            'new_expiry': new_expiry.isoformat(),
            'license_key': license_key
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error extending license: {str(e)}'
        }), 500

@app.route('/api/search', methods=['GET'])
@require_api_key
def search_licenses():
    try:
        query = request.args.get('q', '')
        if not query or len(query) < 3:
            return jsonify({
                'success': False,
                'message': 'Search query must be at least 3 characters'
            }), 400
        
        conn = get_db()
        c = conn.cursor()
        
        search_pattern = f'%{query}%'
        
        c.execute('''
            SELECT l.*, COUNT(a.id) as activation_count
            FROM licenses l
            LEFT JOIN activations a ON l.license_key = a.license_key
            WHERE l.license_key LIKE ? 
               OR l.notes LIKE ? 
               OR l.created_by LIKE ?
               OR EXISTS (
                   SELECT 1 FROM activations a2 
                   WHERE a2.license_key = l.license_key 
                   AND a2.hwid LIKE ?
               )
            GROUP BY l.id
            ORDER BY l.created_at DESC
        ''', (search_pattern, search_pattern, search_pattern, search_pattern))
        
        results = [dict(row) for row in c.fetchall()]
        conn.close()
        
        return jsonify({
            'success': True,
            'query': query,
            'count': len(results),
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Search error: {str(e)}'
        }), 500

@app.route('/api/batch/generate', methods=['POST'])
@require_api_key
def batch_generate():
    try:
        data = request.json or {}
        count = int(data.get('count', 10))
        days_valid = int(data.get('days_valid', 30))
        max_activations = int(data.get('max_activations', 1))
        notes = data.get('notes', '')
        created_by = data.get('created_by', 'batch_generator')
        
        if count <= 0 or count > 1000:
            return jsonify({
                'success': False,
                'message': 'Count must be between 1 and 1000'
            }), 400
        
        generated_keys = []
        
        for i in range(count):
            license_key = generate_license_key()
            license_id = str(uuid.uuid4())
            created_at = datetime.now()
            expires_at = created_at + timedelta(days=days_valid)
            
            conn = get_db()
            c = conn.cursor()
            
            c.execute('''
                INSERT INTO licenses (id, license_key, created_at, expires_at, max_activations, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (license_id, license_key, created_at, expires_at, max_activations, notes, created_by))
            
            conn.commit()
            conn.close()
            
            generated_keys.append({
                'license_key': license_key,
                'license_id': license_id,
                'expires_at': expires_at.isoformat()
            })
            
            # Обновляем статистику
            update_stats('generate')
        
        return jsonify({
            'success': True,
            'message': f'Successfully generated {count} license keys',
            'count': count,
            'keys': generated_keys
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Batch generation error: {str(e)}'
        }), 500

# Обработчик ошибок
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': 'Endpoint not found',
        'error': str(error)
    }), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({
        'success': False,
        'message': 'Internal server error',
        'error': str(error)
    }), 500

# Запуск приложения
if __name__ == '__main__':
    # Инициализация базы данных
    init_db()
    print("Database initialized successfully")
    
    # Проверка переменных окружения
    if not ADMIN_API_KEY or ADMIN_API_KEY == 'admin_key_123':
        print("WARNING: Using default ADMIN_API_KEY. Change this in production!")
    
    if not SERVER_SECRET or SERVER_SECRET == 'secret_key_456':
        print("WARNING: Using default SERVER_SECRET. Change this in production!")
    
    print(f"Server starting on port {os.environ.get('PORT', 5000)}")
    print(f"Admin API Key: {ADMIN_API_KEY[:10]}...")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'False').lower() == 'true')
