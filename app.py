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
    """Инициализирует базу данных и создает таблицы если их нет"""
    try:
        print(f"[INIT] Creating database at: {DATABASE_URL}")
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
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
        
        # Создаем индекс для быстрого поиска
        c.execute('CREATE INDEX IF NOT EXISTS idx_license_key ON licenses(license_key)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_activations ON activations(license_key, hwid)')
        
        conn.commit()
        conn.close()
        print("[INIT] Database tables created successfully")
        
        # Создаем тестовую лицензию для проверки
        create_test_license()
        
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        import traceback
        traceback.print_exc()

def create_test_license():
    """Создает тестовую лицензию для проверки"""
    try:
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
        c = conn.cursor()
        
        # Проверяем, есть ли уже тестовая лицензия
        c.execute('SELECT * FROM licenses WHERE license_key LIKE ?', ('TEST-%',))
        if c.fetchone():
            print("[INIT] Test license already exists")
            conn.close()
            return
        
        # Создаем тестовую лицензию
        test_key = "TEST-SNOS-0000-0000-0000-0000-0001"
        license_id = str(uuid.uuid4())
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=365)
        
        c.execute('''
            INSERT INTO licenses (id, license_key, created_at, expires_at, max_activations, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            license_id,
            test_key,
            created_at.isoformat(),
            expires_at.isoformat(),
            999,  # Много активаций для теста
            "Test license for debugging",
            "system"
        ))
        
        conn.commit()
        conn.close()
        print(f"[INIT] Created test license: {test_key}")
        
    except Exception as e:
        print(f"[WARNING] Could not create test license: {e}")

def get_db():
    """Получает соединение с базой данных"""
    try:
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection error: {e}")
        raise

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
        user_agent = request.headers.get('User-Agent', 'Unknown')[:50]
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {method} {endpoint} - IP: {ip} - UA: {user_agent}")
        return f(*args, **kwargs)
    return decorated_function

# Вспомогательные функции
def generate_license_key():
    """Генерирует уникальный лицензионный ключ"""
    key_base = hashlib.sha256(
        f"{uuid.uuid4()}{SERVER_SECRET}{datetime.now().timestamp()}".encode()
    ).hexdigest().upper()
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
            conn.commit()
        
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
                result = c.fetchone()
                unique_count = result['unique_count'] if result else 0
                c.execute("UPDATE stats SET unique_hwids = ? WHERE date = ?", (unique_count, today))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WARNING] Stats update error: {e}")

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
            'POST /api/generate': 'Generate new license key (requires X-API-Key)',
            'POST /api/activate': 'Activate license',
            'POST /api/validate': 'Validate license',
            'GET /api/licenses': 'Get all licenses (requires X-API-Key)',
            'GET /api/stats': 'Get server statistics (requires X-API-Key)',
            'GET /api/license/<key>': 'Get license details'
        },
        'test_license': 'TEST-SNOS-0000-0000-0000-0000-0001'
    })

@app.route('/api/test', methods=['GET'])
@log_request
def test():
    return jsonify({
        'success': True,
        'message': 'Server is online and responding',
        'server_time': datetime.now().isoformat(),
        'server_version': '2.0.0',
        'database_status': 'connected' if os.path.exists(DATABASE_URL) else 'not_found'
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
        
        try:
            c.execute('''
                INSERT INTO licenses (id, license_key, created_at, expires_at, max_activations, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (license_id, license_key, created_at.isoformat(), expires_at.isoformat(), max_activations, notes, created_by))
            
            conn.commit()
            print(f"[GENERATE] New license created: {license_key}")
            
        except sqlite3.IntegrityError:
            # Если ключ уже существует (очень маловероятно), генерируем новый
            conn.rollback()
            license_key = generate_license_key()  # Генерируем другой ключ
            
            c.execute('''
                INSERT INTO licenses (id, license_key, created_at, expires_at, max_activations, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (license_id, license_key, created_at.isoformat(), expires_at.isoformat(), max_activations, notes, created_by))
            
            conn.commit()
            print(f"[GENERATE] Regenerated license due to conflict: {license_key}")
        
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
        print(f"[ERROR] Generation error: {e}")
        import traceback
        traceback.print_exc()
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
        
        print(f"[ACTIVATE] Request: key={license_key}, hwid={hwid}")
        
        if not license_key:
            return jsonify({
                'success': False,
                'message': 'License key is required',
                'error_code': 'MISSING_KEY'
            }), 400
        
        if not hwid:
            return jsonify({
                'success': False,
                'message': 'HWID is required',
                'error_code': 'MISSING_HWID'
            }), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Получаем информацию о лицензии
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        license_data = c.fetchone()
        
        if not license_data:
            conn.close()
            print(f"[ACTIVATE] License not found: {license_key}")
            return jsonify({
                'success': False,
                'message': 'License key not found in database',
                'error_code': 'LICENSE_NOT_FOUND'
            }), 404
        
        print(f"[ACTIVATE] License found: {dict(license_data)}")
        
        # Проверяем активна ли лицензия
        if not license_data['is_active']:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'License has been revoked',
                'error_code': 'LICENSE_REVOKED'
            }), 400
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
        if expires_at < datetime.now():
            conn.close()
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
            conn.close()
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
            conn.close()
            return jsonify({
                'success': True,
                'message': 'License already activated on this device',
                'already_activated': True,
                'activation_time': existing_activation['activation_time'],
                'expires_at': license_data['expires_at'],
                'license_key': license_key,
                'hwid': hwid
            })
        
        # Активируем лицензию
        activation_time = datetime.now()
        device_info = data.get('device_info', {})
        
        try:
            c.execute('''
                INSERT INTO activations (license_key, hwid, device_name, platform, activation_time, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                license_key,
                hwid,
                device_info.get('device_name', 'Unknown'),
                device_info.get('platform', 'Unknown'),
                activation_time.isoformat(),
                request.remote_addr,
                request.headers.get('User-Agent', 'Unknown')[:200]
            ))
            
            # Обновляем счетчик активаций
            c.execute('''
                UPDATE licenses 
                SET current_activations = current_activations + 1 
                WHERE license_key = ?
            ''', (license_key,))
            
            conn.commit()
            print(f"[ACTIVATE] License activated successfully: {license_key} for HWID: {hwid}")
            
        except Exception as e:
            conn.rollback()
            conn.close()
            print(f"[ERROR] Activation database error: {e}")
            return jsonify({
                'success': False,
                'message': f'Database error during activation: {str(e)}',
                'error_code': 'DATABASE_ERROR'
            }), 500
        
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
        print(f"[ERROR] Activation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}',
            'error_code': 'INTERNAL_ERROR'
        }), 500

@app.route('/api/validate', methods=['POST'])
@log_request
def validate_license():
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        print(f"[VALIDATE] Request: key={license_key}, hwid={hwid}")
        
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
            conn.close()
            return jsonify({
                'valid': False,
                'message': 'License key not found',
                'error_code': 'LICENSE_NOT_FOUND'
            })
        
        # Проверяем активна ли лицензия
        if not license_data['is_active']:
            conn.close()
            return jsonify({
                'valid': False,
                'message': 'License has been revoked',
                'error_code': 'LICENSE_REVOKED'
            })
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
        if expires_at < datetime.now():
            conn.close()
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
                conn.close()
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
        print(f"[ERROR] Validation error: {e}")
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
            
            # Статус лицензии
            expires_at = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
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
        print(f"[ERROR] Get licenses error: {e}")
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
        expires_at = datetime.fromisoformat(license_dict['expires_at'].replace('Z', '+00:00'))
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
        print(f"[ERROR] Get license details error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error retrieving license: {str(e)}'
        }), 500

@app.route('/api/stats', methods=['GET'])
@require_api_key
@log_request
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
            'server_time': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"[ERROR] Get stats error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error retrieving stats: {str(e)}'
        }), 500

@app.route('/api/revoke/<license_key>', methods=['POST'])
@require_api_key
@log_request
def revoke_license(license_key):
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Проверяем существование лицензии
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        if not c.fetchone():
            conn.close()
            return jsonify({
                'success': False,
                'message': 'License not found'
            }), 404
        
        # Отзываем лицензию
        c.execute('UPDATE licenses SET is_active = 0 WHERE license_key = ?', (license_key,))
        conn.commit()
        conn.close()
        
        print(f"[REVOKE] License revoked: {license_key}")
        
        return jsonify({
            'success': True,
            'message': f'License {license_key} has been revoked'
        })
        
    except Exception as e:
        print(f"[ERROR] Revoke error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error revoking license: {str(e)}'
        }), 500

@app.route('/api/extend/<license_key>', methods=['POST'])
@require_api_key
@log_request
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
            conn.close()
            return jsonify({
                'success': False,
                'message': 'License not found'
            }), 404
        
        # Продлеваем срок
        current_expiry = datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
        new_expiry = current_expiry + timedelta(days=days)
        
        c.execute('''
            UPDATE licenses 
            SET expires_at = ?, is_active = 1 
            WHERE license_key = ?
        ''', (new_expiry.isoformat(), license_key))
        
        conn.commit()
        conn.close()
        
        print(f"[EXTEND] License extended: {license_key} by {days} days")
        
        return jsonify({
            'success': True,
            'message': f'License extended by {days} days',
            'new_expiry': new_expiry.isoformat(),
            'license_key': license_key
        })
        
    except Exception as e:
        print(f"[ERROR] Extend error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error extending license: {str(e)}'
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

# Инициализация при запуске
def initialize_app():
    """Инициализирует приложение при запуске"""
    print("=" * 50)
    print("Snos Tool License Server v2.0.0")
    print("=" * 50)
    print(f"Database: {DATABASE_URL}")
    print(f"Admin API Key: {ADMIN_API_KEY[:10]}...")
    print(f"Server Secret: {SERVER_SECRET[:10]}...")
    print("-" * 50)
    
    # Инициализируем базу данных
    init_db()
    
    # Проверяем, существует ли файл базы данных
    if os.path.exists(DATABASE_URL):
        print(f"✓ Database file exists: {DATABASE_URL}")
        
        # Проверяем размер файла
        size = os.path.getsize(DATABASE_URL)
        print(f"✓ Database size: {size} bytes")
    else:
        print(f"✗ Database file NOT found: {DATABASE_URL}")
        print("Creating new database...")
        init_db()
    
    print("✓ Server initialization complete")
    print("=" * 50)

# Запуск приложения
if __name__ == '__main__':
    # Инициализируем приложение
    initialize_app()
    
    # Запускаем сервер
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print(f"Starting server on port {port} (debug={debug_mode})")
    print(f"Test endpoint: http://localhost:{port}/api/test")
    print(f"Test license: TEST-SNOS-0000-0000-0000-0000-0001")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
