from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
from datetime import datetime, timedelta
import hashlib
import json
import os

app = Flask(__name__)
CORS(app)

# In-memory database (в продакшене используйте реальную БД)
licenses_db = {}
activations_db = {}

ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY', 'admin_key_123')
SERVER_SECRET = os.environ.get('SERVER_SECRET', 'secret_key')

def require_api_key(func):
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != ADMIN_API_KEY:
            return jsonify({'success': False, 'message': 'Invalid API key'}), 401
        return func(*args, **kwargs)
    return wrapper

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({
        'status': 'ok',
        'server_time': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/generate_license', methods=['POST'])
@require_api_key
def generate_license():
    try:
        data = request.json
        days_valid = data.get('days_valid', 30)
        max_activations = data.get('max_activations', 1)
        
        # Генерация ключа
        license_id = str(uuid.uuid4())
        key_base = hashlib.md5(f"{license_id}{SERVER_SECRET}".encode()).hexdigest().upper()
        license_key = f"SNOS-{key_base[:4]}-{key_base[4:8]}-{key_base[8:12]}-{key_base[12:16]}-{key_base[16:20]}"
        
        # Данные лицензии
        created = datetime.now()
        expires = created + timedelta(days=days_valid)
        
        license_data = {
            'id': license_id,
            'license_key': license_key,
            'created': created.isoformat(),
            'expires': expires.isoformat(),
            'max_activations': max_activations,
            'activations': [],
            'is_active': True,
            'notes': data.get('notes', '')
        }
        
        licenses_db[license_key] = license_data
        
        return jsonify({
            'success': True,
            'license_key': license_key,
            'id': license_id,
            'created': created.isoformat(),
            'expires': expires.isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/activate', methods=['POST'])
def activate_license():
    try:
        data = request.json
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        if not license_key or not hwid:
            return jsonify({'success': False, 'message': 'Missing license key or HWID'}), 400
        
        # Проверяем лицензию
        license_data = licenses_db.get(license_key)
        if not license_data:
            return jsonify({'success': False, 'message': 'License not found'}), 404
        
        # Проверяем срок
        expires = datetime.fromisoformat(license_data['expires'])
        if expires < datetime.now():
            return jsonify({'success': False, 'message': 'License expired'}), 400
        
        # Проверяем количество активаций
        if len(license_data['activations']) >= license_data['max_activations']:
            return jsonify({'success': False, 'message': 'Maximum activations reached'}), 400
        
        # Проверяем, не активирована ли уже на этом HWID
        for activation in license_data['activations']:
            if activation['hwid'] == hwid:
                return jsonify({
                    'success': True,
                    'expiry': license_data['expires'],
                    'message': 'Already activated on this device'
                })
        
        # Активируем
        activation_data = {
            'hwid': hwid,
            'timestamp': datetime.now().isoformat(),
            'device_info': data.get('device_info', {})
        }
        license_data['activations'].append(activation_data)
        
        return jsonify({
            'success': True,
            'expiry': license_data['expires'],
            'message': 'License activated successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/validate', methods=['POST'])
def validate_license():
    try:
        data = request.json
        license_key = data.get('license_key')
        hwid = data.get('hwid')
        
        license_data = licenses_db.get(license_key)
        if not license_data:
            return jsonify({'valid': False, 'message': 'License not found'})
        
        # Проверяем срок
        expires = datetime.fromisoformat(license_data['expires'])
        if expires < datetime.now():
            return jsonify({'valid': False, 'message': 'License expired'})
        
        # Проверяем активацию
        activated = False
        for activation in license_data['activations']:
            if activation['hwid'] == hwid:
                activated = True
                break
        
        if not activated and license_data['max_activations'] > 0:
            return jsonify({'valid': False, 'message': 'License not activated on this device'})
        
        return jsonify({
            'valid': True,
            'expiry': license_data['expires'],
            'message': 'License is valid'
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)}), 500

@app.route('/api/licenses', methods=['GET'])
@require_api_key
def get_licenses():
    try:
        licenses_list = []
        for license_key, license_data in licenses_db.items():
            licenses_list.append({
                'id': license_data['id'],
                'license_key': license_key,
                'created': license_data['created'],
                'expires': license_data['expires'],
                'is_active': license_data['is_active'],
                'max_activations': license_data['max_activations'],
                'activations_count': len(license_data['activations'])
            })
        
        return jsonify({
            'success': True,
            'licenses': licenses_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
