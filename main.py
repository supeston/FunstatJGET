import os
import sys
import subprocess

if os.environ.get("PYTHON_UPDATED") != "true":
    print("[CD-Система] Проверка обновлений на GitHub...")
    try:
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
        subprocess.run(["git", "reset", "--hard", "origin/main"], check=True)
        print("[CD-Система] Код успешно обновлен до последней версии!")
        os.environ["PYTHON_UPDATED"] = "true"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"[CD-Система] Ошибка автоапдейта (запуск текущей версии): {e}")

import re
import json
import random
import asyncio
import aiohttp
import gc
import time
from datetime import datetime, timedelta, timezone
import urllib.parse
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_VERSION = "1.2.0.6"
AUTH_FILE = "auth.json"
LINKED_FILE = "linked_accounts.json"
FILTERS_FILE = "user_filters.json"
URL_BOOK = "https://jget-events.ru/api/bookings/"
URL_LOGIN = "https://jget-events.ru/api/login/"
URL_PROFILE = "https://jget-events.ru/api/profile/"

PAYOUT_PLAYER = 500
PAYOUT_LEADER = 1000
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

def normalize_phone_for_display(phone_str: str) -> str:
    if not phone_str:
        return ""
    digits = "".join(c for c in str(phone_str) if c.isdigit())
    if len(digits) == 10:
        return f"+7{digits}"
    elif len(digits) == 11:
        if digits.startswith("8") or digits.startswith("7"):
            return f"+7{digits[1:]}"
        return f"+{digits}"
    elif len(digits) > 0:
        return f"+{digits}"
    return ""

def format_compact_shifts_list(shifts: list, is_saturday_preview: bool = False) -> str:
    if not shifts:
        return ""
        
    by_date = {}
    for s in shifts:
        by_date.setdefault(s["date"], []).append(s)
        
    sorted_dates = sorted(by_date.keys())
    
    day_blocks = []
    for d_str in sorted_dates:
        day_shifts = by_date[d_str]
        is_future_day = all(not s.get("is_completed") for s in day_shifts)
        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            day_name = DAYS_RU.get(dt.weekday(), "Неизвестно")
        except Exception:
            day_name = d_str
            
        if is_future_day:
            day_header = f"🔜 *{day_name}* (Предстоит)"
        else:
            day_header = f"📅 *{day_name}*"
        
        by_school = {}
        for s in day_shifts:
            by_school.setdefault(s["school"], []).append(s)
            
        sorted_schools = sorted(by_school.items())
        
        school_lines = []
        for school, s_shifts in sorted_schools:
            s_shifts = sorted(s_shifts, key=lambda x: x["start_time"])
            school_header = f"  🏫 *{school}*"
            
            shift_lines = []
            for item in s_shifts:
                if is_saturday_preview:
                    station_val = item.get("station_num", "?")
                    info = f"{item['category']} · ст. {station_val}"
                    icon = "•"
                else:
                    if item.get("is_completed"):
                        if not item.get("attended", True):
                            icon = "❌"
                            extra = " · Прогул"
                        elif item.get("late", False):
                            icon = "⚠️"
                            extra = " · Опозд."
                        else:
                            icon = "✅"
                            extra = ""
                    else:
                        icon = "⏳"
                        extra = ""
                        
                    role_val = str(item.get("role", "Ведущий")).replace("Станция ", "ст. ")
                    info = f"{item['category']} · {role_val}{extra}"
                
                time_str = f"{item['start_time'][:5]}–{item['end_time'][:5]}"
                shift_lines.append(f"     {icon} {time_str} | {info}")
                
            school_lines.append(school_header + "\n" + "\n".join(shift_lines))
            
        day_blocks.append(day_header + "\n" + "\n".join(school_lines))
        
    return "\n\n".join(day_blocks)



BOT_MESSAGE_ID = {}
USER_LINK_STATE = {}
TEMP_AUTO_BOOKINGS = {}
OSINT_SEARCH_RESULTS = {}

GLOBAL_CACHED_DATA = None
GLOBAL_CACHED_TOPS_ADMIN = None
GLOBAL_CACHED_TOPS_USER = None
PERSISTENT_EVENTS_FILE = "persistent_events.json"
PERSISTENT_EVENTS = {}

VIP_CHAT_IDS = {6871586046, 7932533408, 8556418483, 651563285}
VIP_NAMES = ["макар", "радэль", "радель", "ярик", "ярослав", "карим"]

def is_vip(site_name: str) -> bool:
    if not site_name:
        return False
    return any(vip in site_name.lower() for vip in VIP_NAMES)

def load_persistent_events():
    global PERSISTENT_EVENTS
    if os.path.exists(PERSISTENT_EVENTS_FILE):
        try:
            with open(PERSISTENT_EVENTS_FILE, "r", encoding="utf-8") as f:
                PERSISTENT_EVENTS = json.load(f)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка чтения {PERSISTENT_EVENTS_FILE}: {e}")
            PERSISTENT_EVENTS = {}
    else:
        PERSISTENT_EVENTS = {}

def save_persistent_events():
    try:
        with open(PERSISTENT_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(PERSISTENT_EVENTS, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка записи {PERSISTENT_EVENTS_FILE}: {e}")

def merge_into_persistent(new_events):
    global PERSISTENT_EVENTS
    updated = False
    for ev in new_events:
        ev_id = str(ev.get("id"))
        if ev_id and ev_id != "None":
            if ev_id not in PERSISTENT_EVENTS or PERSISTENT_EVENTS[ev_id] != ev:
                PERSISTENT_EVENTS[ev_id] = ev
                updated = True
    if updated:
        save_persistent_events()
    return updated

router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

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
    if "weekday_intercept_active" not in user_f:
        user_f["weekday_intercept_active"] = False
    if "auto_booking_schools" not in user_f:
        user_f["auto_booking_schools"] = []
    if "auto_booking_schools_exclude_mode" not in user_f:
        user_f["auto_booking_schools_exclude_mode"] = False
    if "auto_booking_stations" not in user_f:
        user_f["auto_booking_stations"] = {}
    if "auto_booking_time_mode" not in user_f:
        user_f["auto_booking_time_mode"] = "any"
    if "auto_booking_time_start" not in user_f:
        user_f["auto_booking_time_start"] = "10:00"
    if "auto_booking_time_end" not in user_f:
        user_f["auto_booking_time_end"] = "15:00"
    if "auto_booking_max_quests" not in user_f:
        user_f["auto_booking_max_quests"] = 6
    return user_f

def save_auto_booking_settings(chat_id, settings):
    filters = load_all_filters()
    cid_str = str(chat_id)
    filters[cid_str] = settings
    save_all_filters(filters)

def get_booked_count_on_day(user_name, date_str):
    count = 0
    if GLOBAL_CACHED_DATA:
        user_name_lower = user_name.strip().lower()
        for ev in GLOBAL_CACHED_DATA:
            if ev.get("date") == date_str:
                for p in ev.get("participants", []):
                    p_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
                    if p_name == user_name_lower:
                        count += 1
                        break
    return count

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


def time_diff_minutes(t1_str, t2_str):
    h1, m1 = map(int, t1_str.split(":"))
    h2, m2 = map(int, t2_str.split(":"))
    return (h2 * 60 + m2) - (h1 * 60 + m1)


def is_shift_valid_for_user(ev, user_name, settings, current_cached_data, temp_booked_shifts_on_date):
    ev_date_str = ev.get("date", "")
    school_name = format_school_name(ev.get("title", ""))
    
    # Enforce minimum 2 shifts for multi-shift schools
    user_schools = settings.get("auto_booking_schools", [])
    user_stations = settings.get("auto_booking_stations", {})
    
    total_school_events = []
    secured_count = 0
    
    if current_cached_data:
        for cached_ev in current_cached_data:
            if cached_ev.get("date") == ev_date_str:
                c_school = format_school_name(cached_ev.get("title", ""))
                if c_school == school_name:
                    raw_cat = cached_ev.get("event_type_name", "")
                    cat = normalize_category(raw_cat, cached_ev.get("title", ""))
                    clean_cat = clean_category_name(cat)
                    allowed_nums = user_stations.get(clean_cat, [])
                    if not allowed_nums:
                        continue
                    
                    total_school_events.append(cached_ev)
                    
                    is_user_booked = False
                    for p in cached_ev.get("participants", []):
                        p_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
                        if p_name == user_name:
                            is_user_booked = True
                            break
                    
                    is_temp_booked = False
                    ev_time_str = f"{cached_ev.get('start_time')[:5]}-{cached_ev.get('end_time')[:5]}"
                    for tb in temp_booked_shifts_on_date:
                        if tb["school"] == school_name and f"{tb['start_time']}-{tb['end_time']}" == ev_time_str:
                            is_temp_booked = True
                            break
                    
                    is_current = (cached_ev.get("id") == ev.get("id"))
                    
                    if is_user_booked or is_temp_booked or is_current:
                        secured_count += 1
                    else:
                        has_free_station = False
                        for target_num in allowed_nums:
                            for s in cached_ev.get("available_stations", []):
                                if s.get("is_available"):
                                    num = get_station_num(s.get("name"))
                                    if num == target_num:
                                        has_free_station = True
                                        break
                            if has_free_station:
                                break
                        if has_free_station:
                            secured_count += 1

    if len(total_school_events) >= 2 and secured_count < 2:
        return False
        
    booked_shifts = []
    if current_cached_data:
        for cached_ev in current_cached_data:
            if cached_ev.get("date") == ev_date_str:
                is_user_booked = False
                for p in cached_ev.get("participants", []):
                    p_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
                    if p_name == user_name:
                        is_user_booked = True
                        break
                # Only add if it's not the exact same event we are currently evaluating
                if is_user_booked and cached_ev.get("id") != ev.get("id"):
                    booked_shifts.append({
                        "start_time": cached_ev.get("start_time")[:5],
                        "end_time": cached_ev.get("end_time")[:5],
                        "school": format_school_name(cached_ev.get("title", ""))
                    })
                
    booked_shifts.extend(temp_booked_shifts_on_date)
                
    if booked_shifts:
        ev_start = ev.get("start_time")[:5]
        ev_end = ev.get("end_time")[:5]
        for booked in booked_shifts:
            # Overlap check
            if max(ev_start, booked["start_time"]) < min(ev_end, booked["end_time"]):
                return False
            # School travel gap check
            if booked["school"] != school_name:
                if ev_start >= booked["end_time"]:
                    gap = time_diff_minutes(booked["end_time"], ev_start)
                else:
                    gap = time_diff_minutes(ev_end, booked["start_time"])
                if gap < 60:
                    return False
                
    max_quests = settings.get("auto_booking_max_quests", 6)
    if max_quests != "max":
        if len(booked_shifts) >= int(max_quests):
            return False
            
    return True


def get_smart_matches(data, user_name, settings):
    user_schools = settings.get("auto_booking_schools", [])
    user_stations = settings.get("auto_booking_stations", {})
    max_quests = settings.get("auto_booking_max_quests", 6)
    
    candidates_by_date = {}
    now = datetime.now()
    
    for ev in data:
        ev_date_str = ev.get("date", "")
        try:
            ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d")
            if ev_date.date() < now.date():
                continue
        except Exception:
            continue
            
        time_mode = settings.get("auto_booking_time_mode", "any")
        if time_mode == "custom":
            start_limit = settings.get("auto_booking_time_start", "10:00")
            end_limit = settings.get("auto_booking_time_end", "15:00")
            if not (ev.get("start_time")[:5] >= start_limit and ev.get("end_time")[:5] <= end_limit):
                continue
                
        title = ev.get("title", "")
        school_name = format_school_name(title)
        if user_schools:
            exclude_mode = settings.get("auto_booking_schools_exclude_mode", False)
            if exclude_mode:
                if school_name in user_schools:
                    continue
            else:
                if school_name not in user_schools:
                    continue
                    
        already_booked = False
        for p in ev.get("participants", []):
            p_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
            if p_name == user_name:
                already_booked = True
                break
        if already_booked:
            continue
            
        raw_cat = ev.get("event_type_name", "")
        cat = normalize_category(raw_cat, title)
        clean_cat = clean_category_name(cat)
        
        allowed_nums = user_stations.get(clean_cat, [])
        if not allowed_nums:
            continue
            
        valid_stations = []
        for idx, target_num in enumerate(allowed_nums):
            for s in ev.get("available_stations", []):
                if s.get("is_available"):
                    num = get_station_num(s.get("name"))
                    if num == target_num:
                        valid_stations.append({
                            "station_id": s.get("id"),
                            "station_num": num,
                            "priority_index": idx
                        })
                        break
                
        if valid_stations:
            best = valid_stations[0]
            c = {
                "event_id": ev.get("id"),
                "station_id": best["station_id"],
                "valid_stations": valid_stations,
                "date": ev_date_str,
                "time": f"{ev.get('start_time')[:5]}-{ev.get('end_time')[:5]}",
                "start_time": ev.get("start_time")[:5],
                "end_time": ev.get("end_time")[:5],
                "school": school_name,
                "category": clean_cat,
                "station_num": best["station_num"],
                "priority_index": best["priority_index"]
            }
            candidates_by_date.setdefault(ev_date_str, []).append(c)
            
    booked_by_date = {}
    for ev in data:
        ev_date_str = ev.get("date", "")
        is_booked = False
        for p in ev.get("participants", []):
            p_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
            if p_name == user_name:
                is_booked = True
                break
        if is_booked:
            booked_by_date.setdefault(ev_date_str, []).append({
                "start_time": ev.get("start_time")[:5],
                "end_time": ev.get("end_time")[:5],
                "school": format_school_name(ev.get("title", ""))
            })
            
    def get_best_subset(candidates, booked_shifts, max_new_allowed):
        candidates = sorted(candidates, key=lambda x: x['start_time'])
        best_subset = []
        best_score = (-1, 999999)
        
        def backtrack(index, current_subset):
            nonlocal best_subset, best_score
            num_shifts = len(current_subset)
            sum_priority = sum(c['priority_index'] for c in current_subset)
            score = (num_shifts, -sum_priority)
            
            if score > best_score:
                best_score = score
                best_subset = list(current_subset)
                
            if num_shifts >= max_new_allowed:
                return
                
            for i in range(index, len(candidates)):
                c = candidates[i]
                overlap = False
                for active in current_subset:
                    if max(c['start_time'], active['start_time']) < min(c['end_time'], active['end_time']):
                        overlap = True
                        break
                    if c['school'] != active['school']:
                        if c['start_time'] >= active['end_time']:
                            gap = time_diff_minutes(active['end_time'], c['start_time'])
                        else:
                            gap = time_diff_minutes(c['end_time'], active['start_time'])
                        if gap < 60:
                            overlap = True
                            break
                if overlap:
                    continue
                for booked in booked_shifts:
                    if max(c['start_time'], booked['start_time']) < min(c['end_time'], booked['end_time']):
                        overlap = True
                        break
                    if c['school'] != booked['school']:
                        if c['start_time'] >= booked['end_time']:
                            gap = time_diff_minutes(booked['end_time'], c['start_time'])
                        else:
                            gap = time_diff_minutes(c['end_time'], booked['start_time'])
                        if gap < 60:
                            overlap = True
                            break
                if overlap:
                    continue
                    
                current_subset.append(c)
                backtrack(i + 1, current_subset)
                current_subset.pop()
                
        backtrack(0, [])
        return best_subset, best_score

    all_selected_matches = []
    all_dates = set(candidates_by_date.keys()) | set(booked_by_date.keys())
    
    for date_str in all_dates:
        candidates = candidates_by_date.get(date_str, [])
        booked = booked_by_date.get(date_str, [])
        
        max_limit = 999999
        if max_quests != "max":
            max_limit = int(max_quests)
            
        max_new_allowed = max_limit - len(booked)
        if max_new_allowed <= 0:
            continue
            
        subset, score = get_best_subset(candidates, booked, max_new_allowed)
        if subset:
            for c in subset:
                all_selected_matches.append({
                    "event_id": c["event_id"],
                    "station_id": c["station_id"],
                    "valid_stations": c["valid_stations"],
                    "date": c["date"],
                    "time": c["time"],
                    "school": c["school"],
                    "category": c["category"],
                    "station_num": c["station_num"]
                })
                
    return all_selected_matches


def get_user_stats(site_name, events_list):
    current_time = datetime.now()
    user_name_lower = site_name.strip().lower()
    completed_player = 0
    completed_leader = 0
    lates = 0
    player_lates = 0
    total_minutes = 0
    history = []
    
    school_mins = {}
    category_mins = {}
    station_mins = {}
    
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
            
        quest_mins = 60
        try:
            ts = datetime.strptime(event.get("start_time")[:8], "%H:%M:%S")
            te = datetime.strptime(event.get("end_time")[:8], "%H:%M:%S")
            diff_mins = (te - ts).total_seconds() / 60
            if diff_mins > 0:
                quest_mins = round(diff_mins)
        except Exception:
            pass
        total_work_mins = quest_mins
        
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
        role = "Главарь" if as_leader else (f"Станция {st_num}" if st_num else "Ведущий")
        
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
                        
                school_mins[school] = school_mins.get(school, 0) + total_work_mins
                clean_cat = clean_category_name(raw_cat)
                category_mins[clean_cat] = category_mins.get(clean_cat, 0) + total_work_mins
                station_mins[role] = station_mins.get(role, 0) + total_work_mins
                        
        hist_item = {
            "date": date_str,
            "category": clean_category_name(raw_cat),
            "role": role,
            "school": school,
            "is_completed": is_completed,
            "attended": attended,
            "late": late,
            "start_time": event.get("start_time", "00:00:00")[:5],
            "end_time": event.get("end_time", "00:00:00")[:5]
        }
        history.append(hist_item)
        
    history = sorted(history, key=lambda x: (x["date"], x["start_time"]))
    
    school_hours = {k: round(v / 60, 1) for k, v in sorted(school_mins.items(), key=lambda item: item[1], reverse=True)}
    category_hours = {k: round(v / 60, 1) for k, v in sorted(category_mins.items(), key=lambda item: item[1], reverse=True)}
    station_hours = {k: round(v / 60, 1) for k, v in sorted(station_mins.items(), key=lambda item: item[1], reverse=True)}
    
    return {
        "completed_player": completed_player,
        "completed_leader": completed_leader,
        "lates": lates,
        "player_lates": player_lates,
        "total_hours": round(total_minutes / 60, 1),
        "school_hours": school_hours,
        "category_hours": category_hours,
        "station_hours": station_hours,
        "history": history
    }

def generate_osint_dossier(target_first_name, target_last_name):
    total_booked = 0
    attended_count = 0
    skipped_count = 0
    late_count = 0
    leader_count = 0
    player_count = 0
    player_lates = 0
    total_minutes = 0
    school_counts = {}
    category_counts = {}
    station_counts = {}
    upcoming_shifts = []
    past_shifts = []
    
    now_msk = get_msk_now()
    today_date = now_msk.date()
    target_fn_lower = target_first_name.strip().lower()
    target_ln_lower = target_last_name.strip().lower()
    
    phone_val = None
    if PERSISTENT_EVENTS:
        for event in PERSISTENT_EVENTS.values():
            user_p = None
            for p in event.get("participants", []):
                p_fn = p.get("first_name", "").strip().lower()
                p_ln = p.get("last_name", "").strip().lower()
                if p_fn == target_fn_lower and p_ln == target_ln_lower:
                    user_p = p
                    if not phone_val and p.get("phone"):
                        phone_val = p.get("phone")
                    break
            if not user_p:
                continue
                
            total_booked += 1
            attended = user_p.get("attended", True)
            late = user_p.get("late", False)
            as_leader = user_p.get("as_leader")
            
            date_str = event.get("date", "")
            title = event.get("title", "")
            raw_cat = event.get("event_type_name", "")
            school_name = format_school_name(title)
            category = clean_category_name(raw_cat)
            
            st_obj = user_p.get("station")
            st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
            st_num = get_station_num(st_name)
            if as_leader:
                role_str = "Главарь"
            elif st_num:
                role_str = f"Станция {st_num}"
            else:
                role_str = "Ведущий"
                
            try:
                ev_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                ev_date = None
                
            shift_info = {
                "date": date_str,
                "start_time": event.get("start_time", "00:00:00")[:5],
                "end_time": event.get("end_time", "00:00:00")[:5],
                "school": school_name,
                "category": category,
                "role": role_str,
                "attended": attended,
                "late": late,
                "as_leader": as_leader
            }
            
            # Check if event is completed (in the past)
            is_completed = False
            current_time = datetime.now()
            try:
                full_end_str = f"{date_str} {event.get('end_time', '23:59:59')[:8]}"
                event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
                if event_end_dt <= current_time:
                    is_completed = True
            except Exception:
                try:
                    ev_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if ev_date_obj < current_time.date():
                        is_completed = True
                except Exception:
                    pass
                    
            if is_completed:
                past_shifts.append(shift_info)
                if attended:
                    attended_count += 1
                    if as_leader:
                        leader_count += 1
                    else:
                        player_count += 1
                        if late:
                            player_lates += 1
                    if late:
                        late_count += 1
                        
                    quest_mins = 60
                    try:
                        ts = datetime.strptime(event.get("start_time")[:8], "%H:%M:%S")
                        te = datetime.strptime(event.get("end_time")[:8], "%H:%M:%S")
                        diff_mins = (te - ts).total_seconds() / 60
                        if diff_mins > 0:
                            quest_mins = round(diff_mins)
                    except Exception:
                        pass
                    total_work_mins = quest_mins
                    total_minutes += total_work_mins
                    
                    school_counts[school_name] = school_counts.get(school_name, 0) + total_work_mins
                    category_counts[category] = category_counts.get(category, 0) + total_work_mins
                    station_counts[role_str] = station_counts.get(role_str, 0) + total_work_mins
                else:
                    skipped_count += 1
            else:
                upcoming_shifts.append(shift_info)
                
    linked_tg_info = None
    conducted_lifetime = None
    cancelled_lifetime = None
    accounts = load_linked_accounts()
    for uid_str, acc_val in accounts.items():
        acc_name = acc_val.get("name", "").strip().lower()
        target_full = f"{target_first_name} {target_last_name}".strip().lower()
        target_rev = f"{target_last_name} {target_first_name}".strip().lower()
        if acc_name == target_full or acc_name == target_rev:
            linked_tg_info = {
                "chat_id": uid_str,
                "phone": acc_val.get("phone", "Н/Д"),
                "experience_year": acc_val.get("experience_year", 1)
            }
            if linked_tg_info["phone"] and linked_tg_info["phone"] != "Н/Д":
                phone_val = linked_tg_info["phone"]
            try:
                conducted_lifetime = int(acc_val.get("conducted", 0))
            except Exception:
                conducted_lifetime = None
            try:
                cancelled_lifetime = int(acc_val.get("cancelled", 0))
            except Exception:
                cancelled_lifetime = None
            break
            
    if not phone_val:
        try:
            for fname in os.listdir("."):
                if fname.startswith("db_dump_") and fname.endswith(".json"):
                    with open(fname, "r", encoding="utf-8") as f:
                        dump_data = json.load(f)
                    found = False
                    for u in dump_data.get("users", []):
                        u_fn = u.get("first_name", "").strip().lower()
                        u_ln = u.get("last_name", "").strip().lower()
                        if u_fn == target_fn_lower and u_ln == target_ln_lower:
                            p_raw = u.get("phone")
                            if p_raw:
                                phone_val = p_raw
                                found = True
                                break
                    if found:
                        break
                    for ev in dump_data.get("raw_events", []):
                        for p in ev.get("participants", []):
                            p_fn = p.get("first_name", "").strip().lower()
                            p_ln = p.get("last_name", "").strip().lower()
                            if p_fn == target_fn_lower and p_ln == target_ln_lower:
                                p_raw = p.get("phone")
                                if p_raw:
                                    phone_val = p_raw
                                    found = True
                                    break
                        if found:
                            break
                    if found:
                        break
        except Exception as e:
            print(f"Error searching phone in db dumps: {e}")

    phone_line = ""
    if phone_val:
        phone_digits = re.sub(r'\D', '', str(phone_val).strip())
        if len(phone_digits) == 10:
            phone_digits = '7' + phone_digits
        if len(phone_digits) == 11 and phone_digits.startswith('8'):
            phone_digits = '7' + phone_digits[1:]
        if len(phone_digits) == 11 and phone_digits.startswith('7'):
            pretty_phone = f"+7 ({phone_digits[1:4]}) {phone_digits[4:7]}-{phone_digits[7:9]}-{phone_digits[9:11]}"
        else:
            pretty_phone = phone_val
        phone_line = f"📱 *Телефон:* `{pretty_phone}`"

    if linked_tg_info:
        phone_raw = linked_tg_info["phone"]
        if len(phone_raw) == 11 and phone_raw.startswith("7"):
            pretty_phone = f"+7 ({phone_raw[1:4]}) {phone_raw[4:7]}-{phone_raw[7:9]}-{phone_raw[9:11]}"
        else:
            pretty_phone = phone_raw
        year_val = linked_tg_info["experience_year"]
        year_str = "2-й (10:00)" if year_val == 2 else "1-й (12:00)"
        tg_part = (
            f"🔗 *Telegram:*\n"
            f"  ├ ID: `{linked_tg_info['chat_id']}`\n"
            f"  ├ Год: *{year_str}*\n"
            f"  └ Тел: `{pretty_phone}`\n\n"
        )
    else:
        tg_part = "⚠️ *Telegram не привязан*\n\n"

    total_completed = max(conducted_lifetime or 0, attended_count)
    uncached_completed = max(0, total_completed - attended_count)
    
    cancelled_val = cancelled_lifetime if cancelled_lifetime is not None else skipped_count
    
    total_hours_adjusted = round((total_minutes + uncached_completed * 60) / 60, 1)
    avg_shift_len = round(total_minutes / attended_count, 1) if attended_count > 0 else 0.0
    
    attendance_rate = round((total_completed / (total_completed + cancelled_val)) * 100, 1) if (total_completed + cancelled_val) > 0 else 0.0
    
    already_earned = 0
    if attended_count > 0 or uncached_completed > 0:
        already_earned = (
            leader_count * PAYOUT_LEADER +
            (player_count - player_lates) * PAYOUT_PLAYER +
            player_lates * 400 +
            uncached_completed * PAYOUT_PLAYER
        )
        
    expected_earnings = sum((PAYOUT_LEADER if s["as_leader"] else PAYOUT_PLAYER) for s in upcoming_shifts)
    total_earned_overall = already_earned + expected_earnings
    
    top_schools = sorted(school_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_schools_str = "\n".join([f"  • {sch}: {round(mins/60, 1)} ч." for sch, mins in top_schools]) if top_schools else "  _Нет сведений_"
    
    top_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cats_str = "\n".join([f"  • {cat}: {round(mins/60, 1)} ч." for cat, mins in top_cats]) if top_cats else "  _Нет сведений_"
    
    top_stations = sorted(station_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_stations_str = "\n".join([f"  • {role}: {round(mins/60, 1)} ч." for role, mins in top_stations]) if top_stations else "  _Нет сведений_"
    
    upcoming_shifts = sorted(upcoming_shifts, key=lambda x: x["date"])
    past_shifts = sorted(past_shifts, key=lambda x: x["date"], reverse=True)
    
    upcoming_lines = []
    for s in upcoming_shifts[:5]:
        upcoming_lines.append(f"  • {s['date']} | {s['start_time']} — {s['category']} ({s['role']}) в {s['school']}")
    upcoming_str = "\n".join(upcoming_lines) if upcoming_lines else "  _Предстоящих смен нет_"
    
    past_lines = []
    for s in past_shifts[:5]:
        late_symbol = " ⚠️ (Опоздание)" if s["late"] else ""
        attn_str = "" if s["attended"] else " ❌ (Неявка)"
        past_lines.append(f"  • {s['date']} | {s['start_time']} — {s['category']} ({s['role']}){attn_str}{late_symbol}")
    past_str = "\n".join(past_lines) if past_lines else "  _История смен пуста_"

    dossier_header = f"👤 *ДОСЬЕ: {target_first_name} {target_last_name}*\n"
    if phone_line:
        dossier_header += f"{phone_line}\n"
    else:
        dossier_header += "\n"

    return (
        f"{dossier_header}"
        f"{tg_part}"
        f"📊 *Статистика:*\n"
        f"  ├ Смен: *{total_completed}* (отмен: *{cancelled_val}*)\n"
        f"  ├ Опозданий: *{late_count}*\n"
        f"  ├ Часов: *{total_hours_adjusted}*\n"
        f"  ├ Ср. смена: *{avg_shift_len}* мин\n"
        f"  └ Посещаемость: *{attendance_rate}%*\n\n"
        f"💰 *Финансы:*\n"
        f"  ├ Заработано: *{already_earned}* ₽\n"
        f"  ├ Ожидается: *{expected_earnings}* ₽\n"
        f"  └ Итого: *{total_earned_overall}* ₽\n\n"
        f"🏫 *Топ школ:*\n{top_schools_str}\n\n"
        f"🎭 *Топ квестов:*\n{top_cats_str}\n\n"
        f"🎯 *Топ станций:*\n{top_stations_str}\n\n"
        f"⏱️ *Ближайшие смены:*\n"
        f"{upcoming_str}\n\n"
        f"📜 *Последние смены:*\n"
        f"{past_str}"
    )



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
            "phone": p.get("phone"),
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

def load_token_from_auth():
    if not os.path.exists(AUTH_FILE):
        return None
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
        if isinstance(auth_data, dict) and "origins" in auth_data:
            for origin in auth_data["origins"]:
                if "localStorage" in origin:
                    for item in origin["localStorage"]:
                        if item.get("name") == "token":
                            return item.get("value")
        return None
    except Exception:
        return None

async def fetch_all_data():
    token = load_token_from_auth()
    if not token:
        try:
            accounts = load_linked_accounts()
            for acc in accounts.values():
                if acc.get("token"):
                    token = acc.get("token")
                    break
        except Exception:
            pass

    if token:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Authorization": f"Token {token}"
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(URL_CURRENT, params={"tab": "current"}, timeout=10) as r1:
                    if r1.status != 200:
                        return None, f"Ошибка API с токеном (current): статус {r1.status}"
                    res1 = await r1.json()
                async with session.get(URL_NEXT, params={"tab": "next"}, timeout=10) as r2:
                    if r2.status != 200:
                        return None, f"Ошибка API с токеном (next): статус {r2.status}"
                    res2 = await r2.json()
                
                merged = {e["id"]: e for e in (res1 + res2)}.values()
                cleaned = [clean_event_for_cache(e) for e in merged]
                gc.collect()
                return cleaned, None
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка запроса с токеном ({e}), пробуем куки...")
    
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
    global GLOBAL_CACHED_DATA, GLOBAL_CACHED_TOPS_ADMIN, GLOBAL_CACHED_TOPS_USER
    last_log_time = 0
    while True:
        data, err = await fetch_all_data()
        if not err and data:
            GLOBAL_CACHED_DATA = data
            changes = merge_into_persistent(data)
            if changes:
                try:
                    GLOBAL_CACHED_TOPS_ADMIN = calculate_tops(is_admin=True)
                    GLOBAL_CACHED_TOPS_USER = calculate_tops(is_admin=False)
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка кэширования топов: {e}")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Глобальный кэш успешно обновлен (есть изменения в базе).")
            else:
                now_time = time.time()
                if now_time - last_log_time >= 60:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Глобальный кэш успешно обновлен (без изменений).")
                    last_log_time = now_time
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка фонового обновления: {err}")
        
        # Periodic garbage collection to ensure minimized RAM footprint
        gc.collect()
        await asyncio.sleep(1)

async def background_profiles_updater():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Фоновое обновление профилей запущено (раз в 5 минут).")
    while True:
        try:
            accounts = load_linked_accounts()
            updated = False
            for cid_str, acc in accounts.items():
                token = acc.get("token")
                if token:
                    profile_data, _ = await api_get_profile(token)
                    if profile_data:
                        stats = profile_data.get("stats", {})
                        user_info = profile_data.get("user", {})
                        conducted = stats.get("conducted", user_info.get("conducted_count", 0))
                        cancelled = stats.get("cancellations", user_info.get("cancellation_count", 0))
                        if acc.get("conducted") != conducted or acc.get("cancelled") != cancelled:
                            accounts[cid_str]["conducted"] = conducted
                            accounts[cid_str]["cancelled"] = cancelled
                            updated = True
                    await asyncio.sleep(0.5) # small delay
            if updated:
                save_linked_accounts(accounts)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка фонового обновления профилей: {e}")
        
        await asyncio.sleep(300)

async def background_weekday_autobooking_loop(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Фоновый перехват автозаписи запущен.")
    while True:
        try:
            now_msk = get_msk_now()
            if GLOBAL_CACHED_DATA:
                linked = load_linked_accounts()
                linked_users = [int(uid) for uid in linked.keys()]
                target_users = []
                priority_id = 6871586046
                if priority_id in linked_users:
                    target_users.append(priority_id)
                for uid in linked_users:
                    if uid != priority_id:
                        target_users.append(uid)

                for cid in target_users:
                    cid_str = str(cid)
                    if cid_str not in linked:
                        continue
                    settings = get_auto_booking_settings(cid)
                    if not settings.get("weekday_intercept_active", False):
                        continue
                    
                    user_name = linked[cid_str].get("name", "").strip().lower()
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
                        newly_booked_shifts = {}
                        for ev in GLOBAL_CACHED_DATA:
                            ev_date_str = ev.get("date", "")
                            try:
                                ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d")
                                if ev_date.date() <= now_msk.date():
                                    continue
                            except Exception:
                                continue
                                
                            temp_booked = newly_booked_shifts.get(ev_date_str, [])
                            if not is_shift_valid_for_user(ev, user_name, settings, GLOBAL_CACHED_DATA, temp_booked):
                                continue
                                
                            time_mode = settings.get("auto_booking_time_mode", "any")
                            if time_mode == "custom":
                                start_limit = settings.get("auto_booking_time_start", "10:00")
                                end_limit = settings.get("auto_booking_time_end", "15:00")
                                if not (ev.get("start_time")[:5] >= start_limit and ev.get("end_time")[:5] <= end_limit):
                                    continue
                                    
                            already_booked = False
                            for p in ev.get("participants", []):
                                p_name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().lower()
                                if p_name == user_name:
                                    already_booked = True
                                    break
                            if already_booked:
                                continue
                                
                            title = ev.get("title", "")
                            school_name = format_school_name(title)
                            if user_schools:
                                exclude_mode = settings.get("auto_booking_schools_exclude_mode", False)
                                if exclude_mode:
                                    if school_name in user_schools:
                                        continue
                                else:
                                    if school_name not in user_schools:
                                        continue
                                
                            raw_cat = ev.get("event_type_name", "")
                            cat = normalize_category(raw_cat, title)
                            clean_cat = clean_category_name(cat)
                            
                            allowed_nums = user_stations.get(clean_cat, [])
                            if not allowed_nums:
                                continue
                                
                            valid_stations = []
                            for target_num in allowed_nums:
                                for s in ev.get("available_stations", []):
                                    if s.get("is_available"):
                                        num = get_station_num(s.get("name"))
                                        if num == target_num:
                                            valid_stations.append((s.get("id"), num))
                                            break
                                    
                            if valid_stations:
                                booked_ok = False
                                booked_num = None
                                booked_station_id = None
                                for stat_id, stat_num in valid_stations:
                                    payload = {"event": ev.get("id"), "station": stat_id}
                                    try:
                                        async with session.post(URL_BOOK, json=payload, timeout=5) as r:
                                            if r.status in [200, 201]:
                                                booked_ok = True
                                                booked_num = stat_num
                                                booked_station_id = stat_id
                                                break
                                            elif r.status == 400:
                                                try:
                                                    res = await r.json()
                                                except Exception:
                                                    res = {}
                                                err_msg = str(res.get("error", ""))
                                                if "Уже записан" in err_msg or "запись закрыта" in err_msg.lower() or "не начата" in err_msg.lower():
                                                    break
                                    except Exception as e:
                                        pass
                                    await asyncio.sleep(0.5)

                                if booked_ok:
                                    # Mark the station as unavailable in memory to prevent other users from trying to book the same station
                                    for s in ev.get("available_stations", []):
                                        if s.get("id") == booked_station_id:
                                            s["is_available"] = False
                                            break

                                    newly_booked_shifts.setdefault(ev_date_str, []).append({
                                        "start_time": ev.get("start_time")[:5],
                                        "end_time": ev.get("end_time")[:5],
                                        "school": school_name
                                    })
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
                                        f"🎯 {clean_cat} | Станция {booked_num}"
                                    )
                                    await bot.send_message(chat_id=cid, text=alert_text, parse_mode="Markdown")
                                await asyncio.sleep(0.5)
        except Exception as ex:
            print(f"[!] Error in background weekday loop: {ex}")
        await asyncio.sleep(1)

def get_main_menu(chat_id=None):
    builder = InlineKeyboardBuilder()
    if chat_id and is_linked(chat_id):
        if chat_id in VIP_CHAT_IDS:
            builder.row(
                InlineKeyboardButton(text="🤖 Автозапись", callback_data="auto_booking_menu")
            )
    is_admin = chat_id and chat_id == ADMIN_ID
    if is_admin:
        builder.row(InlineKeyboardButton(text="🔍 ОСИНТ Поиск", callback_data="osint_search_start"))

    builder.row(InlineKeyboardButton(text="🏆 Топы", callback_data="tops_nav_0"))
    
    row_buttons = []
    if chat_id and is_linked(chat_id):
        row_buttons.append(InlineKeyboardButton(text="👤 Профиль", callback_data="user_profile"))
    else:
        row_buttons.append(InlineKeyboardButton(text="🔗 Привязать аккаунт", callback_data="link_start"))
    
    row_buttons.append(InlineKeyboardButton(text="📚 Гайды", callback_data="guides_menu"))
    builder.row(*row_buttons)
    
    if is_admin:
        builder.row(InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel"))

    return builder.as_markup()

def get_back_btn(target="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data=target)]])

def get_onboarding_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔗 Привязать аккаунт", callback_data="link_start"))
    builder.row(InlineKeyboardButton(text="❓ Зачем это?", callback_data="link_why"))
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
            "🛸 *J-GET*\n\nВыбери раздел:", 
            parse_mode="Markdown", reply_markup=get_main_menu(cid)
        )
        BOT_MESSAGE_ID[cid] = msg.message_id
    else:
        msg = await message.answer(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт jget-events.ru для доступа "
            "к автозаписи, статистике и профилю.",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )
        BOT_MESSAGE_ID[cid] = msg.message_id

@router.callback_query(F.data == "link_start")
async def handle_link_start(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE[cid] = "waiting_credentials"
    await callback.message.edit_text(
        "🔗 *ПРИВЯЗКА*\n\n"
        "Отправьте данные от jget-events.ru в одном сообщении:\n\n"
        "📱 1-я строка — *телефон*\n"
        "🔑 2-я строка — *пароль*\n\n"
        "Пример:\n"
        "`+79261234567`\n"
        "`мойпароль123`",
        parse_mode="Markdown", reply_markup=get_back_btn("link_back_onboarding")
    )

@router.callback_query(F.data == "link_back_onboarding")
async def handle_link_back_onboarding(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE.pop(cid, None)
    if is_linked(cid):
        await callback.message.edit_text(
            "🛸 *J-GET*\n\nВыбери раздел:", 
            parse_mode="Markdown", reply_markup=get_main_menu(cid)
        )
    else:
        await callback.message.edit_text(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт jget-events.ru для доступа "
            "к автозаписи, статистике и профилю.",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )

@router.callback_query(F.data == "link_why")
async def handle_link_why(callback: CallbackQuery):
    cid = callback.message.chat.id
    await callback.message.edit_text(
        "❓ *ЗАЧЕМ ПРИВЯЗЫВАТЬ АККАУНТ?*\n\n"
        "Привязка аккаунта jget-events.ru открывает полный набор функций бота:\n\n"
        "1️⃣ *Автозапись на квесты*\n"
        " └ Автоматический перехват субботних смен (в 10:00/12:00 по году обучения) и ловля будних смен по гибким фильтрам школ и станций.\n\n"
        "2️⃣ *Учет зарплаты и статистики*\n"
        " └ Подсчет заработанных и ожидаемых денег за месяц, статистика смен, отмен, опозданий и отработанного времени.\n\n"
        "3️⃣ *План дня и лог смен*\n"
        " └ Быстрый просмотр расписания на сегодня/завтра (время, школа, категория, станция/роль) и полная история смен.\n\n"
        "🔒 _Ваши данные хранятся локально и используются только для авторизации на официальном сайте._",
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
        
    USER_LINK_STATE[cid] = f"selecting_year:{name}:{phone}:{password}:{token}:{conducted}:{cancelled}"
    
    text = (
        "🎓 *ГОД ОБУЧЕНИЯ*\n\n"
        "Вы ходите на квесты первый или второй год?\n\n"
        "• *1-й год:* запись в *12:00*\n"
        "• *2-й год:* запись в *10:00*"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="1️⃣ 1-й год (12:00)", callback_data="link_year_set_1"))
    builder.row(InlineKeyboardButton(text="2️⃣ 2-й год (10:00)", callback_data="link_year_set_2"))
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("link_year_set_"))
async def handle_link_year_set(callback: CallbackQuery):
    cid = callback.message.chat.id
    state = USER_LINK_STATE.get(cid, "")
    if not state.startswith("selecting_year:"):
        await callback.answer("Сессия истекла. Начните заново.", show_alert=True)
        return
        
    selected_year = int(callback.data.split("_")[3])
    parts = state.split(":", 6)
    
    name = parts[1]
    phone = parts[2]
    password = parts[3]
    token = parts[4]
    conducted = int(parts[5])
    cancelled = int(parts[6])
    
    accounts = load_linked_accounts()
    accounts[str(cid)] = {
        "phone": phone,
        "password": password,
        "token": token,
        "name": name,
        "conducted": conducted,
        "cancelled": cancelled,
        "experience_year": selected_year
    }
    save_linked_accounts(accounts)
    USER_LINK_STATE.pop(cid, None)
    
    await callback.message.edit_text(
        f"✅ *Аккаунт привязан!*\n\n"
        f"👤 Привет, *{name}*!\n"
        f"Статус: *{'2-й год' if selected_year == 2 else '1-й год'}* (запись в {'10:00' if selected_year == 2 else '12:00'})\n\n"
        f"🛸 *J-GET*\n\nВыбери раздел:",
        parse_mode="Markdown", reply_markup=get_main_menu(cid)
    )

@router.callback_query(F.data == "link_confirm_no")
async def handle_link_confirm_no(callback: CallbackQuery):
    cid = callback.message.chat.id
    USER_LINK_STATE[cid] = "waiting_credentials"
    await callback.message.edit_text(
        "🔗 *ПРИВЯЗКА*\n\n"
        "Не ваш аккаунт? Попробуйте ещё раз:\n\n"
        "📱 1-я строка — *телефон*\n"
        "🔑 2-я строка — *пароль*",
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
    
    safe_site_name = site_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    safe_tg_name = tg_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    safe_tg_username = tg_username.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    token = acc.get("token")
    conducted = acc.get("conducted", 0)
    cancelled = acc.get("cancelled", 0)

    lates = 0
    player_lates = 0
    cached_hours = 0.0
    total_cached_completed = 0
    stats = None
    if GLOBAL_CACHED_DATA:
        stats = get_user_stats(site_name, list(PERSISTENT_EVENTS.values()))
        lates = stats["lates"]
        player_lates = stats["player_lates"]
        cached_hours = stats["total_hours"]
        cached_leader = stats["completed_leader"]
        cached_player = stats["completed_player"]
        total_cached_completed = cached_leader + cached_player

    try:
        conducted_val = int(conducted)
    except Exception:
        conducted_val = total_cached_completed

    try:
        cancelled_val = int(cancelled)
    except Exception:
        cancelled_val = 0

    total_completed = max(conducted_val, total_cached_completed)
    uncached_completed = max(0, total_completed - total_cached_completed)
    
    already_earned = 0
    if total_cached_completed > 0 or uncached_completed > 0:
        already_earned = (
            (stats["completed_leader"] if stats else 0) * PAYOUT_LEADER +
            ((stats["completed_player"] if stats else 0) - player_lates) * PAYOUT_PLAYER +
            player_lates * 400 +
            uncached_completed * PAYOUT_PLAYER
        )
        
    total_hours = round(cached_hours + uncached_completed * 1.0, 1)

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

    exp_year = acc.get("experience_year", 1)
    year_str = "1-й (12:00)" if exp_year == 1 else "2-й (10:00)"

    library_str = ""
    if stats:
        top_sch = list(stats["school_hours"].items())[:3]
        top_cats = list(stats["category_hours"].items())[:3]
        top_sts = list(stats["station_hours"].items())[:3]
        
        sch_str = "\n".join([f"  {k}: <b>{v}</b>ч" for k, v in top_sch]) if top_sch else "  <i>нет данных</i>"
        cat_str = "\n".join([f"  {k}: <b>{v}</b>ч" for k, v in top_cats]) if top_cats else "  <i>нет данных</i>"
        sts_str = "\n".join([f"  {k}: <b>{v}</b>ч" for k, v in top_sts]) if top_sts else "  <i>нет данных</i>"
        
        library_str = (
            f"\n<blockquote expandable>📚 <b>Библиотека часов</b>\n\n"
            f"🏫 Школы:\n{sch_str}\n\n"
            f"🎭 Квесты:\n{cat_str}\n\n"
            f"🎯 Станции:\n{sts_str}</blockquote>"
        )

    text = (
        f"👤 <b>ПРОФИЛЬ</b>\n\n"
        f"📛 Имя: <b>{safe_site_name}</b>\n"
        f"💬 TG: <b>{safe_tg_name}</b> ({safe_tg_username})\n"
        f"📞 Тел: <code>{phone_fmt}</code>\n"
        f"🎓 Год: <b>{year_str}</b>\n\n"
        f"📊 <b>Статистика</b>\n"
        f"  ├ Смен: <b>{total_completed}</b> (отмен: <b>{cancelled_val}</b>)\n"
        f"  ├ Опозданий: <b>{lates}</b>\n"
        f"  └ Часов: <b>{total_hours}</b>\n\n"
        f"💰 <b>Финансы</b>\n"
        f"  ├ Заработано: <b>{already_earned}</b> ₽\n"
        f"  ├ Ожидается: <b>{expected_earnings}</b> ₽\n"
        f"  └ Итого: <b>{total_for_month}</b> ₽\n"
        f"{library_str}"
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
                            role_str = f"{st_num} станция" if st_num else "ведущий"
                        tomorrow_shifts.append((start_time, f"{sch_clean}, {category} {start_time}-{end_time}, {role_str}"))

    plan_button = None
    if has_future_shifts_today:
        plan_button = InlineKeyboardButton(text="🗺️ План на сегодня", callback_data="today_plan")
    elif tomorrow_shifts:
        plan_button = InlineKeyboardButton(text="🗺️ План на завтра", callback_data="today_plan")

    builder = InlineKeyboardBuilder()
    if plan_button:
        builder.row(plan_button)
        
    toggle_year_text = "🎓 Сменить на 2-й год (10:00)" if exp_year == 1 else "🎓 Сменить на 1-й год (12:00)"
    builder.row(InlineKeyboardButton(text=toggle_year_text, callback_data="profile_toggle_year"))
    
    builder.row(
        InlineKeyboardButton(text="📜 Лог смен", callback_data="shift_log"),
        InlineKeyboardButton(text="🔑 Пароль", callback_data="show_password")
    )
    builder.row(
        InlineKeyboardButton(text="↩️ Меню", callback_data="main_menu")
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data == "profile_toggle_year")
async def handle_profile_toggle_year(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
        
    accounts = load_linked_accounts()
    acc = accounts.get(str(cid))
    if not acc:
        await callback.answer("Аккаунт не найден!", show_alert=True)
        return
        
    current_year = acc.get("experience_year", 1)
    new_year = 2 if current_year == 1 else 1
    acc["experience_year"] = new_year
    accounts[str(cid)] = acc
    save_linked_accounts(accounts)
    
    new_status = "второгодник (10:00)" if new_year == 2 else "первогодник (12:00)"
    try:
        await callback.answer(f"Статус успешно изменен на {new_status}!", show_alert=False)
    except Exception:
        pass
        
    await handle_user_profile(callback)

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
                    
                    leader_name = "Не назначен"
                    for participant in event.get("participants", []):
                        if participant.get("as_leader"):
                            p_fn = participant.get("first_name", "").strip()
                            p_ln = participant.get("last_name", "").strip()
                            p_full = f"{p_fn} {p_ln}".strip()
                            p_phone = participant.get("phone", "")
                            norm_phone = normalize_phone_for_display(p_phone)
                            if norm_phone:
                                leader_name = f"[{p_full}](tel:{norm_phone})"
                            else:
                                leader_name = p_full
                            break

                    if as_leader:
                        role_str = "Главарь"
                        role_display = "Роль: *Главарь*"
                        icon = "👑"
                    else:
                        st_obj = p.get("station")
                        st_name = st_obj.get("name") if isinstance(st_obj, dict) else ""
                        st_num = get_station_num(st_name)
                        role_str = f"Станция: {st_num}" if st_num else "Ведущий"
                        role_display = f"Станция: *{st_num}* | Ведущий: {leader_name}" if st_num else f"*Ведущий* ({leader_name})"
                        icon = "⭐"
                    
                    friends = ""
                    if is_vip(site_name):
                        friend_list = []
                        for participant in event.get("participants", []):
                            p_fn = participant.get("first_name", "")
                            p_ln = participant.get("last_name", "")
                            p_full = f"{p_fn} {p_ln}".strip()
                            if p_full.lower() != site_name.strip().lower() and is_vip(p_full):
                                p_as_leader = participant.get("as_leader")
                                if p_as_leader:
                                    p_role = "Главарь"
                                else:
                                    p_st_obj = participant.get("station")
                                    p_st_name = p_st_obj.get("name") if isinstance(p_st_obj, dict) else ""
                                    p_st_num = get_station_num(p_st_name)
                                    p_role = f"Станция {p_st_num}" if p_st_num else "Ведущий"
                                    
                                p_phone = participant.get("phone", "")
                                norm_phone = normalize_phone_for_display(p_phone)
                                if norm_phone:
                                    friend_str = f"[{p_full}](tel:{norm_phone}) ({p_role})"
                                else:
                                    friend_str = f"{p_full} ({p_role})"
                                friend_list.append(friend_str)
                        if friend_list:
                            friends = "\n🤝 Свои на смене: " + ", ".join(friend_list)

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
                        "payout": payout,
                        "leader_name": leader_name,
                        "friends": friends
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
                    leader_info = "" if s['role'] == "Главарь" else f" (Ведущий: {s['leader_name']})"
                    role_lines.append(f"  {connector}⏰ *{s['start_time'][:5]} - {s['end_time'][:5]}* — {s['icon']} *{s['role']}*{leader_info}")
                role_str = "\n".join(role_lines)
            friends_out = "".join(dict.fromkeys(s.get("friends", "") for s in block if s.get("friends", "")))
            block_fmt = (
                f"{num_prefix} **[{school}]({geo})**\n"
                f"🎯 Квест: {format_category_link(block[0]['raw_cat'])}\n"
                f"{time_str}\n"
                f"{role_str}{friends_out}"
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
    OSINT_SEARCH_RESULTS.pop(cid, None)
    if is_linked(cid):
        await callback.message.edit_text("🛸 *J-GET*\n\nВыбери раздел:", 
                                         parse_mode="Markdown", reply_markup=get_main_menu(cid))
    else:
        await callback.message.edit_text(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт jget-events.ru для доступа "
            "к автозаписи, статистике и профилю.",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )

@router.callback_query(F.data == "guides_menu")
async def handle_guides_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "📚 *ГАЙДЫ*\n\n"
        "Выберите раздел:"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🤖 Автозапись", callback_data="guide_autobooking"))
    builder.row(InlineKeyboardButton(text="👤 Профиль и баланс", callback_data="guide_profile"))
    builder.row(InlineKeyboardButton(text="🏆 Топы и библиотеки", callback_data="guide_tops"))
    builder.row(InlineKeyboardButton(text="⚠️ Важное", callback_data="guide_important"))
    builder.row(InlineKeyboardButton(text="❓ F.A.Q.", callback_data="guide_faq"))
    builder.row(InlineKeyboardButton(text="↩️ Меню", callback_data="main_menu"))
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "guide_autobooking")
async def handle_guide_autobooking(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    exp_year = acc.get("experience_year", 1) if acc else 1
    storm_time = "10:00" if exp_year == 2 else "12:00"
    precheck_time = "09:50" if exp_year == 2 else "11:50"
    
    text = (
        "🤖 *РУКОВОДСТВО ПО АВТОЗАПИСИ*\n\n"
        "Автозапись — это интеллектуальная система, которая ловит и бронирует смены (квесты) на сайте за вас.\n\n"
        f"⏱️ *Как происходит запись по субботам:*\n"
        f"1️⃣ *В {precheck_time} (Предпроверка):* Бот ищет смены на следующую неделю, подходящие под ваши фильтры.\n"
        f"2️⃣ *В {storm_time} (Штурм):* Бот моментально отправляет запросы на бронирование.\n\n"
        "⚙️ *Режимы работы:*\n"
        f"• *С подтверждением:* в {precheck_time} бот пришлет список найденных смен. Вам нужно нажать кнопку *«Подтвердить автозапись»* до {storm_time}, чтобы бот записал вас.\n"
        "• *Авто-режим (без подтверждения):* бот запишет вас на все подходящие смены автоматически.\n\n"
        "🛠️ *Настройка фильтров:*\n"
        "• *Школы:* можно выбрать только определенные школы (белый список) или исключить ненужные (черный список).\n"
        "• *Станции:* порядок выбора определяет приоритет. Сначала бот пытается записать на первую выбранную станцию, если она занята — на вторую и т.д.\n"
        "• *Время:* задает рамки начала и конца квеста (например, `10:00 - 15:00`). Квесты вне этого интервала будут проигнорированы.\n"
        "• *Кол-во квестов:* лимит смен на один календарный день (от 1 до 6)."
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="guides_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "guide_profile")
async def handle_guide_profile(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "👤 *ПРОФИЛЬ, БАЛАНС И СТАТИСТИКА*\n\n"
        "Раздел *«Профиль»* позволяет в реальном времени отслеживать вашу статистику и заработок.\n\n"
        "📊 *Статистика и аналитика:*\n"
        "• *Проведено:* общее число завершенных смен.\n"
        "• *Отмен:* количество отмененных смен.\n"
        "• *Опозданий:* количество смен с отметкой об опоздании.\n"
        "• *Часов:* суммарное время работы (1 смена = 1 час).\n\n"
        "💰 *Финансовый учет:*\n"
        "• Расчет ведется по ставкам: *1000 ₽* за Главаря, *500 ₽* за Ведущего (или *400 ₽* при опоздании).\n"
        "• *Уже заработано:* сумма за все прошедшие смены.\n"
        "• *В ожидании:* сумма за будущие смены, на которые вы уже записаны.\n"
        "• *Всего заработано:* общая сумма (заработанное + ожидаемое).\n\n"
        "🗺️ *План на сегодня/завтра:*\n"
        "• Отображает список ваших смен, точное время, школы и роли на выбранный день с удобной кнопкой навигации на Яндекс Карты."
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="guides_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "guide_important")
async def handle_guide_important(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "⚠️ *ВАЖНАЯ ИНФОРМАЦИЯ И ПРАВИЛА*\n\n"
        "❗️ *Выбор года обучения (Статуса):*\n"
        "Вы должны строго выбрать свой *реальный* статус (первогодник или второгодник).\n"
        "• Если вы выберете *второй год* будучи первогодником, бот попытается записать вас в 10:00 и получит ошибку сайта.\n"
        "• Если вы выберете *первый год* будучи второгодником, бот начнет запись только в 12:00, когда другие второгодники уже займут все лучшие места.\n\n"
        "❗️ *Ответственность за автозапись:*\n"
        "Бот берет на себя рутину по бронированию смен, но посещение смен и выполнение работы остается на вас. Не забывайте отменять смены, если не сможете прийти!"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="guides_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "guide_tops")
async def handle_guide_tops(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "🏆 *ГЛОБАЛЬНЫЕ ТОПЫ И БИБЛИОТЕКИ ЧАСОВ*\n\n"
        "Теперь в боте есть продвинутая система соревнований и персональной статистики!\n\n"
        "📚 *Библиотеки Часов (в Профиле):*\n"
        "Скрытый блок в вашем профиле показывает суммарное отработанное время (в часах) в разрезе:\n"
        "• Любимых школ (локаций)\n"
        "• Любимых квестов (например, ПДД, Дружба)\n"
        "• Ваших самых популярных ролей/станций\n\n"
        "🏆 *Глобальные Топы (Главное меню):*\n"
        "Вы можете соревноваться со всеми пользователями бота! Доступны 7 категорий:\n"
        "1. *Топ по часам* — кто больше всех отработал?\n"
        "2. *Топ Главарей* / *Топ Ведущих* — лидеры по ролям.\n"
        "3. *Топ Опозданий* — антирейтинг пунктуальности.\n"
        "4. *Тематические топы* — лидеры в квестах Дружба, ПДД и в локации Адымнар.\n\n"
        "💡 _Используйте стрелочки под топом, чтобы переключаться между разными категориями лидербордов!_"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="guides_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "guide_faq")
async def handle_guide_faq(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "❓ *F.A.Q. — ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ*\n\n"
        "❓ *Безопасно ли передавать пароль боту?*\n"
        "➡️ Да, ваши данные хранятся локально в зашифрованном/защищенном виде на сервере бота и передаются исключительно на официальный сайт jget-events.ru для авторизации.\n\n"
        "❓ *Бот перехватывает смены в будни?*\n"
        "➡️ Да! Бот в фоновом режиме каждые 30 секунд проверяет новые смены. Если появляется свободное место в будний день, подходящее под ваши фильтры, бот мгновенно бронирует его и присылает уведомление.\n\n"
        "❓ *Как изменить или сбросить фильтры?*\n"
        "➡️ Перейдите в меню *«Автозапись»* и настройте фильтры заново. Чтобы ловить квесты в любых школах и на любых станциях, просто снимите галочки со всех элементов."
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="guides_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "osint_search_start")
async def handle_osint_search_start(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid != ADMIN_ID:
        await callback.answer("У вас нет прав администратора!", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    USER_LINK_STATE[cid] = "waiting_osint_query"
    OSINT_SEARCH_RESULTS.pop(cid, None)
    
    await callback.message.edit_text(
        "🔍 *ИНТЕЛЛЕКТУАЛЬНЫЙ ОСИНТ-ПОИСК*\n\n"
        "Отправьте имя, фамилию или часть имени/фамилии человека для поиска в базе данных смен.",
        parse_mode="Markdown",
        reply_markup=get_back_btn("main_menu")
    )

@router.callback_query(F.data.startswith("osint_view_"))
async def handle_osint_view(callback: CallbackQuery):
    cid = callback.message.chat.id
    if cid != ADMIN_ID:
        await callback.answer("У вас нет прав администратора!", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    idx_str = callback.data.split("_")[2]
    try:
        idx = int(idx_str)
    except Exception:
        await callback.message.edit_text("❌ Неверный индекс.", reply_markup=get_back_btn("main_menu"))
        return
        
    matches = OSINT_SEARCH_RESULTS.get(cid)
    if not matches or idx < 0 or idx >= len(matches):
        await callback.message.edit_text(
            "⏳ Сессия поиска истекла. Пожалуйста, выполните поиск заново.",
            reply_markup=get_back_btn("osint_search_start")
        )
        return
        
    fn, ln = matches[idx]
    dossier_text = generate_osint_dossier(fn, ln)
    
    await callback.message.edit_text(
        dossier_text,
        parse_mode="Markdown",
        reply_markup=get_back_btn("main_menu")
    )

async def run_saturday_autobooking_precheck(bot: Bot, year_group: int):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Saturday Auto-booking Precheck для группы {year_group}...")
    data, err = await fetch_all_data()
    if err or not data:
        print(f"[!] Precheck error: {err}")
        return
        
    linked = load_linked_accounts()
    group_users = []
    for uid_str, acc in linked.items():
        ug = acc.get("experience_year", 1)
        if ug == year_group:
            group_users.append(int(uid_str))
            
    target_users = []
    priority_id = 6871586046
    if priority_id in group_users:
        target_users.append(priority_id)
    for uid in group_users:
        if uid != priority_id:
            target_users.append(uid)
            
    for cid in target_users:
        cid_str = str(cid)
        if cid_str not in linked:
            continue
        settings = get_auto_booking_settings(cid)
        if not settings.get("auto_booking_active", False):
            continue
            
        user_name = linked.get(cid_str, {}).get("name", "").strip().lower()
        matches = get_smart_matches(data, user_name, settings)
                        
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
        
        matches_text = format_compact_shifts_list(matches, is_saturday_preview=True)
        
        storm_time = "10:00" if year_group == 2 else "12:00"
        if settings.get("auto_booking_mode", "confirm") == "auto":
            message_text = (
                f"🤖 *АВТОЗАПИСЬ (АВТО-РЕЖИМ)*\n\n"
                f"Найдены следующие смены по вашим фильтрам:\n\n"
                f"{matches_text}\n\n"
                f"⚡ Так как у вас включен автоматический режим, бот запишет вас на эти смены ровно в {storm_time} без подтверждения."
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
            f"⚠️ Нажмите кнопку ниже до {storm_time}, чтобы подтвердить автозапись на эти смены. "
            f"При штурме в {storm_time} бот автоматически запишет вас."
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

async def book_user(cid: int, targets: list, bot: Bot, year_group: int):
    _, token = load_account_auth_by_chat_id(cid)
    if not token:
        return
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Token {token}"
    }
    
    async def book_target(session, t):
        valid_stats = t.get("valid_stations", [{"station_id": t["station_id"], "station_num": t["station_num"]}])
        book_start = asyncio.get_event_loop().time()
        
        for st in valid_stats:
            payload = {"event": t["event_id"], "station": st["station_id"]}
            t["station_num"] = st["station_num"]
            
            while asyncio.get_event_loop().time() - book_start < 10:
                try:
                    async with session.post(URL_BOOK, json=payload, timeout=5) as r:
                        if r.status in [200, 201]:
                            return True, None
                        elif r.status == 400:
                            try:
                                res = await r.json()
                            except Exception:
                                res = {}
                            err_msg = str(res.get("error", ""))
                            if "Уже записан" in err_msg:
                                return True, "already"
                            elif "запись закрыта" in err_msg.lower() or "не начата" in err_msg.lower():
                                await asyncio.sleep(0.1)
                                continue
                            else:
                                break
                        else:
                            break
                except Exception:
                    await asyncio.sleep(0.1)
            else:
                return False, "Превышено время ожидания"
        return False, "Все станции заняты или ошибка"
        
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
        time_display = "10:00" if year_group == 2 else "12:00"
        report_text = (
            f"🤖 *ОТЧЕТ ОБ АВТОЗАПИСИ (Суббота {time_display})*\n\n"
            f"Бот завершил попытку автозаписи на подтвержденные смены:\n\n"
            f"{report_lines_joined}\n\n"
            f"Записано смен: *{success_count}* из *{len(targets)}*."
        )
        try:
            await bot.send_message(chat_id=cid, text=report_text, parse_mode="Markdown")
        except Exception as e:
            print(f"[!] Error sending Saturday report to {cid}: {e}")

async def run_saturday_user_autobooking(bot: Bot, year_group: int):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Saturday User Auto-booking Storm для группы {year_group}...")
    confirmed = load_confirmed_bookings()
    linked = load_linked_accounts()
    
    # Check for "auto" mode users and find matches live
    group_users = []
    for uid_str, acc in linked.items():
        ug = acc.get("experience_year", 1)
        if ug == year_group:
            group_users.append(int(uid_str))
            
    # Filter confirmed bookings to only include users from this year_group
    confirmed_group = {}
    for c_id_str, tgts in confirmed.items():
        try:
            c_id = int(c_id_str)
        except Exception:
            continue
        if c_id in group_users:
            confirmed_group[c_id_str] = tgts
            
    auto_users = []
    for cid in group_users:
        cid_str = str(cid)
        settings = get_auto_booking_settings(cid)
        if settings.get("auto_booking_active", False) and settings.get("auto_booking_mode", "confirm") == "auto":
            # Avoid duplicate matching/booking if they already confirmed manually
            if cid_str not in confirmed_group:
                auto_users.append(cid)
                
    priority_id_str = "6871586046"
    priority_id = 6871586046
    
    async def book_users_concurrently(users_dict):
        active_bookings = {cid_str: tgts for cid_str, tgts in users_dict.items() if tgts}
        if not active_bookings:
            return
            
        # Extract admin targets for priority execution
        admin_targets = active_bookings.pop(priority_id_str, None)
        
        admin_task = None
        if admin_targets:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Приоритетный запуск автозаписи для Админа {priority_id_str}...")
            admin_task = asyncio.create_task(book_user(priority_id, admin_targets, bot, year_group))
            # Give admin a 50ms head start
            await asyncio.sleep(0.05)
            
        # Start other users concurrently
        other_tasks = []
        for cid_str, tgts in active_bookings.items():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Параллельный запуск автозаписи для пользователя {cid_str}...")
            other_tasks.append(asyncio.create_task(book_user(int(cid_str), tgts, bot, year_group)))
            
        all_tasks = []
        if admin_task:
            all_tasks.append(admin_task)
        all_tasks.extend(other_tasks)
        
        if all_tasks:
            await asyncio.gather(*all_tasks)

    # 1. Start confirmed bookings immediately (they don't need fetch_all_data)
    confirmed_booking_task = None
    if confirmed_group:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Мгновенный запуск подтвержденных смен для {len(confirmed_group)} пользователей...")
        confirmed_booking_task = asyncio.create_task(book_users_concurrently(confirmed_group))
        
    # 2. Concurrently fetch and match for "auto" users
    async def handle_auto_users():
        if not auto_users:
            return
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Получение данных J-GET для {len(auto_users)} авто-пользователей...")
        data, err = await fetch_all_data()
        if not data:
            print(f"[!] Не удалось получить данные автозаписи: {err}")
            return
            
        auto_bookings = {}
        for cid in auto_users:
            cid_str = str(cid)
            user_name = linked.get(cid_str, {}).get("name", "").strip().lower()
            settings = get_auto_booking_settings(cid)
            matches = get_smart_matches(data, user_name, settings)
            if matches:
                auto_bookings[cid_str] = matches
                
        if auto_bookings:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Найдено {len(auto_bookings)} авто-бронирований, запускаем их...")
            await book_users_concurrently(auto_bookings)

    auto_booking_task = asyncio.create_task(handle_auto_users())
    
    # Wait for both flows to complete
    if confirmed_booking_task:
        await confirmed_booking_task
    await auto_booking_task

    # Clear processed confirmed bookings from the persistent json
    current_confirmed = load_confirmed_bookings()
    for cid_str in confirmed_group.keys():
        current_confirmed.pop(cid_str, None)
    save_confirmed_bookings(current_confirmed)

async def save_scheduler_config_async(cfg):
    save_scheduler_config(cfg)

async def wait_until_precise(target_time: datetime):
    while True:
        now = get_msk_now()
        diff = (target_time - now).total_seconds()
        if diff <= 0:
            break
        if diff > 0.05:
            await asyncio.sleep(0.005)
        else:
            pass

async def saturday_scheduler_loop(bot: Bot):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Планировщик субботы запущен.")
    
    triggered_precheck_g2 = ""
    triggered_storm_g2 = ""
    triggered_precheck_g1 = ""
    triggered_storm_g1 = ""
    
    while True:
        try:
            cfg = load_scheduler_config()
            now_msk = get_msk_now()
            today_str = now_msk.strftime("%Y-%m-%d")
            
            # Sync with config file on startup or refresh
            last_pre_g2 = cfg.get("last_precheck_date_g2", "")
            last_bk_g2 = cfg.get("last_user_booking_date_g2", "")
            last_pre_g1 = cfg.get("last_precheck_date_g1", "")
            last_bk_g1 = cfg.get("last_user_booking_date_g1", "")
            
            # 5 is Saturday
            if now_msk.weekday() == 5:
                # --- Group 2 (Second year) ---
                # Precheck at 09:50
                if now_msk.hour == 9 and now_msk.minute == 50:
                    if last_pre_g2 != today_str and triggered_precheck_g2 != today_str:
                        triggered_precheck_g2 = today_str
                        cfg["last_precheck_date_g2"] = today_str
                        asyncio.create_task(save_scheduler_config_async(cfg))
                        asyncio.create_task(run_saturday_autobooking_precheck(bot, 2))
                        
                # Storm at 10:00 (target time: 09:59:59.990)
                if last_bk_g2 != today_str and triggered_storm_g2 != today_str:
                    target_g2 = now_msk.replace(hour=9, minute=59, second=59, microsecond=990000)
                    if now_msk.hour == 9 and now_msk.minute == 59:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Приближается штурм G2 (10:00). Переход на высокоточный таймер...")
                        await wait_until_precise(target_g2)
                        triggered_storm_g2 = today_str
                        cfg["last_user_booking_date_g2"] = today_str
                        asyncio.create_task(run_saturday_user_autobooking(bot, 2))
                        asyncio.create_task(save_scheduler_config_async(cfg))
                    elif now_msk.hour == 10 and now_msk.minute <= 5:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Обнаружено опоздание на штурм G2. Запуск немедленно.")
                        triggered_storm_g2 = today_str
                        cfg["last_user_booking_date_g2"] = today_str
                        asyncio.create_task(run_saturday_user_autobooking(bot, 2))
                        asyncio.create_task(save_scheduler_config_async(cfg))
                        
                # --- Group 1 (First year) ---
                # Precheck at 11:50
                if now_msk.hour == 11 and now_msk.minute == 50:
                    if last_pre_g1 != today_str and triggered_precheck_g1 != today_str:
                        triggered_precheck_g1 = today_str
                        cfg["last_precheck_date_g1"] = today_str
                        asyncio.create_task(save_scheduler_config_async(cfg))
                        asyncio.create_task(run_saturday_autobooking_precheck(bot, 1))
                        
                # Storm at 12:00 (target time: 11:59:59.990)
                if last_bk_g1 != today_str and triggered_storm_g1 != today_str:
                    target_g1 = now_msk.replace(hour=11, minute=59, second=59, microsecond=990000)
                    if now_msk.hour == 11 and now_msk.minute == 59:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Приближается штурм G1 (12:00). Переход на высокоточный таймер...")
                        await wait_until_precise(target_g1)
                        triggered_storm_g1 = today_str
                        cfg["last_user_booking_date_g1"] = today_str
                        asyncio.create_task(run_saturday_user_autobooking(bot, 1))
                        asyncio.create_task(save_scheduler_config_async(cfg))
                    elif now_msk.hour == 12 and now_msk.minute <= 5:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Обнаружено опоздание на штурм G1. Запуск немедленно.")
                        triggered_storm_g1 = today_str
                        cfg["last_user_booking_date_g1"] = today_str
                        asyncio.create_task(run_saturday_user_autobooking(bot, 1))
                        asyncio.create_task(save_scheduler_config_async(cfg))
            
        except Exception as e:
            print(f"Ошибка в планировщике: {e}")
        await asyncio.sleep(0.5)



def load_account_auth_by_chat_id(chat_id):
    acc = get_linked_account(chat_id)
    if not acc:
        return None, None
    token = acc.get("token")
    return {}, token

@router.callback_query(F.data == "auto_booking_menu")
async def handle_auto_booking_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    acc = get_linked_account(cid)
    if cid not in VIP_CHAT_IDS:
        await callback.answer("🚫 У вас нет доступа к функции Автозаписи.", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    active = settings.get("auto_booking_active", False)
    status_str = "🟢 АКТИВНА" if active else "🔴 ОТКЛЮЧЕНА"
    
    weekday_active = settings.get("weekday_intercept_active", False)
    weekday_status_str = "🟢 АКТИВЕН" if weekday_active else "🔴 ОТКЛЮЧЕН"
    
    mode = settings.get("auto_booking_mode", "confirm")
    
    exp_year = acc.get("experience_year", 1) if acc else 1
    storm_time = "10:00" if exp_year == 2 else "12:00"
    precheck_time = "09:50" if exp_year == 2 else "11:50"

    if mode == "auto":
        desc_text = f"Бот автоматически запишет вас на подходящие смены по субботам в {storm_time} (и перехватит в будни при их появлении)."
        mode_display = f"Автоматический (без подтверждения в {storm_time})"
    else:
        desc_text = f"Каждую субботу в {precheck_time} вы будете получать уведомление со списком найденных смен для подтверждения."
        mode_display = f"С подтверждением ({precheck_time})"
        
    schools = settings.get("auto_booking_schools", [])
    exclude_mode = settings.get("auto_booking_schools_exclude_mode", False)
    if schools:
        mode_prefix = "Все, кроме: " if exclude_mode else "Только: "
        schools_str = mode_prefix + ", ".join(schools)
    else:
        schools_str = "Все школы"
    stations_data = settings.get("auto_booking_stations", {})
    valid_items = [(cat, nums) for cat, nums in stations_data.items() if nums]
    stations_parts = []
    for i, (cat, nums) in enumerate(valid_items):
        prefix = " ├ 🔹 " if i < len(valid_items) - 1 else " └ 🔹 "
        suffix = ";" if i < len(valid_items) - 1 else ""
        stations_parts.append(f"{prefix}{cat}: {', '.join(map(str, sorted(nums)))}{suffix}")
    
    if stations_parts:
        stations_str = "\n" + "\n".join(stations_parts)
    else:
        stations_str = " <i>Не выбраны</i>"
        
    time_mode = settings.get("auto_booking_time_mode", "any")
    if time_mode == "any":
        time_str = "Любое время"
    else:
        time_str = f"С {settings.get('auto_booking_time_start', '10:00')} до {settings.get('auto_booking_time_end', '15:00')}"
        
    max_quests = settings.get("auto_booking_max_quests", 6)
    if max_quests == "max":
        max_quests_str = "♾️ Максимально"
    else:
        max_quests_str = f"{max_quests} в день"

    text = (
        f"🤖 <b>АВТОЗАПИСЬ</b>\n\n"
        f"ℹ️ Субботняя запись: {status_str}\n"
        f"⚡ Перехват будней: {weekday_status_str}\n"
        f"⚙️ Режим: <i>{mode_display}</i>\n"
        f"🏫 Школы: <i>{schools_str}</i>\n"
        f"🎯 Станции:{stations_str}\n"
        f"⏱️ Время: <i>{time_str}</i>\n"
        f"🎮 Лимит: <i>{max_quests_str}</i>\n\n"
        f"<blockquote expandable>📌 Приоритет станций: Бот записывает сначала на те станции, которые вы выбрали первыми. Если первая станция будет занята, бот автоматически попробует записать на вторую по приоритету и так далее.</blockquote>"
    )
    builder = InlineKeyboardBuilder()
    toggle_btn_text = "🔴 Выкл. субботу" if active else "🟢 Вкл. субботу"
    toggle_weekday_text = "🔴 Выкл. будни" if weekday_active else "🟢 Вкл. будни"
    builder.row(
        InlineKeyboardButton(text=toggle_btn_text, callback_data="auto_booking_toggle"),
        InlineKeyboardButton(text=toggle_weekday_text, callback_data="weekday_intercept_toggle")
    )
    
    mode_btn_text = "🔄 Авто-режим" if mode == "confirm" else "🔄 С подтверждением"
    builder.row(InlineKeyboardButton(text=mode_btn_text, callback_data="auto_booking_mode_toggle"))
    builder.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data="auto_booking_settings_menu"))
    builder.row(InlineKeyboardButton(text="↩️ Меню", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data == "auto_booking_settings_menu")
async def handle_auto_booking_settings_menu(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏫 Школы", callback_data="auto_booking_select_schools"),
        InlineKeyboardButton(text="🎯 Станции", callback_data="auto_booking_select_stations")
    )
    builder.row(
        InlineKeyboardButton(text="⏱️ Время", callback_data="auto_booking_select_time"),
        InlineKeyboardButton(text="🎮 Лимит квестов", callback_data="auto_booking_select_max_quests")
    )
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_menu"))
    
    text = "⚙️ *НАСТРОЙКИ*\n\nВыберите параметр:"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "auto_booking_mode_toggle")
async def handle_auto_booking_mode_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
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
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    settings["auto_booking_active"] = not settings.get("auto_booking_active", False)
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_menu(callback)

@router.callback_query(F.data == "weekday_intercept_toggle")
async def handle_weekday_intercept_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    settings["weekday_intercept_active"] = not settings.get("weekday_intercept_active", False)
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_menu(callback)

@router.callback_query(F.data == "auto_booking_select_schools")
async def handle_auto_booking_select_schools(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    selected_schools = settings.get("auto_booking_schools", [])
    exclude_mode = settings.get("auto_booking_schools_exclude_mode", False)
    
    schools_set = set()
    if GLOBAL_CACHED_DATA:
        for ev in GLOBAL_CACHED_DATA:
            title = ev.get("title", "")
            sch = format_school_name(title)
            if sch:
                schools_set.add(sch)
    schools_list = sorted(list(schools_set))
    
    builder = InlineKeyboardBuilder()
    
    # Mode toggle button at the top
    mode_btn_text = "🚫 Режим: Исключить выбранные" if exclude_mode else "✅ Режим: Только выбранные"
    builder.row(InlineKeyboardButton(text=mode_btn_text, callback_data="auto_bk_sch_mode_toggle"))
    
    school_btns = []
    for idx, sch in enumerate(schools_list):
        is_sel = sch in selected_schools
        if is_sel:
            emoji = "🚫" if exclude_mode else "✅"
            btn_text = f"{emoji} {sch}"
        else:
            btn_text = sch
        school_btns.append(InlineKeyboardButton(text=btn_text, callback_data=f"auto_bk_sch_toggle_{idx}"))
        
    for i in range(0, len(school_btns), 2):
        builder.row(*school_btns[i:i+2])
        
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_settings_menu"))
    
    mode_desc = (
        "🚫 *Режим исключения:* бот будет ловить смены во ВСЕХ школах, *кроме* отмеченных ниже галочкой.\n\n"
        if exclude_mode else
        "✅ *Режим белого списка:* бот будет ловить смены *только* в отмеченных ниже школах (если ничего не отмечено — во всех).\n\n"
    )
    
    await callback.message.edit_text(
        f"🏫 *ШКОЛЫ*\n\n{mode_desc}Отметьте нужные:",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "auto_bk_sch_mode_toggle")
async def handle_auto_booking_school_mode_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    current_mode = settings.get("auto_booking_schools_exclude_mode", False)
    settings["auto_booking_schools_exclude_mode"] = not current_mode
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_select_schools(callback)


@router.callback_query(F.data.startswith("auto_bk_sch_toggle_"))
async def handle_auto_booking_school_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
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
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    builder = InlineKeyboardBuilder()
    categories = ["ПДД", "Спасатель", "Дружба", "Сокровища", "Бриллианты"]
    for cat in categories:
        builder.row(InlineKeyboardButton(text=f"🎯 {cat}", callback_data=f"auto_bk_cat_{cat}"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_settings_menu"))
    await callback.message.edit_text(
        "🎯 *СТАНЦИИ*\n\nВыберите категорию:",
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
        if is_sel:
            p_idx = selected_nums.index(i) + 1
            btn_text = f"✅ {i} ({p_idx})"
        else:
            btn_text = str(i)
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"auto_bk_num_{cat}_{i}"))
        if len(row) == 5 or idx == len(station_nums) - 1:
            builder.row(*row)
            row = []
            
    builder.row(InlineKeyboardButton(text="↩️ Назад к категориям", callback_data="auto_booking_select_stations"))
    
    priority_text = ""
    if selected_nums:
        priority_text = "📊 *Приоритет выбора:*\n"
        for idx, num in enumerate(selected_nums, 1):
            priority_text += f"  {idx}️⃣. Станция *{num}*\n"
        priority_text += "\n"
        
    await callback.message.edit_text(
        f"🎯 *{cat} — станции*\n\n"
        f"{priority_text}"
        f"Порядок нажатия = приоритет:",
        parse_mode="Markdown", reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("auto_bk_cat_"))
async def handle_auto_booking_category_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    cat = callback.data.split("_")[3]
    await render_category_stations_menu(callback, cat)

@router.callback_query(F.data.startswith("auto_bk_num_"))
async def handle_auto_booking_number_toggle(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
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

@router.callback_query(F.data == "auto_booking_select_time")
async def handle_auto_booking_select_time(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    settings = get_auto_booking_settings(cid)
    time_mode = settings.get("auto_booking_time_mode", "any")
    start_time = settings.get("auto_booking_time_start", "10:00")
    end_time = settings.get("auto_booking_time_end", "15:00")
    
    if time_mode == "any":
        status_text = "🟢 *Любое время* (бот будет записывать вас на смены с любым временем начала и конца)."
    else:
        status_text = f"⏱️ *Ограничение по времени:* с `{start_time}` до `{end_time}` (бот будет ловить только те смены, которые полностью входят в этот интервал)."
        
    text = (
        "⏱️ *НАСТРОЙКА ВРЕМЕНИ АВТОЗАПИСИ*\n\n"
        f"Текущая настройка:\n{status_text}\n\n"
        "Выберите подходящий режим работы:"
    )
    
    builder = InlineKeyboardBuilder()
    any_check = "✅ " if time_mode == "any" else ""
    cust_check = "✅ " if time_mode == "custom" else ""
    builder.row(InlineKeyboardButton(text=f"{any_check}Любое время", callback_data="auto_booking_time_mode_any"))
    builder.row(InlineKeyboardButton(text=f"{cust_check}Указать свой интервал", callback_data="auto_booking_time_mode_custom"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_settings_menu"))
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "auto_booking_time_mode_any")
async def handle_auto_booking_time_any(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    settings = get_auto_booking_settings(cid)
    settings["auto_booking_time_mode"] = "any"
    save_auto_booking_settings(cid, settings)
    await handle_auto_booking_select_time(callback)

@router.callback_query(F.data == "auto_booking_time_mode_custom")
async def handle_auto_booking_time_custom(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    USER_LINK_STATE[cid] = "waiting_time_range"
    
    text = (
        "⏱️ *УКАЖИТЕ ИНТЕРВАЛ ВРЕМЕНИ*\n\n"
        "Введите желаемый промежуток времени в формате `ЧЧ:ММ - ЧЧ:ММ` (например, `10:00 - 15:00` или `09:30 - 18:00`):\n\n"
        "Бот будет записывать вас только на те смены, которые полностью укладываются в эти рамки.\n\n"
        "📌 _Время должно быть указано в 24-часовом формате, начало должно быть строго раньше конца._"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Отмена", callback_data="auto_booking_select_time"))
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "auto_booking_select_max_quests")
async def handle_auto_booking_select_max_quests(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    settings = get_auto_booking_settings(cid)
    current_max = settings.get("auto_booking_max_quests", 6)
    
    if current_max == "max":
        limit_display = "Максимально (без ограничений)"
    else:
        limit_display = f"{current_max} квест(ов) в день"
        
    text = (
        "🎮 *ЛИМИТ КВЕСТОВ*\n\n"
        f"Сейчас: *{limit_display}*\n\n"
        "Выберите максимум смен в день:"
    )
    
    builder = InlineKeyboardBuilder()
    row = []
    for i in range(1, 7):
        is_sel = (str(i) == str(current_max))
        btn_text = f"✅ {i}" if is_sel else str(i)
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"auto_booking_max_quests_set_{i}"))
        if len(row) == 3:
            builder.row(*row)
            row = []
            
    max_check = "✅ " if current_max == "max" else ""
    builder.row(InlineKeyboardButton(text=f"{max_check}♾️ Максимально", callback_data="auto_booking_max_quests_set_max"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_settings_menu"))
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("auto_booking_max_quests_set_"))
async def handle_auto_booking_max_quests_set(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    
    val_str = callback.data.split("_")[5]
    if val_str == "max":
        val = "max"
    else:
        val = int(val_str)
        
    settings = get_auto_booking_settings(cid)
    settings["auto_booking_max_quests"] = val
    save_auto_booking_settings(cid, settings)
    
    await handle_auto_booking_select_max_quests(callback)

@router.callback_query(F.data == "auto_booking_confirm_confirm")
async def handle_auto_booking_confirm_confirm(callback: CallbackQuery):
    cid = callback.message.chat.id
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
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
    acc = get_linked_account(cid)
    exp_year = acc.get("experience_year", 1) if acc else 1
    storm_time = "10:00" if exp_year == 2 else "12:00"
    await callback.message.edit_text(
        f"✅ *Автозапись успешно подтверждена!*\n\nБот автоматически запишет вас на эти смены в субботу в {storm_time}.",
        parse_mode="Markdown", reply_markup=get_back_btn("user_profile")
    )

async def render_shift_log_page(callback: CallbackQuery, target_monday_str: str):
    cid = callback.message.chat.id
    acc = get_linked_account(cid)
    if not acc:
        await callback.answer("Аккаунт не привязан!", show_alert=True)
        return
    
    site_name = acc.get("name", "")
    if not GLOBAL_CACHED_DATA:
        await callback.message.edit_text(
            "⚠️ Данные ещё не загружены. Попробуйте позже.",
            reply_markup=get_back_btn("user_profile")
        )
        return
        
    stats = get_user_stats(site_name, list(PERSISTENT_EVENTS.values()))
    if not stats or not stats["history"]:
        await callback.message.edit_text(
            "📜 *ЛОГ СМЕН*\n\nИстория смен пуста.",
            parse_mode="Markdown", reply_markup=get_back_btn("user_profile")
        )
        return

    history = stats["history"]
    
    try:
        target_monday = datetime.strptime(target_monday_str, "%Y-%m-%d").date()
    except Exception:
        now_msk = get_msk_now()
        target_monday = now_msk.date() - timedelta(days=now_msk.date().weekday())
        target_monday_str = target_monday.strftime("%Y-%m-%d")

    shift_dates = []
    for h in history:
        try:
            dt = datetime.strptime(h["date"], "%Y-%m-%d").date()
            shift_dates.append(dt)
        except Exception:
            pass
            
    now_msk = get_msk_now()
    current_monday = now_msk.date() - timedelta(days=now_msk.date().weekday())
    
    all_dates = shift_dates + [current_monday]
    min_date = min(all_dates)
    max_date = max(all_dates)
    
    start_monday = min_date - timedelta(days=min_date.weekday())
    end_monday = max_date - timedelta(days=max_date.weekday())
    
    target_sunday = target_monday + timedelta(days=6)
    week_shifts = []
    for h in history:
        try:
            dt = datetime.strptime(h["date"], "%Y-%m-%d").date()
            if target_monday <= dt <= target_sunday:
                week_shifts.append(h)
        except Exception:
            pass
            
    months_ru_genitive = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
        7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    
    monday_fmt = f"{target_monday.day} {months_ru_genitive[target_monday.month]}"
    sunday_fmt = f"{target_sunday.day} {months_ru_genitive[target_sunday.month]}"
    week_range_str = f"с {monday_fmt} - {sunday_fmt}"
    
    completed_p = stats["completed_player"]
    completed_l = stats["completed_leader"]
    total_shifts = completed_p + completed_l
    lates = stats["lates"]
    
    header = (
        f"📜 *ЛОГ СМЕН — {site_name}*\n"
        f"📅 *Неделя: {week_range_str}*\n\n"
        f"Всего смен: *{total_shifts}* (🏃 {completed_p} + 👑 {completed_l}) | Опозданий: *{lates}*\n\n"
    )
    
    if not week_shifts:
        history_text = "_Нет смен на этой неделе._"
    else:
        history_text = format_compact_shifts_list(week_shifts, is_saturday_preview=False)
        
    text = header + history_text
    if len(text) > 4000:
        text = text[:3950] + "\n\n_...обрезано_"
        
    builder = InlineKeyboardBuilder()
    
    nav_row = []
    if target_monday > start_monday:
        prev_monday = target_monday - timedelta(days=7)
        nav_row.append(InlineKeyboardButton(text="◀️ Пред. неделя", callback_data=f"shift_log_week:{prev_monday.strftime('%Y-%m-%d')}"))
    if target_monday < end_monday:
        next_monday = target_monday + timedelta(days=7)
        nav_row.append(InlineKeyboardButton(text="След. неделя ▶️", callback_data=f"shift_log_week:{next_monday.strftime('%Y-%m-%d')}"))
        
    if nav_row:
        builder.row(*nav_row)
        
    builder.row(InlineKeyboardButton(text="↩️ Профиль", callback_data="user_profile"))
    
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())
    except Exception as e:
        print(f"[!] Error editing shift log message: {e}")

@router.callback_query(F.data == "shift_log")
async def handle_shift_log(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    now_msk = get_msk_now()
    current_monday = now_msk.date() - timedelta(days=now_msk.date().weekday())
    await render_shift_log_page(callback, current_monday.strftime("%Y-%m-%d"))

@router.callback_query(F.data.startswith("shift_log_week:"))
async def handle_shift_log_week(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    week_str = callback.data.split(":", 1)[1]
    await render_shift_log_page(callback, week_str)

@router.message(F.text)
async def process_text_input(message: Message, bot: Bot):
    cid = message.chat.id

    link_state = USER_LINK_STATE.get(cid)
    if link_state == "waiting_time_range":
        if message.chat.type == "private":
            try: await message.delete()
            except Exception: pass
            
        time_text = message.text.strip()
        match = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$", time_text)
        if not match:
            await edit_or_send(
                bot=bot, chat_id=cid,
                text="❌ *Неверный формат времени!*\n\nПожалуйста, отправьте диапазон в формате `ЧЧ:ММ - ЧЧ:ММ` (например, `10:00 - 15:00`):\n\nПопробуйте еще раз:",
                reply_markup=get_back_btn("auto_booking_select_time")
            )
            return
            
        start_t_str, end_t_str = match.groups()
        
        def validate_and_format_time(t_str):
            parts = t_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
            return None

        fmt_start = validate_and_format_time(start_t_str)
        fmt_end = validate_and_format_time(end_t_str)
        
        if not fmt_start or not fmt_end or fmt_start >= fmt_end:
            await edit_or_send(
                bot=bot, chat_id=cid,
                text="❌ *Некорректный диапазон времени!*\n\nУбедитесь, что:\n"
                     "1. Часы в диапазоне 0-23, а минуты 0-59\n"
                     "2. Время начала строго раньше времени конца\n\n"
                     "Попробуйте еще раз:",
                reply_markup=get_back_btn("auto_booking_select_time")
            )
            return
            
        USER_LINK_STATE.pop(cid, None)
        settings = get_auto_booking_settings(cid)
        settings["auto_booking_time_mode"] = "custom"
        settings["auto_booking_time_start"] = fmt_start
        settings["auto_booking_time_end"] = fmt_end
        save_auto_booking_settings(cid, settings)
        
        text = (
            f"✅ *Диапазон времени сохранен:* с `{fmt_start}` до `{fmt_end}`.\n\n"
            "Бот будет бронировать для вас только смены, проходящие в рамках этого времени."
        )
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_select_time"))
        
        await edit_or_send(
            bot=bot, chat_id=cid,
            text=text,
            reply_markup=builder.as_markup()
        )
        return

    elif link_state == "waiting_osint_query":
        if cid != ADMIN_ID:
            USER_LINK_STATE.pop(cid, None)
            return
            
        if message.chat.type == "private":
            try: await message.delete()
            except Exception: pass
            
        query = message.text.strip()
        query_words = [w.lower() for w in query.split()]
        if not query_words:
            await edit_or_send(
                bot=bot, chat_id=cid,
                text="❌ *Пустой запрос!*\n\nПожалуйста, отправьте имя и/или фамилию человека для поиска:",
                reply_markup=get_back_btn("main_menu")
            )
            return
            
        unique_names = set()
        if GLOBAL_CACHED_DATA:
            for event in GLOBAL_CACHED_DATA:
                for p in event.get("participants", []):
                    fn = p.get("first_name", "").strip()
                    ln = p.get("last_name", "").strip()
                    if fn or ln:
                        unique_names.add((fn, ln))
        if PERSISTENT_EVENTS:
            for event in PERSISTENT_EVENTS.values():
                for p in event.get("participants", []):
                    fn = p.get("first_name", "").strip()
                    ln = p.get("last_name", "").strip()
                    if fn or ln:
                        unique_names.add((fn, ln))
                        
        matches = []
        for fn, ln in unique_names:
            fn_ln_lower = f"{fn} {ln}".lower()
            ln_fn_lower = f"{ln} {fn}".lower()
            matched = True
            for w in query_words:
                if w not in fn_ln_lower and w not in ln_fn_lower:
                    matched = False
                    break
            if matched:
                matches.append((fn, ln))
                
        matches = sorted(matches, key=lambda x: (x[1], x[0]))
        
        if not matches:
            await edit_or_send(
                bot=bot, chat_id=cid,
                text=f"❌ *Ничего не найдено*\n\n"
                     f"Пользователь по запросу `\"{query}\"` не найден в базе данных смен.\n\n"
                     f"Попробуйте ввести другие ключевые слова:",
                reply_markup=get_back_btn("osint_search_start")
            )
            return
            
        if len(matches) == 1:
            USER_LINK_STATE.pop(cid, None)
            fn, ln = matches[0]
            dossier_text = generate_osint_dossier(fn, ln)
            await edit_or_send(
                bot=bot, chat_id=cid,
                text=dossier_text,
                reply_markup=get_back_btn("main_menu")
            )
            return
            
        OSINT_SEARCH_RESULTS[cid] = matches
        builder = InlineKeyboardBuilder()
        for idx, (fn, ln) in enumerate(matches[:15]):
            builder.row(InlineKeyboardButton(text=f"👤 {fn} {ln}", callback_data=f"osint_view_{idx}"))
            
        builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="osint_search_start"))
        
        limit_note = ""
        if len(matches) > 15:
            limit_note = f"\n\n⚠️ _Показано 15 совпадений из {len(matches)}. Пожалуйста, уточните ваш запрос._"
            
        await edit_or_send(
            bot=bot, chat_id=cid,
            text=f"🔍 *РЕЗУЛЬТАТЫ ПОИСКА ({len(matches)}):*\n\nВыберите нужного человека из списка ниже:{limit_note}",
            reply_markup=builder.as_markup()
        )
        return

    elif link_state == "waiting_credentials":
        if message.chat.type == "private":
            try: await message.delete()
            except Exception: pass

        msg_id = BOT_MESSAGE_ID.get(cid)
        if msg_id:
            try: await bot.delete_message(chat_id=cid, message_id=msg_id)
            except Exception: pass
            BOT_MESSAGE_ID.pop(cid, None)

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
        
    # --- 1. Calculate next Saturday countdowns in Moscow time ---
    now_msk = get_msk_now()
    days_until_saturday = (5 - now_msk.weekday()) % 7
    
    # Storm countdown Group 1 (Saturday 12:00 MSK)
    next_storm_g1 = now_msk.replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=days_until_saturday)
    if next_storm_g1 <= now_msk:
        next_storm_g1 += timedelta(days=7)
    time_to_storm_g1 = next_storm_g1 - now_msk
    days_s1 = time_to_storm_g1.days
    hours_s1, remainder_s1 = divmod(time_to_storm_g1.seconds, 3600)
    minutes_s1, _ = divmod(remainder_s1, 60)
    storm_countdown_g1 = f"{days_s1}д {hours_s1}ч {minutes_s1}м"
    
    # Precheck countdown Group 1 (Saturday 11:50 MSK)
    next_precheck_g1 = now_msk.replace(hour=11, minute=50, second=0, microsecond=0) + timedelta(days=days_until_saturday)
    if next_precheck_g1 <= now_msk:
        next_precheck_g1 += timedelta(days=7)
    time_to_precheck_g1 = next_precheck_g1 - now_msk
    days_p1 = time_to_precheck_g1.days
    hours_p1, remainder_p1 = divmod(time_to_precheck_g1.seconds, 3600)
    minutes_p1, _ = divmod(remainder_p1, 60)
    precheck_countdown_g1 = f"{days_p1}д {hours_p1}ч {minutes_p1}м"

    # Storm countdown Group 2 (Saturday 10:00 MSK)
    next_storm_g2 = now_msk.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=days_until_saturday)
    if next_storm_g2 <= now_msk:
        next_storm_g2 += timedelta(days=7)
    time_to_storm_g2 = next_storm_g2 - now_msk
    days_s2 = time_to_storm_g2.days
    hours_s2, remainder_s2 = divmod(time_to_storm_g2.seconds, 3600)
    minutes_s2, _ = divmod(remainder_s2, 60)
    storm_countdown_g2 = f"{days_s2}д {hours_s2}ч {minutes_s2}м"
    
    # Precheck countdown Group 2 (Saturday 09:50 MSK)
    next_precheck_g2 = now_msk.replace(hour=9, minute=50, second=0, microsecond=0) + timedelta(days=days_until_saturday)
    if next_precheck_g2 <= now_msk:
        next_precheck_g2 += timedelta(days=7)
    time_to_precheck_g2 = next_precheck_g2 - now_msk
    days_p2 = time_to_precheck_g2.days
    hours_p2, remainder_p2 = divmod(time_to_precheck_g2.seconds, 3600)
    minutes_p2, _ = divmod(remainder_p2, 60)
    precheck_countdown_g2 = f"{days_p2}д {hours_p2}ч {minutes_p2}м"

    # --- 2. Build list of registered users and auto-booking statuses ---
    linked_list = []
    for uid_str, acc in linked_accs.items():
        name = acc.get("name", "Неизвестно")
        user_f = filters.get(uid_str, {})
        is_active = user_f.get("auto_booking_active", False)
        mode = user_f.get("auto_booking_mode", "confirm")
        active_symbol = "🟢" if is_active else "🔴"
        mode_symbol = "⚡" if mode == "auto" else "⏳"
        linked_list.append(f"  ├ {active_symbol} {mode_symbol} {name} (ID: {uid_str})")
    linked_users_str = "\n".join(linked_list) if linked_list else "  └ Нет привязанных аккаунтов"

    # --- 3. Fetch live bot account statistics from API ---
    bot_token = None
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                auth_data = json.load(f)
            for origin in auth_data.get("origins", []):
                for item in origin.get("localStorage", []):
                    if item.get("name") == "token":
                        bot_token = item.get("value")
                        break
        except Exception:
            pass

    bot_profile_str = ""
    if bot_token:
        profile_data, err = await api_get_profile(bot_token)
        if profile_data:
            stats = profile_data.get("stats", {})
            user_info = profile_data.get("user", {})
            bot_first = user_info.get("first_name", "")
            bot_last = user_info.get("last_name", "")
            bot_name = f"{bot_first} {bot_last}".strip() or user_info.get("phone", "Бот")
            bot_id = user_info.get("user_id", "Н/Д")
            
            conducted = stats.get("conducted", user_info.get("conducted_count", 0))
            cancellations = stats.get("cancellations", user_info.get("cancellation_count", 0))
            is_leader = user_info.get("is_leader", False)
            is_experienced = user_info.get("is_experienced", False)
            
            roles = []
            if is_leader: roles.append("👑 Главарь")
            if is_experienced: roles.append("⭐ Опытный")
            role_str = ", ".join(roles) if roles else "🏃 Ведущий"
            
            bot_profile_str = (
                f"\n👤 *Профиль бота в J-GET:*\n"
                f"• Имя: *{bot_name}* (ID: {bot_id})\n"
                f"• Статус: *{role_str}*\n"
                f"• Проведено смен: *{conducted}*\n"
                f"• Отменено смен: *{cancellations}*\n"
            )

    # --- 4. Calculate cached events summary ---
    total_booked_slots = 0
    total_free_slots = 0
    cat_counts = {}
    school_slots = {}
    
    if GLOBAL_CACHED_DATA:
        for e in GLOBAL_CACHED_DATA:
            raw_cat = e.get("event_type_name", "")
            title = e.get("title", "")
            cat = normalize_category(raw_cat, title)
            clean_cat = clean_category_name(cat)
            
            free_here = sum(1 for s in e.get("available_stations", []) if s.get("is_available"))
            booked_here = len(e.get("participants", []))
            
            total_booked_slots += booked_here
            total_free_slots += free_here
            
            # Category counts
            if clean_cat not in cat_counts:
                cat_counts[clean_cat] = {"booked": 0, "free": 0}
            cat_counts[clean_cat]["booked"] += booked_here
            cat_counts[clean_cat]["free"] += free_here
            
            # School counts
            sch = format_school_name(title)
            if sch and free_here > 0:
                school_slots[sch] = school_slots.get(sch, 0) + free_here
                
    cat_lines = []
    for cat_name, counts in sorted(cat_counts.items()):
        total = counts["booked"] + counts["free"]
        cat_lines.append(f"  └ {cat_name}: *{total}* слотов (свободно: *{counts['free']}*, занято: *{counts['booked']}*)")
    cat_breakdown = "\n".join(cat_lines) if cat_lines else "  └ Нет данных"
    
    top_schools = sorted(school_slots.items(), key=lambda x: x[1], reverse=True)[:3]
    school_lines = []
    for sch_name, free_cnt in top_schools:
        school_lines.append(f"  └ {sch_name}: *{free_cnt}* своб. слотов")
    school_breakdown = "\n".join(school_lines) if school_lines else "  └ Нет свободных слотов"

    text = (
        f"👑 *АДМИН* (v{BOT_VERSION})\n\n"
        f"📊 *Бот:*\n"
        f"  ├ Аккаунтов: *{total_linked}*\n"
        f"  ├ Фильтров: *{total_filters}*\n"
        f"  ├ Автозаписей: *{active_autobooking}*\n"
        f"  ├ Смен в кэше: *{cached_events_count}*\n"
        f"  └ RAM: *{ram_str}*\n"
        f"\n👥 *Пользователи:*\n{linked_users_str}\n"
        f"\n⏳ *До штурма (Сб):*\n"
        f"  2-й год: 09:50 (*{precheck_countdown_g2}*) → 10:00 (*{storm_countdown_g2}*)\n"
        f"  1-й год: 11:50 (*{precheck_countdown_g1}*) → 12:00 (*{storm_countdown_g1}*)\n"
        f"{bot_profile_str}\n"
        f"📅 *API ({cached_events_count} смен):*\n"
        f"  ├ Всего: *{total_booked_slots + total_free_slots}* (своб: *{total_free_slots}*, зан: *{total_booked_slots}*)\n"
        f"  ├ Категории:\n{cat_breakdown}\n"
        f"  └ Топ школ:\n{school_breakdown}\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_panel"))
    builder.row(InlineKeyboardButton(text="↩️ Меню", callback_data="main_menu"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

def format_name_for_top(first_name, last_name, is_admin):
    first_name = first_name.strip()
    last_name = last_name.strip()
    if is_admin:
        return f"{first_name} {last_name}".strip()
    else:
        last_initial = f"{last_name[0]}." if last_name else ""
        return f"{first_name} {last_initial}".strip()

def calculate_tops(is_admin):
    tops = {
        "hours": {"title": "⏳ Топ по часам", "data": {}},
        "earn": {"title": "💰 Топ Заработка", "data": {}},
        "veterans": {"title": "🎖 Ветераны (Всего смен)", "data": {}},
        "leaders": {"title": "👑 Топ Главарей", "data": {}},
        "players": {"title": "🏃 Топ Ведущих", "data": {}},
        "lates": {"title": "⏰ Топ Опозданий", "data": {}},
        
        # Квесты
        "druzhba": {"title": "🤝 Топ Дружбы", "data": {}},
        "pdd": {"title": "🚗 Топ ПДД", "data": {}},
        "spasatel": {"title": "🚨 Топ Спасателей", "data": {}},
        "diamonds": {"title": "💎 Топ Бриллиантов", "data": {}},
        "treasures": {"title": "🗺 Топ Сокровищ", "data": {}},
        
        # Разное
        "weekend_warriors": {"title": "🎉 Герои Выходных", "data": {}},
        "early_birds": {"title": "🌅 Ранние пташки", "data": {}},
        "night_owls": {"title": "🌌 Вечерние совы", "data": {}},
        "perfect": {"title": "✅ Идеальная пунктуальность", "data": {}},
        "non_attendance": {"title": "❌ Топ Прогулов", "data": {}}
    }
    
    if not PERSISTENT_EVENTS:
        return tops
        
    current_time = datetime.now()
    for event in PERSISTENT_EVENTS.values():
        title = event.get("title", "")
        school_name = format_school_name(title)
        raw_cat = event.get("event_type_name", "")
        cat = clean_category_name(normalize_category(raw_cat, title))
        
        date_str = event.get("date", "")
        is_completed = False
        try:
            full_end_str = f"{date_str} {event.get('end_time', '23:59:59')[:8]}"
            event_end_dt = datetime.strptime(full_end_str, "%Y-%m-%d %H:%M:%S")
            if event_end_dt <= current_time:
                is_completed = True
        except Exception:
            try:
                ev_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                if ev_date_obj < current_time.date():
                    is_completed = True
            except Exception:
                pass
        if not is_completed:
            continue
        
        quest_mins = 60
        start_hour = 12
        try:
            ts = datetime.strptime(event.get("start_time")[:8], "%H:%M:%S")
            te = datetime.strptime(event.get("end_time")[:8], "%H:%M:%S")
            diff_mins = (te - ts).total_seconds() / 60
            if diff_mins > 0:
                quest_mins = round(diff_mins)
            start_hour = ts.hour
        except Exception:
            pass
        total_work_mins = quest_mins
        
        for p in event.get("participants", []):
            fn = p.get("first_name", "")
            ln = p.get("last_name", "")
            if not fn and not ln:
                continue
                
            uid = f"{fn.lower()}_{ln.lower()}"
            name_fmt = format_name_for_top(fn, ln, is_admin)
            
            late = p.get("late", False)
            as_leader = p.get("as_leader", False)
            
            if uid not in tops["hours"]["data"]:
                for key in tops:
                    tops[key]["data"][uid] = {"name": name_fmt, "val": 0}
            
            if not p.get("attended", True):
                tops["non_attendance"]["data"][uid]["val"] += 1
                continue
                
            tops["hours"]["data"][uid]["val"] += total_work_mins
            
            if as_leader:
                tops["leaders"]["data"][uid]["val"] += 1
            else:
                tops["players"]["data"][uid]["val"] += 1
                
            if late:
                tops["lates"]["data"][uid]["val"] += 1
                
            if cat == "Дружба":
                tops["druzhba"]["data"][uid]["val"] += 1
            elif cat == "ПДД":
                tops["pdd"]["data"][uid]["val"] += 1
            elif cat == "Спасатель":
                tops["spasatel"]["data"][uid]["val"] += 1
            elif cat == "Бриллианты":
                tops["diamonds"]["data"][uid]["val"] += 1
            elif cat == "Сокровища":
                tops["treasures"]["data"][uid]["val"] += 1
                
            # Additional tops
            tops["veterans"]["data"][uid]["val"] += 1
            try:
                ev_date = datetime.strptime(event.get("date", ""), "%Y-%m-%d")
                if ev_date.weekday() >= 5:
                    tops["weekend_warriors"]["data"][uid]["val"] += 1
            except Exception:
                pass
                
            if as_leader:
                tops["earn"]["data"][uid]["val"] += PAYOUT_LEADER
            else:
                tops["earn"]["data"][uid]["val"] += PAYOUT_PLAYER
                if late:
                    tops["earn"]["data"][uid]["val"] -= (PAYOUT_PLAYER - 400)
            
            if not late:
                tops["perfect"]["data"][uid]["val"] += 1
                
            if start_hour < 10:
                tops["early_birds"]["data"][uid]["val"] += 1
            elif start_hour >= 15:
                tops["night_owls"]["data"][uid]["val"] += 1
                
    accounts = load_linked_accounts()
    for acc in accounts.values():
        name = acc.get("name", "")
        if not name:
            continue
        parts = name.strip().split()
        if len(parts) >= 2:
            fn = parts[0]
            ln = parts[1]
        else:
            fn = name
            ln = ""
        uid = f"{fn.lower()}_{ln.lower()}"
        conducted_val = acc.get("conducted", 0)
        
        if uid in tops["veterans"]["data"]:
            cached_veterans = tops["veterans"]["data"][uid]["val"]
            if conducted_val > cached_veterans:
                uncached = conducted_val - cached_veterans
                tops["veterans"]["data"][uid]["val"] += uncached
                if uid in tops["hours"]["data"]:
                    tops["hours"]["data"][uid]["val"] += uncached * 60
                if uid in tops["earn"]["data"]:
                    tops["earn"]["data"][uid]["val"] += uncached * PAYOUT_PLAYER

    for key in tops:
        raw_list = list(tops[key]["data"].values())
        if key in ["hours"]:
            for r in raw_list:
                r["val"] = round(r["val"] / 60, 1)
        raw_list = [r for r in raw_list if r["val"] > 0]
        raw_list.sort(key=lambda x: x["val"], reverse=True)
        tops[key]["sorted"] = raw_list
        
    return tops

TOP_IDS = [
    "hours", "earn", "veterans", "leaders", "players", "lates",
    "druzhba", "pdd", "spasatel", "diamonds", "treasures",
    "weekend_warriors", "early_birds", "night_owls", "perfect", "non_attendance"
]

def get_tops_menu(top_index, tops_data):
    if top_index < 0:
        top_index = len(TOP_IDS) - 1
    elif top_index >= len(TOP_IDS):
        top_index = 0
        
    top_id = TOP_IDS[top_index]
    top_info = tops_data.get(top_id)
    if not top_info:
        return None, None
        
    items_per_page = 15
    page_data = top_info["sorted"][:items_per_page]
    
    text = f"🏆 <b>{top_info['title']}</b>\n\n"
    if not page_data:
        text += "<i>Пока нет данных...</i>\n"
    else:
        for i, item in enumerate(page_data, start=1):
            val = item["val"]
            if top_id == "hours":
                val_str = f"{val} ч."
            elif top_id == "earn":
                val_str = f"{val} ₽"
            elif top_id in ["lates", "early_birds", "night_owls", "non_attendance"]:
                val_str = f"{val} раз(а)"
            else:
                val_str = f"{val} смен"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🎗"
            text += f"{medal} <b>{i}.</b> {item['name']} — {val_str}\n"
            
    builder = InlineKeyboardBuilder()
    
    prev_idx = top_index - 1 if top_index > 0 else len(TOP_IDS) - 1
    next_idx = top_index + 1 if top_index < len(TOP_IDS) - 1 else 0
    
    nav_buttons = [
        InlineKeyboardButton(text="⬅️", callback_data=f"tops_nav_{prev_idx}"),
        InlineKeyboardButton(text=f"{top_index + 1}/{len(TOP_IDS)}", callback_data="ignore"),
        InlineKeyboardButton(text="➡️", callback_data=f"tops_nav_{next_idx}")
    ]
        
    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    
    return text, builder.as_markup()

@router.callback_query(F.data == "ignore")
async def handle_ignore(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("tops_nav_"))
async def handle_tops_nav(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) >= 3:
        try:
            top_index = int(parts[2])
        except ValueError:
            top_index = 0
            
        cid = callback.message.chat.id
        is_admin = (cid == ADMIN_ID)
        
        await callback.answer()
        
        tops_data = GLOBAL_CACHED_TOPS_ADMIN if is_admin else GLOBAL_CACHED_TOPS_USER
        if not tops_data:
            tops_data = calculate_tops(is_admin)
        text, markup = get_tops_menu(top_index, tops_data)
        if text:
            try:
                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            except Exception as e:
                pass

async def main():
    global GLOBAL_CACHED_DATA, GLOBAL_CACHED_TOPS_ADMIN, GLOBAL_CACHED_TOPS_USER
    load_persistent_events()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    print("[+] Первичный сбор данных...")
    data, err = await fetch_all_data()
    if not err and data:
        GLOBAL_CACHED_DATA = data
        merge_into_persistent(data)
        try:
            GLOBAL_CACHED_TOPS_ADMIN = calculate_tops(is_admin=True)
            GLOBAL_CACHED_TOPS_USER = calculate_tops(is_admin=False)
        except Exception as e:
            pass
        print("[+] Кэш инициализирован. Запуск...")
    else:
        print("[!] Запуск с пустым кэшем.")
    asyncio.create_task(background_cache_updater())
    asyncio.create_task(background_profiles_updater())
    asyncio.create_task(saturday_scheduler_loop(bot))
    asyncio.create_task(background_weekday_autobooking_loop(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
