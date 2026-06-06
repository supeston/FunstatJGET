import os
import io
import re
import json
import random
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import urllib.parse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8593726524:AAG3ofTD1LXZTPt7nLD2MFOzBEKL_ELemqU"
AUTH_FILE = "auth.json"
ACCOUNTS_DIR = "accounts"
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
    "Команда первых": {1: 40, 2: 25, 3: 45, 4: 30, 5: 35, 6: 20, 7: 25, 8: 15, 9: 35, 10: 30},
    "Школьный спасатель": {1: 55, 2: 65, 3: 45, 4: 50, 5: 30, 6: 70, 7: 35, 8: 40, 9: 20}
}

EASY_STATIONS = {
    "Бриллианты": [5, 6, 8],
    "Сокровища": [1, 2, 3, 5, 7],
    "ПДД квест": [8],
    "Дружба": [2, 4, 6, 7, 8, 10],
    "Команда первых": [2, 4, 6, 7, 8, 10],
    "Школьный спасатель": [5]
}

STATIONS_MAP = {
    "Первая": 1, "Вторая": 2, "Третья": 3, "Четвёртая": 4, "Четвертая": 4,
    "Пятая": 5, "Шестая": 6, "Седьмая": 7, "Восьмая": 8, "Девятая": 9, "Десятая": 10
}

MONTHS_RU = {1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн", 7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"}
DAYS_RU = {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"}

BOT_MESSAGE_ID = {}     
USER_SEARCHING = {}     
USER_PAGES = {}         
NOTIFIED_EVENTS = set()    
USER_LINK_STATE = {}
USER_COMBO_PAGES = {}
USER_TEMP_FILTERS = {}

GLOBAL_CACHED_DATA = None  
GLOBAL_WEATHER_CACHE = {}
LAST_WEATHER_UPDATE = None
STORM_LOCK = asyncio.Lock()


async def update_weather_cache():
    global GLOBAL_WEATHER_CACHE, LAST_WEATHER_UPDATE
    now = datetime.now()
    if LAST_WEATHER_UPDATE and (now - LAST_WEATHER_UPDATE).total_seconds() < 7200:
        return
    url = "https://api.open-meteo.com/v1/forecast?latitude=55.73&longitude=52.41&daily=weather_code,temperature_2m_max&timezone=Europe/Moscow"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=8) as r:
                if r.status == 200:
                    data = await r.json()
                    daily = data.get("daily", {})
                    times = daily.get("time", [])
                    codes = daily.get("weather_code", [])
                    temps = daily.get("temperature_2m_max", [])
                    new_cache = {}
                    for t, code, temp in zip(times, codes, temps):
                        if code in [0, 1]:
                            w_type = "Солнечно ☀️"
                        elif code in [2, 3]:
                            w_type = "Облачно ⛅"
                        elif code in [45, 48]:
                            w_type = "Туман 🌫️"
                        elif code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]:
                            w_type = "Дождь 🌧️"
                        elif code in [71, 73, 75, 77, 85, 86]:
                            w_type = "Снег ❄️"
                        elif code in [95, 96, 99]:
                            w_type = "Гроза ⚡"
                        else:
                            w_type = "🌤️"
                        temp_val = int(round(temp))
                        temp_str = f"+{temp_val}" if temp_val > 0 else str(temp_val)
                        new_cache[t] = f"{w_type} {temp_str}°C"
                    GLOBAL_WEATHER_CACHE = new_cache
                    LAST_WEATHER_UPDATE = now
                    print(f"[{now.strftime('%H:%M:%S')}] Кэш погоды успешно обновлен.")
    except Exception as e:
        print(f"Ошибка обновления погоды: {e}")

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

def get_user_filters(chat_id):
    filters = load_all_filters()
    cid_str = str(chat_id)
    if cid_str not in filters:
        filters[cid_str] = {
            "difficulties": {
                "easy": True,
                "medium": True,
                "hard": True
            },
            "categories": {
                "ПДД": True,
                "Спасатель": True,
                "Дружба": True,
                "Сокровища": True,
                "Бриллианты": True
            }
        }
    else:
        user_f = filters[cid_str]
        if "difficulties" not in user_f:
            easy_val = user_f.pop("easy_only", False)
            if easy_val:
                user_f["difficulties"] = {"easy": True, "medium": False, "hard": False}
            else:
                user_f["difficulties"] = {"easy": True, "medium": True, "hard": True}
    return filters[cid_str]

def save_user_filters(chat_id, user_filter):
    filters = load_all_filters()
    filters[str(chat_id)] = user_filter
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

def is_booking_open(event_date_str):
    """Проверяет, открыта ли запись на неделю, к которой относится event_date_str.
    Запись открывается в субботу перед этой неделей в 12:00 по МСК."""
    try:
        ev_dt = datetime.strptime(event_date_str, "%Y-%m-%d")
        monday = ev_dt - timedelta(days=ev_dt.weekday())
        opening_saturday = monday - timedelta(days=2)
        opening_time = datetime(opening_saturday.year, opening_saturday.month, opening_saturday.day, 12, 0, 0)
        return datetime.now() >= opening_time
    except Exception:
        return True


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

def get_msk_now():
    tz_msk = timezone(timedelta(hours=3))
    return datetime.now(tz_msk)

async def check_bot_session(account_id: int) -> bool:
    cookies, token = load_account_auth(account_id)
    if not cookies:
        return False
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    if token:
        headers["Authorization"] = f"Token {token}"
    try:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            async with session.get(URL_PROFILE, timeout=5) as r:
                return r.status == 200
    except Exception:
        return False

async def measure_api_ping() -> int:
    import time
    start = time.time()
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(URL_PROFILE, timeout=3) as r:
                await r.read()
                return int((time.time() - start) * 1000)
    except Exception:
        return 9999

LAST_BOT_CHECK_TIME = None
CACHED_ACTIVE_BOT_IDS = []
CACHED_INACTIVE_BOT_COUNT = 0
CACHED_API_PING_MS = 9999

async def run_silent_bot_check():
    global LAST_BOT_CHECK_TIME, CACHED_ACTIVE_BOT_IDS, CACHED_INACTIVE_BOT_COUNT, CACHED_API_PING_MS
    results = {}
    
    async def check_and_store(acc_id):
        is_ok = await check_bot_session(acc_id)
        results[acc_id] = is_ok
        
    for chunk_start in range(1, 51, 10):
        tasks = [check_and_store(i) for i in range(chunk_start, min(chunk_start + 10, 51))]
        await asyncio.gather(*tasks)
        
    active_ids = [acc_id for acc_id, is_ok in results.items() if is_ok]
    CACHED_ACTIVE_BOT_IDS = active_ids
    CACHED_INACTIVE_BOT_COUNT = 50 - len(active_ids)
    LAST_BOT_CHECK_TIME = datetime.now()
    
    ping_ms = await measure_api_ping()
    CACHED_API_PING_MS = ping_ms
    ping_str = f"{ping_ms} ms" if ping_ms != 9999 else "offline"
    print(f"[{LAST_BOT_CHECK_TIME.strftime('%H:%M:%S')}] [Проверка ботов] Активных: {len(active_ids)}, неактивных: {CACHED_INACTIVE_BOT_COUNT}. API Ping: {ping_str}.")

async def background_bot_check_loop():
    while True:
        try:
            await run_silent_bot_check()
        except Exception as e:
            print(f"Ошибка при фоновой проверке ботов: {e}")
        await asyncio.sleep(30 * 60)


class MassAutomationTracker:
    def __init__(self, total):
        self.total = total
        self.success = 0
        self.failed = 0
        self.processed = 0
        self.last_update = 0

def load_account_auth(account_id):
    file_path = os.path.join(ACCOUNTS_DIR, f"auth{account_id}.json")
    if not os.path.exists(file_path):
        return None, None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
        token = None
        for origin in data.get("origins", []):
            for item in origin.get("localStorage", []):
                if "token" in item["name"].lower() or "auth" in item["name"].lower():
                    token = item["value"].strip('"')
                    break
        return cookies, token
    except Exception:
        return None, None

def check_time_overlap(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1

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
    if "дружба" in name_lower or "дружба" in title_lower:
        return "Дружба"
    if "перв" in name_lower:
        return "Команда первых"
    if "спас" in name_lower:
        return "Школьный спасатель"
    if "брилл" in name_lower:
        return "Бриллианты"
    if "сокр" in name_lower:
        return "Сокровища"
    if "пдд" in name_lower:
        return "ПДД квест"
    return event_type_name

def get_difficulty_indicator(category, station_num):
    pct = DIFFICULTY_DATA.get(category, {}).get(station_num, 0)
    if not pct:
        return "⚪ (Сложность неизвестна)"
    if pct <= 25:
        return "🟩▫️▫️▫️ (Легкая)"
    elif pct <= 45:
        return "🟨🟨▫️▫️ (Средняя)"
    elif pct <= 65:
        return "🟧🟧🟧▫️ (Повышенная)"
    else:
        return "🟥🟥🟥🟥 (Высокая нагрузка! 🔥)"

def find_initial_page(sorted_dates):
    now = datetime.now()
    if now.weekday() == 6:
        now += timedelta(days=1)
    target_str = now.strftime("%Y-%m-%d")
    if target_str in sorted_dates:
        return sorted_dates.index(target_str)
    for idx, d_str in enumerate(sorted_dates):
        if d_str >= target_str:
            return idx
    return max(0, len(sorted_dates) - 1)

def find_best_combo_for_day(events):
    candidates = []
    for ev in events:
        raw_cat = ev.get("event_type_name", "")
        title = ev.get("title", "")
        cat = normalize_category(raw_cat, title)
        school_fmt = format_school_name(title)
        free_stations = []
        for s in ev.get("available_stations", []):
            if s.get("is_available"):
                num = get_station_num(s.get("name"))
                if num > 0:
                    diff = DIFFICULTY_DATA.get(cat, {}).get(num, 50)
                    free_stations.append((num, diff, s.get("id")))
        if not free_stations:
            continue
        easiest_st = min(free_stations, key=lambda x: x[1])
        candidates.append({
            "id": ev.get("id"),
            "start": ev.get("start_time")[:5],
            "end": ev.get("end_time")[:5],
            "school": school_fmt,
            "raw_cat": raw_cat,
            "cat": cat,
            "station_num": easiest_st[0],
            "station_id": easiest_st[2],
            "diff_pct": easiest_st[1]
        })
    if not candidates:
        return []
    candidates.sort(key=lambda x: x["start"])
    valid_combos = []
    def time_to_minutes(t_str):
        try:
            parts = t_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            return 0
    def is_valid_transition(a, b):
        a_end_mins = time_to_minutes(a["end"])
        b_start_mins = time_to_minutes(b["start"])
        if a["school"] == b["school"]:
            return b_start_mins >= a_end_mins
        return b_start_mins > a_end_mins
    def backtrack(index, current_combo):
        if index == len(candidates):
            if current_combo:
                valid_combos.append(list(current_combo))
            return
        backtrack(index + 1, current_combo)
        if not current_combo or is_valid_transition(current_combo[-1], candidates[index]):
            current_combo.append(candidates[index])
            backtrack(index + 1, current_combo)
            current_combo.pop()
    backtrack(0, [])
    if not valid_combos:
        return []
    valid_combos.sort(key=lambda c: (len(c), -sum(x["diff_pct"] for x in c)/len(c)), reverse=True)
    return valid_combos[0]

def chunk_combos(events_data, chat_id=None):
    by_date = {}
    for ev in events_data:
        d = ev["date"]
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(ev)
    pages = []
    actual_valid_dates = []
    combos_data = []
    is_user_linked = chat_id and is_linked(chat_id)
    for d in sorted(by_date.keys()):
        best_combo = find_best_combo_for_day(by_date[d])
        if not best_combo:
            continue
        actual_valid_dates.append(d)
        combos_data.append(best_combo)
        weather_str = ""
        if is_user_linked and d in GLOBAL_WEATHER_CACHE:
            weather_str = f" | 🌡️ *{GLOBAL_WEATHER_CACHE[d]}*"
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            header = f"🚀 *КОМБО-МАРШРУТ (МАКСИМАЛЬНЫЙ ЗАРАБОТОК)*\n📅 *ДАТА: {dt.day} {MONTHS_RU[dt.month]} ({DAYS_RU[dt.weekday()]})*{weather_str}\n\n"
        except Exception:
            header = f"🚀 *КОМБО-МАРШРУТ (МАКСИМАЛЬНЫЙ ЗАРАБОТОК)*\n📅 *ДАТА: {d}*{weather_str}\n\n"
        total_cash = len(best_combo) * PAYOUT_PLAYER
        avg_diff = sum(x["diff_pct"] for x in best_combo) / len(best_combo)
        if avg_diff <= 25:
            route_diff = "🟩 Маршрут на расслабоне (Легчайший)"
        elif avg_diff <= 45:
            route_diff = "🟨 Средний уровень (Оптимальный)"
        else:
            route_diff = "🟧 Высокая нагрузка (Потребуется выносливость)"
        summary = (
            f"💰 *Ожидаемый доход за день:* **{total_cash} руб.**\n"
            f"⏱️ *Сложность пакета:* {route_diff}\n\n"
            f"🔥 *Идеальный пошаговый план записи:*\n"
        )
        lines = []
        for idx, item in enumerate(best_combo, 1):
            diff_indicator = get_difficulty_indicator(item["cat"], item["station_num"])
            lines.append(
                f"{idx}. ⏰ **{item['start']} - {item['end']}**\n"
                f"   🏫 {item['school']}\n"
                f"   🎯 Квест: {format_category_link(item['raw_cat'])}\n"
                f"   ⭐ Твоя позиция: *Станция {item['station_num']}* -> {diff_indicator}"
            )
        pages.append(header + summary + "\n\n".join(lines))
    return pages, actual_valid_dates, combos_data

def chunk_by_days(events_data, chat_id=None):
    user_filter = get_user_filters(chat_id) if chat_id else {
        "difficulties": {
            "easy": True,
            "medium": True,
            "hard": True
        },
        "categories": {
            "ПДД": True,
            "Спасатель": True,
            "Дружба": True,
            "Сокровища": True,
            "Бриллианты": True
        }
    }
    allowed_difficulties = user_filter.get("difficulties", {})
    allowed_categories = user_filter.get("categories", {})

    grouped = {}
    for ev in events_data:
        raw_cat = ev.get("event_type_name", "")
        title = ev.get("title", "")
        formatted_title = format_school_name(title)
        cat = normalize_category(raw_cat, title)

        clean_cat = clean_category_name(raw_cat)
        if not allowed_categories.get(clean_cat, True):
            continue

        raw_stations = ev.get("available_stations", [])
        valid_nums = sorted([get_station_num(s.get("name")) for s in raw_stations if s.get("is_available")])

        filtered_nums = []
        for n in valid_nums:
            if n > 0:
                pct = DIFFICULTY_DATA.get(cat, {}).get(n, 0)
                if pct == 0:
                    st_diff = "medium"
                elif pct <= 25:
                    st_diff = "easy"
                elif pct <= 45:
                    st_diff = "medium"
                else:
                    st_diff = "hard"

                if allowed_difficulties.get(st_diff, True):
                    filtered_nums.append(n)

        if not filtered_nums:
            continue

        date_str = ev["date"]
        if date_str not in grouped:
            grouped[date_str] = []
        time_str = f"{ev['start_time'][:5]} - {ev['end_time'][:5]}"
        geo_query = f"https://yandex.ru/maps/?text=Набережные+Челны+{formatted_title.replace(' ', '+')}"
        station_lines = []
        for n in filtered_nums:
            diff_label = get_difficulty_indicator(cat, n)
            station_lines.append(f" ├ Станция {n} -> {diff_label}")
        stations_block = "\n".join(station_lines)
        grouped[date_str].append(f"⏰ *{time_str}*\n🏫 [{formatted_title}]({geo_query}) ({format_category_link(raw_cat)})\n🔥 Свободные позиции:\n{stations_block}")

    pages = []
    sorted_dates = sorted(grouped.keys())
    is_user_linked = chat_id and is_linked(chat_id)
    for d in sorted_dates:
        weather_str = ""
        if is_user_linked and d in GLOBAL_WEATHER_CACHE:
            weather_str = f" | 🌡️ *{GLOBAL_WEATHER_CACHE[d]}*"
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            header = f"📅 *ДАТА: {dt.day} {MONTHS_RU[dt.month]} ({DAYS_RU[dt.weekday()]})*{weather_str}"
        except Exception:
            header = f"📅 *ДАТА: {d}*{weather_str}"
        pages.append(header + "\n\n" + "\n\n───────────────\n\n".join(grouped[d]))
    return pages, sorted_dates

def chunk_stations(events_data):
    grouped = {}
    for ev in events_data:
        date_str = ev["date"]
        if date_str not in grouped:
            grouped[date_str] = []
        title = ev.get("title", "")
        formatted_title = format_school_name(title)
        geo_query = f"https://yandex.ru/maps/?text=Набережные+Челны+{formatted_title.replace(' ', '+')}"
        cat = normalize_category(ev.get("event_type_name", ""), title)
        block = f"📍 {format_category_link(ev.get('event_type_name', ''))} ([{formatted_title}]({geo_query})) | ⏰ {ev['start_time'][:5]} - {ev['end_time'][:5]}\n"
        def sort_key(part):
            if part.get("as_leader"):
                return (0, 0)
            st_obj = part.get("station")
            st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
            return (1, get_station_num(st_name))
        sorted_participants = sorted(ev.get("participants", []), key=sort_key)
        parts = []
        for p in sorted_participants:
            if p.get("as_leader"):
                role = "👑 Главарь"
            else:
                st_obj = p.get("station")
                st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
                st_num = get_station_num(st_name)
                if st_num:
                    pct = DIFFICULTY_DATA.get(cat, {}).get(st_num, 0)
                    if not pct:
                        diff_emoji = "⚪"
                    elif pct <= 25:
                        diff_emoji = "🟩"
                    elif pct <= 45:
                        diff_emoji = "🟨"
                    elif pct <= 65:
                        diff_emoji = "🟧"
                    else:
                        diff_emoji = "🟥"
                    role = f"{st_num} {diff_emoji}"
                else:
                    role = "Без позиции"
            parts.append(f" ├ {p['first_name']} {p['last_name']} -> *{role}*")
        block += "\n".join(parts) if parts else " └ Состав пуст"
        grouped[date_str].append(block)
    pages = []
    sorted_dates = sorted(grouped.keys())
    for d in sorted_dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            header = f"📅 *ДАТА: {dt.day} {MONTHS_RU[dt.month]} ({DAYS_RU[dt.weekday()]})*\n\n"
        except Exception:
            header = f"📅 *ДАТА: {d}*\n\n"
        pages.append(header + "\n\n".join(grouped[d]))
    return pages, sorted_dates

def analyze_community(events_list):
    users = {}
    current_time = datetime.now()
    for event in events_list:
        raw_cat = event.get("event_type_name", "")
        school = event.get("title", "")
        formatted_school = format_school_name(school)
        date_str = event.get("date", "")
        end_time_str = event.get("end_time", "23:59:59")
        cat = normalize_category(raw_cat, school)
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
        for p in event.get("participants", []):
            name = f"{p['first_name']} {p['last_name']}".strip()
            if not name: continue
            if name not in users:
                users[name] = {
                    "total_player": 0, "completed_player": 0,
                    "total_leader": 0, "completed_leader": 0,
                    "minutes_player": 0, "minutes_leader": 0,
                    "skips": 0, "categories": {},
                    "partners": {}, "history": [],
                    "lates": 0, "player_lates": 0
                }
            as_leader = p.get("as_leader")
            attended = p.get("attended", True)
            late = p.get("late", False)
            st_obj = p.get("station")
            st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
            st_num = get_station_num(st_name)
            users[name]["categories"][cat] = users[name]["categories"].get(cat, 0) + 1
            if is_completed and attended and late:
                users[name]["lates"] = users[name].get("lates", 0) + 1
                if not as_leader:
                    users[name]["player_lates"] = users[name].get("player_lates", 0) + 1
            if as_leader:
                users[name]["total_leader"] += 1
                if is_completed:
                    if attended:
                        users[name]["completed_leader"] += 1
                        users[name]["minutes_leader"] += total_work_mins
                    else:
                        users[name]["skips"] += 1
                role = "Главарь"
            else:
                users[name]["total_player"] += 1
                if is_completed:
                    if attended:
                        users[name]["completed_player"] += 1
                        users[name]["minutes_player"] += total_work_mins
                    else:
                        users[name]["skips"] += 1
                role = f"Станция {st_num}" if st_num else "Без позиции"
            for partner in event.get("participants", []):
                p_name = f"{partner['first_name']} {partner['last_name']}".strip()
                if p_name != name and p_name:
                    users[name]["partners"][p_name] = users[name]["partners"].get(p_name, 0) + 1
            hist_item = f"• {date_str} | {clean_category_name(raw_cat)} — *{role}* ({formatted_school})"
            if is_completed and attended and late:
                hist_item += " ⚠️ (Опоздание)"
            users[name]["history"].append(hist_item)
    for name in users:
        users[name]["history"] = sorted(users[name]["history"])
    return users



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
            return list(merged), None
        except Exception as e:
            return None, f"Ошибка выполнения HTTP-запроса: {e}"

async def api_login(phone, password):
    """Попытка авторизации на jget-events.ru. Возвращает (token, name, error)."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [api_login] Попытка входа:")
    print(f"  └ URL: {URL_LOGIN}")
    print(f"  └ Phone: {phone}")
    print(f"  └ Password: {password}")
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
    try:
        await update_weather_cache()
    except Exception:
        pass
    while True:
        data, err = await fetch_all_data()
        if not err and data:
            GLOBAL_CACHED_DATA = data
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Глобальный кэш успешно обновлен.")
            try:
                linked = load_linked_accounts()
                changed = False
                for cid_str, acc_data in list(linked.items()):
                    token = acc_data.get("token")
                    if token:
                        profile_data, p_err = await api_get_profile(token)
                        if profile_data:
                            stats = profile_data.get("stats", {})
                            user_info = profile_data.get("user", {})
                            conducted = stats.get("conducted", user_info.get("conducted_count", 0))
                            cancelled = stats.get("cancellations", user_info.get("cancellation_count", 0))
                            if acc_data.get("conducted") != conducted or acc_data.get("cancelled") != cancelled:
                                acc_data["conducted"] = conducted
                                acc_data["cancelled"] = cancelled
                                changed = True
                        await asyncio.sleep(0.5)
                if changed:
                    save_linked_accounts(linked)
            except Exception as le:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка фонового обновления профилей: {le}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка фонового обновления: {err}")
        try:
            await update_weather_cache()
        except Exception:
            pass
        await asyncio.sleep(3 * 60)

async def background_notifier(bot: Bot):
    """Уведомления только для привязанных аккаунтов."""
    global GLOBAL_CACHED_DATA
    while True:
        if GLOBAL_CACHED_DATA:
            linked = load_linked_accounts()
            if linked:
                now = datetime.now()
                for ev in GLOBAL_CACHED_DATA:
                    try:
                        ev_id = ev.get("id")
                        ev_date_str = ev.get("date")
                        ev_start_str = ev.get("start_time")
                        full_start_str = f"{ev_date_str} {ev_start_str[:8]}"
                        start_dt = datetime.strptime(full_start_str, "%Y-%m-%d %H:%M:%S")
                        if start_dt <= now:
                            continue
                        if now <= start_dt <= (now + timedelta(minutes=90)):
                            school_fmt = format_school_name(ev.get("title", ""))
                            for p in ev.get("participants", []):
                                p_name = f"{p['first_name']} {p['last_name']}".strip()
                                for cid_str, acc_data in list(linked.items()):
                                    if not acc_data.get("notifs_enabled", True):
                                        continue
                                    sub_name = acc_data.get("name", "")
                                    if sub_name == p_name:
                                        cid = int(cid_str)
                                        notif_key = f"{cid}_{ev_date_str}_{school_fmt}"
                                        if notif_key in NOTIFIED_EVENTS:
                                            continue
                                        user_school_events = []
                                        for sub_ev in GLOBAL_CACHED_DATA:
                                            if sub_ev.get("date") == ev_date_str and format_school_name(sub_ev.get("title", "")) == school_fmt:
                                                sub_start_dt = datetime.strptime(f"{ev_date_str} {sub_ev.get('start_time')[:8]}", "%Y-%m-%d %H:%M:%S")
                                                if sub_start_dt > now:
                                                    for sub_p in sub_ev.get("participants", []):
                                                        if f"{sub_p['first_name']} {sub_p['last_name']}".strip() == sub_name:
                                                            user_school_events.append((sub_ev, sub_p, sub_start_dt))
                                        if not user_school_events:
                                            continue
                                        user_school_events.sort(key=lambda x: x[2])
                                        lines = []
                                        total_payout = 0
                                        for s_ev, s_p, _ in user_school_events:
                                            is_leader = s_p.get("as_leader")
                                            payout = PAYOUT_LEADER if is_leader else PAYOUT_PLAYER
                                            total_payout += payout
                                            if is_leader:
                                                role_str = "👑 Главарь"
                                            else:
                                                st_obj = s_p.get("station")
                                                st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
                                                st_num = get_station_num(st_name)
                                                role_str = f"Станция {st_num}" if st_num else "Ведущий"
                                            q_name_fmt = format_category_link(s_ev.get("event_type_name", ""))
                                            time_range = f"{s_ev.get('start_time')[:5]}-{s_ev.get('end_time')[:5]}"
                                            lines.append(f" ├ ⏰ *{time_range}* | {q_name_fmt} — `{role_str}`")
                                        phrases = [
                                            f"Время разносить квесты и забирать свои {total_payout}₽! 🚀",
                                            f"Твой кошелек уже готов принять {total_payout} рублей? Заряжай самокат! ⚡",
                                            f"Школа ждет своего героя. На кону {total_payout}₽, не подведи! 👑",
                                            f"Минута работы — копеечка в карман, а за сегодня выйдет аж {total_payout}₽! 💰",
                                            f"Покажи им высший пилотаж и забирай честно заработанные {total_payout}₽! 🔥",
                                            f"Сделай этот день легендарным, а {total_payout} рублей станут отличным бонусом! 💸"
                                        ]
                                        chosen_phrase = random.choice(phrases)
                                        alert_text = (
                                            f"🔔 *НАПОМИНАНИЕ О КВЕСТАХ (ОСТАЛОСЬ 1.30 ЧАСА)!*\n\n"
                                            f"👤 Ведущий: *{sub_name}*\n"
                                            f"🏫 Место проведения: *{school_fmt}*\n\n"
                                            f"📋 *План твоей работы в этой локации:*\n" + "\n".join(lines) + f"\n\n"
                                            f"💬 _{chosen_phrase}_"
                                        )
                                        try:
                                            await bot.send_message(chat_id=cid, text=alert_text, parse_mode="Markdown")
                                            NOTIFIED_EVENTS.add(notif_key)
                                        except Exception:
                                            pass
                    except Exception:
                        pass
        await asyncio.sleep(60)



def generate_analytics_plot(profiles):
    sorted_users = sorted(profiles.items(), key=lambda x: (x[1]["completed_player"] * PAYOUT_PLAYER + x[1]["completed_leader"] * PAYOUT_LEADER), reverse=True)[:10]
    names = [x[0].split()[0] + "\n" + (x[0].split()[1] if len(x[0].split()) > 1 else "") for x in sorted_users]
    earnings = [(x[1]["completed_player"] * PAYOUT_PLAYER + x[1]["completed_leader"] * PAYOUT_LEADER) for x in sorted_users]
    plt.figure(figsize=(10, 5))
    colors = ['#4CAF50' if x[1]['completed_leader'] == 0 else '#FF9800' for x in sorted_users]
    bars = plt.bar(names, earnings, color=colors, edgecolor='black', alpha=0.85)
    plt.title("ТОП-10 ВЕДУЩИХ ПО ВЫПЛАТАМ (РУБ.)", fontsize=14, fontweight='bold', pad=15)
    plt.ylabel("Заработано (рублей)", fontsize=11)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval + 100, f"{int(yval)}₽", ha='center', va='bottom', fontsize=9, fontweight='bold')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close()
    return buf



def get_main_menu(chat_id=None):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Запись на квесты", callback_data="booking_hub")
    )
    if chat_id and is_linked(chat_id):
        builder.row(
            InlineKeyboardButton(text="👤 Мой профиль", callback_data="user_profile")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔗 Привязать аккаунт", callback_data="link_start")
        )
    builder.row(
        InlineKeyboardButton(text="💻 Технический раздел", callback_data="osint_menu")
    )
    if chat_id == ADMIN_ID:
        builder.row(
            InlineKeyboardButton(text="⚙️ Панель админа", callback_data="admin_mass_panel")
        )
    builder.row(
        InlineKeyboardButton(text="❓ Что это за бот?", callback_data="about_bot")
    )
    return builder.as_markup()

def get_back_btn(target="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data=target)]])

def get_pagination_keyboard(current_page, total_pages, mode_prefix, chat_id=None, combo_date=None):
    builder = InlineKeyboardBuilder()
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Пред.", callback_data=f"{mode_prefix}_{current_page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📖 {current_page + 1}/{total_pages}", callback_data="noop"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="След. ▶️", callback_data=f"{mode_prefix}_{current_page + 1}"))
    builder.row(*nav_buttons)

    if mode_prefix == "page_combo" and chat_id and is_linked(chat_id):
        if not combo_date or is_booking_open(combo_date):
            builder.row(InlineKeyboardButton(text="📝 Записать на комбо", callback_data=f"book_combo_{current_page}"))
    if mode_prefix == "page_all":
        builder.row(InlineKeyboardButton(text="⚙️ Фильтры", callback_data=f"filters_slots_{current_page}"))
    
    if mode_prefix == "page_st":
        back_target = "osint_menu"
    else:
        back_target = "booking_hub"
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=back_target))
    return builder.as_markup()


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
    USER_SEARCHING.pop(cid, None)
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
    USER_SEARCHING.pop(cid, None)
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
        "hidden": False,
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
    hidden_status = "🔒 Скрыты" if acc.get("hidden") else "🔓 Видны всем"

    conducted = acc.get("conducted", 0)
    cancelled = acc.get("cancelled", 0)

    lates = 0
    player_lates = 0
    total_hours = 0.0
    user_profile_info = None
    if GLOBAL_CACHED_DATA:
        profiles = analyze_community(GLOBAL_CACHED_DATA)
        for name, info in profiles.items():
            if name.strip().lower() == site_name.strip().lower():
                user_profile_info = info
                lates = info.get("lates", 0)
                player_lates = info.get("player_lates", 0)
                total_minutes = info.get("minutes_player", 0) + info.get("minutes_leader", 0)
                total_hours = round(total_minutes / 60, 1)
                break

    site_extra = f"\n📊 Проведено: *{conducted}* | Отмен: *{cancelled}* | ⏰ Опозданий: *{lates}* | ⏳ Часов: *{total_hours}*"

    already_earned = conducted * 517
    if user_profile_info:
        cached_leader = user_profile_info.get("completed_leader", 0)
        cached_player = user_profile_info.get("completed_player", 0)
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

    notifs_enabled = acc.get("notifs_enabled", True)
    notifs_status_text = "🟢 Включены" if notifs_enabled else "🔴 Выключены"

    text = (
        f"👤 *ПРОФИЛЬ*\n\n"
        f"📛 Имя на сайте: *{site_name}*\n"
        f"💬 Telegram: *{tg_name}* ({tg_username})\n"
        f"🆔 Telegram ID: `{tg_id}`\n"
        f"📞 Телефон: `{phone_fmt}`"
        f"{site_extra}\n\n"
        f"💰 Уже заработано: *{already_earned}* ₽\n"
        f"⏳ В ожидании: *{expected_earnings}* ₽\n"
        f"🔥 Всего за месяц: *{total_for_month}* ₽\n\n"
        f"🛡️ Данные в ОСИНТ: {hidden_status}\n"
        f"🔔 Уведомления (1.5ч): {notifs_status_text}\n\n"
        f"📌 _Подробную статистику и историю смотрите в разделе_ "
        f"_ОСИНТ (⚙️ Полезное → 🔍 ОСИНТ)_"
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
    if tomorrow_shifts:
        tomorrow_shifts.sort(key=lambda x: x[0])
        report_text = "\n".join([item[1] for item in tomorrow_shifts])
        share_url = f"https://t.me/share/url?url=&text={urllib.parse.quote(report_text)}"
        builder.row(InlineKeyboardButton(text="📝 Отправить отчет на завтра", url=share_url))
    builder.row(
        InlineKeyboardButton(text="🔑 Мой пароль", callback_data="show_password"),
        InlineKeyboardButton(text="🔔 Уведомления: " + ("Вкл" if notifs_enabled else "Выкл"), callback_data="toggle_notifs")
    )
    if acc.get("hidden"):
        builder.row(InlineKeyboardButton(text="🔓 Показать в ОСИНТ", callback_data="toggle_hidden"))
    else:
        builder.row(InlineKeyboardButton(text="🔒 Скрыть из ОСИНТ", callback_data="toggle_hidden"))
    builder.row(
        InlineKeyboardButton(text="🔗 Отвязать аккаунт", callback_data="unlink_confirm"),
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


@router.callback_query(F.data == "tomorrow_report")
async def handle_tomorrow_report(callback: CallbackQuery):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    site_name = acc.get("name", "")
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("⚠️ Внутренний кэш базы данных пуст. Ожидайте прогрузки...", reply_markup=get_back_btn("user_profile"))
        return
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    shifts = []
    format_time = lambda t: t[1:5] if t.startswith("0") else t[:5]
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
                    shifts.append((start_time, f"{sch_clean}, {category} {start_time}-{end_time}, {role_str}"))
    if not shifts:
        text = (
            "📋 *ОТЧЕТ НА ЗАВТРА*\n\n"
            "⚠️ На завтра у тебя нет запланированных смен, поэтому отчет пуст."
        )
    else:
        shifts.sort(key=lambda x: x[0])
        report_lines = [item[1] for item in shifts]
        report_text = "\n".join(report_lines)
        text = (
            "📋 *ОТЧЕТ НА ЗАВТРА для группы «Это моя станция»*\n\n"
            "Нажми на текст ниже, чтобы скопировать его:\n\n"
            f"```\n{report_text}\n```"
        )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_back_btn("user_profile"))


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

@router.callback_query(F.data == "toggle_hidden")
async def handle_toggle_hidden(callback: CallbackQuery):
    cid = callback.message.chat.id
    accounts = load_linked_accounts()
    cid_str = str(cid)
    if cid_str not in accounts:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    accounts[cid_str]["hidden"] = not accounts[cid_str].get("hidden", False)
    save_linked_accounts(accounts)
    new_state = accounts[cid_str]["hidden"]
    if new_state:
        await callback.answer("🔒 Данные скрыты от ОСИНТ-поиска.", show_alert=True)
    else:
        await callback.answer("🔓 Данные теперь видны в ОСИНТ-поиске.", show_alert=True)
    await handle_user_profile(callback)

@router.callback_query(F.data == "toggle_notifs")
async def handle_toggle_notifs(callback: CallbackQuery):
    cid = callback.message.chat.id
    accounts = load_linked_accounts()
    cid_str = str(cid)
    if cid_str not in accounts:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    accounts[cid_str]["notifs_enabled"] = not accounts[cid_str].get("notifs_enabled", True)
    save_linked_accounts(accounts)
    new_state = accounts[cid_str]["notifs_enabled"]
    if new_state:
        await callback.answer("🔔 Уведомления за 1.5 часа включены.", show_alert=True)
    else:
        await callback.answer("🔕 Уведомления за 1.5 часа выключены.", show_alert=True)
    await handle_user_profile(callback)


@router.callback_query(F.data == "unlink_confirm")
async def handle_unlink_confirm(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, отвязать", callback_data="unlink_yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="user_profile")
    )
    await callback.message.edit_text(
        "⚠️ *Вы уверены, что хотите отвязать аккаунт?*\n\n"
        "Вы потеряете доступ к:\n"
        " ├ Автоматической записи на квесты\n"
        " ├ Уведомлениям за 1.5 часа\n"
        " └ Скрытию данных в ОСИНТ\n\n"
        "Привязать аккаунт можно будет заново в любой момент.",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "unlink_yes")
async def handle_unlink_yes(callback: CallbackQuery):
    cid = callback.message.chat.id
    accounts = load_linked_accounts()
    accounts.pop(str(cid), None)
    save_linked_accounts(accounts)
    await callback.message.edit_text(
        "✅ Аккаунт успешно отвязан.\n\n"
        "🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:",
        parse_mode="Markdown", reply_markup=get_main_menu(cid)
    )



@router.callback_query(F.data == "main_menu")
async def go_to_main_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_SEARCHING.pop(cid, None)
    USER_LINK_STATE.pop(cid, None)
    await callback.message.edit_text("🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
                                     parse_mode="Markdown", reply_markup=get_main_menu(cid))

@router.callback_query(F.data == "booking_hub")
async def handle_booking_hub(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Свободные места", callback_data="slots_all"),
        InlineKeyboardButton(text="🚀 Комбо-пакеты", callback_data="slots_combo")
    )
    builder.row(
        InlineKeyboardButton(text="📚 Обучалки", callback_data="study_menu"),
        InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")
    )
    await callback.message.edit_text(
        "📅 *ЗАПИСЬ НА КВЕСТЫ*\n\n"
        "Выбери нужный раздел для просмотра свободных мест, подбора комбо-маршрутов или изучения обучающих материалов:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "tech_mass_panel")
async def handle_tech_mass_panel(callback: CallbackQuery):
    cid = callback.message.chat.id
    active_count = min(10, len(CACHED_ACTIVE_BOT_IDS))
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📆 Эта неделя (10 ботов)", callback_data="tech_run_current"),
        InlineKeyboardButton(text="📆 След. неделя (10 ботов)", callback_data="tech_run_next")
    )
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="osint_menu"))
    await callback.message.edit_text(
        f"🤖 *Авто-штурм ботами (Раздел Технарей)*\n\n"
        f"Вы можете запустить высокоскоростное параллельное распределение активных ботов по свободным позициям. "
        f"Под вашим управлением: *до 10 ботов* (всего сейчас активно: `{len(CACHED_ACTIVE_BOT_IDS)}`).\n\n"
        f"Выберите целевой период:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.in_(["slots_all", "slots_combo", "stations_who", "osint_menu"]))
async def handle_menus(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("⚠️ Внутренний кэш базы данных пуст. Ожидайте прогрузки...", reply_markup=get_back_btn())
        return
    data = GLOBAL_CACHED_DATA
    action = callback.data
    if action == "slots_all":
        pages, sorted_dates = chunk_by_days(data, chat_id=cid)
        if not pages:
            await callback.message.edit_text("🟢 На этой неделе свободных мест нет.", reply_markup=get_back_btn("booking_hub"))
            return
        initial_page = find_initial_page(sorted_dates)
        USER_PAGES[cid] = initial_page
        await callback.message.edit_text(text=pages[initial_page], parse_mode="Markdown", reply_markup=get_pagination_keyboard(initial_page, len(pages), "page_all", cid), disable_web_page_preview=True)
    elif action == "slots_combo":
        pages, sorted_dates, combos_data = chunk_combos(data, chat_id=cid)
        if not pages:
            await callback.message.edit_text("🟢 Нет доступных комбо-цепочек на этой неделе.", reply_markup=get_back_btn("booking_hub"))
            return
        initial_page = find_initial_page(sorted_dates)
        USER_PAGES[cid] = initial_page
        USER_COMBO_PAGES[cid] = combos_data
        await callback.message.edit_text(text=pages[initial_page], parse_mode="Markdown", reply_markup=get_pagination_keyboard(initial_page, len(pages), "page_combo", cid, sorted_dates[initial_page]), disable_web_page_preview=True)
    elif action == "stations_who":
        pages, sorted_dates = chunk_stations(data)
        if not pages:
            await callback.message.edit_text("🟢 Список станций пуст.", reply_markup=get_back_btn("osint_menu"))
            return
        initial_page = find_initial_page(sorted_dates)
        USER_PAGES[cid] = initial_page
        await callback.message.edit_text(text=pages[initial_page], parse_mode="Markdown", reply_markup=get_pagination_keyboard(initial_page, len(pages), "page_st", cid), disable_web_page_preview=True)
    elif action == "osint_menu":
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🏫 Станции ведущих", callback_data="stations_who"),
            InlineKeyboardButton(text="🔍 ОСИНТ Поиск", callback_data="osint_search_mode")
        )
        builder.row(
            InlineKeyboardButton(text="🏃 Выплаты: Ведущие", callback_data="osint_rates_players"),
            InlineKeyboardButton(text="👑 Выплаты: Главари", callback_data="osint_rates_leaders")
        )
        builder.row(
            InlineKeyboardButton(text="🏆 Рейтинг лидеров", callback_data="osint_tops"),
            InlineKeyboardButton(text="🎲 Фановые рекорды", callback_data="osint_fun")
        )
        builder.row(
            InlineKeyboardButton(text="📊 График выплат", callback_data="osint_chart"),
            InlineKeyboardButton(text="🤖 Авто-штурм ботами", callback_data="tech_mass_panel")
        )
        builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
        await callback.message.edit_text(
            "💻 *ТЕХНИЧЕСКИЙ РАЗДЕЛ (ДЛЯ ТЕХНАРЕЙ)*\n\n"
            "Здесь собраны инструменты продвинутой статистики, аналитики выплат и управления ботами:",
            parse_mode="Markdown",
            reply_markup=builder.as_markup()
        )



@router.callback_query(F.data == "admin_mass_panel")
async def handle_admin_panel(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid != ADMIN_ID:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    cfg = load_scheduler_config()
    sched_active = cfg.get("active", False)
    sched_status = "активен" if sched_active else "выключен"
    sched_btn_text = "Отключить авто-штурм в СБ" if sched_active else "Включить авто-штурм в СБ"
    
    active_count = len(CACHED_ACTIVE_BOT_IDS)
    inactive_count = CACHED_INACTIVE_BOT_COUNT
    if LAST_BOT_CHECK_TIME:
        mins_ago = int((datetime.now() - LAST_BOT_CHECK_TIME).total_seconds() / 60)
        time_display = f"_(обновлено {mins_ago} мин. назад)_"
    else:
        time_display = f"_(проверка выполняется...)_"

    # Получаем пинг из кэша
    ping_ms = CACHED_API_PING_MS
    if ping_ms == 9999:
        ping_display = "🔴 API: Недоступно (ошибка)"
    elif ping_ms <= 150:
        ping_display = f"🟢 API Пинг: `{ping_ms} ms` (Отлично)"
    elif ping_ms <= 300:
        ping_display = f"🟡 API Пинг: `{ping_ms} ms` (Средне)"
    else:
        ping_display = f"🔴 API Пинг: `{ping_ms} ms` (Задержка!)"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📆 Эта неделя", callback_data="mass_run_current"),
        InlineKeyboardButton(text="📆 След. неделя", callback_data="mass_run_next")
    )
    builder.row(
        InlineKeyboardButton(text=sched_btn_text, callback_data="toggle_saturday_scheduler")
    )
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    await callback.message.edit_text(
        f"🤖 *Авто-штурм ботами*\n\n"
        f"📊 *Статус сессий ботов:*\n"
        f" ├ 🟢 Активных: `{active_count}`\n"
        f" └ 🔴 Неактивных: `{inactive_count}`\n"
        f"   {time_display}\n\n"
        f"📶 *Состояние сети:*\n"
        f" └ {ping_display}\n\n"
        f"Выберите целевой период для распределения активных профилей по свободным позициям.\n\n"
        f"⏰ Авто-штурм в СБ 12:00: *{sched_status}*",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "toggle_saturday_scheduler")
async def handle_toggle_scheduler(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid != ADMIN_ID:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
    cfg = load_scheduler_config()
    cfg["active"] = not cfg.get("active", False)
    save_scheduler_config(cfg)
    await callback.answer("Статус планировщика обновлен!", show_alert=True)
    await handle_admin_panel(callback)

async def update_progress_msg(bot, chat_id, msg_id, tracker, final=False, back_target="osint_menu"):
    now_ts = asyncio.get_event_loop().time()
    if not final and (now_ts - tracker.last_update < 1.8):
        return
    tracker.last_update = now_ts
    text = (
        f"🤖 *Авто-штурм ботами*\n\n"
        f"📊 *Текущий прогресс по сетке:*\n"
        f" ├ Обработано профилей: `{tracker.processed}/{tracker.total}`\n"
        f" ├ Успешных бронирований: `{tracker.success}`\n"
        f" └ Ошибок/Отказов бэкенда: `{tracker.failed}`\n\n"
    )
    if final:
        text += "🏁 *Штурм завершен!*\n⏱️ Все доступные позиции заняты. Запущен скрытый фоновый кулдаун (14 минут) — автоматическая очистка всех зарегистрированных мест произойдет без лишнего спама."
        markup = get_back_btn(back_target)
    else:
        text += "⏳ Выполняю параллельную высокоскоростную запись..."
        markup = None
    try:
        if markup:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode="Markdown", reply_markup=markup)
        else:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode="Markdown")
    except Exception:
        pass

async def run_all_and_cooldown(tasks, bot, chat_id, msg_id, tracker, tab_week, active_ids, back_target="osint_menu"):
    async with STORM_LOCK:
        await asyncio.gather(*tasks)
        await update_progress_msg(bot, chat_id, msg_id, tracker, final=True, back_target=back_target)
    await asyncio.sleep(840)
    for i in active_ids:
        cookies, token = load_account_auth(i)
        if not cookies: continue
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        if token: headers["Authorization"] = f"Token {token}"
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            try:
                async with session.get(URL_CURRENT, params={"tab": tab_week}, timeout=8) as r:
                    if r.status == 200:
                        personal_events = await r.json()
                        for ev in personal_events:
                            booking_id = ev.get("user_booking_id")
                            if booking_id is not None:
                                url = f"https://jget-events.ru/api/bookings/{booking_id}/cancel/"
                                async with session.patch(url, timeout=5) as rp: pass
            except Exception: pass
            await asyncio.sleep(0.4)

@router.callback_query(F.data.startswith("mass_run_") | F.data.startswith("tech_run_"))
async def run_mass_automation(callback: CallbackQuery, bot: Bot):
    cid = callback.message.chat.id
    is_tech = callback.data.startswith("tech_run_")
    
    if not is_tech and cid != ADMIN_ID:
        await callback.answer("⭐ Это премиум функция", show_alert=True)
        return
        
    tab_week = callback.data.split("_")[2]
    msg_id = callback.message.message_id
    
    if is_tech:
        active_ids = CACHED_ACTIVE_BOT_IDS[:10]
        back_target = "tech_mass_panel"
    else:
        active_ids = CACHED_ACTIVE_BOT_IDS
        back_target = "admin_mass_panel"
        
    active_count = len(active_ids)
    
    if active_count == 0:
        await bot.edit_message_text(
            chat_id=cid, message_id=msg_id,
            text=f"❌ *Штурм отменен*\n\nНи одна сессия ботов не активна. Проверьте файлы в `accounts/`.",
            parse_mode="Markdown",
            reply_markup=get_back_btn(back_target)
        )
        return

    if STORM_LOCK.locked():
        await bot.edit_message_text(
            chat_id=cid, message_id=msg_id,
            text="⏳ *Вся сеть занята*\n\nДругой авто-штурм уже выполняется. Ваш запрос поставлен в очередь ожидания...",
            parse_mode="Markdown"
        )
    else:
        await bot.edit_message_text(
            chat_id=cid, message_id=msg_id,
            text=f"⏳ Загружаю расписание для активных ботов ({active_count})...",
            parse_mode="Markdown"
        )

    events = []
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(URL_CURRENT, params={"tab": tab_week}, timeout=10) as r:
                if r.status == 200: events = await r.json()
        except Exception: pass
    if not events:
        await callback.message.edit_text("❌ Не удалось получить расписание с сервера. Попробуй позже.", reply_markup=get_back_btn(back_target))
        return
        
    tracker = MassAutomationTracker(total=active_count)
    async def worker_task(account_id):
        cookies, token = load_account_auth(account_id)
        if not cookies:
            tracker.processed += 1
            return
        headers_acc = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"}
        if token: headers_acc["Authorization"] = f"Token {token}"
        async with aiohttp.ClientSession(cookies=cookies, headers=headers_acc) as session_acc:
            now = datetime.now()
            booked_today = {}
            for ev in events:
                if not ev.get("is_open", True): continue
                try:
                    ev_date = ev.get("date")
                    ev_start = ev.get("start_time")[:8]
                    ev_end = ev.get("end_time")[:8]
                    if datetime.strptime(f"{ev_date} {ev_end}", "%Y-%m-%d %H:%M:%S") <= now: continue
                except Exception: continue
                has_overlap = False
                if ev_date in booked_today:
                    for b_start, b_end in booked_today[ev_date]:
                        if check_time_overlap(ev_start, ev_end, b_start, b_end):
                            has_overlap = True
                            break
                if has_overlap: continue
                for station in ev.get("available_stations", []):
                    if station.get("is_available"):
                        station_id = station.get("id")
                        payload = {"event": ev.get("id"), "station": station_id}
                        try:
                            async with session_acc.post(URL_BOOK, json=payload, timeout=5) as r:
                                if r.status in [200, 201]:
                                    tracker.success += 1
                                    if ev_date not in booked_today: booked_today[ev_date] = []
                                    booked_today[ev_date].append((ev_start, ev_end))
                                    break
                                elif r.status == 400:
                                    res = await r.json()
                                    if "Уже записан" in res.get("error", ""):
                                        if ev_date not in booked_today: booked_today[ev_date] = []
                                        booked_today[ev_date].append((ev_start, ev_end))
                                        break
                                    else: tracker.failed += 1
                                else: tracker.failed += 1
                        except Exception: tracker.failed += 1
        tracker.processed += 1
        await update_progress_msg(bot, cid, callback.message.message_id, tracker, back_target=back_target)

    tasks = [worker_task(acc_id) for acc_id in active_ids]
    asyncio.create_task(run_all_and_cooldown(tasks, bot, cid, callback.message.message_id, tracker, tab_week, active_ids, back_target))

async def run_saturday_storm(bot: Bot, active_ids: list[int]):
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text="🚀 *Запуск автоматической записи...*\n"
                 f"Количество активных профилей: `{len(active_ids)}`.\n"
                 "Загружаю расписание на следующую неделю..."
        )
    except Exception:
        pass
        
    events = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    start_fetch = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_fetch < 15:
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(URL_CURRENT, params={"tab": "next"}, timeout=8) as r:
                    if r.status == 200:
                        events = await r.json()
                        if events:
                            break
        except Exception:
            pass
        await asyncio.sleep(0.5)
        
    if not events:
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text="❌ *Ошибка авто-записи*: Не удалось загрузить расписание на следующую неделю с сервера за 15 секунд."
            )
        except Exception:
            pass
        return
        
    tracker = MassAutomationTracker(total=len(active_ids))
    
    async def worker_task(account_id):
        cookies, token = load_account_auth(account_id)
        if not cookies:
            tracker.processed += 1
            return
        headers_acc = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"}
        if token:
            headers_acc["Authorization"] = f"Token {token}"
            
        async with aiohttp.ClientSession(cookies=cookies, headers=headers_acc) as session_acc:
            now = datetime.now()
            booked_today = {}
            for ev in events:
                if not ev.get("is_open", True):
                    continue
                try:
                    ev_date = ev.get("date")
                    ev_start = ev.get("start_time")[:8]
                    ev_end = ev.get("end_time")[:8]
                    if datetime.strptime(f"{ev_date} {ev_end}", "%Y-%m-%d %H:%M:%S") <= now:
                        continue
                except Exception:
                    continue
                has_overlap = False
                if ev_date in booked_today:
                    for b_start, b_end in booked_today[ev_date]:
                        if check_time_overlap(ev_start, ev_end, b_start, b_end):
                            has_overlap = True
                            break
                if has_overlap:
                    continue
                    
                for station in ev.get("available_stations", []):
                    if station.get("is_available"):
                        station_id = station.get("id")
                        payload = {"event": ev.get("id"), "station": station_id}
                        
                        book_start = asyncio.get_event_loop().time()
                        booked_ok = False
                        while asyncio.get_event_loop().time() - book_start < 10:
                            try:
                                async with session_acc.post(URL_BOOK, json=payload, timeout=5) as r:
                                    if r.status in [200, 201]:
                                        tracker.success += 1
                                        if ev_date not in booked_today:
                                            booked_today[ev_date] = []
                                        booked_today[ev_date].append((ev_start, ev_end))
                                        booked_ok = True
                                        break
                                    elif r.status == 400:
                                        res = await r.json()
                                        err_msg = res.get("error", "")
                                        if "Уже записан" in err_msg:
                                            if ev_date not in booked_today:
                                                booked_today[ev_date] = []
                                            booked_today[ev_date].append((ev_start, ev_end))
                                            booked_ok = True
                                            break
                                        elif "запись закрыта" in err_msg.lower() or "не начата" in err_msg.lower():
                                            await asyncio.sleep(0.2)
                                            continue
                                        else:
                                            tracker.failed += 1
                                            break
                                    else:
                                        tracker.failed += 1
                                        break
                            except Exception:
                                await asyncio.sleep(0.2)
                        if booked_ok:
                            break
                            
        tracker.processed += 1

    async with STORM_LOCK:
        await asyncio.gather(*[worker_task(acc_id) for acc_id in active_ids])
    
    report_text = (
        f"🏁 *Автоматическая запись завершена*\n\n"
        f"📊 *Итоги распределения профилей:*\n"
        f" ├ Всего ботов: `{tracker.total}`\n"
        f" ├ Успешных записей: `{tracker.success}`\n"
        f" └ Ошибок/Отказов: `{tracker.failed}`\n\n"
        f"⏳ Запущен 14-минутный кулдаун — автоматическая отмена всех бронирований произойдет через 14 минут."
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=report_text, parse_mode="Markdown")
    except Exception:
        pass

    await asyncio.sleep(840)

    for i in active_ids:
        cookies, token = load_account_auth(i)
        if not cookies: continue
        headers_cancel = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        if token: headers_cancel["Authorization"] = f"Token {token}"
        async with aiohttp.ClientSession(cookies=cookies, headers=headers_cancel) as session:
            try:
                async with session.get(URL_CURRENT, params={"tab": "next"}, timeout=8) as r:
                    if r.status == 200:
                        personal_events = await r.json()
                        for ev in personal_events:
                            booking_id = ev.get("user_booking_id")
                            if booking_id is not None:
                                url = f"https://jget-events.ru/api/bookings/{booking_id}/cancel/"
                                async with session.patch(url, timeout=5) as rp: pass
            except Exception: pass
            await asyncio.sleep(0.4)

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text="🧹 *Авто-штурм полностью завершен!*\n\nВсе созданные бронирования ботов успешно отменены.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

async def saturday_scheduler_loop(bot: Bot):
    while True:
        try:
            cfg = load_scheduler_config()
            if cfg.get("active", False):
                now_msk = get_msk_now()
                # 5 is Saturday
                if now_msk.weekday() == 5:
                    last_run_date = cfg.get("last_run_date", "")
                    today_str = now_msk.strftime("%Y-%m-%d")
                    if last_run_date != today_str:
                        target_pre = now_msk.replace(hour=11, minute=58, second=30, microsecond=0)
                        target_start = now_msk.replace(hour=12, minute=0, second=0, microsecond=0)
                        
                        if target_pre <= now_msk < target_start:
                            print(f"[{now_msk.strftime('%H:%M:%S')}] Планировщик: подготовка к авто-записи в субботу...")
                            try:
                                await bot.send_message(
                                    chat_id=ADMIN_ID,
                                    text="⏰ *Планировщик*: Подготовка к записи на следующую неделю...\nПроверяю сессии ботов..."
                                )
                            except Exception:
                                pass
                                
                            active_ids = []
                            for i in range(1, 51):
                                if await check_bot_session(i):
                                    active_ids.append(i)
                                    
                            try:
                                await bot.send_message(
                                    chat_id=ADMIN_ID,
                                    text=f"⏰ *Планировщик*: Сессии проверены.\n"
                                         f"🟢 Активно ботов: `{len(active_ids)}` / 50.\n"
                                         f"Ожидаю 12:00:00 для запуска авто-записи..."
                                )
                            except Exception:
                                pass
                                
                            while True:
                                now_msk = get_msk_now()
                                if now_msk >= target_start:
                                    break
                                await asyncio.sleep(0.1)
                                
                            print(f"[{now_msk.strftime('%H:%M:%S')}] Планировщик: Суббота 12:00! Запуск авто-записи!")
                            cfg["last_run_date"] = today_str
                            save_scheduler_config(cfg)
                            asyncio.create_task(run_saturday_storm(bot, active_ids))
                            
                        elif now_msk >= target_start and now_msk < target_start + timedelta(minutes=5):
                            print(f"[{now_msk.strftime('%H:%M:%S')}] Планировщик: Запуск авто-записи (догоняющий режим)!")
                            cfg["last_run_date"] = today_str
                            save_scheduler_config(cfg)
                            
                            active_ids = []
                            for i in range(1, 51):
                                if await check_bot_session(i):
                                    active_ids.append(i)
                            asyncio.create_task(run_saturday_storm(bot, active_ids))
        except Exception as e:
            print(f"Ошибка в планировщике: {e}")
        await asyncio.sleep(5)



@router.callback_query(F.data.startswith("book_combo_"))
async def handle_book_combo(callback: CallbackQuery, bot: Bot):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("🔗 Сначала привяжите аккаунт!", show_alert=True)
        return
    page_idx = int(callback.data.split("_")[2])
    combos = USER_COMBO_PAGES.get(cid)
    if not combos or page_idx >= len(combos):
        await callback.answer("⚠️ Данные устарели, обновите комбо-пакет.", show_alert=True)
        return
    combo = combos[page_idx]
    token = acc.get("token", "")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Token {token}",
        "Referer": "https://jget-events.ru/events/"
    }
    total = len(combo)
    success = 0
    failed = 0
    results = []
    await callback.message.edit_text(
        f"📝 *ЗАПИСЬ НА КОМБО-МАРШРУТ*\n\n"
        f"⏳ Начинаю запись на {total} квест(ов)...\n"
        f"👤 Аккаунт: *{acc.get('name', '?')}*",
        parse_mode="Markdown"
    )
    async with aiohttp.ClientSession(headers=headers) as session:
        for idx, item in enumerate(combo, 1):
            event_id = item.get("id")
            station_id = item.get("station_id")
            payload = {"event": event_id, "station": station_id}
            status_text = (
                f"📝 *ЗАПИСЬ НА КОМБО-МАРШРУТ*\n\n"
                f"👤 Аккаунт: *{acc.get('name', '?')}*\n"
                f"📊 Прогресс: `{idx}/{total}`\n\n"
            )
            try:
                async with session.post(URL_BOOK, json=payload, timeout=8) as r:
                    if r.status in [200, 201]:
                        success += 1
                        results.append(f"✅ {item['start']} | {item['school']} — Записан (ст. {item['station_num']})")
                    elif r.status == 400:
                        res = await r.json()
                        err_msg = res.get("error", res.get("detail", "Ошибка 400"))
                        if "Уже записан" in str(err_msg):
                            success += 1
                            results.append(f"✅ {item['start']} | {item['school']} — Уже записан")
                        else:
                            failed += 1
                            results.append(f"❌ {item['start']} | {item['school']} — {err_msg}")
                    else:
                        failed += 1
                        results.append(f"❌ {item['start']} | {item['school']} — Статус {r.status}")
            except Exception as e:
                failed += 1
                results.append(f"❌ {item['start']} | {item['school']} — Ошибка сети")
            progress_lines = "\n".join(results)
            try:
                await callback.message.edit_text(
                    status_text + progress_lines,
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await asyncio.sleep(0.3)

    final_text = (
        f"📝 *ЗАПИСЬ НА КОМБО-МАРШРУТ — ЗАВЕРШЕНО*\n\n"
        f"👤 Аккаунт: *{acc.get('name', '?')}*\n"
        f"✅ Успешно: *{success}*  |  ❌ Ошибки: *{failed}*\n\n"
        + "\n".join(results)
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад к комбо", callback_data="slots_combo"))
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    try:
        await callback.message.edit_text(final_text, parse_mode="Markdown", reply_markup=builder.as_markup())
    except Exception:
        pass



@router.callback_query(F.data == "study_menu")
async def handle_study_menu(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👮 Квест ПДД", url="https://t.me/+kVpp9O_zG5NiNmYy"),
        InlineKeyboardButton(text="👨‍🚒 Квест Спасатели", url="https://t.me/+F9tjTvQySNhiOTM6")
    )
    builder.row(
        InlineKeyboardButton(text="🤝 Квест Дружба", url="https://t.me/+CKJhCn8uue43NDNi"),
        InlineKeyboardButton(text="🏴‍☠️ Квест Сокровища", url="https://t.me/+zm3hNS-6WXU4YWVi")
    )
    builder.row(
        InlineKeyboardButton(text="💎 Квест Бриллианты", url="https://t.me/+YG7BrGbZwq80ZTUy")
    )
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    await callback.message.edit_text(
        text="📚 *БАЗА ЗНАНИЙ И ОБУЧАЮЩИЕ МАТЕРИАЛЫ*\nВыбери интересующий квест для перехода на закрытый канал:",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "about_bot")
async def handle_about_bot(callback: CallbackQuery):
    text = (
        "Привет. На связи @lysuki. \n\n"
        "Я решил сделать эту страницу, чтобы рассказать, как вообще появился этот бот, зачем он нужен и что умеет. Это не какой-то официальный продукт, а просто мой личный проект, который я написал от души и для удобства всех нас.\n\n"
        "Как все началось:\n"
        "Я сам пришел учиться в школу программирования J-GET. Мне всегда нравилось возиться с кодом, парсить данные, автоматизировать рутину и искать слабые места в разных системах. Когда я начал работать здесь ведущим квестов и пользоваться сайтом смен, я заметил, что у него открытый API. Любой, кто хоть немного разбирается в веб-разработке, мог без всякого взлома получить доступ к расписанию и спискам ведущих.\n\n"
        "Тогда мне и пришла идея объединить это в один проект. Я взял открытые данные с сайта J-GET и написал автоматизацию. Из-за того, что бот мгновенно собирает информацию и делает расчеты, администраторам квестов иногда кажется, будто я взломал их базу данных. Но на самом деле тут нет никакого хакерства — только парсинг открытого API и формулы математического расчета, которые работают в фоне. \n\n"
        "Я написал этот софт исключительно для удобства — своего и ребят, которые работают со мной на квестах. Здесь нет ничего скрытого. Если ты привязываешь свой аккаунт, бот использует твои данные только для того, чтобы отправлять запросы на сайт J-GET от твоего имени — например, автоматически записывать тебя на смены или показывать твою личную статистику. Это просто инструмент, помогающий не тратить время на ручное обновление сайта.\n\n"
        "Что именно умеет делать этот бот:\n\n"
        "1. Свободные места. Показывает актуальную информацию о том, в каких школах есть свободные смены на сегодня или другие дни недели, чтобы тебе не приходилось постоянно заходить на сайт.\n\n"
        "2. Гибкие фильтры. Позволяет настроить список свободных мест полностью под себя: можно отключить квесты определенных тематик или отфильтровать станции по сложности (оставить только легкие, средние или сложные в зависимости от твоего настроя).\n\n"
        "3. Комбо-пакеты. Это моя гордость — специальный алгоритм, который берет все свободные смены на день, анализирует их время и собирает для тебя самый выгодный маршрут. Он учитывает переезды между школами и выбирает самые простые станции, чтобы ты мог заработать максимум за день с минимальной усталостью.\n\n"
        "4. Станции ведущих. Показывает распределение ролей в каждой школе. Ты сразу видишь, кто сегодня работает напарником, кто назначен главарем, а кто стоит на какой станции.\n\n"
        "5. Личный кабинет и профиль. Показывает твое имя, телефон и статистику смен с сайта. Здесь встроен финансовый трекер. Бот автоматически считает, сколько денег ты уже заработал за проведенные смены, сколько сейчас находится в ожидании за будущие смены и какая выйдет общая сумма за текущий месяц. Также здесь можно посмотреть свой план на сегодня со ссылками на Яндекс Карты для быстрой навигации.\n\n"
        "6. Уведомления. Если ты записан на квесты, бот пришлет тебе напоминание ровно за полтора часа до начала, чтобы ты точно не опоздал. Эту функцию можно в любой момент отключить в настройках профиля.\n\n"
        "7. Раздел Полезное. Это аналитический блок, где можно посмотреть таблицу выплат ведущим и главарям, увидеть график заработка топ-10 участников, рейтинги по проведенным квестам и даже поискать досье любого ведущего в базе, если он не скрыл свои данные через настройки приватности.\n\n"
        "Этот проект — просто помощь себе и другим. Мне хотелось сделать качественный инструмент, который уберет рутину с бесконечным обновлением сайта и поможет нам всем работать более эффективно. \n\n"
        "Если у тебя появятся идеи или ты найдешь ошибку — обязательно пиши мне в личные сообщения. Удачи на сменах."
    )
    await callback.message.edit_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=get_back_btn("main_menu")
    )


def get_filters_keyboard(chat_id, page_idx):
    import copy
    if chat_id not in USER_TEMP_FILTERS:
        USER_TEMP_FILTERS[chat_id] = copy.deepcopy(get_user_filters(chat_id))
    uf = USER_TEMP_FILTERS[chat_id]
    difficulties = uf.setdefault("difficulties", {"easy": True, "medium": True, "hard": True})
    categories = uf.get("categories", {})
    builder = InlineKeyboardBuilder()
    
    easy_lbl = ("✅" if difficulties.get("easy", True) else "❌") + " Легк"
    med_lbl = ("✅" if difficulties.get("medium", True) else "❌") + " Сред"
    hard_lbl = ("✅" if difficulties.get("hard", True) else "❌") + " Слож"
    builder.row(
        InlineKeyboardButton(text=easy_lbl, callback_data=f"filter_toggle_diff_easy_{page_idx}"),
        InlineKeyboardButton(text=med_lbl, callback_data=f"filter_toggle_diff_medium_{page_idx}"),
        InlineKeyboardButton(text=hard_lbl, callback_data=f"filter_toggle_diff_hard_{page_idx}")
    )
    
    builder.row(
        InlineKeyboardButton(text=("✅ " if categories.get("ПДД", True) else "❌ ") + "ПДД", callback_data=f"filter_toggle_cat_ПДД_{page_idx}"),
        InlineKeyboardButton(text=("✅ " if categories.get("Спасатель", True) else "❌ ") + "Спасатели", callback_data=f"filter_toggle_cat_Спасатель_{page_idx}")
    )
    builder.row(
        InlineKeyboardButton(text=("✅ " if categories.get("Дружба", True) else "❌ ") + "Дружба", callback_data=f"filter_toggle_cat_Дружба_{page_idx}"),
        InlineKeyboardButton(text=("✅ " if categories.get("Сокровища", True) else "❌ ") + "Сокровища", callback_data=f"filter_toggle_cat_Сокровища_{page_idx}")
    )
    builder.row(
        InlineKeyboardButton(text=("✅ " if categories.get("Бриллианты", True) else "❌ ") + "Бриллианты", callback_data=f"filter_toggle_cat_Бриллианты_{page_idx}")
    )
    builder.row(
        InlineKeyboardButton(text="💾 Сохранить", callback_data=f"filter_save_{page_idx}"),
        InlineKeyboardButton(text="↩️ Назад", callback_data=f"filter_cancel_{page_idx}")
    )
    return builder.as_markup()

@router.callback_query(F.data.startswith("filters_slots_"))
async def handle_filters_slots(callback: CallbackQuery):
    cid = callback.message.chat.id
    page_idx = int(callback.data.split("_")[2])
    import copy
    USER_TEMP_FILTERS[cid] = copy.deepcopy(get_user_filters(cid))
    text = (
        "⚙️ *НАСТРОЙКА ФИЛЬТРОВ РАСПИСАНИЯ*\n\n"
        "Настрой отображение квестов под себя. Выбранные категории будут показываться в списке свободных мест, а выключенные будут скрыты."
    )
    await callback.message.edit_text(text=text, parse_mode="Markdown", reply_markup=get_filters_keyboard(cid, page_idx))

@router.callback_query(F.data.startswith("filter_toggle_diff_"))
async def handle_filter_toggle_diff(callback: CallbackQuery):
    cid = callback.message.chat.id
    parts = callback.data.split("_")
    diff_level = parts[3]
    page_idx = int(parts[4])
    if cid not in USER_TEMP_FILTERS:
        import copy
        USER_TEMP_FILTERS[cid] = copy.deepcopy(get_user_filters(cid))
    diffs = USER_TEMP_FILTERS[cid].setdefault("difficulties", {"easy": True, "medium": True, "hard": True})
    diffs[diff_level] = not diffs.get(diff_level, True)
    text = (
        "⚙️ *НАСТРОЙКА ФИЛЬТРОВ РАСПИСАНИЯ*\n\n"
        "Настрой отображение квестов под себя. Выбранные категории будут показываться в списке свободных мест, а выключенные будут скрыты."
    )
    try:
        await callback.message.edit_text(text=text, parse_mode="Markdown", reply_markup=get_filters_keyboard(cid, page_idx))
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("filter_toggle_cat_"))
async def handle_filter_toggle_cat(callback: CallbackQuery):
    cid = callback.message.chat.id
    parts = callback.data.split("_")
    cat_name = parts[3]
    page_idx = int(parts[4])
    if cid not in USER_TEMP_FILTERS:
        import copy
        USER_TEMP_FILTERS[cid] = copy.deepcopy(get_user_filters(cid))
    cats = USER_TEMP_FILTERS[cid].setdefault("categories", {})
    cats[cat_name] = not cats.get(cat_name, True)
    text = (
        "⚙️ *НАСТРОЙКА ФИЛЬТРОВ РАСПИСАНИЯ*\n\n"
        "Настрой отображение квестов под себя. Выбранные категории будут показываться в списке свободных мест, а выключенные будут скрыты."
    )
    try:
        await callback.message.edit_text(text=text, parse_mode="Markdown", reply_markup=get_filters_keyboard(cid, page_idx))
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("filter_save_"))
async def handle_filter_save(callback: CallbackQuery):
    cid = callback.message.chat.id
    page_idx = int(callback.data.split("_")[2])
    if cid in USER_TEMP_FILTERS:
        save_user_filters(cid, USER_TEMP_FILTERS[cid])
        USER_TEMP_FILTERS.pop(cid, None)
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("Ошибка доступа к кэшу. Вернись в меню.", reply_markup=get_back_btn())
        return
    pages, sorted_dates = chunk_by_days(GLOBAL_CACHED_DATA, chat_id=cid)
    if not pages:
        await callback.message.edit_text("🟢 На этой неделе свободных мест по данным фильтрам нет.", reply_markup=get_pagination_keyboard(0, 1, "page_all", cid))
        return
    if page_idx >= len(pages):
        page_idx = len(pages) - 1
    if page_idx < 0:
        page_idx = 0
    USER_PAGES[cid] = page_idx
    await callback.message.edit_text(text=pages[page_idx], parse_mode="Markdown", reply_markup=get_pagination_keyboard(page_idx, len(pages), "page_all", cid), disable_web_page_preview=True)

@router.callback_query(F.data.startswith("filter_cancel_"))
async def handle_filter_cancel(callback: CallbackQuery):
    cid = callback.message.chat.id
    page_idx = int(callback.data.split("_")[2])
    USER_TEMP_FILTERS.pop(cid, None)
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("Ошибка доступа к кэшу. Вернись в меню.", reply_markup=get_back_btn())
        return
    pages, sorted_dates = chunk_by_days(GLOBAL_CACHED_DATA, chat_id=cid)
    if not pages:
        await callback.message.edit_text("🟢 На этой неделе свободных мест нет.", reply_markup=get_back_btn())
        return
    if page_idx >= len(pages):
        page_idx = len(pages) - 1
    if page_idx < 0:
        page_idx = 0
    USER_PAGES[cid] = page_idx
    await callback.message.edit_text(text=pages[page_idx], parse_mode="Markdown", reply_markup=get_pagination_keyboard(page_idx, len(pages), "page_all", cid), disable_web_page_preview=True)


@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("Ошибка доступа к кэшу. Вернись в меню.", reply_markup=get_back_btn())
        return
    parts = callback.data.split("_")
    mode = parts[1]
    page_idx = int(parts[2])
    if mode == "st":
        pages, sorted_dates = chunk_stations(GLOBAL_CACHED_DATA)
        prefix = "page_st"
    elif mode == "combo":
        pages, sorted_dates, combos_data = chunk_combos(GLOBAL_CACHED_DATA, chat_id=cid)
        USER_COMBO_PAGES[cid] = combos_data
        prefix = "page_combo"
    else:
        pages, sorted_dates = chunk_by_days(GLOBAL_CACHED_DATA, chat_id=cid)
        prefix = "page_all"
    if page_idx < 0 or page_idx >= len(pages):
        await callback.answer()
        return
    USER_PAGES[cid] = page_idx
    combo_date = sorted_dates[page_idx] if prefix == "page_combo" else None
    await callback.message.edit_text(text=pages[page_idx], parse_mode="Markdown", reply_markup=get_pagination_keyboard(page_idx, len(pages), prefix, cid, combo_date), disable_web_page_preview=True)

@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery):
    await callback.answer()



@router.callback_query(F.data.in_(["osint_rates_players", "osint_rates_leaders", "osint_tops", "osint_fun", "osint_search_mode", "osint_chart"]))
async def handle_osint_sub(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text("Кэш пуст. Вернись в меню.", reply_markup=get_back_btn())
        return
    profiles = analyze_community(GLOBAL_CACHED_DATA)
    action = callback.data
    if action == "osint_rates_players":
        linked_accounts = load_linked_accounts()
        linked_names_map = {}
        for acc_data in linked_accounts.values():
            n = acc_data.get("name", "").strip()
            if n:
                linked_names_map[n.lower()] = acc_data
        player_payouts = []
        for name, info in profiles.items():
            if info["total_player"] > 0:
                player_payouts.append({
                    "name": name,
                    "conducted": info["completed_player"],
                    "is_linked": False,
                    "player_lates": info.get("player_lates", 0)
                })
        profiles_names_lower = {n.lower() for n in profiles.keys()}
        for n_lower, acc_data in linked_names_map.items():
            if n_lower not in profiles_names_lower:
                c_count = acc_data.get("conducted", 0)
                if c_count > 0:
                    player_payouts.append({
                        "name": acc_data["name"],
                        "conducted": c_count,
                        "is_linked": True,
                        "player_lates": 0
                    })
        for p in player_payouts:
            n_lower = p["name"].lower()
            if n_lower in linked_names_map:
                acc_data = linked_names_map[n_lower]
                p["is_linked"] = True
                p["conducted"] = acc_data.get("conducted", p["conducted"])
            p["player_lates"] = 0
            for name, info in profiles.items():
                if name.lower() == p["name"].lower():
                    p["player_lates"] = info.get("player_lates", 0)
                    break
        player_payouts.sort(key=lambda x: x["conducted"], reverse=True)
        res = ["🏃 *ВЫПЛАТЫ ВЕДУЩИХ СТАНЦИЙ (517 руб/квест, опоздание - 400 руб):*\n"]
        for p in player_payouts:
            if p["conducted"] > 0:
                p_lates = p.get("player_lates", 0)
                clean_count = max(0, p["conducted"] - p_lates)
                cash = clean_count * PAYOUT_PLAYER + min(p["conducted"], p_lates) * 400
                res.append(f"👤 *{p['name']}* — 💸 *{cash} руб.* (опозданий: {p_lates})")
        await callback.message.edit_text("\n".join(res), parse_mode="Markdown", reply_markup=get_back_btn("osint_menu"))
    elif action == "osint_rates_leaders":
        sorted_users = sorted(profiles.items(), key=lambda x: x[1]["completed_leader"], reverse=True)
        res = ["👑 *ВЫПЛАТЫ ГЛАВАРЕЙ КВЕСТОВ (1500 руб/квест):*\n"]
        for name, info in sorted_users:
            if info["total_leader"] > 0:
                cash = info["completed_leader"] * PAYOUT_LEADER
                res.append(f"👤 *{name}* — 💸 *{cash} руб.*")
        await callback.message.edit_text("\n".join(res), parse_mode="Markdown", reply_markup=get_back_btn("osint_menu"))
    elif action == "osint_tops":
        sorted_leaders = sorted(profiles.items(), key=lambda x: x[1]["completed_leader"], reverse=True)
        res = ["👑 *ТОП ПО ПРОВЕДЕННЫМ КВЕСТАМ В РОЛИ ГЛАВАРЯ:* \n"]
        for idx, (name, info) in enumerate(sorted_leaders, 1):
            if info["total_leader"] > 0:
                res.append(f"{idx}. *{name}* — успешно провел {info['completed_leader']} из {info['total_leader']}")
        await callback.message.edit_text("\n".join(res), parse_mode="Markdown", reply_markup=get_back_btn("osint_menu"))
    elif action == "osint_chart":
        await callback.message.answer("📊 Генерирую аналитический график...")
        chart_buffer = generate_analytics_plot(profiles)
        img_file = BufferedInputFile(chart_buffer.read(), filename="analytics.png")
        await callback.message.answer_photo(photo=img_file, caption="📈 Топ-10 по выплатам.")
    elif action == "osint_fun":
        sorted_all = sorted(profiles.items(), key=lambda x: (x[1]["completed_player"] + x[1]["completed_leader"]), reverse=True)
        sorted_leaders = sorted(profiles.items(), key=lambda x: x[1]["completed_leader"], reverse=True)
        sorted_players = sorted(profiles.items(), key=lambda x: x[1]["completed_player"], reverse=True)
        unique_leaders_count = sum(1 for u in profiles.values() if u["total_leader"] > 0)
        total_budget = sum(
            (u["completed_player"] - u.get("player_lates", 0)) * PAYOUT_PLAYER
            + u.get("player_lates", 0) * 400
            + u["completed_leader"] * PAYOUT_LEADER
            for u in profiles.values()
        )
        sorted_lates = sorted(profiles.items(), key=lambda x: x[1].get("lates", 0), reverse=True)
        latecomer_str = "Опаздунов нет 😇"
        if sorted_lates and sorted_lates[0][1].get("lates", 0) > 0:
            latecomer_str = f"{sorted_lates[0][0]} ({sorted_lates[0][1].get('lates')} раз)"
        duo_counts = {}
        for u_name, u_info in profiles.items():
            for p_name, count in u_info.get("partners", {}).items():
                pair = tuple(sorted([u_name, p_name]))
                duo_counts[pair] = count
        if duo_counts:
            best_duo, best_duo_count = max(duo_counts.items(), key=lambda x: x[1])
            duo_str = f"{best_duo[0]} и {best_duo[1]} ({best_duo_count} квестов вместе)"
        else:
            duo_str = "Не определен"
        linked_accounts = load_linked_accounts()
        cancellations = []
        for acc_data in linked_accounts.values():
            n = acc_data.get("name", "").strip()
            c = acc_data.get("cancelled", 0)
            if n and c > 0:
                cancellations.append((n, c))
        if cancellations:
            cancellations.sort(key=lambda x: x[1], reverse=True)
            king_of_cancels_str = f"{cancellations[0][0]} ({cancellations[0][1]} отмен)"
        else:
            king_of_cancels_str = "Нет отмен у привязанных участников"
        sorted_skips = sorted(profiles.items(), key=lambda x: x[1].get("skips", 0), reverse=True)
        skipper_str = "Прогулов нет 😇"
        if sorted_skips and sorted_skips[0][1].get("skips", 0) > 0:
            skipper_str = f"{sorted_skips[0][0]} ({sorted_skips[0][1].get('skips')} прогулов)"
        sorted_diversity = sorted(profiles.items(), key=lambda x: len(x[1].get("categories", {})), reverse=True)
        diversity_str = "Нет"
        if sorted_diversity:
            diversity_str = f"{sorted_diversity[0][0]} ({len(sorted_diversity[0][1].get('categories', {}))} категорий)"
        sorted_minutes = sorted(profiles.items(), key=lambda x: (x[1].get("minutes_player", 0) + x[1].get("minutes_leader", 0)), reverse=True)
        marathon_str = "Нет"
        if sorted_minutes:
            m_user, m_info = sorted_minutes[0]
            total_hours = round((m_info.get("minutes_player", 0) + m_info.get("minutes_leader", 0)) / 60, 1)
            marathon_str = f"{m_user} ({total_hours} ч. на арене)"
        cat_champs = {}
        for name, info in profiles.items():
            for cat, count in info.get("categories", {}).items():
                if cat not in cat_champs or cat_champs[cat][1] < count:
                    cat_champs[cat] = (name, count)
        cat_lines = []
        for cat in ["Бриллианты", "Сокровища", "ПДД квест", "Дружба", "Команда первых", "Школьный спасатель"]:
            if cat in cat_champs:
                cat_lines.append(f"   🔹 *{cat}:* {cat_champs[cat][0]} ({cat_champs[cat][1]} квестов)")
        cat_champs_str = "\n".join(cat_lines) if cat_lines else "Нет данных"
        fun_txt = (
            "🎲 *ФАНОВАЯ СТАТИСТИКА И РЕКОРДЫ ПО ФАКТУ*\n\n"
            f"👑 *Главный Трудоголик:* {sorted_all[0][0]} ({sorted_all[0][1]['completed_player'] + sorted_all[0][1]['completed_leader']} квестов)\n"
            f"⭐ *Альфа-Главарь:* {sorted_leaders[0][0]} ({sorted_leaders[0][1]['completed_leader']} квестов)\n"
            f"🦾 *Раб станций:* {sorted_players[0][0]} ({sorted_players[0][1]['completed_player']} квестов)\n"
            f"⏰ *Главный опаздун:* {latecomer_str}\n"
            f"👻 *Главный прогульщик:* {skipper_str}\n"
            f"❌ *Король отмен:* {king_of_cancels_str}\n"
            f"👩‍❤️‍👨 *Легендарный Дуэт:* {duo_str}\n"
            f"🌈 *Мастер на все руки:* {diversity_str}\n"
            f"⏳ *Марафонщик:* {marathon_str}\n\n"
            f"🎯 *ЛИДЕРЫ КАТЕГОРИЙ:*\n{cat_champs_str}\n\n"
            f"📈 *Общая фактическая выплата команде:* {total_budget} руб."
        )
        await callback.message.edit_text(fun_txt, parse_mode="Markdown", reply_markup=get_back_btn("osint_menu"))
    elif action == "osint_search_mode":
        USER_SEARCHING[cid] = True
        await callback.message.edit_text("🔍 *ИНТЕЛЛЕКТУАЛЬНЫЙ ОСИНТ-ПОИСК*\n\nПришли фамилию и имя.", parse_mode="Markdown", reply_markup=get_back_btn("osint_menu"))



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

    if cid not in USER_SEARCHING or not GLOBAL_CACHED_DATA:
        return
    query_words = message.text.lower().strip().split()
    if message.chat.type == "private":
        try: await message.delete()
        except Exception: pass
    profiles = analyze_community(GLOBAL_CACHED_DATA)

    linked = load_linked_accounts()
    hidden_names = set()
    my_name = None
    my_acc = linked.get(str(cid))
    if my_acc:
        my_name = my_acc.get("name")
    for cid_str, acc_data in linked.items():
        if acc_data.get("hidden"):
            hidden_names.add(acc_data.get("name", ""))
    found_profiles = {}
    for name, info in profiles.items():
        if all(word in name.lower() for word in query_words):
            found_profiles[name] = info
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад в ОСИНТ меню", callback_data="osint_menu"))
    if not found_profiles:
        await edit_or_send(bot=bot, chat_id=cid, text="❌ Ведущий не обнаружен.", reply_markup=builder.as_markup())
        return
    report = []
    for name, info in found_profiles.items():

        is_self = (my_name and my_name == name)
        is_admin = (cid == ADMIN_ID)
        if name in hidden_names and not is_self and not is_admin:

            report.append(
                f"🔒 *{name}*\n\n"
                f"_Этот пользователь привязал аккаунт и скрыл свои данные._"
            )
            continue
        player_lates = info.get("player_lates", 0)
        lates_count = info.get("lates", 0)
        cash_player = (info["completed_player"] - player_lates) * PAYOUT_PLAYER + player_lates * 400
        cash_leader = info["completed_leader"] * PAYOUT_LEADER
        total_minutes = info.get("minutes_player", 0) + info.get("minutes_leader", 0)
        total_hours = round(total_minutes / 60, 1)
        history_block = "\n".join(info["history"])
        dosser = (
            f"👤 *ДОСЬЕ: {name}*\n"
            f"🏃 Как Ведущий: {info['completed_player']} -> *{cash_player} руб.*\n"
            f"👑 Как Главарь: {info['completed_leader']} -> *{cash_leader} руб.*\n"
            f"⚠️ Опозданий: *{lates_count}*\n"
            f"⏳ Отработано часов: *{total_hours}*\n\n"
            f"💰 *СУММАРНЫЙ ЗАРАБОТОК:* *{cash_player + cash_leader} рублей*\n\n"
            f"📅 *Лог:* \n{history_block}"
        )
        report.append(dosser)
    final_text = ("\n\n" + "-"*20 + "\n\n").join(report)
    await edit_or_send(bot=bot, chat_id=cid, text=final_text, reply_markup=builder.as_markup())


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
    asyncio.create_task(background_notifier(bot))
    asyncio.create_task(saturday_scheduler_loop(bot))
    asyncio.create_task(background_bot_check_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    if not os.path.exists(ACCOUNTS_DIR):
        os.makedirs(ACCOUNTS_DIR)
    asyncio.run(main())
