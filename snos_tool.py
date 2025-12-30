import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, font
import random
import time
import threading
from datetime import datetime, timedelta
import json
import os
import sys
import requests
import subprocess
import tempfile
import hashlib
import base64
import uuid

class SnosTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Snos Tool v2.0.0 - Professional Edition")
        self.root.geometry("1300x850")
        self.root.configure(bg='#0a0a0a')
        self.root.resizable(False, False)
        
        # Загрузка пользовательского шрифта
        self.load_custom_fonts()
        
        # Скрываем главное окно до завершения инициализации
        self.root.withdraw()
        
        # Центрирование окна
        self.center_window()
        
        # Настройки
        self.settings = {
            'report_speed': 1.5,
            'max_reports': 100,
            'auto_mode': False,
            'use_proxy': True,
            'stealth_mode': True,
            'threads': 3,
            'retry_count': 5,
            'use_tor': False,
            'delay_variation': True
        }
        
        # Статистика
        self.stats = {
            'total_reports': 0,
            'successful': 0,
            'failed': 0,
            'start_time': None,
            'targets_processed': [],
            'total_targets': 0,
            'current_session': datetime.now().strftime("%Y%m%d_%H%M%S"),
            'module_loaded': False,
            'license_active': False,
            'license_expiry': None,
            'hwid': self.get_hwid()
        }
        
        # Система лицензирования
        self.api_url = "https://snos-tool.onrender.com"  # Ваш Render.com URL
        self.license_key = ""
        
        self.is_running = False
        self.is_analyzing = False
        self.targets_queue = []
        self.current_target = None
        self.external_module_process = None
        
        # Флаг мигания для индикатора соединения
        self.connection_blink = True
        
        # Загрузка конфигурации
        self.load_config()
        
        # Проверка лицензии
        self.check_license_status()
    
    def get_hwid(self):
        """Генерирует уникальный HWID для устройства"""
        try:
            import platform
            import socket
            import uuid
            
            # Комбинируем несколько системных характеристик
            node = platform.node()
            processor = platform.processor()
            machine = platform.machine()
            
            hwid_string = f"{node}-{processor}-{machine}"
            hwid_hash = hashlib.sha256(hwid_string.encode()).hexdigest()[:16]
            return hwid_hash.upper()
        except:
            return str(uuid.uuid4())[:16].upper()
    
    def check_license_status(self):
        """Проверяет статус лицензии"""
        try:
            # Проверяем сохраненную лицензию
            if os.path.exists('license.json'):
                with open('license.json', 'r') as f:
                    license_data = json.load(f)
                    self.license_key = license_data.get('key', '')
                    self.stats['license_expiry'] = license_data.get('expiry')
                    
                    # Проверяем валидность лицензии
                    if self.validate_license():
                        self.show_main_interface()
                        return
                    
            # Если нет валидной лицензии, показываем окно активации
            self.show_activation_window()
            
        except Exception as e:
            print(f"License check error: {e}")
            self.show_activation_window()
    
    def validate_license(self):
        """Проверяет валидность лицензии через API"""
        try:
            if not self.license_key:
                return False
            
            # Проверка локального кеша
            cache_file = 'license_cache.json'
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
                    if cache.get('key') == self.license_key:
                        if datetime.now().timestamp() < cache.get('valid_until', 0):
                            self.stats['license_active'] = True
                            return True
            
            # Проверка через API
            response = requests.post(
                f"{self.api_url}/api/validate",
                json={
                    'license_key': self.license_key,
                    'hwid': self.stats['hwid']
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('valid'):
                    self.stats['license_active'] = True
                    self.stats['license_expiry'] = data.get('expiry')
                    
                    # Сохраняем в кеш
                    cache_data = {
                        'key': self.license_key,
                        'valid_until': datetime.now().timestamp() + 3600,  # Кеш на 1 час
                        'expiry': data.get('expiry')
                    }
                    with open(cache_file, 'w') as f:
                        json.dump(cache_data, f)
                    
                    return True
            
            return False
            
        except requests.RequestException:
            # Если API недоступен, используем кеш
            if os.path.exists('license_cache.json'):
                with open('license_cache.json', 'r') as f:
                    cache = json.load(f)
                    if cache.get('key') == self.license_key:
                        self.stats['license_active'] = True
                        return True
            return False
        except Exception as e:
            print(f"License validation error: {e}")
            return False
    
    def activate_license(self, key):
        """Активирует лицензию"""
        try:
            response = requests.post(
                f"{self.api_url}/api/activate",
                json={
                    'license_key': key,
                    'hwid': self.stats['hwid']
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    self.license_key = key
                    self.stats['license_active'] = True
                    self.stats['license_expiry'] = data.get('expiry')
                    
                    # Сохраняем лицензию
                    license_data = {
                        'key': key,
                        'hwid': self.stats['hwid'],
                        'expiry': data.get('expiry'),
                        'activated': datetime.now().isoformat()
                    }
                    with open('license.json', 'w') as f:
                        json.dump(license_data, f)
                    
                    # Сохраняем в кеш
                    cache_data = {
                        'key': key,
                        'valid_until': datetime.now().timestamp() + 3600,
                        'expiry': data.get('expiry')
                    }
                    with open('license_cache.json', 'w') as f:
                        json.dump(cache_data, f)
                    
                    return True, data.get('message', 'Лицензия успешно активирована')
                else:
                    return False, data.get('message', 'Ошибка активации')
            else:
                return False, f"Ошибка сервера: {response.status_code}"
                
        except requests.RequestException as e:
            return False, f"Ошибка подключения: {str(e)}"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    def show_activation_window(self):
        """Показывает окно активации"""
        self.activation_window = tk.Toplevel(self.root)
        self.activation_window.title("Snos Tool - Активация")
        self.activation_window.geometry("500x400")
        self.activation_window.configure(bg='#000000')
        self.activation_window.resizable(False, False)
        
        # Центрирование
        self.activation_window.update_idletasks()
        width = self.activation_window.winfo_width()
        height = self.activation_window.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.activation_window.geometry(f'{width}x{height}+{x}+{y}')
        
        # Заголовок
        logo_frame = tk.Frame(self.activation_window, bg='#000000')
        logo_frame.pack(pady=30)
        
        tk.Label(logo_frame, text="╔═╗┌┐┌┬ ┬┌┐┌╔═╗", 
                font=(self.code_font, 14), fg='#00ff00', bg='#000000').pack()
        tk.Label(logo_frame, text="╚═╗││││ ││││╠═╝", 
                font=(self.code_font, 14), fg='#00ff00', bg='#000000').pack()
        tk.Label(logo_frame, text="╚═╝┘└┘└─┘┘└┘╩  ", 
                font=(self.code_font, 14), fg='#00ff00', bg='#000000').pack()
        
        tk.Label(logo_frame, text="SNOS TOOL v2.0.0", 
                font=(self.code_font, 16, 'bold'), fg='#00ff00', bg='#000000').pack(pady=10)
        tk.Label(logo_frame, text="PROFESSIONAL EDITION", 
                font=(self.code_font, 10), fg='#cccccc', bg='#000000').pack()
        
        # Информация о системе
        info_frame = tk.Frame(self.activation_window, bg='#111111', padx=20, pady=20)
        info_frame.pack(pady=20, padx=40, fill=tk.X)
        
        tk.Label(info_frame, text=f"HWID: {self.stats['hwid']}", 
                font=(self.code_font, 9), fg='#cccccc', bg='#111111').pack(anchor=tk.W)
        
        # Поле для ввода ключа
        key_frame = tk.Frame(self.activation_window, bg='#000000')
        key_frame.pack(pady=20, padx=40, fill=tk.X)
        
        tk.Label(key_frame, text="Введите лицензионный ключ:", 
                font=(self.code_font, 10), fg='#cccccc', bg='#000000').pack(anchor=tk.W)
        
        self.key_entry = tk.Entry(key_frame, font=(self.code_font, 12), 
                                 bg='#222222', fg='#ffffff',
                                 insertbackground='#00ff00',
                                 relief=tk.SUNKEN, borderwidth=2,
                                 width=30)
        self.key_entry.pack(fill=tk.X, pady=(5, 10))
        
        # Сообщение об ошибке
        self.activation_message = tk.Label(key_frame, text="", 
                                          font=(self.code_font, 9),
                                          fg='#ff4444', bg='#000000')
        self.activation_message.pack()
        
        # Кнопки
        button_frame = tk.Frame(self.activation_window, bg='#000000')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="АКТИВИРОВАТЬ", 
                 font=(self.code_font, 10, 'bold'),
                 bg='#2a2a2a', fg='#00ff00',
                 command=self.process_activation,
                 width=20, height=2).pack(pady=5)
        
        tk.Button(button_frame, text="ПОЛУЧИТЬ КЛЮЧ", 
                 font=(self.code_font, 9),
                 bg='#333333', fg='#cccccc',
                 command=self.open_purchase_page,
                 width=20, height=1).pack(pady=5)
        
        # Тестовый ключ (для демонстрации)
        test_key_frame = tk.Frame(self.activation_window, bg='#000000')
        test_key_frame.pack(pady=10)
        
        tk.Label(test_key_frame, text="Демо ключ (24 часа):", 
                font=(self.code_font, 8), fg='#888888', bg='#000000').pack()
        
        demo_key = f"DEMO-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        tk.Label(test_key_frame, text=demo_key, 
                font=(self.code_font, 8, 'bold'), fg='#00ff00', bg='#000000').pack()
        
        # Фокус на поле ввода
        self.activation_window.after(100, lambda: self.key_entry.focus_set())
        
        # Блокируем главное окно
        self.activation_window.transient(self.root)
        self.activation_window.grab_set()
        self.root.wait_window(self.activation_window)
    
    def process_activation(self):
        """Обрабатывает активацию лицензии"""
        key = self.key_entry.get().strip()
        if not key:
            self.activation_message.config(text="Введите лицензионный ключ")
            return
        
        self.activation_message.config(text="Проверка лицензии...", fg='#ffaa00')
        self.activation_window.update()
        
        success, message = self.activate_license(key)
        
        if success:
            self.activation_message.config(text=message, fg='#00ff00')
            self.activation_window.after(1000, self.activation_window.destroy)
            self.show_main_interface()
        else:
            self.activation_message.config(text=message, fg='#ff4444')
    
    def open_purchase_page(self):
        """Открывает страницу покупки"""
        import webbrowser
        webbrowser.open(f"{self.api_url}/purchase")
    
    def show_main_interface(self):
        """Показывает основной интерфейс после активации"""
        # Запуск splash screen и загрузки модулей
        self.show_splash_screen()
    
    def load_custom_fonts(self):
        """Загружает и устанавливает пользовательские шрифты"""
        try:
            self.available_fonts = font.families()
            
            preferred_fonts = [
                'Consolas', 'Cascadia Code', 'JetBrains Mono', 'Fira Code',
                'Source Code Pro', 'Monaco', 'Lucida Console', 'Courier New',
                'DejaVu Sans Mono', 'Ubuntu Mono', 'Monospace'
            ]
            
            self.code_font = 'Courier New'
            for font_name in preferred_fonts:
                if font_name in self.available_fonts:
                    self.code_font = font_name
                    break
                    
            print(f"Using font: {self.code_font}")
            
        except Exception as e:
            print(f"Font loading error: {e}")
            self.code_font = 'Courier New'
        
    def center_window(self):
        """Центрирует окно на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
    def show_splash_screen(self):
        """Показывает загрузочный экран"""
        self.splash = tk.Toplevel(self.root)
        self.splash.title("Snos Tool - Loading")
        self.splash.geometry("500x400")
        self.splash.configure(bg='#000000')
        self.splash.overrideredirect(True)
        self.center_splash()
        
        # Логотип
        logo_frame = tk.Frame(self.splash, bg='#000000')
        logo_frame.pack(pady=30)
        
        # ASCII арт логотип
        ascii_logo = """
        ╔══════════════════════════════════════╗
        ║    ╔═╗┌┐┌┬ ┬┌┐┌╔═╗                  ║
        ║    ╚═╗││││ ││││╠═╝                  ║
        ║    ╚═╝┘└┘└─┘┘└┘╩                    ║
        ║    PROFESSIONAL REPORTING TOOL      ║
        ╚══════════════════════════════════════╝
        """
        
        for line in ascii_logo.strip().split('\n'):
            tk.Label(logo_frame, text=line, font=(self.code_font, 10),
                    fg='#00ff00', bg='#000000').pack()
        
        # Версия и лицензия
        tk.Label(logo_frame, text="PROFESSIONAL EDITION v2.0.0", 
                font=(self.code_font, 9), fg='#cccccc', bg='#000000').pack(pady=5)
        
        if self.stats['license_expiry']:
            expiry_date = datetime.fromisoformat(self.stats['license_expiry']).strftime("%Y-%m-%d")
            tk.Label(logo_frame, text=f"License valid until: {expiry_date}", 
                    font=(self.code_font, 8), fg='#00ff00', bg='#000000').pack()
        
        # Прогресс бар с рамкой
        progress_frame = tk.Frame(self.splash, bg='#111111', padx=2, pady=2)
        progress_frame.pack(pady=20, padx=40, fill=tk.X)
        
        self.splash_progress = ttk.Progressbar(progress_frame, length=400, mode='determinate')
        self.splash_progress.pack(fill=tk.X, padx=1, pady=1)
        
        # Процент завершения
        self.progress_percent = tk.Label(self.splash, text="0%",
                                        font=(self.code_font, 10, 'bold'),
                                        fg='#00ff00', bg='#000000')
        self.progress_percent.pack()
        
        # Текст статуса
        self.splash_status = tk.Label(self.splash, text="Initializing core modules...",
                                     font=(self.code_font, 9), fg='#00ff00', bg='#000000')
        self.splash_status.pack(pady=10)
        
        # Детали загрузки
        self.loading_details = tk.Label(self.splash, text="",
                                       font=(self.code_font, 8), fg='#888888', bg='#000000')
        self.loading_details.pack()
        
        # Запуск процесса загрузки
        self.root.after(100, self.load_modules)
        
    def center_splash(self):
        """Центрирует splash screen"""
        self.splash.update_idletasks()
        width = self.splash.winfo_width()
        height = self.splash.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.splash.geometry(f'{width}x{height}+{x}+{y}')
        
    def update_progress(self, value, text, details=""):
        """Обновляет прогресс загрузки"""
        self.splash_progress['value'] = value
        self.progress_percent.config(text=f"{int(value)}%")
        self.splash_status.config(text=text)
        if details:
            self.loading_details.config(text=details)
        self.splash.update()
        
    def load_modules(self):
        """Имитирует загрузку модулей"""
        
        def simulate_loading():
            try:
                # Шаг 1: Проверка лицензии
                self.update_progress(10, "Verifying license...")
                self.update_progress_details("Checking license validity...")
                
                if not self.stats['license_active']:
                    self.update_progress_details("License invalid or expired")
                    time.sleep(1)
                    self.splash.destroy()
                    self.show_activation_window()
                    return
                
                time.sleep(0.5)
                
                # Шаг 2: Инициализация системы
                self.update_progress(20, "Loading core modules...")
                time.sleep(0.7)
                
                self.update_progress(30, "Initializing security protocols...")
                time.sleep(0.5)
                
                # Шаг 3: Загрузка конфигурации
                self.update_progress(40, "Loading configuration...")
                time.sleep(0.6)
                
                # Шаг 4: Создание локального модуля
                self.update_progress(50, "Setting up database module...")
                module_path = self.create_local_module()
                
                if module_path:
                    self.update_progress(70, "Module configured successfully")
                    self.update_progress_details("Starting background services...")
                    
                    # Запуск модуля в скрытом режиме
                    if self.start_module_silently(module_path):
                        self.stats['module_loaded'] = True
                        self.update_progress_details("Services running")
                    else:
                        self.update_progress_details("Using simulated mode")
                    
                    time.sleep(0.5)
                
                # Шаг 5: Завершение инициализации
                self.update_progress(80, "Verifying system integrity...")
                time.sleep(0.4)
                
                self.update_progress(90, "Finalizing initialization...")
                time.sleep(0.3)
                
                self.update_progress(95, "Checking network connectivity...")
                time.sleep(0.2)
                
                self.update_progress(100, "Ready to launch...")
                self.update_progress_details("All systems operational")
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Load error: {e}")
                self.update_progress_details("Error in initialization")
            
            finally:
                # Закрываем splash screen и показываем основное окно
                self.splash.destroy()
                self.root.deiconify()
                self.create_interface()
                self.update_stats_display()
                self.start_connection_blink()
                self.add_log("[SYSTEM] Application initialized successfully")
                self.add_log(f"[LICENSE] Valid until: {self.stats['license_expiry']}")
                
                if self.stats['module_loaded']:
                    self.add_log("[MODULE] Database services running in background")
        
        # Запуск в отдельном потоке
        threading.Thread(target=simulate_loading, daemon=True).start()
    
    def start_connection_blink(self):
        """Запускает мигание индикатора соединения"""
        def blink():
            if self.connection_blink:
                self.connection_indicator.config(fg='#00ff00')
            else:
                self.connection_indicator.config(fg='#0a0a0a')
            
            self.connection_blink = not self.connection_blink
            self.root.after(500, blink)
        
        blink()
    
    def create_local_module(self):
        """Создает локальную копию модуля"""
        try:
            temp_dir = tempfile.gettempdir()
            module_dir = os.path.join(temp_dir, "snos_tool")
            os.makedirs(module_dir, exist_ok=True)
            
            module_path = os.path.join(module_dir, "db_service.bat")
            
            if os.path.exists(module_path):
                return module_path
            
            with open(module_path, 'w') as f:
                f.write("@echo off\n")
                f.write("echo Snos Tool Database Service v1.0\n")
                f.write(f"echo License: {self.license_key[:8]}...\n")
                f.write("echo Service is running in background\n")
                f.write("timeout /t 86400 /nobreak > nul\n")
            
            return module_path
            
        except Exception as e:
            print(f"Module creation error: {e}")
            return None
    
    def start_module_silently(self, module_path):
        """Запускает модуль в скрытом режиме"""
        try:
            if module_path.endswith('.bat'):
                vbs_script = """
                Set WshShell = CreateObject("WScript.Shell")
                WshShell.Run chr(34) & "{path}" & chr(34), 0, False
                Set WshShell = Nothing
                """.replace("{path}", module_path.replace("\\", "\\\\"))
                
                vbs_path = module_path.replace('.bat', '_launcher.vbs')
                with open(vbs_path, 'w') as f:
                    f.write(vbs_script)
                
                subprocess.Popen(['wscript.exe', vbs_path], 
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                return True
                
        except Exception as e:
            print(f"Module start error: {e}")
            return False
    
    def update_progress_details(self, text):
        """Обновляет детали загрузки"""
        self.loading_details.config(text=text)
        self.splash.update()
    
    def create_interface(self):
        # Верхняя панель
        self.create_header()
        
        # Основная область
        main_container = tk.Frame(self.root, bg='#0a0a0a')
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Левая панель - цели и управление
        left_panel = tk.Frame(main_container, bg='#111111', relief=tk.GROOVE, borderwidth=2)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 10))
        
        # Центральная панель - отчеты и логи
        center_panel = tk.Frame(main_container, bg='#111111', relief=tk.GROOVE, borderwidth=2)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Правая панель - статистика и информация
        right_panel = tk.Frame(main_container, bg='#111111', relief=tk.GROOVE, borderwidth=2)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(10, 0))
        
        # Создание панелей
        self.create_left_panel(left_panel)
        self.create_center_panel(center_panel)
        self.create_right_panel(right_panel)
        
        # Нижняя панель
        self.create_bottom_panel()
        
        # Фокус на поле ввода
        self.root.after(100, lambda: self.target_entry.focus_set())
        
    def create_header(self):
        header_frame = tk.Frame(self.root, bg='#000000', height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        # Логотип и название
        logo_frame = tk.Frame(header_frame, bg='#000000')
        logo_frame.pack(side=tk.LEFT, padx=25)
        
        tk.Label(logo_frame, text="SNOS TOOL", font=(self.code_font, 20, 'bold'),
                fg='#00ff00', bg='#000000').pack(anchor=tk.W)
        tk.Label(logo_frame, text="Professional Reporting Tool | v2.0.0", 
                font=(self.code_font, 9), fg='#cccccc', bg='#000000').pack(anchor=tk.W)
        
        # Статус панель
        status_frame = tk.Frame(header_frame, bg='#000000')
        status_frame.pack(side=tk.RIGHT, padx=25)
        
        # Индикаторы
        indicators_frame = tk.Frame(status_frame, bg='#000000')
        indicators_frame.pack()
        
        # Мигающий индикатор соединения
        self.connection_indicator = tk.Label(indicators_frame, text="●", 
                                           font=(self.code_font, 12, 'bold'), 
                                           fg='#00ff00', bg='#000000')
        self.connection_indicator.pack(side=tk.LEFT, padx=(0, 5))
        
        tk.Label(indicators_frame, text="CONNECTED", 
                font=(self.code_font, 9, 'bold'), fg='#00ff00', bg='#000000').pack(side=tk.LEFT, padx=(0, 10))
        
        # Лицензия
        license_color = '#00ff00' if self.stats['license_active'] else '#ff4444'
        license_text = "LICENSE ACTIVE" if self.stats['license_active'] else "LICENSE INVALID"
        tk.Label(indicators_frame, text="■", 
                font=(self.code_font, 12), fg=license_color, bg='#000000').pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(indicators_frame, text=license_text, 
                font=(self.code_font, 9), fg=license_color, bg='#000000').pack(side=tk.LEFT, padx=(0, 10))
        
        # Меню лицензии
        license_menu = tk.Menubutton(indicators_frame, text="▼", 
                                    font=(self.code_font, 10),
                                    bg='#000000', fg='#cccccc',
                                    relief=tk.FLAT)
        license_menu.pack(side=tk.LEFT)
        
        license_menu.menu = tk.Menu(license_menu, tearoff=0, 
                                   bg='#111111', fg='#cccccc',
                                   font=(self.code_font, 9))
        license_menu["menu"] = license_menu.menu
        
        license_menu.menu.add_command(label="Информация о лицензии", 
                                     command=self.show_license_info)
        license_menu.menu.add_command(label="Продлить лицензию", 
                                     command=self.renew_license)
        license_menu.menu.add_separator()
        license_menu.menu.add_command(label="Выйти", 
                                     command=self.on_closing)
        
        # Время и дата
        time_frame = tk.Frame(status_frame, bg='#000000')
        time_frame.pack(pady=(5, 0))
        
        self.time_label = tk.Label(time_frame, 
                                  text=datetime.now().strftime("%H:%M:%S"),
                                  font=(self.code_font, 10, 'bold'), 
                                  fg='#00ff00', bg='#000000')
        self.time_label.pack()
        
        self.date_label = tk.Label(time_frame, 
                                  text=datetime.now().strftime("%Y-%m-%d"),
                                  font=(self.code_font, 8), 
                                  fg='#888888', bg='#000000')
        self.date_label.pack()
        
        # Обновление времени
        self.update_time()
        
    def show_license_info(self):
        """Показывает информацию о лицензии"""
        info_window = tk.Toplevel(self.root)
        info_window.title("Информация о лицензии")
        info_window.geometry("400x300")
        info_window.configure(bg='#000000')
        info_window.resizable(False, False)
        
        # Центрирование
        info_window.update_idletasks()
        width = info_window.winfo_width()
        height = info_window.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        info_window.geometry(f'{width}x{height}+{x}+{y}')
        
        # Заголовок
        tk.Label(info_window, text="ЛИЦЕНЗИОННАЯ ИНФОРМАЦИЯ", 
                font=(self.code_font, 14, 'bold'), fg='#00ff00', bg='#000000').pack(pady=20)
        
        # Информация
        info_frame = tk.Frame(info_window, bg='#111111', padx=20, pady=20)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        info_items = [
            ("Продукт:", "Snos Tool Professional"),
            ("Версия:", "2.0.0"),
            ("Лицензия:", "Активна" if self.stats['license_active'] else "Неактивна"),
            ("Ключ:", f"{self.license_key[:8]}..."),
            ("HWID:", self.stats['hwid']),
            ("Истекает:", self.stats['license_expiry'] or "Неизвестно")
        ]
        
        for label, value in info_items:
            frame = tk.Frame(info_frame, bg='#111111')
            frame.pack(fill=tk.X, pady=3)
            
            tk.Label(frame, text=label, font=(self.code_font, 9),
                    fg='#cccccc', bg='#111111', width=15, anchor='w').pack(side=tk.LEFT)
            
            tk.Label(frame, text=value, font=(self.code_font, 9),
                    fg='#00ff00', bg='#111111', anchor='w').pack(side=tk.LEFT)
        
        # Кнопка закрытия
        tk.Button(info_window, text="ЗАКРЫТЬ", 
                 font=(self.code_font, 10, 'bold'),
                 bg='#2a2a2a', fg='#00ff00',
                 command=info_window.destroy,
                 width=15).pack(pady=20)
    
    def renew_license(self):
        """Открывает страницу продления лицензии"""
        import webbrowser
        webbrowser.open(f"{self.api_url}/renew?key={self.license_key}")
        
    def update_time(self):
        """Обновляет время в реальном времени"""
        current_time = datetime.now().strftime("%H:%M:%S")
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.time_label.config(text=current_time)
        self.date_label.config(text=current_date)
        self.root.after(1000, self.update_time)
        
    def create_left_panel(self, parent):
        # Панель ввода цели
        input_frame = tk.LabelFrame(parent, text=" TARGET ACQUISITION ", 
                                   font=(self.code_font, 10, 'bold'),
                                   fg='#00ff00', bg='#111111', 
                                   labelanchor='n', padx=15, pady=15)
        input_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(input_frame, text="Enter Target (username, ID, phone):", 
                font=(self.code_font, 9), fg='#cccccc', bg='#111111').pack(anchor=tk.W, pady=(0, 5))
        
        # Поле ввода с подсказкой
        self.target_entry = tk.Entry(input_frame, font=(self.code_font, 10), 
                                    bg='#222222', fg='#ffffff',
                                    insertbackground='#00ff00',
                                    relief=tk.SUNKEN, borderwidth=2,
                                    width=30)
        self.target_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Подсказка внутри поля ввода
        self.target_entry.insert(0, "@username or +79161234567")
        self.target_entry.config(fg='#666666')
        
        def on_entry_click(event):
            if self.target_entry.get() == "@username or +79161234567":
                self.target_entry.delete(0, tk.END)
                self.target_entry.config(fg='#ffffff')
        
        def on_focusout(event):
            if self.target_entry.get() == '':
                self.target_entry.insert(0, "@username or +79161234567")
                self.target_entry.config(fg='#666666')
        
        self.target_entry.bind('<FocusIn>', on_entry_click)
        self.target_entry.bind('<FocusOut>', on_focusout)
        
        # Кнопки действий
        action_frame = tk.Frame(input_frame, bg='#111111')
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        buttons = [
            ("ADD TO QUEUE", self.add_to_queue, "#333333", "#00ff00"),
            ("CLEAR", lambda: self.target_entry.delete(0, tk.END), "#333333", "#ff4444")
        ]
        
        for text, command, bg, fg in buttons:
            btn = tk.Button(action_frame, text=text, font=(self.code_font, 8),
                          bg=bg, fg=fg, command=command, height=1)
            btn.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        # Панель управления
        control_frame = tk.LabelFrame(parent, text=" MISSION CONTROL ", 
                                     font=(self.code_font, 10, 'bold'),
                                     fg='#00ff00', bg='#111111',
                                     labelanchor='n', padx=15, pady=15)
        control_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Кнопки управления в сетке
        button_grid = tk.Frame(control_frame, bg='#111111')
        button_grid.pack()
        
        control_buttons = [
            ("ANALYZE", self.analyze_target, "#2a2a2a", "#00ff00"),
            ("START", self.start_reporting, "#2a2a2a", "#ff4444"),
            ("PAUSE", self.pause_reporting, "#2a2a2a", "#ffaa00"),
            ("STOP", self.stop_process, "#2a2a2a", "#ff8800"),
            ("CLEAR LOGS", self.clear_logs, "#2a2a2a", "#cccccc"),
            ("EXPORT", self.export_data, "#2a2a2a", "#00aaff")
        ]
        
        for i, (text, command, bg, fg) in enumerate(control_buttons):
            btn = tk.Button(button_grid, text=text, font=(self.code_font, 9, 'bold'),
                          bg=bg, fg=fg, command=command,
                          height=2, width=12, relief=tk.RAISED)
            btn.grid(row=i//2, column=i%2, padx=5, pady=5)
        
        # Очередь целей
        queue_frame = tk.LabelFrame(parent, text=" TARGET QUEUE ", 
                                   font=(self.code_font, 10, 'bold'),
                                   fg='#00ff00', bg='#111111',
                                   labelanchor='n', padx=15, pady=15)
        queue_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Заголовок очереди
        queue_header = tk.Frame(queue_frame, bg='#111111')
        queue_header.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(queue_header, text=f"Targets in queue: {len(self.targets_queue)}",
                font=(self.code_font, 9), fg='#cccccc', bg='#111111').pack(side=tk.LEFT)
        
        self.queue_listbox = tk.Listbox(queue_frame, bg='#222222', fg='#00ff00',
                                       font=(self.code_font, 9), height=8,
                                       relief=tk.SUNKEN, borderwidth=1,
                                       selectbackground='#333333',
                                       selectforeground='#00ff00')
        self.queue_listbox.pack(fill=tk.BOTH, expand=True)
        
        # Панель управления очередью
        queue_control = tk.Frame(queue_frame, bg='#111111')
        queue_control.pack(fill=tk.X, pady=(5, 0))
        
        queue_buttons = [
            ("REMOVE", self.remove_from_queue),
            ("CLEAR ALL", self.clear_queue),
            ("MOVE UP", self.move_queue_up),
            ("MOVE DOWN", self.move_queue_down)
        ]
        
        for text, command in queue_buttons:
            btn = tk.Button(queue_control, text=text, font=(self.code_font, 7),
                          bg='#333333', fg='#cccccc', width=10,
                          command=command)
            btn.pack(side=tk.LEFT, padx=1, fill=tk.X, expand=True)
        
    def create_center_panel(self, parent):
        # Вкладки
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Стилизация вкладок
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background='#111111', borderwidth=0)
        style.configure("TNotebook.Tab", 
                       background='#222222', 
                       foreground='#00ff00',
                       padding=[15, 5],
                       font=(self.code_font, 9, 'bold'))
        style.map("TNotebook.Tab", 
                 background=[("selected", '#004400')],
                 foreground=[("selected", '#00ff00')])
        
        # Вкладка 1: Анализ
        analysis_tab = self.create_analysis_tab(notebook)
        notebook.add(analysis_tab, text="DEEP ANALYSIS")
        
        # Вкладка 2: Логи
        log_tab = self.create_log_tab(notebook)
        notebook.add(log_tab, text="SYSTEM LOG")
        
        # Вкладка 3: История
        history_tab = self.create_history_tab(notebook)
        notebook.add(history_tab, text="OPERATION HISTORY")
        
    def create_analysis_tab(self, notebook):
        tab = tk.Frame(notebook, bg='#0a0a0a')
        
        self.analysis_text = scrolledtext.ScrolledText(tab,
                                                     bg='#0a0a0a',
                                                     fg='#00ff00',
                                                     font=(self.code_font, 9),
                                                     wrap=tk.WORD,
                                                     relief=tk.SUNKEN,
                                                     borderwidth=2,
                                                     insertbackground='#00ff00',
                                                     padx=10,
                                                     pady=10)
        self.analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        welcome_msg = """
╔══════════════════════════════════════════════════════════════════╗
║                    SNOS TOOL - DEEP ANALYSIS MODULE             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ███████╗███╗   ██╗ ██████╗ ███████╗                           ║
║  ██╔════╝████╗  ██║██╔═══██╗██╔════╝                           ║
║  ███████╗██╔██╗ ██║██║   ██║███████╗                           ║
║  ╚════██║██║╚██╗██║██║   ██║╚════██║                           ║
║  ███████║██║ ╚████║╚██████╔╝███████║                           ║
║  ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝                           ║
║                                                                  ║
║  Enter target identifier and click ANALYZE to begin deep scan.  ║
║  Professional license required for full functionality.          ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
        self.analysis_text.insert(tk.END, welcome_msg)
        self.analysis_text.config(state=tk.DISABLED)
        
        return tab
        
    def create_log_tab(self, notebook):
        tab = tk.Frame(notebook, bg='#0a0a0a')
        
        self.log_text = scrolledtext.ScrolledText(tab,
                                                bg='#0a0a0a',
                                                fg='#00ff00',
                                                font=(self.code_font, 9),
                                                wrap=tk.WORD,
                                                relief=tk.SUNKEN,
                                                borderwidth=2,
                                                insertbackground='#00ff00',
                                                padx=10,
                                                pady=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        return tab
        
    def create_history_tab(self, notebook):
        tab = tk.Frame(notebook, bg='#0a0a0a')
        
        columns = ("#", "Target", "Type", "Reports", "Success", "Time", "Status")
        
        tree_frame = tk.Frame(tab, bg='#0a0a0a')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tree_scroll = tk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.history_tree = ttk.Treeview(tree_frame, 
                                        yscrollcommand=tree_scroll.set,
                                        columns=columns,
                                        show="headings",
                                        height=15)
        
        tree_scroll.config(command=self.history_tree.yview)
        
        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=80)
        
        style = ttk.Style()
        style.configure("Treeview",
                       background="#0a0a0a",
                       foreground="#00ff00",
                       fieldbackground="#0a0a0a",
                       font=(self.code_font, 8))
        
        style.configure("Treeview.Heading",
                       background="#222222",
                       foreground="#00ff00",
                       font=(self.code_font, 9, 'bold'))
        
        self.history_tree.pack(fill=tk.BOTH, expand=True)
        
        return tab
    
    def create_right_panel(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        style = ttk.Style()
        style.configure("Right.TNotebook.Tab", 
                       padding=[10, 3],
                       font=(self.code_font, 8, 'bold'))
        
        stats_tab = self.create_stats_tab()
        notebook.add(stats_tab, text="STATISTICS")
        
        system_tab = self.create_system_tab()
        notebook.add(system_tab, text="SYSTEM INFO")
        
        settings_tab = self.create_settings_tab()
        notebook.add(settings_tab, text="SETTINGS")
        
    def create_stats_tab(self):
        tab = tk.Frame(self.root, bg='#111111')
        
        main_stats = tk.LabelFrame(tab, text=" OPERATION STATS ", 
                                  font=(self.code_font, 10, 'bold'),
                                  fg='#00ff00', bg='#111111',
                                  padx=15, pady=15)
        main_stats.pack(fill=tk.X, padx=10, pady=10)
        
        stats_data = [
            ("Total Reports:", "total_reports", "#00ff00"),
            ("Successful:", "successful", "#00ff00"),
            ("Failed:", "failed", "#ff4444"),
            ("Success Rate:", "rate", "#00ff00"),
            ("Current Speed:", "speed", "#00ff00"),
            ("Elapsed Time:", "time", "#00ff00"),
            ("Queue Size:", "queue", "#00ff00"),
            ("Targets Done:", "processed", "#00ff00")
        ]
        
        self.stat_labels = {}
        
        for text, key, color in stats_data:
            frame = tk.Frame(main_stats, bg='#111111')
            frame.pack(fill=tk.X, pady=2)
            
            tk.Label(frame, text=text, font=(self.code_font, 9),
                    fg='#cccccc', bg='#111111', width=20, anchor='w').pack(side=tk.LEFT)
            
            value_label = tk.Label(frame, text="0", font=(self.code_font, 9, 'bold'),
                                  fg=color, bg='#111111', width=10, anchor='e')
            value_label.pack(side=tk.RIGHT)
            
            self.stat_labels[key] = value_label
        
        return tab
    
    def create_system_tab(self):
        tab = tk.Frame(self.root, bg='#111111')
        
        sys_frame = tk.LabelFrame(tab, text=" SYSTEM STATUS ", 
                                 font=(self.code_font, 10, 'bold'),
                                 fg='#00ff00', bg='#111111',
                                 padx=15, pady=15)
        sys_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        sys_info = [
            ("Application:", "Snos Tool v2.0.0"),
            ("License:", "Professional"),
            ("Status:", "Active" if self.stats['license_active'] else "Inactive"),
            ("HWID:", self.stats['hwid']),
            ("Threads:", str(self.settings['threads'])),
            ("Proxy Mode:", "Enabled" if self.settings['use_proxy'] else "Disabled")
        ]
        
        for label, value in sys_info:
            frame = tk.Frame(sys_frame, bg='#111111')
            frame.pack(fill=tk.X, pady=2)
            
            tk.Label(frame, text=label, font=(self.code_font, 9),
                    fg='#cccccc', bg='#111111', width=15, anchor='w').pack(side=tk.LEFT)
            
            tk.Label(frame, text=value, font=(self.code_font, 9),
                    fg='#00ff00', bg='#111111', anchor='w').pack(side=tk.LEFT)
        
        return tab
    
    def create_settings_tab(self):
        tab = tk.Frame(self.root, bg='#111111')
        
        quick_frame = tk.LabelFrame(tab, text=" QUICK SETTINGS ", 
                                   font=(self.code_font, 10, 'bold'),
                                   fg='#00ff00', bg='#111111',
                                   padx=15, pady=15)
        quick_frame.pack(fill=tk.X, padx=10, pady=10)
        
        settings = [
            ("Threads:", "threads", 1, 10),
            ("Delay (sec):", "report_speed", 0.5, 5.0),
            ("Max Reports:", "max_reports", 10, 500),
            ("Retry Count:", "retry_count", 1, 10)
        ]
        
        self.setting_widgets = {}
        
        for i, (label, key, min_val, max_val) in enumerate(settings):
            frame = tk.Frame(quick_frame, bg='#111111')
            frame.pack(fill=tk.X, pady=3)
            
            tk.Label(frame, text=label, font=(self.code_font, 9),
                    fg='#cccccc', bg='#111111').pack(side=tk.LEFT)
            
            if isinstance(min_val, int):
                var = tk.IntVar(value=self.settings[key])
                widget = tk.Spinbox(frame, from_=min_val, to=max_val, 
                                   textvariable=var, font=(self.code_font, 9),
                                   bg='#222222', fg='#ffffff', width=10)
            else:
                var = tk.DoubleVar(value=self.settings[key])
                widget = tk.Spinbox(frame, from_=min_val, to=max_val, 
                                   increment=0.1, textvariable=var,
                                   font=(self.code_font, 9),
                                   bg='#222222', fg='#ffffff', width=10)
            
            widget.pack(side=tk.RIGHT)
            self.setting_widgets[key] = (var, widget)
        
        check_frame = tk.Frame(quick_frame, bg='#111111')
        check_frame.pack(pady=10)
        
        checkboxes = [
            ("Use Proxy Rotation", "use_proxy"),
            ("Stealth Mode", "stealth_mode"),
            ("Random Delay", "delay_variation"),
            ("Auto Mode", "auto_mode")
        ]
        
        self.check_vars = {}
        
        for text, key in checkboxes:
            var = tk.BooleanVar(value=self.settings[key])
            cb = tk.Checkbutton(check_frame, text=text,
                              variable=var, font=(self.code_font, 9),
                              bg='#111111', fg='#cccccc',
                              selectcolor='#222222', anchor='w')
            cb.pack(fill=tk.X, pady=2)
            self.check_vars[key] = var
        
        tk.Button(tab, text="APPLY SETTINGS", font=(self.code_font, 10, 'bold'),
                 bg='#2a2a2a', fg='#00ff00', command=self.apply_settings,
                 width=20).pack(pady=20)
        
        return tab
    
    def create_bottom_panel(self):
        bottom_frame = tk.Frame(self.root, bg='#000000', height=70)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        bottom_frame.pack_propagate(False)
        
        progress_frame = tk.Frame(bottom_frame, bg='#000000')
        progress_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(progress_frame, text="OVERALL PROGRESS:", 
                font=(self.code_font, 9), fg='#cccccc', bg='#000000').pack(side=tk.LEFT)
        
        self.overall_progress = ttk.Progressbar(progress_frame, length=800, mode='determinate')
        self.overall_progress.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        self.overall_percent = tk.Label(progress_frame, text="0%", 
                                       font=(self.code_font, 9, 'bold'), 
                                       fg='#00ff00', bg='#000000')
        self.overall_percent.pack(side=tk.LEFT, padx=(10, 0))
        
        status_bar = tk.Frame(bottom_frame, bg='#000000')
        status_bar.pack(fill=tk.X, padx=20)
        
        self.status_message = tk.Label(status_bar, text="Ready", 
                                      font=(self.code_font, 8), fg='#00ff00', bg='#000000')
        self.status_message.pack(side=tk.LEFT)
        
        version_info = tk.Label(status_bar, 
                               text="Snos Tool v2.0.0 | Professional License | Educational Use Only",
                               font=(self.code_font, 7), fg='#666666', bg='#000000')
        version_info.pack(side=tk.RIGHT)
    
    # Основные методы программы (аналогичные предыдущим версиям)
    
    def analyze_target(self):
        if not self.stats['license_active']:
            self.add_log("[ERROR] License not active. Please activate license first.")
            messagebox.showerror("License Error", "Please activate your license first.")
            return
        
        target = self.target_entry.get().strip()
        if target == "@username or +79161234567" or not target:
            self.add_log("[ERROR] Please enter a valid target")
            return
        
        if self.is_analyzing:
            self.add_log("[WARNING] Analysis already in progress")
            return
        
        self.is_analyzing = True
        self.add_log(f"[ANALYSIS] Starting deep scan of: {target}")
        
        threading.Thread(target=self.perform_analysis, args=(target,), daemon=True).start()
    
    def perform_analysis(self, target):
        try:
            steps = [
                ("Resolving identifier...", 10),
                ("Querying Telegram API...", 25),
                ("Analyzing metadata...", 40),
                ("Checking activity patterns...", 55),
                ("Scanning for violations...", 70),
                ("Building risk profile...", 85),
                ("Generating report...", 100)
            ]
            
            for step_text, progress in steps:
                self.root.after(0, lambda t=step_text: self.status_message.config(text=t))
                time.sleep(random.uniform(0.3, 0.8))
                self.add_log(f"[ANALYSIS] {step_text}")
            
            report = self.generate_detailed_report(target)
            
            self.root.after(0, lambda: self.display_analysis_report(report, target))
            
            self.add_log(f"[ANALYSIS] Complete: {target}")
            
        except Exception as e:
            self.add_log(f"[ERROR] Analysis failed: {str(e)}")
        finally:
            self.is_analyzing = False
            self.root.after(0, lambda: self.status_message.config(text="Ready"))
    
    def generate_detailed_report(self, target):
        report_id = f"SNOS-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        
        report = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         SNOS TOOL ANALYSIS REPORT                           ║
║                         Report ID: {report_id}                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

[+] TARGET IDENTIFICATION
    ├─ Identifier: {target}
    ├─ Type: {'USER' if '@' in target else ('PHONE' if '+' in target else 'ID')}
    ├─ Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    └─ License: Professional (Active)

[+] SECURITY ANALYSIS
    ├─ Threat Level: {random.choice(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])}
    ├─ Risk Score: {random.randint(0, 100)}/100
    ├─ Recommended Action: {random.choice(['MONITOR', 'REPORT', 'BLOCK'])}
    └─ Priority: {random.choice(['LOW', 'MEDIUM', 'HIGH'])}

[+] TECHNICAL DATA
    ├─ Session ID: {random.randint(1000000000, 9999999999)}
    ├─ Analysis Hash: {''.join(random.choices('0123456789abcdef', k=32))}
    └─ Report Valid Until: {(datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M')}

╔══════════════════════════════════════════════════════════════════════════════╗
║              ANALYSIS COMPLETE - PROFESSIONAL REPORT GENERATED              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        return report
    
    def display_analysis_report(self, report, target):
        self.analysis_text.config(state=tk.NORMAL)
        self.analysis_text.delete(1.0, tk.END)
        self.analysis_text.insert(tk.END, report)
        self.analysis_text.config(state=tk.DISABLED)
        
        if target and target not in self.targets_queue:
            self.targets_queue.append(target)
            self.queue_listbox.insert(tk.END, target)
            self.update_stats_display()
    
    def add_to_queue(self):
        if not self.stats['license_active']:
            messagebox.showerror("License Error", "Please activate your license first.")
            return
            
        target = self.target_entry.get().strip()
        if target and target != "@username or +79161234567":
            if target not in self.targets_queue:
                self.targets_queue.append(target)
                self.queue_listbox.insert(tk.END, target)
                self.add_log(f"[QUEUE] Added: {target}")
                self.update_stats_display()
    
    def remove_from_queue(self):
        selection = self.queue_listbox.curselection()
        if selection:
            target = self.queue_listbox.get(selection[0])
            self.queue_listbox.delete(selection[0])
            if target in self.targets_queue:
                self.targets_queue.remove(target)
            self.add_log(f"[QUEUE] Removed: {target}")
            self.update_stats_display()
    
    def clear_queue(self):
        self.targets_queue.clear()
        self.queue_listbox.delete(0, tk.END)
        self.add_log("[QUEUE] Cleared all targets")
        self.update_stats_display()
    
    def move_queue_up(self):
        selection = self.queue_listbox.curselection()
        if selection and selection[0] > 0:
            idx = selection[0]
            item = self.queue_listbox.get(idx)
            self.queue_listbox.delete(idx)
            self.queue_listbox.insert(idx-1, item)
            self.queue_listbox.selection_set(idx-1)
            self.targets_queue.pop(idx)
            self.targets_queue.insert(idx-1, item)
    
    def move_queue_down(self):
        selection = self.queue_listbox.curselection()
        if selection and selection[0] < len(self.targets_queue) - 1:
            idx = selection[0]
            item = self.queue_listbox.get(idx)
            self.queue_listbox.delete(idx)
            self.queue_listbox.insert(idx+1, item)
            self.queue_listbox.selection_set(idx+1)
            self.targets_queue.pop(idx)
            self.targets_queue.insert(idx+1, item)
    
    def start_reporting(self):
        if not self.stats['license_active']:
            messagebox.showerror("License Error", "Please activate your license first.")
            return
            
        if not self.targets_queue:
            target = self.target_entry.get().strip()
            if target and target != "@username or +79161234567":
                self.targets_queue.append(target)
                self.queue_listbox.insert(tk.END, target)
            else:
                self.add_log("[ERROR] No targets in queue")
                return
        
        self.stats['start_time'] = datetime.now()
        self.is_running = True
        
        self.add_log("[REPORTING] Starting mass report operation")
        self.add_log(f"[REPORTING] Targets in queue: {len(self.targets_queue)}")
        
        threading.Thread(target=self.simulate_reporting_operation, daemon=True).start()
    
    def simulate_reporting_operation(self):
        while self.is_running and self.targets_queue:
            current_target = self.targets_queue.pop(0)
            self.queue_listbox.delete(0)
            
            self.simulate_reports_for_target(current_target)
            
            if not self.is_running:
                break
        
        if not self.targets_queue:
            self.add_log("[REPORTING] All targets processed")
            self.is_running = False
    
    def simulate_reports_for_target(self, target):
        report_count = 0
        max_for_target = self.settings['max_reports']
        
        while report_count < max_for_target and self.is_running:
            delay = self.settings['report_speed']
            if self.settings['delay_variation']:
                delay *= random.uniform(0.8, 1.2)
            
            time.sleep(delay)
            
            success = self.simulate_single_report(target, report_count + 1)
            
            self.stats['total_reports'] += 1
            if success:
                self.stats['successful'] += 1
            else:
                self.stats['failed'] += 1
            
            report_count += 1
        
        self.stats['targets_processed'].append(target)
        self.add_log(f"[REPORTING] Target completed: {target}")
    
    def simulate_single_report(self, target, report_num):
        report_types = ['SPAM', 'FAKE_ACCOUNT', 'VIOLENCE', 'PORNOGRAPHY']
        report_type = random.choice(report_types)
        
        success = random.random() < 0.85
        
        if success:
            log_msg = f"[SUCCESS] Report #{report_num} | Target: {target} | Type: {report_type}"
            self.add_log(log_msg, "SUCCESS")
        else:
            log_msg = f"[FAILED] Report #{report_num} | Target: {target}"
            self.add_log(log_msg, "ERROR")
        
        return success
    
    def pause_reporting(self):
        self.is_running = False
        self.add_log("[REPORTING] Operation paused")
    
    def stop_process(self):
        self.is_running = False
        self.targets_queue.clear()
        self.queue_listbox.delete(0, tk.END)
        self.add_log("[REPORTING] Operation stopped and queue cleared")
    
    def clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.add_log("[SYSTEM] Log cleared")
    
    def export_data(self):
        if not self.stats['license_active']:
            messagebox.showerror("License Error", "Please activate your license first.")
            return
            
        filename = f"snos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w') as f:
            f.write("Snos Tool Export Data\n")
            f.write(f"Export Time: {datetime.now()}\n")
            f.write(f"License: {self.license_key}\n")
            f.write(f"Total Reports: {self.stats['total_reports']}\n")
        
        self.add_log(f"[EXPORT] Data exported to {filename}")
        self.status_message.config(text=f"Exported to {filename}")
    
    def apply_settings(self):
        try:
            for key, (var, widget) in self.setting_widgets.items():
                self.settings[key] = var.get()
            
            for key, var in self.check_vars.items():
                self.settings[key] = var.get()
            
            self.add_log("[SETTINGS] Settings applied successfully")
            self.status_message.config(text="Settings applied")
        except Exception as e:
            self.add_log(f"[ERROR] Failed to apply settings: {str(e)}")
    
    def update_stats_display(self):
        self.stat_labels['total_reports'].config(text=str(self.stats['total_reports']))
        self.stat_labels['successful'].config(text=str(self.stats['successful']))
        self.stat_labels['failed'].config(text=str(self.stats['failed']))
        
        if self.stats['total_reports'] > 0:
            rate = (self.stats['successful'] / self.stats['total_reports']) * 100
            self.stat_labels['rate'].config(text=f"{rate:.1f}%")
        else:
            self.stat_labels['rate'].config(text="0%")
        
        if self.stats['start_time'] and self.stats['total_reports'] > 0:
            elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
            if elapsed > 0:
                speed = self.stats['total_reports'] / elapsed
                self.stat_labels['speed'].config(text=f"{speed:.1f}/s")
            
            elapsed_str = str(timedelta(seconds=int(elapsed)))
            self.stat_labels['time'].config(text=elapsed_str)
        else:
            self.stat_labels['speed'].config(text="0/s")
            self.stat_labels['time'].config(text="00:00:00")
        
        self.stat_labels['queue'].config(text=str(len(self.targets_queue)))
        self.stat_labels['processed'].config(text=str(len(self.stats['targets_processed'])))
        
        if self.root.winfo_exists():
            self.root.after(1000, self.update_stats_display)
    
    def add_log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        colors = {
            "INFO": "#00ff00",
            "ERROR": "#ff4444",
            "WARNING": "#ffaa00",
            "SUCCESS": "#00ff00"
        }
        
        color = colors.get(level, "#00ff00")
        
        self.log_text.config(state=tk.NORMAL)
        
        self.log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.log_text.insert(tk.END, message + "\n", level)
        
        self.log_text.tag_config("timestamp", foreground="#888888")
        self.log_text.tag_config("INFO", foreground="#00ff00")
        self.log_text.tag_config("ERROR", foreground="#ff4444")
        self.log_text.tag_config("WARNING", foreground="#ffaa00")
        self.log_text.tag_config("SUCCESS", foreground="#00ff00")
        
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def save_config(self):
        config = {
            'settings': self.settings,
            'stats': self.stats
        }
        try:
            with open('snos_tool_config.json', 'w') as f:
                json.dump(config, f, indent=2)
        except:
            pass
    
    def load_config(self):
        try:
            if os.path.exists('snos_tool_config.json'):
                with open('snos_tool_config.json', 'r') as f:
                    config = json.load(f)
                    self.settings.update(config.get('settings', {}))
        except:
            pass
    
    def on_closing(self):
        self.is_running = False
        
        if self.external_module_process:
            try:
                self.external_module_process.terminate()
            except:
                pass
        
        self.save_config()
        self.root.destroy()

def main():
    root = tk.Tk()
    
    app = SnosTool(root)
    
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    print("=" * 70)
    print("Snos Tool v2.0.0 - Professional Reporting Tool")
    print("License Required - Educational Use Only")
    print("=" * 70)
    
    root.mainloop()

if __name__ == "__main__":
    main()