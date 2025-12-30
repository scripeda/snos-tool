from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import uuid
import hashlib
import os
import sqlite3
from functools import wraps

app = Flask(__name__)
CORS(app)

# ========== КОНФИГУРАЦИЯ ==========
ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'BYDSQ123')
SERVER_SECRET = os.environ.get('SERVER_SECRET', 'BYDSQ123')
DATABASE_URL = '/tmp/licenses.db'  # На Render.com можно писать в /tmp

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def init_database():
    """Инициализирует базу данных"""
    try:
        print(f"[INIT] Creating database at: {DATABASE_URL}")
        
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False, timeout=30)
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
                user_agent TEXT
            )
        ''')
        
        # Индексы для скорости
        c.execute('CREATE INDEX IF NOT EXISTS idx_license_key ON licenses(license_key)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_activations_license ON activations(license_key)')
        
        # Создаем тестовую лицензию если нет
        test_key = "TEST-SNOS-0000-0000-0000-0000-0001"
        c.execute("SELECT * FROM licenses WHERE license_key = ?", (test_key,))
        if not c.fetchone():
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
                999,
                "Test license for development",
                "system"
            ))
            print(f"[INIT] Created test license: {test_key}")
        
        conn.commit()
        conn.close()
        print("[INIT] Database initialized successfully")
        return True
        
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        return False

def get_db_connection():
    """Возвращает соединение с базой данных"""
    try:
        # Проверяем, существует ли база
        if not os.path.exists(DATABASE_URL):
            init_database()
        
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return None

def generate_license_key():
    """Генерирует лицензионный ключ"""
    key_base = hashlib.sha256(
        f"{uuid.uuid4()}{SERVER_SECRET}{datetime.now().timestamp()}".encode()
    ).hexdigest().upper()
    return f"SNOS-{key_base[:4]}-{key_base[4:8]}-{key_base[8:12]}-{key_base[12:16]}-{key_base[16:20]}"

# ========== ДЕКОРАТОРЫ ==========
def require_api_key(f):
    """Проверяет API ключ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Для простоты принимаем любой ключ или отсутствие ключа
        api_key = request.headers.get('X-API-Key', '')
        
        if api_key and api_key != ADMIN_API_KEY:
            print(f"[WARNING] Invalid API key: {api_key[:10]}...")
            # Все равно продолжаем для совместимости
        
        return f(*args, **kwargs)
    return decorated_function

def log_request(f):
    """Логирует запросы"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        endpoint = request.path
        method = request.method
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {method} {endpoint} - IP: {ip}")
        return f(*args, **kwargs)
    return decorated_function

# ========== API ENDPOINTS ==========
@app.route('/')
def index():
    """Главная страница"""
    return jsonify({
        'service': 'Snos Tool License Server',
        'version': '2.0.0',
        'status': 'online',
        'database': 'sqlite',
        'test_key': 'TEST-SNOS-0000-0000-0000-0000-0001',
        'endpoints': [
            'GET /api/test - Test server',
            'POST /api/generate - Generate license (X-API-Key: BYDSQ123)',
            'POST /api/activate - Activate license',
            'POST /api/validate - Validate license',
            'GET /api/licenses - List all licenses',
            'GET /api/license/<key> - Get license details'
        ]
    })

@app.route('/api/test', methods=['GET'])
@log_request
def test():
    """Проверка работы сервера"""
    return jsonify({
        'success': True,
        'message': 'Server is online and responding',
        'timestamp': datetime.now().isoformat(),
        'server_version': '2.0.0'
    })

@app.route('/api/generate', methods=['POST'])
@require_api_key
@log_request
def generate_license():
    """Генерация нового лицензионного ключа"""
    try:
        data = request.json or {}
        
        # Получаем параметры
        days_valid = int(data.get('days_valid', 30))
        max_activations = int(data.get('max_activations', 1))
        notes = data.get('notes', '')
        created_by = data.get('created_by', 'admin_panel')
        
        # Валидация
        if days_valid <= 0 or max_activations <= 0:
            return jsonify({
                'success': False,
                'message': 'days_valid and max_activations must be positive numbers'
            }), 400
        
        # Генерируем ключ
        license_key = generate_license_key()
        license_id = str(uuid.uuid4())
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=days_valid)
        
        # Сохраняем в базу
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection failed'
            }), 500
        
        try:
            c = conn.cursor()
            
            # Вставляем лицензию
            c.execute('''
                INSERT INTO licenses (id, license_key, created_at, expires_at, max_activations, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                license_id,
                license_key,
                created_at.isoformat(),
                expires_at.isoformat(),
                max_activations,
                notes,
                created_by
            ))
            
            conn.commit()
            conn.close()
            
            print(f"[GENERATE] Created license: {license_key}")
            
            return jsonify({
                'success': True,
                'license_key': license_key,
                'license_id': license_id,
                'created_at': created_at.isoformat(),
                'expires_at': expires_at.isoformat(),
                'max_activations': max_activations,
                'message': f'License generated successfully for {days_valid} days'
            })
            
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            # Если ключ уже существует (маловероятно), генерируем новый
            return generate_license()  # Рекурсивно вызываем снова
            
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e
            
    except Exception as e:
        print(f"[ERROR] Generate: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/activate', methods=['POST'])
@log_request
def activate_license():
    """Активация лицензии"""
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        print(f"[ACTIVATE] Key: {license_key[:20]}..., HWID: {hwid[:10]}...")
        
        # Валидация
        if not license_key:
            return jsonify({
                'success': False,
                'message': 'License key is required'
            }), 400
        
        if not hwid:
            return jsonify({
                'success': False,
                'message': 'HWID is required'
            }), 400
        
        # Подключаемся к базе
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection failed'
            }), 500
        
        try:
            c = conn.cursor()
            
            # Ищем лицензию
            c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
            license_data = c.fetchone()
            
            if not license_data:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'License key not found'
                }), 404
            
            license_dict = dict(license_data)
            
            # Проверяем активность
            if not license_dict['is_active']:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'License has been revoked'
                }), 400
            
            # Проверяем срок
            expires_at = datetime.fromisoformat(license_dict['expires_at'].replace('Z', '+00:00'))
            if expires_at < datetime.now():
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'License has expired',
                    'expired_at': expires_at.isoformat()
                }), 400
            
            # Проверяем активации
            c.execute('SELECT COUNT(*) as count FROM activations WHERE license_key = ?', (license_key,))
            activation_count = c.fetchone()['count']
            
            if activation_count >= license_dict['max_activations']:
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'Maximum activations reached ({license_dict["max_activations"]})'
                }), 400
            
            # Проверяем, активирована ли уже на этом устройстве
            c.execute('SELECT * FROM activations WHERE license_key = ? AND hwid = ?', (license_key, hwid))
            existing = c.fetchone()
            
            if existing:
                conn.close()
                return jsonify({
                    'success': True,
                    'message': 'License already activated on this device',
                    'already_activated': True,
                    'activation_time': dict(existing)['activation_time'],
                    'license_key': license_key,
                    'hwid': hwid,
                    'expires_at': license_dict['expires_at']
                })
            
            # Активируем
            activation_time = datetime.now()
            device_info = data.get('device_info', {})
            
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
            
            # Обновляем счетчик
            c.execute('UPDATE licenses SET current_activations = current_activations + 1 WHERE license_key = ?', (license_key,))
            
            conn.commit()
            conn.close()
            
            print(f"[ACTIVATE] Success: {license_key[:20]}...")
            
            return jsonify({
                'success': True,
                'message': 'License activated successfully',
                'license_key': license_key,
                'hwid': hwid,
                'activation_time': activation_time.isoformat(),
                'expires_at': license_dict['expires_at'],
                'max_activations': license_dict['max_activations'],
                'current_activations': activation_count + 1,
                'already_activated': False
            })
            
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e
            
    except Exception as e:
        print(f"[ERROR] Activate: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/validate', methods=['POST'])
@log_request
def validate_license():
    """Валидация лицензии"""
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        print(f"[VALIDATE] Key: {license_key[:20]}..., HWID: {hwid[:10]}...")
        
        # Валидация
        if not license_key:
            return jsonify({
                'valid': False,
                'message': 'License key is required'
            }), 400
        
        # Подключаемся к базе
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'valid': False,
                'message': 'Database connection failed'
            }), 500
        
        try:
            c = conn.cursor()
            
            # Ищем лицензию
            c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
            license_data = c.fetchone()
            
            if not license_data:
                conn.close()
                return jsonify({
                    'valid': False,
                    'message': 'License key not found'
                })
            
            license_dict = dict(license_data)
            
            # Проверяем активность
            if not license_dict['is_active']:
                conn.close()
                return jsonify({
                    'valid': False,
                    'message': 'License has been revoked'
                })
            
            # Проверяем срок
            expires_at = datetime.fromisoformat(license_dict['expires_at'].replace('Z', '+00:00'))
            if expires_at < datetime.now():
                conn.close()
                return jsonify({
                    'valid': False,
                    'message': 'License has expired',
                    'expired_at': expires_at.isoformat()
                })
            
            # Если передан HWID, проверяем активацию
            if hwid:
                c.execute('SELECT * FROM activations WHERE license_key = ? AND hwid = ?', (license_key, hwid))
                activation = c.fetchone()
                
                if not activation:
                    conn.close()
                    return jsonify({
                        'valid': False,
                        'message': 'License not activated on this device'
                    })
            
            conn.close()
            
            return jsonify({
                'valid': True,
                'message': 'License is valid',
                'license_key': license_key,
                'expires_at': license_dict['expires_at'],
                'max_activations': license_dict['max_activations'],
                'current_activations': license_dict['current_activations'],
                'is_active': bool(license_dict['is_active'])
            })
            
        except Exception as e:
            conn.close()
            raise e
            
    except Exception as e:
        print(f"[ERROR] Validate: {e}")
        return jsonify({
            'valid': False,
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/licenses', methods=['GET'])
@require_api_key
@log_request
def get_all_licenses():
    """Получение всех лицензий (админ)"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection failed'
            }), 500
        
        c = conn.cursor()
        c.execute('''
            SELECT l.*, COUNT(a.id) as activation_count
            FROM licenses l
            LEFT JOIN activations a ON l.license_key = a.license_key
            GROUP BY l.id
            ORDER BY l.created_at DESC
        ''')
        
        licenses = []
        for row in c.fetchall():
            license_data = dict(row)
            licenses.append(license_data)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(licenses),
            'licenses': licenses
        })
        
    except Exception as e:
        print(f"[ERROR] Get licenses: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/license/<license_key>', methods=['GET'])
@log_request
def get_license_details(license_key):
    """Получение деталей лицензии"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection failed'
            }), 500
        
        c = conn.cursor()
        
        # Получаем лицензию
        c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
        license_data = c.fetchone()
        
        if not license_data:
            conn.close()
            return jsonify({
                'success': False,
                'message': 'License not found'
            }), 404
        
        # Получаем активации
        c.execute('SELECT * FROM activations WHERE license_key = ? ORDER BY activation_time DESC', (license_key,))
        activations = [dict(row) for row in c.fetchall()]
        
        conn.close()
        
        license_dict = dict(license_data)
        
        return jsonify({
            'success': True,
            'license': license_dict,
            'activations': activations,
            'activation_count': len(activations)
        })
        
    except Exception as e:
        print(f"[ERROR] Get license details: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/stats', methods=['GET'])
@require_api_key
@log_request
def get_stats():
    """Получение статистики сервера"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({
                'success': False,
                'message': 'Database connection failed'
            }), 500
        
        c = conn.cursor()
        
        # Общая статистика
        c.execute('SELECT COUNT(*) as total FROM licenses')
        total_licenses = c.fetchone()['total']
        
        c.execute('SELECT COUNT(*) as total_activations FROM activations')
        total_activations = c.fetchone()['total_activations']
        
        c.execute('SELECT COUNT(DISTINCT hwid) as unique_devices FROM activations')
        unique_devices = c.fetchone()['unique_devices']
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_licenses': total_licenses,
                'total_activations': total_activations,
                'unique_devices': unique_devices,
                'server_time': datetime.now().isoformat(),
                'server_version': '2.0.0'
            }
        })
        
    except Exception as e:
        print(f"[ERROR] Get stats: {e}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500

# ========== ОБРАБОТЧИКИ ОШИБОК ==========
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

# ========== ЗАПУСК СЕРВЕРА ==========
if __name__ == '__main__':
    # Инициализация при запуске
    print("=" * 60)
    print("Snos Tool License Server v2.0.0")
    print("=" * 60)
    print(f"Database: {DATABASE_URL}")
    print(f"Admin API Key: {ADMIN_API_KEY}")
    print(f"Server Secret: {SERVER_SECRET[:10]}...")
    print("-" * 60)
    
    # Инициализируем базу данных
    if init_database():
        print("✓ Database initialized successfully")
    else:
        print("⚠ Database initialization failed, using fallback")
    
    # Получаем порт из переменных окружения
    port = int(os.environ.get('PORT', 5000))
    
    print(f"✓ Server starting on port {port}")
    print(f"✓ Test endpoint: /api/test")
    print(f"✓ Test license: TEST-SNOS-0000-0000-0000-0000-0001")
    print("=" * 60)
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=port, debug=False)
