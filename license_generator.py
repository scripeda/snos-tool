import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, font
import random
import string
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
import base64
import secrets
import qrcode
from PIL import Image, ImageTk
import io
import threading

class LicenseGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title("Snos Tool - License Generator v2.0")
        self.root.geometry("1000x700")
        self.root.configure(bg='#0a0a0a')
        self.root.resizable(True, True)
        
        # Загрузка шрифтов
        self.load_custom_fonts()
        
        # Центрирование окна
        self.center_window()
        
        # Данные лицензий
        self.licenses = []
        self.key_counter = 1
        self.current_license = None
        
        # Настройки по умолчанию
        self.settings = {
            'prefix': 'SNOS',
            'key_length': 16,
            'days_valid': 30,
            'max_activations': 1,
            'auto_save': True
        }
        
        # Загрузка конфигурации
        self.load_config()
        
        # Создание интерфейса
        self.create_interface()
        
        # Загрузка сохраненных лицензий
        self.load_licenses()
    
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
    
    def create_interface(self):
        # Верхняя панель
        self.create_header()
        
        # Основная область
        main_container = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg='#0a0a0a')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Левая панель - генерация
        left_panel = tk.Frame(main_container, bg='#111111', relief=tk.GROOVE, borderwidth=2)
        main_container.add(left_panel, minsize=400)
        
        # Правая панель - список лицензий
        right_panel = tk.Frame(main_container, bg='#111111', relief=tk.GROOVE, borderwidth=2)
        main_container.add(right_panel, minsize=400)
        
        # Создание панелей
        self.create_left_panel(left_panel)
        self.create_right_panel(right_panel)
        
        # Нижняя панель
        self.create_bottom_panel()
    
    def create_header(self):
        header_frame = tk.Frame(self.root, bg='#000000', height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        # Логотип и название
        logo_frame = tk.Frame(header_frame, bg='#000000')
        logo_frame.pack(side=tk.LEFT, padx=25)
        
        tk.Label(logo_frame, text="SNOS TOOL", font=(self.code_font, 20, 'bold'),
                fg='#00ff00', bg='#000000').pack(anchor=tk.W)
        tk.Label(logo_frame, text="License Generator v2.0 | Admin Panel", 
                font=(self.code_font, 9), fg='#cccccc', bg='#000000').pack(anchor=tk.W)
        
        # Статус
        status_frame = tk.Frame(header_frame, bg='#000000')
        status_frame.pack(side=tk.RIGHT, padx=25)
        
        self.status_label = tk.Label(status_frame, text="● READY", 
                                   font=(self.code_font, 10, 'bold'), 
                                   fg='#00ff00', bg='#000000')
        self.status_label.pack()
        
        tk.Label(status_frame, text=f"Licenses: {len(self.licenses)}", 
                font=(self.code_font, 8), fg='#888888', bg='#000000').pack()
    
    def create_left_panel(self, parent):
        # Панель настроек генерации
        settings_frame = tk.LabelFrame(parent, text=" GENERATION SETTINGS ", 
                                      font=(self.code_font, 11, 'bold'),
                                      fg='#00ff00', bg='#111111', 
                                      labelanchor='n', padx=15, pady=15)
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Настройки
        settings_grid = tk.Frame(settings_frame, bg='#111111')
        settings_grid.pack(fill=tk.X, pady=5)
        
        setting_items = [
            ("Prefix:", "prefix", tk.Entry),
            ("Key Length:", "key_length", tk.Spinbox),
            ("Days Valid:", "days_valid", tk.Spinbox),
            ("Max Activations:", "max_activations", tk.Spinbox)
        ]
        
        self.setting_widgets = {}
        
        for i, (label, key, widget_type) in enumerate(setting_items):
            frame = tk.Frame(settings_grid, bg='#111111')
            frame.pack(fill=tk.X, pady=5)
            
            tk.Label(frame, text=label, font=(self.code_font, 10),
                    fg='#cccccc', bg='#111111', width=15, anchor='w').pack(side=tk.LEFT)
            
            if widget_type == tk.Entry:
                var = tk.StringVar(value=self.settings[key])
                widget = tk.Entry(frame, textvariable=var, font=(self.code_font, 10),
                                 bg='#222222', fg='#ffffff', insertbackground='#00ff00')
                widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            elif widget_type == tk.Spinbox:
                var = tk.IntVar(value=self.settings[key])
                if key == 'key_length':
                    widget = tk.Spinbox(frame, from_=8, to=32, textvariable=var,
                                       font=(self.code_font, 10), width=10,
                                       bg='#222222', fg='#ffffff')
                elif key == 'days_valid':
                    widget = tk.Spinbox(frame, from_=1, to=365, textvariable=var,
                                       font=(self.code_font, 10), width=10,
                                       bg='#222222', fg='#ffffff')
                elif key == 'max_activations':
                    widget = tk.Spinbox(frame, from_=1, to=999, textvariable=var,
                                       font=(self.code_font, 10), width=10,
                                       bg='#222222', fg='#ffffff')
                widget.pack(side=tk.LEFT)
            
            self.setting_widgets[key] = var
        
        # Чекбоксы
        check_frame = tk.Frame(settings_frame, bg='#111111')
        check_frame.pack(fill=tk.X, pady=10)
        
        self.auto_save_var = tk.BooleanVar(value=self.settings['auto_save'])
        auto_save_cb = tk.Checkbutton(check_frame, text="Auto-save licenses",
                                     variable=self.auto_save_var,
                                     font=(self.code_font, 9),
                                     bg='#111111', fg='#cccccc',
                                     selectcolor='#222222')
        auto_save_cb.pack(anchor=tk.W)
        
        # Кнопки генерации
        button_frame = tk.Frame(settings_frame, bg='#111111')
        button_frame.pack(fill=tk.X, pady=15)
        
        gen_buttons = [
            ("GENERATE SINGLE", self.generate_single),
            ("GENERATE BATCH (10)", lambda: self.generate_batch(10)),
            ("GENERATE BATCH (50)", lambda: self.generate_batch(50)),
            ("GENERATE BATCH (100)", lambda: self.generate_batch(100))
        ]
        
        for text, command in gen_buttons:
            btn = tk.Button(button_frame, text=text, font=(self.code_font, 9, 'bold'),
                          bg='#2a2a2a', fg='#00ff00', command=command,
                          height=2)
            btn.pack(fill=tk.X, pady=2)
        
        # Панель предпросмотра
        preview_frame = tk.LabelFrame(parent, text=" KEY PREVIEW ", 
                                     font=(self.code_font, 11, 'bold'),
                                     fg='#00ff00', bg='#111111',
                                     labelanchor='n', padx=15, pady=15)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.key_preview = tk.Text(preview_frame, height=4,
                                  bg='#222222', fg='#00ff00',
                                  font=(self.code_font, 12, 'bold'),
                                  wrap=tk.WORD, relief=tk.SUNKEN)
        self.key_preview.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки копирования
        copy_frame = tk.Frame(preview_frame, bg='#111111')
        copy_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(copy_frame, text="COPY KEY", font=(self.code_font, 8),
                 bg='#333333', fg='#cccccc', width=12,
                 command=self.copy_key).pack(side=tk.LEFT, padx=2)
        
        tk.Button(copy_frame, text="GENERATE QR", font=(self.code_font, 8),
                 bg='#333333', fg='#cccccc', width=12,
                 command=self.generate_qr).pack(side=tk.LEFT, padx=2)
    
    def create_right_panel(self, parent):
        # Панель списка лицензий
        list_frame = tk.LabelFrame(parent, text=" LICENSE DATABASE ", 
                                  font=(self.code_font, 11, 'bold'),
                                  fg='#00ff00', bg='#111111',
                                  labelanchor='n', padx=15, pady=15)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Панель поиска и фильтров
        filter_frame = tk.Frame(list_frame, bg='#111111')
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(filter_frame, text="Search:", font=(self.code_font, 9),
                fg='#cccccc', bg='#111111').pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_licenses)
        search_entry = tk.Entry(filter_frame, textvariable=self.search_var,
                               font=(self.code_font, 9),
                               bg='#222222', fg='#ffffff', width=20)
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # Таблица лицензий
        columns = ("ID", "License Key", "Created", "Expires", "Status", "Activations")
        
        # Создаем Treeview с полосой прокрутки
        tree_frame = tk.Frame(list_frame, bg='#111111')
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll = tk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.license_tree = ttk.Treeview(tree_frame, 
                                        yscrollcommand=tree_scroll.set,
                                        columns=columns,
                                        show="headings",
                                        height=15,
                                        selectmode='browse')
        
        tree_scroll.config(command=self.license_tree.yview)
        
        # Настраиваем колонки
        col_widths = [40, 150, 100, 100, 80, 80]
        for i, col in enumerate(columns):
            self.license_tree.heading(col, text=col)
            self.license_tree.column(col, width=col_widths[i], minwidth=50)
        
        # Стилизация дерева
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview",
                       background="#0a0a0a",
                       foreground="#00ff00",
                       fieldbackground="#0a0a0a",
                       font=(self.code_font, 8))
        
        style.configure("Treeview.Heading",
                       background="#222222",
                       foreground="#00ff00",
                       font=(self.code_font, 9, 'bold'))
        
        style.map("Treeview", 
                 background=[('selected', '#004400')],
                 foreground=[('selected', '#00ff00')])
        
        self.license_tree.pack(fill=tk.BOTH, expand=True)
        
        # Привязываем событие выбора
        self.license_tree.bind('<<TreeviewSelect>>', self.on_license_select)
        
        # Панель управления списком
        list_control = tk.Frame(list_frame, bg='#111111')
        list_control.pack(fill=tk.X, pady=(10, 0))
        
        control_buttons = [
            ("VIEW DETAILS", self.view_license_details),
            ("DELETE", self.delete_license),
            ("EXPORT", self.export_licenses),
            ("IMPORT", self.import_licenses)
        ]
        
        for text, command in control_buttons:
            btn = tk.Button(list_control, text=text, font=(self.code_font, 8),
                          bg='#333333', fg='#cccccc', width=12,
                          command=command)
            btn.pack(side=tk.LEFT, padx=2)
    
    def create_bottom_panel(self):
        bottom_frame = tk.Frame(self.root, bg='#000000', height=50)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        bottom_frame.pack_propagate(False)
        
        # Статистика
        stats_frame = tk.Frame(bottom_frame, bg='#000000')
        stats_frame.pack(side=tk.LEFT, padx=20)
        
        self.total_label = tk.Label(stats_frame, text="Total: 0", 
                                   font=(self.code_font, 9),
                                   fg='#00ff00', bg='#000000')
        self.total_label.pack(side=tk.LEFT, padx=10)
        
        self.active_label = tk.Label(stats_frame, text="Active: 0", 
                                    font=(self.code_font, 9),
                                    fg='#00ff00', bg='#000000')
        self.active_label.pack(side=tk.LEFT, padx=10)
        
        self.expired_label = tk.Label(stats_frame, text="Expired: 0", 
                                     font=(self.code_font, 9),
                                     fg='#ff4444', bg='#000000')
        self.expired_label.pack(side=tk.LEFT, padx=10)
        
        # Информация
        info_label = tk.Label(bottom_frame, 
                             text="Snos Tool License Generator | For Admin Use Only",
                             font=(self.code_font, 7), fg='#666666', bg='#000000')
        info_label.pack(side=tk.RIGHT, padx=20)
    
    def generate_license_key(self):
        """Генерирует лицензионный ключ"""
        prefix = self.setting_widgets['prefix'].get()
        length = self.setting_widgets['key_length'].get()
        
        # Генерация случайной части
        chars = string.ascii_uppercase + string.digits
        random_part = ''.join(secrets.choice(chars) for _ in range(length))
        
        # Создание ключа с префиксом
        key = f"{prefix}-{random_part[:4]}-{random_part[4:8]}-{random_part[8:12]}-{random_part[12:]}"
        
        # Вычисление контрольной суммы
        checksum = hashlib.md5(key.encode()).hexdigest()[:4].upper()
        
        return f"{key}-{checksum}"
    
    def create_license_data(self, key):
        """Создает данные лицензии"""
        days_valid = self.setting_widgets['days_valid'].get()
        max_activations = self.setting_widgets['max_activations'].get()
        
        created = datetime.now()
        expires = created + timedelta(days=days_valid)
        
        license_data = {
            'id': self.key_counter,
            'key': key,
            'created': created.isoformat(),
            'expires': expires.isoformat(),
            'max_activations': max_activations,
            'activations': [],
            'status': 'active',
            'notes': ''
        }
        
        self.key_counter += 1
        return license_data
    
    def generate_single(self):
        """Генерирует одиночную лицензию"""
        try:
            key = self.generate_license_key()
            license_data = self.create_license_data(key)
            
            # Показываем превью
            self.key_preview.delete(1.0, tk.END)
            self.key_preview.insert(tk.END, key)
            
            # Сохраняем лицензию
            self.licenses.append(license_data)
            self.current_license = license_data
            
            # Обновляем список
            self.update_license_list()
            
            # Авто-сохранение
            if self.auto_save_var.get():
                self.save_licenses()
            
            self.status_label.config(text="● KEY GENERATED", fg='#00ff00')
            
            # Показываем уведомление
            messagebox.showinfo("Success", f"License key generated:\n{key}")
            
        except Exception as e:
            self.status_label.config(text="● ERROR", fg='#ff4444')
            messagebox.showerror("Error", f"Failed to generate key: {str(e)}")
    
    def generate_batch(self, count):
        """Генерирует пакет лицензий"""
        try:
            generated_keys = []
            
            for i in range(count):
                key = self.generate_license_key()
                license_data = self.create_license_data(key)
                self.licenses.append(license_data)
                generated_keys.append(key)
            
            # Показываем последний ключ
            if generated_keys:
                self.key_preview.delete(1.0, tk.END)
                self.key_preview.insert(tk.END, generated_keys[-1])
                self.current_license = self.licenses[-1]
            
            # Обновляем список
            self.update_license_list()
            
            # Авто-сохранение
            if self.auto_save_var.get():
                self.save_licenses()
            
            self.status_label.config(text=f"● {count} KEYS GENERATED", fg='#00ff00')
            
            # Показываем уведомление
            messagebox.showinfo("Success", f"Generated {count} license keys")
            
        except Exception as e:
            self.status_label.config(text="● ERROR", fg='#ff4444')
            messagebox.showerror("Error", f"Failed to generate batch: {str(e)}")
    
    def copy_key(self):
        """Копирует ключ в буфер обмена"""
        key = self.key_preview.get(1.0, tk.END).strip()
        if key:
            self.root.clipboard_clear()
            self.root.clipboard_append(key)
            self.status_label.config(text="● COPIED TO CLIPBOARD", fg='#00ff00')
    
    def generate_qr(self):
        """Генерирует QR код для ключа"""
        key = self.key_preview.get(1.0, tk.END).strip()
        if not key:
            messagebox.showwarning("Warning", "No key to generate QR code")
            return
        
        try:
            # Создаем QR код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(key)
            qr.make(fit=True)
            
            # Создаем изображение
            img = qr.make_image(fill_color="#00ff00", back_color="#000000")
            
            # Показываем в новом окне
            qr_window = tk.Toplevel(self.root)
            qr_window.title("QR Code - License Key")
            qr_window.geometry("400x450")
            qr_window.configure(bg='#000000')
            
            # Конвертируем PIL Image в Tkinter PhotoImage
            img_tk = ImageTk.PhotoImage(img)
            
            tk.Label(qr_window, image=img_tk, bg='#000000').pack(pady=20)
            
            # Ключ под QR кодом
            tk.Label(qr_window, text=key, font=(self.code_font, 10),
                    fg='#00ff00', bg='#000000').pack(pady=10)
            
            # Кнопки
            button_frame = tk.Frame(qr_window, bg='#000000')
            button_frame.pack(pady=10)
            
            tk.Button(button_frame, text="SAVE QR", font=(self.code_font, 9),
                     bg='#2a2a2a', fg='#00ff00',
                     command=lambda: self.save_qr_image(img)).pack(side=tk.LEFT, padx=5)
            
            tk.Button(button_frame, text="CLOSE", font=(self.code_font, 9),
                     bg='#2a2a2a', fg='#cccccc',
                     command=qr_window.destroy).pack(side=tk.LEFT, padx=5)
            
            # Сохраняем ссылку на изображение
            qr_window.img = img_tk
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate QR code: {str(e)}")
    
    def save_qr_image(self, img):
        """Сохраняет QR код как изображение"""
        from tkinter import filedialog
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            initialfile=f"license_qr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        
        if filename:
            try:
                img.save(filename)
                self.status_label.config(text="● QR CODE SAVED", fg='#00ff00')
                messagebox.showinfo("Success", f"QR code saved to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save QR code: {str(e)}")
    
    def update_license_list(self):
        """Обновляет список лицензий"""
        # Очищаем дерево
        for item in self.license_tree.get_children():
            self.license_tree.delete(item)
        
        # Добавляем лицензии
        for license_data in self.licenses:
            created = datetime.fromisoformat(license_data['created']).strftime("%Y-%m-%d")
            expires = datetime.fromisoformat(license_data['expires']).strftime("%Y-%m-%d")
            activations = len(license_data['activations'])
            max_activations = license_data['max_activations']
            status = license_data['status']
            
            # Цвет статуса
            tags = ()
            if status == 'active':
                tags = ('active',)
            elif status == 'expired':
                tags = ('expired',)
            elif status == 'revoked':
                tags = ('revoked',)
            
            self.license_tree.insert("", tk.END, 
                                   values=(
                                       license_data['id'],
                                       license_data['key'][:20] + "...",
                                       created,
                                       expires,
                                       status.upper(),
                                       f"{activations}/{max_activations}"
                                   ),
                                   tags=tags)
        
        # Настраиваем теги для цветов
        self.license_tree.tag_configure('active', foreground='#00ff00')
        self.license_tree.tag_configure('expired', foreground='#ff4444')
        self.license_tree.tag_configure('revoked', foreground='#ffaa00')
        
        # Обновляем статистику
        self.update_stats()
    
    def update_stats(self):
        """Обновляет статистику"""
        total = len(self.licenses)
        active = sum(1 for l in self.licenses if l['status'] == 'active')
        expired = sum(1 for l in self.licenses if l['status'] == 'expired')
        
        self.total_label.config(text=f"Total: {total}")
        self.active_label.config(text=f"Active: {active}")
        self.expired_label.config(text=f"Expired: {expired}")
    
    def filter_licenses(self, *args):
        """Фильтрует лицензии по поисковому запросу"""
        search_term = self.search_var.get().lower()
        
        # Очищаем дерево
        for item in self.license_tree.get_children():
            self.license_tree.delete(item)
        
        # Фильтруем и добавляем
        for license_data in self.licenses:
            if (search_term in license_data['key'].lower() or 
                search_term in license_data['status'].lower()):
                
                created = datetime.fromisoformat(license_data['created']).strftime("%Y-%m-%d")
                expires = datetime.fromisoformat(license_data['expires']).strftime("%Y-%m-%d")
                activations = len(license_data['activations'])
                max_activations = license_data['max_activations']
                status = license_data['status']
                
                tags = ()
                if status == 'active':
                    tags = ('active',)
                elif status == 'expired':
                    tags = ('expired',)
                elif status == 'revoked':
                    tags = ('revoked',)
                
                self.license_tree.insert("", tk.END, 
                                       values=(
                                           license_data['id'],
                                           license_data['key'][:20] + "...",
                                           created,
                                           expires,
                                           status.upper(),
                                           f"{activations}/{max_activations}"
                                       ),
                                       tags=tags)
    
    def on_license_select(self, event):
        """Обработчик выбора лицензии"""
        selection = self.license_tree.selection()
        if selection:
            item = self.license_tree.item(selection[0])
            license_id = item['values'][0]
            
            # Находим лицензию
            for license_data in self.licenses:
                if license_data['id'] == license_id:
                    self.current_license = license_data
                    
                    # Показываем полный ключ
                    self.key_preview.delete(1.0, tk.END)
                    self.key_preview.insert(tk.END, license_data['key'])
                    break
    
    def view_license_details(self):
        """Показывает детальную информацию о лицензии"""
        if not self.current_license:
            messagebox.showwarning("Warning", "No license selected")
            return
        
        details_window = tk.Toplevel(self.root)
        details_window.title("License Details")
        details_window.geometry("500x600")
        details_window.configure(bg='#000000')
        details_window.resizable(False, False)
        
        # Центрирование
        details_window.update_idletasks()
        width = details_window.winfo_width()
        height = details_window.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        details_window.geometry(f'{width}x{height}+{x}+{y}')
        
        # Заголовок
        tk.Label(details_window, text="LICENSE DETAILS", 
                font=(self.code_font, 16, 'bold'), fg='#00ff00', bg='#000000').pack(pady=20)
        
        # Детали
        details_frame = tk.Frame(details_window, bg='#111111', padx=20, pady=20)
        details_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        license_data = self.current_license
        
        details = [
            ("ID:", str(license_data['id'])),
            ("License Key:", license_data['key']),
            ("Created:", datetime.fromisoformat(license_data['created']).strftime("%Y-%m-%d %H:%M:%S")),
            ("Expires:", datetime.fromisoformat(license_data['expires']).strftime("%Y-%m-%d %H:%M:%S")),
            ("Status:", license_data['status'].upper()),
            ("Max Activations:", str(license_data['max_activations'])),
            ("Current Activations:", str(len(license_data['activations']))),
            ("Notes:", license_data.get('notes', 'None'))
        ]
        
        for label, value in details:
            frame = tk.Frame(details_frame, bg='#111111')
            frame.pack(fill=tk.X, pady=5)
            
            tk.Label(frame, text=label, font=(self.code_font, 10),
                    fg='#cccccc', bg='#111111', width=20, anchor='w').pack(side=tk.LEFT)
            
            if label == "License Key:":
                text_widget = tk.Text(frame, height=3, width=30,
                                     bg='#222222', fg='#00ff00',
                                     font=(self.code_font, 9), wrap=tk.WORD)
                text_widget.insert(tk.END, value)
                text_widget.config(state=tk.DISABLED)
                text_widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            else:
                tk.Label(frame, text=value, font=(self.code_font, 10),
                        fg='#00ff00', bg='#111111', anchor='w').pack(side=tk.LEFT)
        
        # Активации
        if license_data['activations']:
            tk.Label(details_frame, text="Activation History:", 
                    font=(self.code_font, 10, 'bold'),
                    fg='#cccccc', bg='#111111').pack(anchor=tk.W, pady=(20, 5))
            
            activations_text = tk.Text(details_frame, height=5,
                                      bg='#222222', fg='#cccccc',
                                      font=(self.code_font, 8))
            activations_text.pack(fill=tk.X)
            
            for activation in license_data['activations']:
                activations_text.insert(tk.END, f"{activation}\n")
            activations_text.config(state=tk.DISABLED)
        
        # Кнопки управления
        button_frame = tk.Frame(details_window, bg='#000000')
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="REVOKE LICENSE", 
                 font=(self.code_font, 10, 'bold'),
                 bg='#2a2a2a', fg='#ffaa00',
                 command=self.revoke_license).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="EXTEND LICENSE", 
                 font=(self.code_font, 10),
                 bg='#2a2a2a', fg='#00ff00',
                 command=self.extend_license).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="CLOSE", 
                 font=(self.code_font, 10),
                 bg='#2a2a2a', fg='#cccccc',
                 command=details_window.destroy).pack(side=tk.LEFT, padx=5)
    
    def revoke_license(self):
        """Отзывает лицензию"""
        if not self.current_license:
            return
        
        if messagebox.askyesno("Confirm", "Are you sure you want to revoke this license?"):
            self.current_license['status'] = 'revoked'
            self.update_license_list()
            self.save_licenses()
            self.status_label.config(text="● LICENSE REVOKED", fg='#ffaa00')
    
    def extend_license(self):
        """Продлевает лицензию"""
        if not self.current_license:
            return
        
        extend_window = tk.Toplevel(self.root)
        extend_window.title("Extend License")
        extend_window.geometry("300x200")
        extend_window.configure(bg='#000000')
        
        tk.Label(extend_window, text="Extend by (days):", 
                font=(self.code_font, 11), fg='#cccccc', bg='#000000').pack(pady=20)
        
        days_var = tk.IntVar(value=30)
        days_spin = tk.Spinbox(extend_window, from_=1, to=365, 
                              textvariable=days_var, font=(self.code_font, 11),
                              bg='#222222', fg='#ffffff', width=10)
        days_spin.pack()
        
        def apply_extension():
            days = days_var.get()
            current_expiry = datetime.fromisoformat(self.current_license['expires'])
            new_expiry = current_expiry + timedelta(days=days)
            self.current_license['expires'] = new_expiry.isoformat()
            
            if self.current_license['status'] == 'expired':
                self.current_license['status'] = 'active'
            
            self.update_license_list()
            self.save_licenses()
            extend_window.destroy()
            
            self.status_label.config(text=f"● EXTENDED BY {days} DAYS", fg='#00ff00')
            messagebox.showinfo("Success", f"License extended by {days} days")
        
        tk.Button(extend_window, text="APPLY", 
                 font=(self.code_font, 10, 'bold'),
                 bg='#2a2a2a', fg='#00ff00',
                 command=apply_extension).pack(pady=20)
    
    def delete_license(self):
        """Удаляет выбранную лицензию"""
        if not self.current_license:
            messagebox.showwarning("Warning", "No license selected")
            return
        
        if messagebox.askyesno("Confirm Delete", 
                              "Are you sure you want to delete this license?\nThis action cannot be undone."):
            # Удаляем лицензию из списка
            self.licenses = [l for l in self.licenses if l['id'] != self.current_license['id']]
            self.current_license = None
            
            # Обновляем список
            self.update_license_list()
            
            # Очищаем превью
            self.key_preview.delete(1.0, tk.END)
            
            # Сохраняем изменения
            self.save_licenses()
            
            self.status_label.config(text="● LICENSE DELETED", fg='#ff4444')
    
    def export_licenses(self):
        """Экспортирует лицензии в файл"""
        from tkinter import filedialog
        
        if not self.licenses:
            messagebox.showwarning("Warning", "No licenses to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"licenses_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.licenses, f, indent=2, default=str)
                
                self.status_label.config(text="● LICENSES EXPORTED", fg='#00ff00')
                messagebox.showinfo("Success", f"Licenses exported to:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export licenses: {str(e)}")
    
    def import_licenses(self):
        """Импортирует лицензии из файла"""
        from tkinter import filedialog
        
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    imported_licenses = json.load(f)
                
                # Находим максимальный ID
                max_id = max([l['id'] for l in self.licenses], default=0)
                for license_data in imported_licenses:
                    if license_data['id'] <= max_id:
                        license_data['id'] = max_id + 1
                        max_id += 1
                
                # Добавляем лицензии
                self.licenses.extend(imported_licenses)
                
                # Обновляем счетчик
                self.key_counter = max([l['id'] for l in self.licenses], default=0) + 1
                
                # Обновляем список
                self.update_license_list()
                
                # Сохраняем
                self.save_licenses()
                
                self.status_label.config(text="● LICENSES IMPORTED", fg='#00ff00')
                messagebox.showinfo("Success", f"Imported {len(imported_licenses)} licenses")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import licenses: {str(e)}")
    
    def save_licenses(self):
        """Сохраняет лицензии в файл"""
        try:
            data = {
                'licenses': self.licenses,
                'key_counter': self.key_counter,
                'settings': self.settings
            }
            
            with open('licenses_database.json', 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            # Обновляем настройки
            for key, var in self.setting_widgets.items():
                self.settings[key] = var.get()
            self.settings['auto_save'] = self.auto_save_var.get()
            
            self.save_config()
            
        except Exception as e:
            print(f"Save error: {e}")
    
    def load_licenses(self):
        """Загружает лицензии из файла"""
        try:
            if os.path.exists('licenses_database.json'):
                with open('licenses_database.json', 'r') as f:
                    data = json.load(f)
                
                self.licenses = data.get('licenses', [])
                self.key_counter = data.get('key_counter', 1)
                
                # Обновляем список
                self.update_license_list()
                
        except Exception as e:
            print(f"Load error: {e}")
    
    def save_config(self):
        """Сохраняет конфигурацию"""
        try:
            config = {
                'settings': self.settings,
                'window_geometry': self.root.geometry()
            }
            
            with open('generator_config.json', 'w') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            print(f"Config save error: {e}")
    
    def load_config(self):
        """Загружает конфигурацию"""
        try:
            if os.path.exists('generator_config.json'):
                with open('generator_config.json', 'r') as f:
                    config = json.load(f)
                
                self.settings.update(config.get('settings', {}))
                
                # Восстанавливаем геометрию окна
                geometry = config.get('window_geometry')
                if geometry:
                    self.root.geometry(geometry)
                    
        except Exception as e:
            print(f"Config load error: {e}")
    
    def on_closing(self):
        """Обработчик закрытия окна"""
        self.save_licenses()
        self.save_config()
        self.root.destroy()

def main():
    root = tk.Tk()
    
    app = LicenseGenerator(root)
    
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    print("=" * 70)
    print("Snos Tool - License Generator v2.0")
    print("Admin Panel - For authorized personnel only")
    print("=" * 70)
    
    root.mainloop()

if __name__ == "__main__":
    main()