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

# Конфигурация - ВАЖНО ДЛЯ RENDER.COM!
ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'BYDSQ123')
SERVER_SECRET = os.environ.get('SERVER_SECRET', 'BYDSQ123')

# На Render.com используем путь в /tmp для SQLite
if os.environ.get('RENDER'):
    DATABASE_URL = '/tmp/licenses.db'  # Render.com позволяет писать в /tmp
else:
    DATABASE_URL = 'licenses.db'

# Хранилище в памяти для тестирования (резервный вариант)
in_memory_licenses = {}
in_memory_activations = []

# Инициализация базы данных на Render.com
def init_db():
    """Инициализирует базу данных на Render.com"""
    try:
        print(f"[INIT] Initializing database at: {DATABASE_URL}")
        print(f"[INIT] Render.com environment: {'YES' if os.environ.get('RENDER') else 'NO'}")
        
        # Создаем директорию если нужно
        db_dir = os.path.dirname(DATABASE_URL)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False, timeout=30)
        c = conn.cursor()
        
        # Проверяем существование таблицы licenses
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='licenses'")
        table_exists = c.fetchone()
        
        if not table_exists:
            print("[INIT] Creating database tables...")
            
            # Таблица лицензий
            c.execute('''
                CREATE TABLE licenses (
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
                CREATE TABLE activations (
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
            
            # Индексы для производительности
            c.execute('CREATE INDEX idx_license_key ON licenses(license_key)')
            c.execute('CREATE INDEX idx_activations_key ON activations(license_key)')
            c.execute('CREATE INDEX idx_activations_hwid ON activations(hwid)')
            
            # Создаем тестовую лицензию
            create_test_license(conn)
            
            conn.commit()
            print("[INIT] Database tables created successfully")
        else:
            print("[INIT] Database tables already exist")
            c.execute("SELECT COUNT(*) as count FROM licenses")
            count = c.fetchone()[0]
            print(f"[INIT] Existing licenses in database: {count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERROR] Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Попробуем использовать память как резерв
        print("[WARNING] Using in-memory storage as fallback")
        create_test_license_in_memory()
        return False

def create_test_license(conn=None):
    """Создает тестовую лицензию"""
    try:
        if conn is None:
            conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
        
        c = conn.cursor()
        
        # Проверяем, есть ли уже тестовая лицензия
        c.execute("SELECT * FROM licenses WHERE license_key LIKE 'TEST-%'")
        if c.fetchone():
            print("[INIT] Test license already exists")
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
            999,
            "Test license for debugging",
            "system"
        ))
        
        conn.commit()
        print(f"[INIT] Created test license: {test_key}")
        
    except Exception as e:
        print(f"[WARNING] Could not create test license: {e}")

def create_test_license_in_memory():
    """Создает тестовую лицензию в памяти"""
    test_key = "TEST-SNOS-0000-0000-0000-0000-0001"
    license_id = str(uuid.uuid4())
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=365)
    
    in_memory_licenses[test_key] = {
        'id': license_id,
        'license_key': test_key,
        'created_at': created_at.isoformat(),
        'expires_at': expires_at.isoformat(),
        'max_activations': 999,
        'current_activations': 0,
        'is_active': 1,
        'notes': "Test license in memory",
        'created_by': 'system',
        'source': 'memory'
    }
    
    print(f"[INIT] Created test license in memory: {test_key}")

def get_db():
    """Получает соединение с базой данных"""
    try:
        conn = sqlite3.connect(DATABASE_URL, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        
        # Проверяем, существуют ли таблицы
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='licenses'")
        if not c.fetchone():
            # Таблиц нет, создаем их
            init_db()
        
        return conn
    except Exception as e:
        print(f"[WARNING] Database connection error: {e}")
        print("[WARNING] Using in-memory storage")
        return None

# Простая проверка API ключа для демонстрации
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Для тестирования принимаем любой ключ
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({
                'success': False,
                'message': 'API key is required',
                'error_code': 'MISSING_API_KEY'
            }), 401
        
        # Принимаем ключ из генератора
        if api_key != ADMIN_API_KEY:
            print(f"[WARNING] Invalid API key received: {api_key[:10]}...")
            # Все равно продолжаем для тестирования
        
        return f(*args, **kwargs)
    return decorated_function

# Генерация ключа
def generate_license_key():
    """Генерирует уникальный лицензионный ключ"""
    key_base = hashlib.sha256(
        f"{uuid.uuid4()}{SERVER_SECRET}{datetime.now().timestamp()}".encode()
    ).hexdigest().upper()
    return f"SNOS-{key_base[:4]}-{key_base[4:8]}-{key_base[8:12]}-{key_base[12:16]}-{key_base[16:20]}"

# Простые API эндпоинты
@app.route('/')
def index():
    return jsonify({
        'service': 'Snos Tool License Server',
        'version': '2.0.0',
        'status': 'online',
        'database': 'sqlite' if os.path.exists(DATABASE_URL) else 'in-memory',
        'test_license': 'TEST-SNOS-0000-0000-0000-0000-0001',
        'endpoints': {
            'GET /api/test': 'Test connection',
            'POST /api/generate': 'Generate license (X-API-Key: BYDSQ123)',
            'POST /api/activate': 'Activate license',
            'POST /api/validate': 'Validate license'
        }
    })

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({
        'success': True,
        'message': 'Server is online',
        'timestamp': datetime.now().isoformat(),
        'database': 'available' if os.path.exists(DATABASE_URL) else 'in-memory'
    })

@app.route('/api/generate', methods=['POST'])
@require_api_key
def generate_license_endpoint():
    try:
        data = request.json or {}
        
        days_valid = int(data.get('days_valid', 30))
        max_activations = int(data.get('max_activations', 1))
        notes = data.get('notes', '')
        created_by = data.get('created_by', 'admin_panel')
        
        if days_valid <= 0 or max_activations <= 0:
            return jsonify({
                'success': False,
                'message': 'Invalid parameters'
            }), 400
        
        # Генерируем ключ
        license_key = generate_license_key()
        license_id = str(uuid.uuid4())
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=days_valid)
        
        print(f"[GENERATE] Creating license: {license_key}")
        
        # Пробуем сохранить в базу данных
        conn = get_db()
        if conn:
            try:
                c = conn.cursor()
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
                print(f"[GENERATE] Saved to database: {license_key}")
            except Exception as e:
                print(f"[WARNING] Database save failed: {e}")
                # Сохраняем в память
                in_memory_licenses[license_key] = {
                    'id': license_id,
                    'license_key': license_key,
                    'created_at': created_at.isoformat(),
                    'expires_at': expires_at.isoformat(),
                    'max_activations': max_activations,
                    'current_activations': 0,
                    'is_active': 1,
                    'notes': notes,
                    'created_by': created_by,
                    'source': 'memory'
                }
                print(f"[GENERATE] Saved to memory: {license_key}")
        else:
            # Сохраняем в память
            in_memory_licenses[license_key] = {
                'id': license_id,
                'license_key': license_key,
                'created_at': created_at.isoformat(),
                'expires_at': expires_at.isoformat(),
                'max_activations': max_activations,
                'current_activations': 0,
                'is_active': 1,
                'notes': notes,
                'created_by': created_by,
                'source': 'memory'
            }
            print(f"[GENERATE] Saved to memory: {license_key}")
        
        return jsonify({
            'success': True,
            'license_key': license_key,
            'license_id': license_id,
            'created_at': created_at.isoformat(),
            'expires_at': expires_at.isoformat(),
            'max_activations': max_activations,
            'message': f'License generated successfully'
        })
        
    except Exception as e:
        print(f"[ERROR] Generation error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/api/activate', methods=['POST'])
def activate_license():
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        print(f"[ACTIVATE] Request: key={license_key}, hwid={hwid}")
        
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
        
        # Ищем лицензию в базе данных
        conn = get_db()
        license_data = None
        
        if conn:
            try:
                c = conn.cursor()
                c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
                row = c.fetchone()
                if row:
                    license_data = dict(row)
                conn.close()
            except Exception as e:
                print(f"[WARNING] Database query failed: {e}")
                conn.close()
        
        # Если не нашли в базе, ищем в памяти
        if not license_data and license_key in in_memory_licenses:
            license_data = in_memory_licenses[license_key]
        
        if not license_data:
            # Проверяем тестовую лицензию
            if license_key == "TEST-SNOS-0000-0000-0000-0000-0001":
                license_data = {
                    'license_key': license_key,
                    'expires_at': (datetime.now() + timedelta(days=365)).isoformat(),
                    'max_activations': 999,
                    'current_activations': 0,
                    'is_active': 1
                }
            else:
                return jsonify({
                    'success': False,
                    'message': 'License not found'
                }), 404
        
        # Проверяем активна ли лицензия
        if not license_data.get('is_active', 1):
            return jsonify({
                'success': False,
                'message': 'License has been revoked'
            }), 400
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
        if expires_at < datetime.now():
            return jsonify({
                'success': False,
                'message': 'License has expired'
            }), 400
        
        # Активируем лицензию
        activation_time = datetime.now()
        
        # Сохраняем активацию
        activation = {
            'license_key': license_key,
            'hwid': hwid,
            'activation_time': activation_time.isoformat(),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'Unknown')
        }
        in_memory_activations.append(activation)
        
        print(f"[ACTIVATE] License activated: {license_key}")
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully',
            'license_key': license_key,
            'hwid': hwid,
            'activation_time': activation_time.isoformat(),
            'expires_at': license_data['expires_at']
        })
        
    except Exception as e:
        print(f"[ERROR] Activation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/api/validate', methods=['POST'])
def validate_license():
    try:
        data = request.json or {}
        
        license_key = data.get('license_key', '').strip()
        hwid = data.get('hwid', '').strip()
        
        print(f"[VALIDATE] Request: key={license_key}, hwid={hwid}")
        
        if not license_key:
            return jsonify({
                'valid': False,
                'message': 'License key is required'
            }), 400
        
        # Ищем лицензию
        conn = get_db()
        license_data = None
        
        if conn:
            try:
                c = conn.cursor()
                c.execute('SELECT * FROM licenses WHERE license_key = ?', (license_key,))
                row = c.fetchone()
                if row:
                    license_data = dict(row)
                conn.close()
            except Exception as e:
                print(f"[WARNING] Database query failed: {e}")
                conn.close()
        
        # Если не нашли в базе, ищем в памяти
        if not license_data and license_key in in_memory_licenses:
            license_data = in_memory_licenses[license_key]
        
        if not license_data:
            # Проверяем тестовую лицензию
            if license_key == "TEST-SNOS-0000-0000-0000-0000-0001":
                license_data = {
                    'license_key': license_key,
                    'expires_at': (datetime.now() + timedelta(days=365)).isoformat(),
                    'max_activations': 999,
                    'current_activations': 0,
                    'is_active': 1
                }
            else:
                return jsonify({
                    'valid': False,
                    'message': 'License not found'
                })
        
        # Проверяем активна ли лицензия
        if not license_data.get('is_active', 1):
            return jsonify({
                'valid': False,
                'message': 'License has been revoked'
            })
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(license_data['expires_at'].replace('Z', '+00:00'))
        if expires_at < datetime.now():
            return jsonify({
                'valid': False,
                'message': 'License has expired'
            })
        
        return jsonify({
            'valid': True,
            'message': 'License is valid',
            'license_key': license_key,
            'expires_at': license_data['expires_at']
        })
        
    except Exception as e:
        print(f"[ERROR] Validation error: {e}")
        return jsonify({
            'valid': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/api/licenses', methods=['GET'])
def get_licenses():
    """Возвращает все лицензии (для админа)"""
    try:
        licenses_list = []
        
        # Получаем из базы данных
        conn = get_db()
        if conn:
            try:
                c = conn.cursor()
                c.execute('SELECT * FROM licenses')
                for row in c.fetchall():
                    licenses_list.append(dict(row))
                conn.close()
            except Exception as e:
                print(f"[WARNING] Database query failed: {e}")
                conn.close()
        
        # Добавляем из памяти
        for license_key, license_data in in_memory_licenses.items():
            licenses_list.append(license_data)
        
        return jsonify({
            'success': True,
            'count': len(licenses_list),
            'licenses': licenses_list
        })
        
    except Exception as e:
        print(f"[ERROR] Get licenses error: {e}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

# Инициализация при запуске
if __name__ == '__main__':
    print("=" * 60)
    print("Snos Tool License Server v2.0.0")
    print("=" * 60)
    print(f"Environment: {'Render.com' if os.environ.get('RENDER') else 'Local'}")
    print(f"Database path: {DATABASE_URL}")
    print(f"Admin API Key: {ADMIN_API_KEY}")
    print("-" * 60)
    
    # Инициализируем базу данных
    init_db()
    
    # Проверяем доступность
    if os.path.exists(DATABASE_URL):
        print(f"✓ Database file exists: {os.path.getsize(DATABASE_URL)} bytes")
    else:
        print("⚠ Using in-memory storage (database file not writable)")
    
    print("✓ Server ready")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
