import os
import re
import json
import random
import asyncio
import aiohttp
import gc
from datetime import datetime, timedelta, timezone
import urllib.parse
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTH_FILE = "auth.json"
LINKED_FILE = "linked_accounts.json"
FILTERS_FILE = "user_filters.json"
URL_BOOK = "https://jget-events.ru/api/bookings/"
URL_LOGIN = "https://jget-events.ru/api/login/"
URL_PROFILE = "https://jget-events.ru/api/profile/"

PAYOUT_PLAYER = 517
PAYOUT_LEADER = 1500
ADMIN_ID = 6871586046

URL_CURRENT = "https://jget-events.ru/api/events/"
URL_NEXT = "https://jget-events.ru/api/events/"

DIFFICULTY_DATA = {
    "Бриллианты": {1: 35, 2: 80, 3: 65, 4: 45, 5: 25, 6: 30, 7: 55, 8: 20},
    "Сокровища": {1: 25, 2: 20, 3: 30, 4: 40, 5: 30, 6: 45, 7: 15, 8: 50},
    "ПДД квест": {1: 75, 2: 55, 3: 65, 4: 35, 5: 50, 6: 40, 7: 35, 8: 15, 9: 35},
    "Дружба": {1: 40, 2: 25, 3: 45, 4: 30, 5: 35, 6: 20, 7: 25, 8: 30, 9: 35, 10: 30},
    "Школьный спасатель": {1: 55, 2: 65, 3: 45, 4: 50, 5: 30, 6: 70, 7: 35, 8: 40, 9: 20}
}



STATIONS_MAP = {
    "Первая": 1, "Вторая": 2, "Третья": 3, "Четвёртая": 4, "Четвертая": 4,
    "Пятая": 5, "Шестая": 6, "Седьмая": 7, "Восьмая": 8, "Девятая": 9, "Десятая": 10
}

MONTHS_RU = {1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн", 7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"}
DAYS_RU = {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"}

BOT_MESSAGE_ID = {}
USER_LINK_STATE = {}
TEMP_AUTO_BOOKINGS = {}

GLOBAL_CACHED_DATA = None
router = Router()

async def edit_or_send(bot: Bot, chat_id: int, text: str, reply_markup=None, parse_mode="Markdown", disable_web_page_preview=True):
    msg_id = BOT_MESSAGE_ID.get(chat_id)
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=text, reply_markup=reply_markup, parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [edit_or_send] Не удалось изменить сообщение {msg_id}: {e}")
    try:
        msg = await bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        BOT_MESSAGE_ID[chat_id] = msg.message_id
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [edit_or_send] Не удалось отправить новое сообщение: {e}")


def load_linked_accounts():
    if not os.path.exists(LINKED_FILE):
        return {}
    try:
        with open(LINKED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_linked_accounts(data):
    with open(LINKED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_all_filters():
    if not os.path.exists(FILTERS_FILE):
        return {}
    try:
        with open(FILTERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_all_filters(data):
    try:
        with open(FILTERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass



def get_auto_booking_settings(chat_id):
    filters = load_all_filters()
    cid_str = str(chat_id)
    if cid_str not in filters:
        filters[cid_str] = {}
    user_f = filters[cid_str]
    if "auto_booking_active" not in user_f:
        user_f["auto_booking_active"] = False
    if "auto_booking_schools" not in user_f:
        user_f["auto_booking_schools"] = []
    if "auto_booking_stations" not in user_f:
        user_f["auto_booking_stations"] = {}
    return user_f

def save_auto_booking_settings(chat_id, settings):
    filters = load_all_filters()
    cid_str = str(chat_id)
    filters[cid_str] = settings
    save_all_filters(filters)

def is_linked(chat_id):
    accounts = load_linked_accounts()
    return str(chat_id) in accounts

def get_linked_account(chat_id):
    accounts = load_linked_accounts()
    return accounts.get(str(chat_id))

def normalize_phone(raw):
    digits = re.sub(r'\D', '', raw.strip())
    if len(digits) == 10:
        digits = '7' + digits
    if len(digits) == 11 and digits[0] == '8':
        digits = '7' + digits[1:]
    return digits


SCHEDULER_FILE = "scheduler_config.json"

def load_scheduler_config():
    if not os.path.exists(SCHEDULER_FILE):
        return {"active": False, "last_run_date": ""}
    try:
        with open(SCHEDULER_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"active": False, "last_run_date": ""}

def save_scheduler_config(cfg):
    try:
        with open(SCHEDULER_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

CONFIRMED_FILE = "confirmed_auto_bookings.json"

def load_confirmed_bookings():
    if not os.path.exists(CONFIRMED_FILE):
        return {}
    try:
        with open(CONFIRMED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_confirmed_bookings(data):
    try:
        with open(CONFIRMED_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_msk_now():
    tz_msk = timezone(timedelta(hours=3))
    return datetime.now(tz_msk)



def get_station_num(name_str):
    if not name_str: return 0
    match = re.search(r'\d+', name_str)
    if match:
        return int(match.group(0))
    name_lower = name_str.lower()
    for word, num in STATIONS_MAP.items():
        if word.lower() in name_lower:
            return num
    return 0

def format_school_name(raw_title):
    if not raw_title: 
        return ""
    title_lower = raw_title.lower()
    if "адымнар" in title_lower:
        return "Адымнар"
    match_num = re.search(r'\d+', raw_title)
    num_str = match_num.group(0) if match_num else ""
    if "пролицей" in title_lower:
        type_str = "Пролицей"
    elif "лицей" in title_lower:
        type_str = "Лицей"
    elif "гимназия" in title_lower:
        type_str = "Гимназия"
    else:
        type_str = "Школа"
    if num_str:
        return f"{type_str} №{num_str}"
    return raw_title

def clean_category_name(raw_name):
    name_lower = raw_name.lower()
    if "спасатель" in name_lower or "спас" in name_lower:
        return "Спасатель"
    if "первых" in name_lower or "дружб" in name_lower or "перв" in name_lower:
        return "Дружба"
    if "пдд" in name_lower:
        return "ПДД"
    if "сокр" in name_lower:
        return "Сокровища"
    if "брилл" in name_lower:
        return "Бриллианты"
    return raw_name

def format_category_link(raw_name):
    cat_clean = clean_category_name(raw_name)
    links = {
        "ПДД": "https://t.me/+kVpp9O_zG5NiNmYy",
        "Спасатель": "https://t.me/+F9tjTvQySNhiOTM6",
        "Дружба": "https://t.me/+CKJhCn8uue43NDNi",
        "Сокровища": "https://t.me/+zm3hNS-6WXU4YWVi",
        "Бриллианты": "https://t.me/+YG7BrGbZwq80ZTUy"
    }
    link = links.get(cat_clean)
    if link:
        return f"[{cat_clean}]({link})"
    return f"*{cat_clean}*"

def normalize_category(event_type_name, title=""):
    name_lower = event_type_name.lower()
    title_lower = title.lower()
    if "дружба" in name_lower or "дружба" in title_lower or "перв" in name_lower:
        return "Дружба"
    if "спас" in name_lower:
        return "Школьный спасатель"
    if "брилл" in name_lower:
        return "Бриллианты"
    if "сокр" in name_lower:
        return "Сокровища"
    if "пдд" in name_lower:
        return "ПДД квест"
    return event_type_name

def get_user_stats(site_name, events_list):
    current_time = datetime.now()
    user_name_lower = site_name.strip().lower()
    completed_player = 0
    completed_leader = 0
    lates = 0
    player_lates = 0
    total_minutes = 0
    history = []
    
    for event in events_list:
        raw_cat = event.get("event_type_name", "")
        school = format_school_name(event.get("title", ""))
        date_str = event.get("date", "")
        
        user_p = None
        for p in event.get("participants", []):
            p_name = f"{p['first_name']} {p['last_name']}".strip()
            if p_name.lower() == user_name_lower:
                user_p = p
                break
        if not user_p:
            continue
            
        quest_mins = 65
        try:
            ts = datetime.strptime(event.get("start_time")[:8], "%H:%M:%S")
            te = datetime.strptime(event.get("end_time")[:8], "%H:%M:%S")
            diff_mins = (te - ts).total_seconds() / 60
            if diff_mins > 0:
                quest_mins = diff_mins
        except Exception:
            pass
        total_work_mins = quest_mins + 40
        
        is_completed = False
        try:
            full_end_str = f"{date_str} {event.get('end_time', '23:59:59')[:8]}"
            event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
            if event_end_dt <= current_time:
                is_completed = True
        except Exception:
            pass
            
        as_leader = user_p.get("as_leader")
        attended = user_p.get("attended", True)
        late = user_p.get("late", False)
        
        st_obj = user_p.get("station")
        st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
        st_num = get_station_num(st_name)
        role = "Главарь" if as_leader else (f"Станция {st_num}" if st_num else "Без позиции")
        
        if is_completed:
            if attended:
                if as_leader:
                    completed_leader += 1
                    total_minutes += total_work_mins
                else:
                    completed_player += 1
                    total_minutes += total_work_mins
                if late:
                    lates += 1
                    if not as_leader:
                        player_lates += 1
                        
        hist_item = f"• {date_str} | {clean_category_name(raw_cat)} — *{role}* ({school})"
        if is_completed and attended and late:
            hist_item += " ⚠️ (Опоздание)"
        history.append(hist_item)
        
    history = sorted(history)
    return {
        "completed_player": completed_player,
        "completed_leader": completed_leader,
        "lates": lates,
        "player_lates": player_lates,
        "total_hours": round(total_minutes / 60, 1),
        "history": history
    }



def load_cookies_from_auth():
    if not os.path.exists(AUTH_FILE):
        return None
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
        cookies = {}
        if isinstance(auth_data, dict) and "cookies" in auth_data:
            for cookie in auth_data["cookies"]:
                cookies[cookie["name"]] = cookie["value"]
        return cookies
    except Exception:
        return None

def clean_event_for_cache(event):
    cleaned = {
        "id": event.get("id"),
        "date": event.get("date"),
        "title": event.get("title"),
        "start_time": event.get("start_time"),
        "end_time": event.get("end_time"),
        "event_type_name": event.get("event_type_name"),
    }
    
    participants = []
    for p in event.get("participants", []):
        cleaned_p = {
            "first_name": p.get("first_name", ""),
            "last_name": p.get("last_name", ""),
            "as_leader": p.get("as_leader"),
            "attended": p.get("attended", True),
            "late": p.get("late", False),
        }
        st = p.get("station")
        if isinstance(st, dict):
            cleaned_p["station"] = {"name": st.get("name", "")}
        else:
            cleaned_p["station"] = None
        participants.append(cleaned_p)
    cleaned["participants"] = participants
    
    avail_stations = []
    for s in event.get("available_stations", []):
        avail_stations.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "is_available": s.get("is_available")
        })
    cleaned["available_stations"] = avail_stations
    
    return cleaned

async def fetch_all_data():
    cookies = load_cookies_from_auth()
    if not cookies:
        return None, "Файл auth.json отсутствует или поврежден."
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jget-events.ru/events/?tab=current"
    }
    async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
        try:
            async with session.get(URL_CURRENT, params={"tab": "current"}, timeout=10) as r1:
                if r1.status != 200:
                    return None, f"Ошибка API (current): статус {r1.status}"
                res1 = await r1.json()
            async with session.get(URL_NEXT, params={"tab": "next"}, timeout=10) as r2:
                if r2.status != 200:
                    return None, f"Ошибка API (next): статус {r2.status}"
                res2 = await r2.json()
            
            merged = {e["id"]: e for e in (res1 + res2)}.values()
            cleaned = [clean_event_for_cache(e) for e in merged]
            
            # Explicitly collect garbage to free memory immediately after parsing large JSON responses
            gc.collect()
            
            return cleaned, None
        except Exception as e:
            return None, f"Ошибка выполнения HTTP-запроса: {e}"

async def api_login(phone, password):
    """Попытка авторизации на jget-events.ru. Возвращает (token, name, error)."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [api_login] Попытка входа для телефона {phone}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://jget-events.ru/login/"
    }
    payload = {"username": phone, "password": password}
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.post(URL_LOGIN, json=payload, timeout=10) as r:
                status = r.status
                body_text = await r.text()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [api_login] Ответ сервера:")
                print(f"  └ Status: {status}")
                print(f"  └ Body: {body_text}")
                if status == 200:
                    try:
                        data = json.loads(body_text)
                    except Exception:
                        data = {}
                    token = data.get("token", "")
                    first = data.get("first_name", "")
                    last = data.get("last_name", "")
                    name = f"{first} {last}".strip()
                    return token, name, None
                else:
                    return None, None, "Неверный номер телефона или пароль."
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [api_login] Исключение при запросе:")
            print(tb)
            return None, None, f"Ошибка подключения: {e}"

async def api_get_profile(token):
    """Получить профиль с сайта."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Token {token}"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(URL_PROFILE, timeout=10) as r:
                if r.status == 200:
                    return await r.json(), None
                return None, f"Статус {r.status}"
        except Exception as e:
            return None, str(e)



async def background_cache_updater():
    global GLOBAL_CACHED_DATA
    while True:
        data, err = await fetch_all_data()
        if not err and data:
            GLOBAL_CACHED_DATA = data
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Глобальный кэш успешно обновлен.")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка фонового обновления: {err}")
        
        # Periodic garbage collection to ensure minimized RAM footprint
        gc.collect()
        await asyncio.sleep(30)

async def background_weekday_autobooking_loop(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Фоновый перехват автозаписи запущен.")
    while True:
        try:
            now_msk = get_msk_now()
            # Weekdays are Monday to Friday (0 to 4)
            if now_msk.weekday() < 5 and GLOBAL_CACHED_DATA:
                linked = load_linked_accounts()
                target_users = [6871586046, 7932533408, 8556418483]
                for cid in target_users:
                    cid_str = str(cid)
                    if cid_str not in linked:
                        continue
                    settings = get_auto_booking_settings(cid)
                    if not settings.get("auto_booking_active", False):
                        continue
                    
                    user_schools = settings.get("auto_booking_schools", [])
                    user_stations = settings.get("auto_booking_stations", {})
                    
                    _, token = load_account_auth_by_chat_id(cid)
                    if not token:
                        continue
                        
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "application/json, text/plain, */*",
                        "Authorization": f"Token {token}"
                    }
                    
                    now = datetime.now()
                    async with aiohttp.ClientSession(headers=headers) as session:
                        for ev in GLOBAL_CACHED_DATA:
                            ev_date_str = ev.get("date", "")
                            try:
                                ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d")
                                if ev_date.date() < now.date():
                                    continue
                            except Exception:
                                continue
                                
                            title = ev.get("title", "")
                            school_name = format_school_name(title)
                            if user_schools and school_name not in user_schools:
                                continue
                                
                            raw_cat = ev.get("event_type_name", "")
                            cat = normalize_category(raw_cat, title)
                            clean_cat = clean_category_name(cat)
                            
                            allowed_nums = user_stations.get(clean_cat, [])
                            if not allowed_nums:
                                continue
                                
                            for s in ev.get("available_stations", []):
                                if s.get("is_available"):
                                    num = get_station_num(s.get("name"))
                                    if num in allowed_nums:
                                        payload = {"event": ev.get("id"), "station": s.get("id")}
                                        try:
                                            async with session.post(URL_BOOK, json=payload, timeout=5) as r:
                                                if r.status in [200, 201]:
                                                    try:
                                                        dt = datetime.strptime(ev_date_str, "%Y-%m-%d")
                                                        day_w = DAYS_RU.get(dt.weekday(), "")
                                                        mon = MONTHS_RU.get(dt.month, "")
                                                        date_fmt = f"{dt.day} {mon} ({day_w})"
                                                    except Exception:
                                                        date_fmt = ev_date_str
                                                    
                                                    alert_text = (
                                                        f"🤖 *АВТОЗАПИСЬ: УСПЕШНЫЙ ПЕРЕХВАТ!* 🚀\n\n"
                                                        f"Бот автоматически перехватил и записал вас на смену:\n"
                                                        f"📅 *{date_fmt}* | ⏱️ *{ev.get('start_time')[:5]}-{ev.get('end_time')[:5]}*\n"
                                                        f"🏫 Школа: *{school_name}*\n"
                                                        f"🎯 {clean_cat} | Станция {num}"
                                                    )
                                                    await bot.send_message(chat_id=cid, text=alert_text, parse_mode="Markdown")
                                                elif r.status == 400:
                                                    pass
                                        except Exception as e:
                                            print(f"[!] Error in background booking: {e}")
                                        await asyncio.sleep(0.5)
        except Exception as ex:
            print(f"[!] Error in background weekday loop: {ex}")
        await asyncio.sleep(30)

def get_main_menu(chat_id=None):
    builder = InlineKeyboardBuilder()
    if chat_id and chat_id in [6871586046, 7932533408, 8556418483]:
        builder.row(
            InlineKeyboardButton(text="🤖 Автозапись", callback_data="auto_booking_menu")
        )
    if chat_id and chat_id == ADMIN_ID:
        builder.row(
            InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")
        )
    if chat_id and is_linked(chat_id):
        builder.row(
            InlineKeyboardButton(text="👤 Профиль", callback_data="user_profile")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔗 Привязать аккаунт", callback_data="link_start")
        )
    return builder.as_markup()

def get_back_btn(target="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data=target)]])

def get_onboarding_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔗 Привязать аккаунт", callback_data="link_start"))
    builder.row(
        InlineKeyboardButton(text="👤 Войти гостем", callback_data="link_skip"),
        InlineKeyboardButton(text="❓ Зачем это?", callback_data="link_why")
    )
    return builder.as_markup()

@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message):
    cid = message.chat.id
    user = message.from_user
    if user:
        username = f"@{user.username}" if user.username else "нет username"
        fullname = f"{user.first_name or ''} {user.last_name or ''}".strip()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Бот запущен пользователем: ID: {user.id} | TG: {username} | Имя: {fullname}")
    USER_LINK_STATE.pop(cid, None)
    if message.chat.type == "private":
        try: await message.delete()
        except Exception: pass
    if is_linked(cid):

        msg = await message.answer(
            "🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
            parse_mode="Markdown", reply_markup=get_main_menu(cid)
        )
        BOT_MESSAGE_ID[cid] = msg.message_id
    else:
        msg = await message.answer(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт сайта jget-events.ru чтобы получить полный доступ "
            "к автоматической записи, уведомлениям и управлению профилем.\n\n"
            "Выберите действие:",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )
        BOT_MESSAGE_ID[cid] = msg.message_id

@router.callback_query(F.data == "link_start")
async def handle_link_start(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE[cid] = "waiting_credentials"
    await callback.message.edit_text(
        "🔗 *ПРИВЯЗКА АККАУНТА*\n\n"
        "Отправьте данные от аккаунта jget-events.ru в одном сообщении:\n\n"
        "📱 Первая строка — *номер телефона*\n"
        "🔑 Вторая строка — *пароль*\n\n"
        "Пример:\n"
        "`+79261234567`\n"
        "`мойпароль123`\n\n"
        "📌 _Номер можно писать в любом формате: +7, 8, или просто цифры_",
        parse_mode="Markdown", reply_markup=get_back_btn("link_back_onboarding")
    )

@router.callback_query(F.data == "link_back_onboarding")
async def handle_link_back_onboarding(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE.pop(cid, None)
    if is_linked(cid):
        await callback.message.edit_text(
            "🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
            parse_mode="Markdown", reply_markup=get_main_menu(cid)
        )
    else:
        await callback.message.edit_text(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт сайта jget-events.ru чтобы получить полный доступ "
            "к автоматической записи, уведомлениям и управлению профилем.\n\n"
            "Выберите действие:",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )

@router.callback_query(F.data == "link_skip")
async def handle_link_skip(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE.pop(cid, None)
    await callback.message.edit_text(
        "🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
        parse_mode="Markdown", reply_markup=get_main_menu(cid)
    )

@router.callback_query(F.data == "link_why")
async def handle_link_why(callback: CallbackQuery):
    cid = callback.message.chat.id
    await callback.message.edit_text(
        "❓ *ЗАЧЕМ ПРИВЯЗЫВАТЬ АККАУНТ?*\n\n"
        "Привязка аккаунта jget-events.ru открывает мощные возможности:\n\n"
        "1️⃣ *Мгновенная запись на пачки квестов*\n"
        " └ Записывайтесь на целые комбо-маршруты одной кнопкой — быстрее всех, благодаря нашему продвинутому боту.\n\n"
        "2️⃣ *Защита данных от ОСИНТ-запросов*\n"
        " └ Скройте свою информацию от поисковых запросов других пользователей. "
        "Вместо досье мы покажем, что вы привязали аккаунт и скрыли данные.\n\n"
        "3️⃣ *Умные уведомления*\n"
        " └ Автоматические напоминания за 1 час 30 минут до начала квеста, "
        "чтобы вы точно не опоздали и не забыли.\n\n"
        "🔒 _Ваши данные хранятся локально и используются только для работы с сайтом._",
        parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
    )

@router.callback_query(F.data == "link_confirm_yes")
async def handle_link_confirm_yes(callback: CallbackQuery):
    cid = callback.message.chat.id
    state = USER_LINK_STATE.get(cid, "")
    if not state.startswith("confirming:"):
        await callback.answer("Сессия истекла. Начните заново.", show_alert=True)
        return
    parts = state.split(":", 4)

    name = parts[1]
    phone = parts[2]
    password = parts[3]
    token = parts[4]
    conducted = 0
    cancelled = 0
    profile_data, err = await api_get_profile(token)
    if profile_data:
        stats = profile_data.get("stats", {})
        user_info = profile_data.get("user", {})
        conducted = stats.get("conducted", user_info.get("conducted_count", 0))
        cancelled = stats.get("cancellations", user_info.get("cancellation_count", 0))
    accounts = load_linked_accounts()
    accounts[str(cid)] = {
        "phone": phone,
        "password": password,
        "token": token,
        "name": name,
        "conducted": conducted,
        "cancelled": cancelled
    }
    save_linked_accounts(accounts)
    USER_LINK_STATE.pop(cid, None)
    await callback.message.edit_text(
        f"✅ *Аккаунт успешно привязан!*\n\n"
        f"👤 Привет, *{name}*!\n"
        f"Теперь тебе доступны все функции бота: автоматическая запись, "
        f"уведомления за 1.5 часа и управление профилем.\n\n"
        f"🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:",
        parse_mode="Markdown", reply_markup=get_main_menu(cid)
    )

@router.callback_query(F.data == "link_confirm_no")
async def handle_link_confirm_no(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE[cid] = "waiting_credentials"
    await callback.message.edit_text(
        "🔗 *ПРИВЯЗКА АККАУНТА*\n\n"
        "Похоже, это не ваш аккаунт. Попробуйте ввести данные ещё раз:\n\n"
        "📱 Первая строка — *номер телефона*\n"
        "🔑 Вторая строка — *пароль*\n\n"
        "Пример:\n"
        "`+79261234567`\n"
        "`мойпароль123`",
        parse_mode="Markdown", reply_markup=get_back_btn("link_back_onboarding")
    )



@router.callback_query(F.data == "user_profile")
async def handle_user_profile(callback: CallbackQuery):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return

    phone_raw = acc.get("phone", "")
    if len(phone_raw) == 11:
        phone_fmt = f"+{phone_raw[0]} ({phone_raw[1:4]}) {phone_raw[4:7]}-{phone_raw[7:9]}-{phone_raw[9:11]}"
    else:
        phone_fmt = phone_raw

    tg_user = callback.from_user
    tg_username = f"@{tg_user.username}" if tg_user.username else "не указан"
    tg_id = tg_user.id
    tg_name = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip()

    site_name = acc.get("name", "Неизвестно")
    token = acc.get("token")
    conducted = acc.get("conducted", 0)
    cancelled = acc.get("cancelled", 0)
    
    if token:
        profile_data, _ = await api_get_profile(token)
        if profile_data:
            stats = profile_data.get("stats", {})
            user_info = profile_data.get("user", {})
            conducted = stats.get("conducted", user_info.get("conducted_count", 0))
            cancelled = stats.get("cancellations", user_info.get("cancellation_count", 0))
            # Save live stats locally
            accounts = load_linked_accounts()
            if str(cid) in accounts:
                accounts[str(cid)]["conducted"] = conducted
                accounts[str(cid)]["cancelled"] = cancelled
                save_linked_accounts(accounts)

    lates = 0
    player_lates = 0
    total_hours = 0.0
    stats = None
    if GLOBAL_CACHED_DATA:
        stats = get_user_stats(site_name, GLOBAL_CACHED_DATA)
        lates = stats["lates"]
        player_lates = stats["player_lates"]
        total_hours = stats["total_hours"]

    site_extra = f"\n📊 Проведено: *{conducted}* | Отмен: *{cancelled}* | ⏰ Опозданий: *{lates}* | ⏳ Часов: *{total_hours}*"

    already_earned = conducted * 517
    if stats:
        cached_leader = stats["completed_leader"]
        cached_player = stats["completed_player"]
        total_cached_completed = cached_leader + cached_player
        cached_earned = cached_leader * PAYOUT_LEADER + (cached_player - player_lates) * PAYOUT_PLAYER + player_lates * 400
        outside_shifts = max(0, conducted - total_cached_completed)
        already_earned = cached_earned + outside_shifts * PAYOUT_PLAYER

    expected_earnings = 0
    if GLOBAL_CACHED_DATA:
        current_time = datetime.now()
        for event in GLOBAL_CACHED_DATA:
            date_str = event.get("date", "")
            end_time_str = event.get("end_time", "23:59:59")
            is_completed = False
            try:
                full_end_str = f"{date_str} {end_time_str[:8]}"
                event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
                if event_end_dt <= current_time:
                    is_completed = True
            except Exception:
                try:
                    event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if event_date < current_time.date():
                        is_completed = True
                except Exception:
                    pass
            if not is_completed:
                for p in event.get("participants", []):
                    p_name = f"{p['first_name']} {p['last_name']}".strip()
                    if p_name.lower() == site_name.strip().lower():
                        as_leader = p.get("as_leader")
                        payout = PAYOUT_LEADER if as_leader else PAYOUT_PLAYER
                        expected_earnings += payout

    total_for_month = already_earned + expected_earnings

    text = (
        f"👤 *ПРОФИЛЬ*\n\n"
        f"📛 Имя на сайте: *{site_name}*\n"
        f"💬 Telegram: *{tg_name}* ({tg_username})\n"
        f"🆔 Telegram ID: `{tg_id}`\n"
        f"📞 Телефон: `{phone_fmt}`"
        f"{site_extra}\n\n"
        f"💰 Уже заработано: *{already_earned}* ₽\n"
        f"⏳ В ожидании: *{expected_earnings}* ₽\n"
        f"🔥 Всего за месяц: *{total_for_month}* ₽"
    )
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    has_future_shifts_today = False
    if GLOBAL_CACHED_DATA:
        for event in GLOBAL_CACHED_DATA:
            if event.get("date") == today_str:
                for p in event.get("participants", []):
                    p_name = f"{p['first_name']} {p['last_name']}".strip()
                    if p_name.lower() == site_name.strip().lower():
                        end_time_str = event.get("end_time", "23:59:59")
                        try:
                            full_end_str = f"{today_str} {end_time_str[:8]}"
                            event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
                            if event_end_dt > now:
                                has_future_shifts_today = True
                                break
                        except Exception:
                            has_future_shifts_today = True
                            break
                if has_future_shifts_today:
                    break
    plan_btn_text = "🗺️ План на сегодня" if has_future_shifts_today else "🗺️ План на завтра"

    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_shifts = []
    format_time = lambda t: t[1:5] if t.startswith("0") else t[:5]
    if GLOBAL_CACHED_DATA:
        for event in GLOBAL_CACHED_DATA:
            if event.get("date") == tomorrow_str:
                for p in event.get("participants", []):
                    p_name = f"{p['first_name']} {p['last_name']}".strip()
                    if p_name.lower() == site_name.strip().lower():
                        as_leader = p.get("as_leader")
                        school_name = format_school_name(event.get("title", ""))
                        sch_clean = school_name.lower().replace("№", "").strip()
                        start_time = format_time(event.get("start_time", "00:00:00"))
                        end_time = format_time(event.get("end_time", "23:59:59"))
                        raw_cat = event.get("event_type_name", "")
                        category = clean_category_name(raw_cat).lower()
                        if as_leader:
                            role_str = "главарь"
                        else:
                            st_obj = p.get("station")
                            st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
                            st_num = get_station_num(st_name)
                            role_str = f"{st_num} станция" if st_num else "без позиции"
                        tomorrow_shifts.append((start_time, f"{sch_clean}, {category} {start_time}-{end_time}, {role_str}"))

    plan_button = None
    if has_future_shifts_today:
        plan_button = InlineKeyboardButton(text="🗺️ План на сегодня", callback_data="today_plan")
    elif tomorrow_shifts:
        plan_button = InlineKeyboardButton(text="🗺️ План на завтра", callback_data="today_plan")

    builder = InlineKeyboardBuilder()
    if plan_button:
        builder.row(plan_button)
    builder.row(
        InlineKeyboardButton(text="📜 Лог смен", callback_data="shift_log"),
        InlineKeyboardButton(text="🔑 Мой пароль", callback_data="show_password")
    )
    builder.row(
        InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "today_plan")
async def handle_today_plan(callback: CallbackQuery):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    site_name = acc.get("name", "")
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("⚠️ Внутренний кэш базы данных пуст. Ожидайте прогрузки...", reply_markup=get_back_btn("user_profile"))
        return
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    has_future_shifts_today = False
    for event in GLOBAL_CACHED_DATA:
        if event.get("date") == today_str:
            for p in event.get("participants", []):
                p_name = f"{p['first_name']} {p['last_name']}".strip()
                if p_name.lower() == site_name.strip().lower():
                    end_time_str = event.get("end_time", "23:59:59")
                    try:
                        full_end_str = f"{today_str} {end_time_str[:8]}"
                        event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
                        if event_end_dt > now:
                            has_future_shifts_today = True
                            break
                    except Exception:
                        has_future_shifts_today = True
                        break
            if has_future_shifts_today:
                break
    target_date_str = today_str if has_future_shifts_today else (now + timedelta(days=1)).strftime("%Y-%m-%d")
    is_today = (target_date_str == today_str)
    target_shifts = []
    total_profit = 0
    for event in GLOBAL_CACHED_DATA:
        if event.get("date") == target_date_str:
            for p in event.get("participants", []):
                p_name = f"{p['first_name']} {p['last_name']}".strip()
                if p_name.lower() == site_name.strip().lower():
                    as_leader = p.get("as_leader")
                    payout = PAYOUT_LEADER if as_leader else PAYOUT_PLAYER
                    if is_today:
                        end_time_str = event.get("end_time", "23:59:59")
                        try:
                            full_end_str = f"{today_str} {end_time_str[:8]}"
                            event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
                            if event_end_dt <= now:
                                continue
                        except Exception:
                            pass
                    total_profit += payout
                    school_name = format_school_name(event.get("title", ""))
                    geo_query = f"https://yandex.ru/maps/?text=Набережные+Челны+{school_name.replace(' ', '+')}"
                    start_time = event.get("start_time", "00:00:00")
                    end_time = event.get("end_time", "23:59:59")
                    raw_cat = event.get("event_type_name", "")
                    category = clean_category_name(raw_cat)
                    if as_leader:
                        role_str = "Главарь"
                        role_display = "Роль: *Главарь*"
                        icon = "👑"
                    else:
                        st_obj = p.get("station")
                        st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
                        st_num = get_station_num(st_name)
                        role_str = f"Станция: {st_num}" if st_num else "Ведущий"
                        role_display = f"Станция: *{st_num}*" if st_num else "*Ведущий*"
                        icon = "⭐"
                    target_shifts.append({
                        "school": school_name,
                        "geo": geo_query,
                        "start_time": start_time,
                        "end_time": end_time,
                        "role": role_str,
                        "role_display": role_display,
                        "icon": icon,
                        "category": category,
                        "raw_cat": raw_cat,
                        "payout": payout
                    })
    if not target_shifts:
        if is_today:
            phrases = [
                "Сегодня смен нет, отдыхай, кайфуй! 🥳",
                "Смен нет, можно спать до обеда! 🛌",
                "Полный релакс, сегодня никаких квестов! 🏖️",
                "Чиллим и отдыхаем, сегодня свободный день! 🍿",
                "Выходной! Время восстановить силы. 🔋",
                "Сегодня твой день без работы, наслаждайся! 🍕",
                "Работы нет, можно заняться своими делами! 🎮",
                "Календарь пуст, кайфуй на всю катушку! 🎉"
            ]
            text = f"🗺️ *МОЙ ПЛАН НА СЕГОДНЯ*\n\n{random.choice(phrases)}"
        else:
            phrases = [
                "Завтра смен нет, отдыхай, кайфуй! 🥳",
                "Завтра смен нет, можно спать до обеда! 🛌",
                "Полный релакс, завтра никаких квестов! 🏖️",
                "Чиллим и отдыхаем, завтра свободный день! 🍿",
                "Выходной! Время восстановить силы. 🔋",
                "Завтра твой день без работы, наслаждайся! 🍕",
                "Работы нет, завтра можно заняться своими делами! 🎮",
                "Завтра календарь пуст, кайфуй на всю катушку! 🎉"
            ]
            text = f"🗺️ *МОЙ ПЛАН НА ЗАВТРА*\n\n{random.choice(phrases)}"
    else:
        target_shifts.sort(key=lambda x: x["start_time"])
        grouped_blocks = []
        for shift in target_shifts:
            if not grouped_blocks:
                grouped_blocks.append([shift])
            else:
                last_block = grouped_blocks[-1]
                if shift["school"] == last_block[-1]["school"]:
                    last_block.append(shift)
                else:
                    grouped_blocks.append([shift])
        blocks_text = []
        num_emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}
        for idx, block in enumerate(grouped_blocks, 1):
            school = block[0]["school"]
            geo = block[0]["geo"]
            category = block[0]["category"]
            start_time = block[0]["start_time"][:5]
            end_time = block[-1]["end_time"][:5]
            roles = [s["role"] for s in block]
            all_same_role = all(r == roles[0] for r in roles)
            num_prefix = num_emojis.get(idx, f"{idx}.")
            if all_same_role:
                time_str = f"⏰ Время: *{start_time} - {end_time}*"
                role_str = f"{block[0]['icon']} {block[0]['role_display']}"
            else:
                time_str = f"⏰ Общее время: *{start_time} - {end_time}*"
                role_lines = ["⭐ Роли по сменам:"]
                for s_idx, s in enumerate(block):
                    connector = " ├ " if s_idx < len(block) - 1 else " └ "
                    role_lines.append(f"  {connector}⏰ *{s['start_time'][:5]} - {s['end_time'][:5]}* — {s['icon']} *{s['role']}*")
                role_str = "\n".join(role_lines)
            block_fmt = (
                f"{num_prefix} **[{school}]({geo})**\n"
                f"🎯 Квест: {format_category_link(block[0]['raw_cat'])}\n"
                f"{time_str}\n"
                f"{role_str}"
            )
            blocks_text.append(block_fmt)
        blocks_joined = "\n\n".join(blocks_text)
        title_word = "СЕГОДНЯ" if is_today else "ЗАВТРА"
        text = (
            f"🗺️ *МОЙ ПЛАН НА {title_word}*\n\n"
            f"{blocks_joined}\n\n"
            f"💰 *Итоговый профит за {'день' if is_today else 'завтрашний день'}:* **{total_profit}** ₽"
        )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_btn("user_profile"), disable_web_page_preview=True)



@router.callback_query(F.data == "show_password")
async def handle_show_password(callback: CallbackQuery, bot: Bot):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    password = acc.get("password", "???")
    pwd_msg = await bot.send_message(
        chat_id=cid,
        text=f"🔑 Ваш пароль:\n\n`{password}`\n\n_Это сообщение будет удалено через 10 секунд..._",
        parse_mode="Markdown"
    )
    await callback.answer("🔑 Пароль отправлен! Исчезнет через 10 сек.", show_alert=False)
    async def delete_later():
        await asyncio.sleep(10)
        try:
            await bot.delete_message(chat_id=cid, message_id=pwd_msg.message_id)
        except Exception:
            pass
    asyncio.create_task(delete_later())



@router.callback_query(F.data == "main_menu")
async def go_to_main_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE.pop(cid, None)
    await callback.message.edit_text("🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
                                     parse_mode="Markdown", reply_markup=get_main_menu(cid))

async def run_saturday_autobooking_precheck(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Saturday Auto-booking Precheck...")
    data, err = await fetch_all_data()
    if err or not data:
        print(f"[!] Precheck error: {err}")
        return
        
    linked = load_linked_accounts()
    target_users = [6871586046, 7932533408, 8556418483]
    
    for cid in target_users:
        cid_str = str(cid)
        if cid_str not in linked:
            continue
        settings = get_auto_booking_settings(cid)
        if not settings.get("auto_booking_active", False):
            continue
            
        user_schools = settings.get("auto_booking_schools", [])
        user_stations = settings.get("auto_booking_stations", {})
        
        matches = []
        now = datetime.now()
        for ev in data:
            ev_date_str = ev.get("date", "")
            try:
                ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d")
                if ev_date.date() < now.date():
                    continue
            except Exception:
                continue
                
            title = ev.get("title", "")
            school_name = format_school_name(title)
            if user_schools and school_name not in user_schools:
                continue
                
            raw_cat = ev.get("event_type_name", "")
            cat = normalize_category(raw_cat, title)
            clean_cat = clean_category_name(cat)
            
            allowed_nums = user_stations.get(clean_cat, [])
            if not allowed_nums:
                continue
                
            for s in ev.get("available_stations", []):
                if s.get("is_available"):
                    num = get_station_num(s.get("name"))
                    if num in allowed_nums:
                        matches.append({
                            "event_id": ev.get("id"),
                            "station_id": s.get("id"),
                            "date": ev_date_str,
                            "time": f"{ev.get('start_time')[:5]}-{ev.get('end_time')[:5]}",
                            "school": school_name,
                            "category": clean_cat,
                            "station_num": num
                        })
                        
        if not matches:
            try:
                await bot.send_message(
                    chat_id=cid,
                    text="🤖 *Автозапись*: На следующую неделю подходящих смен по вашим фильтрам не найдено."
                )
            except Exception:
                pass
            continue
            
        TEMP_AUTO_BOOKINGS[cid] = matches
        
        lines = []
        for idx, m in enumerate(matches, 1):
            try:
                dt = datetime.strptime(m["date"], "%Y-%m-%d")
                day_w = DAYS_RU.get(dt.weekday(), "")
                mon = MONTHS_RU.get(dt.month, "")
                date_fmt = f"{dt.day} {mon} ({day_w})"
            except Exception:
                date_fmt = m["date"]
            lines.append(
                f"{idx}. 📅 {date_fmt} | ⏱️ {m['time']}\n"
                f"   🏫 {m['school']}\n"
                f"   🎯 {m['category']} | Станция {m['station_num']}"
            )
            
        matches_text = "\n\n".join(lines)
        
        if settings.get("auto_booking_mode", "confirm") == "auto":
            message_text = (
                f"🤖 *АВТОЗАПИСЬ (АВТО-РЕЖИМ)*\n\n"
                f"Найдены следующие смены по вашим фильтрам:\n\n"
                f"{matches_text}\n\n"
                f"⚡ Так как у вас включен автоматический режим, бот запишет вас на эти смены ровно в 12:00 без подтверждения."
            )
            try:
                await bot.send_message(
                    chat_id=cid,
                    text=message_text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"[!] Error sending auto preview to {cid}: {e}")
            continue
            
        message_text = (
            f"🤖 *АВТОЗАПИСЬ: ПОДТВЕРЖДЕНИЕ СМЕН*\n\n"
            f"{matches_text}\n\n"
            f"⚠️ Нажмите кнопку ниже до 12:00, чтобы подтвердить автозапись на эти смены. "
            f"При штурме в 12:00 бот автоматически запишет вас."
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✅ Подтвердить автозапись", callback_data="auto_booking_confirm_confirm"))
        try:
            await bot.send_message(
                chat_id=cid,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            print(f"[!] Error sending precheck msg to {cid}: {e}")

async def run_saturday_user_autobooking(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Saturday User Auto-booking Storm...")
    confirmed = load_confirmed_bookings()
    
    # Check for "auto" mode users and find matches live
    linked = load_linked_accounts()
    target_users = [6871586046, 7932533408, 8556418483]
    
    auto_users = []
    for cid in target_users:
        cid_str = str(cid)
        if cid_str not in linked:
            continue
        settings = get_auto_booking_settings(cid)
        if settings.get("auto_booking_active", False) and settings.get("auto_booking_mode", "confirm") == "auto":
            auto_users.append(cid)
            
    if auto_users:
        data, err = await fetch_all_data()
        if data:
            now = datetime.now()
            for cid in auto_users:
                cid_str = str(cid)
                settings = get_auto_booking_settings(cid)
                user_schools = settings.get("auto_booking_schools", [])
                user_stations = settings.get("auto_booking_stations", {})
                matches = []
                for ev in data:
                    ev_date_str = ev.get("date", "")
                    try:
                        ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d")
                        if ev_date.date() < now.date():
                            continue
                    except Exception:
                        continue
                    title = ev.get("title", "")
                    school_name = format_school_name(title)
                    if user_schools and school_name not in user_schools:
                        continue
                    raw_cat = ev.get("event_type_name", "")
                    cat = normalize_category(raw_cat, title)
                    clean_cat = clean_category_name(cat)
                    allowed_nums = user_stations.get(clean_cat, [])
                    if not allowed_nums:
                        continue
                    for s in ev.get("available_stations", []):
                        if s.get("is_available"):
                            num = get_station_num(s.get("name"))
                            if num in allowed_nums:
                                matches.append({
                                    "event_id": ev.get("id"),
                                    "station_id": s.get("id"),
                                    "date": ev_date_str,
                                    "time": f"{ev.get('start_time')[:5]}-{ev.get('end_time')[:5]}",
                                    "school": school_name,
                                    "category": clean_cat,
                                    "station_num": num
                                })
                if matches:
                    confirmed[cid_str] = matches

    if not confirmed:
        print("[!] Confirmed user bookings empty.")
        return
        
    for cid_str, targets in confirmed.items():
        if not targets:
            continue
        try:
            cid = int(cid_str)
        except Exception:
            continue
            
        _, token = load_account_auth_by_chat_id(cid)
        if not token:
            continue
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Token {token}"
        }
        
        async def book_target(session, t):
            payload = {"event": t["event_id"], "station": t["station_id"]}
            book_start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - book_start < 10:
                try:
                    async with session.post(URL_BOOK, json=payload, timeout=5) as r:
                        if r.status in [200, 201]:
                            return True, None
                        elif r.status == 400:
                            res = await r.json()
                            err_msg = res.get("error", "")
                            if "Уже записан" in err_msg:
                                return True, "already"
                            elif "запись закрыта" in err_msg.lower() or "не начата" in err_msg.lower():
                                await asyncio.sleep(0.1)
                                continue
                            else:
                                return False, err_msg
                        else:
                            return False, f"HTTP status {r.status}"
                except Exception:
                    await asyncio.sleep(0.1)
            return False, "Превышено время ожидания"
            
        async with aiohttp.ClientSession(headers=headers) as session:
            results = await asyncio.gather(*[book_target(session, t) for t in targets])
            
            success_count = sum(1 for ok, err in results if ok)
            report_lines = []
            for t, (ok, err) in zip(targets, results):
                status_symbol = "🟢" if ok else "🔴"
                status_reason = "(уже записан)" if err == "already" else (f"({err})" if err else "")
                report_lines.append(
                    f"{status_symbol} {t['date']} {t['time']} | {t['school']} | Станция {t['station_num']} {status_reason}"
                )
                
            report_lines_joined = "\n".join(report_lines)
            report_text = (
                f"🤖 *ОТЧЕТ ОБ АВТОЗАПИСИ (Суббота 12:00)*\n\n"
                f"Бот завершил попытку автозаписи на подтвержденные смены:\n\n"
                f"{report_lines_joined}\n\n"
                f"Записано смен: *{success_count}* из *{len(targets)}*."
            )
            try:
                await bot.send_message(chat_id=cid, text=report_text, parse_mode="Markdown")
            except Exception:
                pass
                
    # Clear confirmed bookings
    save_confirmed_bookings({})

async def saturday_scheduler_loop(bot: Bot):
    while True:
        try:
            cfg = load_scheduler_config()
            now_msk = get_msk_now()
            today_str = now_msk.strftime("%Y-%m-%d")
            
            # 5 is Saturday
            if now_msk.weekday() == 5:
                # 1. Premium Auto-booking Precheck at 11:50
                if now_msk.hour == 11 and now_msk.minute == 50:
                    last_pre = cfg.get("last_precheck_date", "")
                    if last_pre != today_str:
                        cfg["last_precheck_date"] = today_str
                        save_scheduler_config(cfg)
                        asyncio.create_task(run_saturday_autobooking_precheck(bot))
                        
                # 2. Premium Auto-booking Storm at 12:00
                if now_msk.hour == 12 and now_msk.minute == 0:
                    last_user_bk = cfg.get("last_user_booking_date", "")
                    if last_user_bk != today_str:
                        cfg["last_user_booking_date"] = today_str
                        save_scheduler_config(cfg)
                        asyncio.create_task(run_saturday_user_autobooking(bot))
            
        except Exception as e:
            print(f"Ошибка в планировщике: {e}")
        await asyncio.sleep(5)



def load_account_auth_by_chat_id(chat_id):
    acc = get_linked_account(chat_id)
    if not acc:
        return None, None
    token = acc.get("token")
    return {}, token

@router.callback_query(F.data == "auto_booking_menu")
async def handle_auto_booking_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    active = settings.get("auto_booking_active", False)
    status_str = "🟢 АКТИВНА" if active else "🔴 ОТКЛЮЧЕНА"
    mode = settings.get("auto_booking_mode", "confirm")
    
    if mode == "auto":
        desc_text = "Бот автоматически запишет вас на подходящие смены по субботам в 12:00 (и перехватит в будни при их появлении)."
        mode_display = "Автоматический (без подтверждения)"
    else:
        desc_text = "Каждую субботу в 11:50 вы будете получать уведомление со списком найденных смен для подтверждения."
        mode_display = "С подтверждением (11:50)"
        
    schools = settings.get("auto_booking_schools", [])
    schools_str = ", ".join(schools) if schools else "Все школы"
    stations_data = settings.get("auto_booking_stations", {})
    stations_parts = []
    for cat, nums in stations_data.items():
        if nums:
            stations_parts.append(f"{cat}: {', '.join(map(str, sorted(nums)))}")
    stations_str = "; ".join(stations_parts) if stations_parts else "Не выбраны"
    text = (
        f"🤖 *АВТОЗАПИСЬ НА КВЕСТЫ*\n\n"
        f"{desc_text}\n\n"
        f"ℹ️ *Статус автозаписи:* {status_str}\n"
        f"⚙️ *Режим записи:* {mode_display}\n"
        f"🏫 *Целевые школы:* _{schools_str}_\n"
        f"🎯 *Фаворит-станции:* _{stations_str}_\n"
    )
    builder = InlineKeyboardBuilder()
    toggle_btn_text = "🔴 Выключить автозапись" if active else "🟢 Включить автозапись"
    builder.row(InlineKeyboardButton(text=toggle_btn_text, callback_data="auto_booking_toggle"))
    
    mode_btn_text = "🔄 Включить Авто-режим" if mode == "confirm" else "🔄 Включить Подтверждение"
    builder.row(InlineKeyboardButton(text=mode_btn_text, callback_data="auto_booking_mode_toggle"))
    
    builder.row(
        InlineKeyboardButton(text="🏫 Выбрать школы", callback_data="auto_booking_select_schools"),
        InlineKeyboardButton(text="🎯 Выбрать станции", callback_data="auto_booking_select_stations")
    )
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "auto_booking_mode_toggle")
async def handle_auto_booking_mode_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    current_mode = settings.get("auto_booking_mode", "confirm")
    settings["auto_booking_mode"] = "auto" if current_mode == "confirm" else "confirm"
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_menu(callback)

@router.callback_query(F.data == "auto_booking_toggle")
async def handle_auto_booking_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    settings["auto_booking_active"] = not settings.get("auto_booking_active", False)
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_menu(callback)

@router.callback_query(F.data == "auto_booking_select_schools")
async def handle_auto_booking_select_schools(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    selected_schools = settings.get("auto_booking_schools", [])
    
    schools_set = set()
    if GLOBAL_CACHED_DATA:
        for ev in GLOBAL_CACHED_DATA:
            title = ev.get("title", "")
            sch = format_school_name(title)
            if sch:
                schools_set.add(sch)
    schools_list = sorted(list(schools_set))
    
    builder = InlineKeyboardBuilder()
    for idx, sch in enumerate(schools_list):
        is_sel = sch in selected_schools
        btn_text = f"✅ {sch}" if is_sel else sch
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"auto_bk_sch_toggle_{idx}"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_menu"))
    
    await callback.message.edit_text(
        "🏫 *ВЫБОР ЦЕЛЕВЫХ ШКОЛ*\n\nОтметьте школы, в которых бот должен ловить смены:",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("auto_bk_sch_toggle_"))
async def handle_auto_booking_school_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    idx = int(callback.data.split("_")[4])
    
    schools_set = set()
    if GLOBAL_CACHED_DATA:
        for ev in GLOBAL_CACHED_DATA:
            title = ev.get("title", "")
            sch = format_school_name(title)
            if sch:
                schools_set.add(sch)
    schools_list = sorted(list(schools_set))
    
    if idx >= len(schools_list):
        await callback.answer("Ошибка выбора школы", show_alert=True)
        return
        
    sch = schools_list[idx]
    settings = get_auto_booking_settings(cid)
    selected = settings.get("auto_booking_schools", [])
    if sch in selected:
        selected.remove(sch)
    else:
        selected.append(sch)
    settings["auto_booking_schools"] = selected
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_select_schools(callback)

@router.callback_query(F.data == "auto_booking_select_stations")
async def handle_auto_booking_select_stations(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    builder = InlineKeyboardBuilder()
    categories = ["ПДД", "Спасатель", "Дружба", "Сокровища", "Бриллианты"]
    for cat in categories:
        builder.row(InlineKeyboardButton(text=f"🎯 {cat}", callback_data=f"auto_bk_cat_{cat}"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_menu"))
    await callback.message.edit_text(
        "🎯 *ВЫБОР ФАВОРИТ-СТАНЦИЙ*\n\nВыберите категорию квеста для настройки номеров станций:",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

async def render_category_stations_menu(callback: CallbackQuery, cat: str):
    cid = callback.message.chat.id
    settings = get_auto_booking_settings(cid)
    stations_dict = settings.setdefault("auto_booking_stations", {})
    selected_nums = stations_dict.setdefault(cat, [])
    builder = InlineKeyboardBuilder()
    
    diff_cat = "ПДД квест" if cat == "ПДД" else ("Школьный спасатель" if cat == "Спасатель" else cat)
    station_nums = sorted(list(DIFFICULTY_DATA.get(diff_cat, {}).keys()))
    if not station_nums:
        station_nums = list(range(1, 11))
        
    row = []
    for idx, i in enumerate(station_nums):
        is_sel = i in selected_nums
        btn_text = f"✅ {i}" if is_sel else str(i)
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"auto_bk_num_{cat}_{i}"))
        if len(row) == 5 or idx == len(station_nums) - 1:
            builder.row(*row)
            row = []
            
    builder.row(InlineKeyboardButton(text="↩️ Назад к категориям", callback_data="auto_booking_select_stations"))
    await callback.message.edit_text(
        f"🎯 *СТАНЦИИ ДЛЯ КАТЕГОРИИ: {cat}*\n\nВыберите номера станций, на которые вас нужно автоматически записывать:",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("auto_bk_cat_"))
async def handle_auto_booking_category_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    cat = callback.data.split("_")[3]
    await render_category_stations_menu(callback, cat)

@router.callback_query(F.data.startswith("auto_bk_num_"))
async def handle_auto_booking_number_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    parts = callback.data.split("_")
    cat = parts[3]
    num = int(parts[4])
    settings = get_auto_booking_settings(cid)
    stations_dict = settings.setdefault("auto_booking_stations", {})
    selected_nums = stations_dict.setdefault(cat, [])
    if num in selected_nums:
        selected_nums.remove(num)
    else:
        selected_nums.append(num)
    settings["auto_booking_stations"][cat] = selected_nums
    save_auto_booking_settings(cid, settings)
    
    await render_category_stations_menu(callback, cat)

@router.callback_query(F.data == "auto_booking_confirm_confirm")
async def handle_auto_booking_confirm_confirm(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid not in [6871586046, 7932533408, 8556418483]:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    targets = TEMP_AUTO_BOOKINGS.get(cid)
    if not targets:
        await callback.message.edit_text("⏳ Время подтверждения истекло или смены не найдены.", reply_markup=get_back_btn("user_profile"))
        return
    confirmed = load_confirmed_bookings()
    confirmed[str(cid)] = targets
    save_confirmed_bookings(confirmed)
    await callback.message.edit_text(
        "✅ *Автозапись успешно подтверждена!*\n\nБот автоматически запишет вас на эти смены в субботу в 12:00.",
        parse_mode="Markdown", reply_markup=get_back_btn("user_profile")
    )

@router.callback_query(F.data == "shift_log")
async def handle_shift_log(callback: CallbackQuery):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    site_name = acc.get("name", "")
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text(
            "⚠️ Данные ещё не загружены. Попробуйте позже.",
            reply_markup=get_back_btn("user_profile")
        )
        return
    stats = get_user_stats(site_name, GLOBAL_CACHED_DATA)
    if not stats or not stats["history"]:
        await callback.message.edit_text(
            "📜 *ЛОГ СМЕН*\n\nИстория смен пуста.",
            parse_mode="Markdown", reply_markup=get_back_btn("user_profile")
        )
        return
    history = stats["history"]
    completed_p = stats["completed_player"]
    completed_l = stats["completed_leader"]
    total_shifts = completed_p + completed_l
    lates = stats["lates"]
    header = (
        f"📜 *ЛОГ СМЕН — {site_name}*\n\n"
        f"📊 Всего смен: *{total_shifts}* (🏃 {completed_p} + 👑 {completed_l})\n"
        f"⚠️ Опозданий: *{lates}*\n\n"
    )
    history_text = "\n".join(history[-30:])
    if len(history) > 30:
        history_text = f"_...показаны последние 30 из {len(history)}_\n\n" + history_text
    text = header + history_text
    if len(text) > 4000:
        text = text[:3950] + "\n\n_...обрезано_"
    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=get_back_btn("user_profile")
    )

@router.message(F.text)
async def process_text_input(message: Message, bot: Bot):
    cid = message.chat.id

    link_state = USER_LINK_STATE.get(cid)
    if link_state == "waiting_credentials":
        if message.chat.type == "private":
            try: await message.delete()
            except Exception: pass
        lines = message.text.strip().split("\n")
        if len(lines) < 2:
            await edit_or_send(
                bot=bot, chat_id=cid,
                text="❌ *Неверный формат!*\n\nОтправьте данные в две строки:\n"
                     "📱 Первая строка — номер телефона\n"
                     "🔑 Вторая строка — пароль\n\n"
                     "Пример:\n`+79261234567`\n`мойпароль123`",
                reply_markup=get_back_btn("link_back_onboarding")
            )
            return
        phone_raw = lines[0].strip()
        password = lines[1].strip()
        phone = normalize_phone(phone_raw)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [process_text_input] Получены учетные данные:")
        print(f"  └ Сырой телефон: {phone_raw}")
        print(f"  └ Нормализованный телефон: {phone}")
        if len(phone) != 11 or not phone.isdigit():
            await edit_or_send(
                bot=bot, chat_id=cid,
                text="❌ *Некорректный номер телефона!*\n\nНомер должен содержать 11 цифр.\n"
                     "Допустимые форматы: `+79261234567`, `89261234567`, `79261234567`\n\n"
                     "Попробуйте ещё раз:",
                reply_markup=get_back_btn("link_back_onboarding")
            )
            return

        await edit_or_send(
            bot=bot, chat_id=cid,
            text="⏳ *Подключаюсь к серверу jget-events.ru...*"
        )
        await asyncio.sleep(0.5)

        await edit_or_send(
            bot=bot, chat_id=cid,
            text="🔐 *Проверяю учётные данные...*\n\n"
                 f"📱 Номер: `{phone[:2]}***{phone[-3:]}`"
        )
        token, name, error = await api_login(phone, password)
        if error:
            await edit_or_send(
                bot=bot, chat_id=cid,
                text=f"❌ *Ошибка авторизации*\n\n{error}\n\n"
                     "Проверьте данные и попробуйте ещё раз.\n\n"
                     "📱 Первая строка — номер телефона\n"
                     "🔑 Вторая строка — пароль",
                reply_markup=get_back_btn("link_back_onboarding")
            )
            return

        USER_LINK_STATE[cid] = f"confirming:{name}:{phone}:{password}:{token}"
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Да, это я", callback_data="link_confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="link_confirm_no")
        )
        await edit_or_send(
            bot=bot, chat_id=cid,
            text=f"✅ *Авторизация успешна!*\n\n"
                 f"👤 Это вы — *{name}*?",
            reply_markup=builder.as_markup()
        )
        return


@router.callback_query(F.data == "admin_panel")
async def handle_admin_panel(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid != ADMIN_ID:
        await callback.answer("У вас нет прав администратора!", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    linked_accs = load_linked_accounts()
    filters = load_all_filters()
    
    total_linked = len(linked_accs)
    total_filters = len(filters)
    
    active_autobooking = 0
    for user_f in filters.values():
        if user_f.get("auto_booking_active", False):
            active_autobooking += 1
            
    cached_events_count = len(GLOBAL_CACHED_DATA) if GLOBAL_CACHED_DATA else 0
    
    ram_str = "Н/Д"
    try:
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    parts = line.split()
                    ram_str = f"{float(parts[1]) / 1024:.1f} MB"
                    break
    except Exception:
        pass
        
    text = (
        f"👑 *ПАНЕЛЬ АДМИНИСТРАТОРА*\n\n"
        f"📊 *Статистика бота:*\n"
        f"• Привязанных аккаунтов: *{total_linked}*\n"
        f"• Пользователей с фильтрами: *{total_filters}*\n"
        f"• Активных автозаписей: *{active_autobooking}*\n"
        f"• Смен в кэше API: *{cached_events_count}*\n"
        f"• Потребление RAM: *{ram_str}*\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_panel"))
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())


async def main():
    global GLOBAL_CACHED_DATA
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    print("[+] Первичный сбор данных...")
    data, err = await fetch_all_data()
    if not err and data:
        GLOBAL_CACHED_DATA = data
        print("[+] Кэш инициализирован. Запуск...")
    else:
        print("[!] Запуск с пустым кэшем.")
    asyncio.create_task(background_cache_updater())
    asyncio.create_task(saturday_scheduler_loop(bot))
    asyncio.create_task(background_weekday_autobooking_loop(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
