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

BOT_MESSAGE_ID = {}
USER_LINK_STATE = {}
TEMP_AUTO_BOOKINGS = {}
OSINT_SEARCH_RESULTS = {}

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
            
        matched_s = None
        matched_num = None
        priority_index = 999999
        for idx, target_num in enumerate(allowed_nums):
            for s in ev.get("available_stations", []):
                if s.get("is_available"):
                    num = get_station_num(s.get("name"))
                    if num == target_num:
                        matched_s = s
                        matched_num = num
                        priority_index = idx
                        break
            if matched_s:
                break
                
        if matched_s:
            c = {
                "event_id": ev.get("id"),
                "station_id": matched_s.get("id"),
                "date": ev_date_str,
                "time": f"{ev.get('start_time')[:5]}-{ev.get('end_time')[:5]}",
                "start_time": ev.get("start_time")[:5],
                "end_time": ev.get("end_time")[:5],
                "school": school_name,
                "category": clean_cat,
                "station_num": matched_num,
                "priority_index": priority_index
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
    
    if GLOBAL_CACHED_DATA:
        for event in GLOBAL_CACHED_DATA:
            user_p = None
            for p in event.get("participants", []):
                p_fn = p.get("first_name", "").strip().lower()
                p_ln = p.get("last_name", "").strip().lower()
                if p_fn == target_fn_lower and p_ln == target_ln_lower:
                    user_p = p
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
            
            if ev_date and ev_date >= today_date:
                upcoming_shifts.append(shift_info)
            else:
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
                total_minutes += total_work_mins
                
                school_counts[school_name] = school_counts.get(school_name, 0) + 1
                category_counts[category] = category_counts.get(category, 0) + 1
                station_counts[role_str] = station_counts.get(role_str, 0) + 1
            else:
                skipped_count += 1
                
    attendance_rate = round((attended_count / total_booked) * 100, 1) if total_booked > 0 else 0.0
    late_rate = round((late_count / attended_count) * 100, 1) if attended_count > 0 else 0.0
    total_hours = round(total_minutes / 60, 1)
    avg_shift_len = round(total_minutes / attended_count, 1) if attended_count > 0 else 0.0
    
    earned_leader = leader_count * PAYOUT_LEADER
    earned_player = (player_count - player_lates) * PAYOUT_PLAYER + player_lates * 400
    total_earned = earned_leader + earned_player
    late_penalties = player_lates * (PAYOUT_PLAYER - 400)
    avg_hourly_pay = round(total_earned / (total_minutes / 60), 1) if total_minutes > 0 else 0.0
    
    top_schools = sorted(school_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_schools_str = ", ".join([f"{sch} ({cnt})" for sch, cnt in top_schools]) if top_schools else "Нет сведений"
    
    top_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cats_str = ", ".join([f"{cat} ({cnt})" for cat, cnt in top_cats]) if top_cats else "Нет сведений"
    
    top_stations = sorted(station_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_stations_str = ", ".join([f"{role} ({cnt})" for role, cnt in top_stations]) if top_stations else "Нет сведений"
    
    upcoming_shifts = sorted(upcoming_shifts, key=lambda x: x["date"])
    past_shifts = sorted(past_shifts, key=lambda x: x["date"], reverse=True)
    
    linked_tg_info = None
    accounts = load_linked_accounts()
    for uid_str, acc in accounts.items():
        acc_name = acc.get("name", "").strip().lower()
        target_full = f"{target_first_name} {target_last_name}".strip().lower()
        target_rev = f"{target_last_name} {target_first_name}".strip().lower()
        if acc_name == target_full or acc_name == target_rev:
            linked_tg_info = {
                "chat_id": uid_str,
                "phone": acc.get("phone", "Н/Д"),
                "experience_year": acc.get("experience_year", 1)
            }
            break
            
    tg_part = ""
    if linked_tg_info:
        phone_raw = linked_tg_info["phone"]
        if len(phone_raw) == 11 and phone_raw.startswith("7"):
            pretty_phone = f"+7 ({phone_raw[1:4]}) {phone_raw[4:7]}-{phone_raw[7:9]}-{phone_raw[9:11]}"
        else:
            pretty_phone = phone_raw
        year_val = linked_tg_info["experience_year"]
        year_str = "Второй (второгодник, 10:00)" if year_val == 2 else "Первый (первогодник, 12:00)"
        tg_part = (
            f"🔗 *СВЯЗАННЫЙ TELEGRAM-АККАУНТ:*\n"
            f"  ├ 🆔 Telegram ID: `{linked_tg_info['chat_id']}`\n"
            f"  ├ 🎓 Год обучения: *{year_str}*\n"
            f"  └ 📞 Телефон: `{pretty_phone}`\n\n"
        )
    else:
        tg_part = "⚠️ *Telegram-аккаунт не привязан к боту*\n\n"
        
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
    
    return (
        f"👤 *ДОСЬЕ: {target_first_name} {target_last_name}*\n\n"
        f"{tg_part}"
        f"📊 *ОСНОВНАЯ СТАТИСТИКА:*\n"
        f"  ├ Всего записей: *{total_booked}*\n"
        f"  ├ Посещено смен: *{attended_count}* (👑 Главарь: {leader_count} | 🏃 Игрок: {player_count})\n"
        f"  ├ Пропущено смен: *{skipped_count}*\n"
        f"  ├ Количество опозданий: *{late_count}*\n"
        f"  ├ Отработано времени: *{total_hours}* ч\n"
        f"  ├ Среднее время смены: *{avg_shift_len}* мин\n"
        f"  ├ Процент посещаемости: *{attendance_rate}%*\n"
        f"  └ Процент опозданий: *{late_rate}%*\n\n"
        f"💰 *ФИНАНСОВЫЙ ОТЧЕТ:*\n"
        f"  ├ Всего начислено: *{total_earned}* ₽\n"
        f"  ├ Из них за Главаря: *{earned_leader}* ₽\n"
        f"  ├ Из них за Игрока: *{earned_player}* ₽\n"
        f"  ├ Вычеты за опоздания: *{late_penalties}* ₽\n"
        f"  └ Средняя ставка: *{avg_hourly_pay}* ₽/час\n\n"
        f"🎯 *ПРЕДПОЧТЕНИЯ:*\n"
        f"  ├ Любимые локации: _{top_schools_str}_\n"
        f"  ├ Любимые квесты: _{top_cats_str}_\n"
        f"  └ Любимые роли/позиции: _{top_stations_str}_\n\n"
        f"⏱️ *БЛИЖАЙШИЕ СМЕНЫ:*\n"
        f"{upcoming_str}\n\n"
        f"📜 *ИСТОРИЯ ПОСЛЕДНИХ СМЕН (до 5):*\n"
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
                    if not settings.get("auto_booking_active", False):
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
                                
                            matched_s = None
                            matched_num = None
                            for target_num in allowed_nums:
                                for s in ev.get("available_stations", []):
                                    if s.get("is_available"):
                                        num = get_station_num(s.get("name"))
                                        if num == target_num:
                                            matched_s = s
                                            matched_num = num
                                            break
                                if matched_s:
                                    break
                                    
                            if matched_s:
                                payload = {"event": ev.get("id"), "station": matched_s.get("id")}
                                try:
                                    async with session.post(URL_BOOK, json=payload, timeout=5) as r:
                                        if r.status in [200, 201]:
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
                                                f"🎯 {clean_cat} | Станция {matched_num}"
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
    if chat_id and is_linked(chat_id):
        builder.row(
            InlineKeyboardButton(text="🤖 Автозапись", callback_data="auto_booking_menu")
        )
    if chat_id and chat_id == ADMIN_ID:
        builder.row(
            InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel"),
            InlineKeyboardButton(text="🔍 ОСИНТ Поиск", callback_data="osint_search_start")
        )
    row_buttons = []
    if chat_id and is_linked(chat_id):
        row_buttons.append(InlineKeyboardButton(text="👤 Профиль", callback_data="user_profile"))
    else:
        row_buttons.append(InlineKeyboardButton(text="🔗 Привязать аккаунт", callback_data="link_start"))
    
    row_buttons.append(InlineKeyboardButton(text="📚 Гайды", callback_data="guides_menu"))
    builder.row(*row_buttons)
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
            "🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
            parse_mode="Markdown", reply_markup=get_main_menu(cid)
        )
        BOT_MESSAGE_ID[cid] = msg.message_id
    else:
        msg = await message.answer(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт сайта jget-events.ru чтобы получить полный доступ "
            "к автоматической записи, учету статистики и управлению профилем.\n\n"
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
            "к автоматической записи, учету статистики и управлению профилем.\n\n"
            "Выберите действие:",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )

@router.callback_query(F.data == "link_why")
async def handle_link_why(callback: CallbackQuery):
    cid = callback.message.chat.id
    await callback.message.edit_text(
        "❓ *ЗАЧЕМ ПРИВЯЗЫВАТЬ АККАУНТ?*\n\n"
        "Привязка аккаунта jget-events.ru открывает полный набор функций бота:\n\n"
        "1️⃣ *Автозапись на квесты*\n"
        " └ Автоматический перехват смен по субботам в 12:00 и ловля будних смен по гибким фильтрам школ и станций.\n\n"
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
        "🎓 *ВЫБОР ГОДА ОБУЧЕНИЯ*\n\n"
        "На квесты вы ходите первый или второй год? От этого зависит время вашей автозаписи:\n\n"
        "• *Первый год (первогодник):* запись проходит в *12:00* (предпроверка в 11:50).\n"
        "• *Второй год (второгодник):* запись проходит в *10:00* (предпроверка в 09:50).\n\n"
        "💡 _Второгодники имеют преимущество записи в 10:00 на сайте J-GET._"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="1️⃣ Первый год (12:00)", callback_data="link_year_set_1"))
    builder.row(InlineKeyboardButton(text="2️⃣ Второй год (10:00)", callback_data="link_year_set_2"))
    
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
        f"✅ *Аккаунт успешно привязан!*\n\n"
        f"👤 Привет, *{name}*!\n"
        f"Вы зарегистрированы как *{'второгодник' if selected_year == 2 else 'первогодник'}* (запись в {'10:00' if selected_year == 2 else '12:00'}).\n\n"
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

    already_earned = conducted * PAYOUT_PLAYER
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

    exp_year = acc.get("experience_year", 1)
    year_str = "Первый год (первогодник, 12:00)" if exp_year == 1 else "Второй год (второгодник, 10:00)"

    text = (
        f"👤 *ПРОФИЛЬ*\n\n"
        f"📛 Имя на сайте: *{site_name}*\n"
        f"💬 Telegram: *{tg_name}* ({tg_username})\n"
        f"🆔 Telegram ID: `{tg_id}`\n"
        f"📞 Телефон: `{phone_fmt}`\n"
        f"🎓 Год обучения: *{year_str}*"
        f"{site_extra}\n\n"
        f"💰 Уже заработано: *{already_earned}* ₽\n"
        f"⏳ В ожидании: *{expected_earnings}* ₽\n"
        f"🔥 Всего за месяц: *{total_for_month}* ₽\n\n"
        f"⚠️ *ВАЖНО:* Вы должны строго выбрать свой *реальный* статус! "
        f"Если вы выберете второй год будучи первогодником, бот попытается записать вас в 10:00 и получит ошибку сайта. "
        f"Если вы выберете первый год будучи второгодником, бот начнет запись только в 12:00, "
        f"когда другие второгодники уже займут все лучшие места."
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
        
    toggle_year_text = "🎓 Сменить на: Второй год (10:00)" if exp_year == 1 else "🎓 Сменить на: Первый год (12:00)"
    builder.row(InlineKeyboardButton(text=toggle_year_text, callback_data="profile_toggle_year"))
    
    builder.row(
        InlineKeyboardButton(text="📜 Лог смен", callback_data="shift_log"),
        InlineKeyboardButton(text="🔑 Мой пароль", callback_data="show_password")
    )
    builder.row(
        InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

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
    OSINT_SEARCH_RESULTS.pop(cid, None)
    if is_linked(cid):
        await callback.message.edit_text("🛸 *Главное меню J-GET*\n\nВыбери нужный раздел:", 
                                         parse_mode="Markdown", reply_markup=get_main_menu(cid))
    else:
        await callback.message.edit_text(
            "🛸 *Добро пожаловать в J-GET!*\n\n"
            "Привяжите аккаунт сайта jget-events.ru чтобы получить полный доступ "
            "к автоматической записи, учету статистики и управлению профилем.\n\n"
            "Выберите действие:",
            parse_mode="Markdown", reply_markup=get_onboarding_keyboard()
        )

@router.callback_query(F.data == "guides_menu")
async def handle_guides_menu(callback: CallbackQuery):
    cid = callback.message.chat.id
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "📚 *СПРАВОЧНИК И РУКОВОДСТВА J-GET*\n\n"
        "Выберите интересующий вас раздел инструкций ниже:"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🤖 Инструкция к автозаписи", callback_data="guide_autobooking"))
    builder.row(InlineKeyboardButton(text="👤 Управление профилем и баланс", callback_data="guide_profile"))
    builder.row(InlineKeyboardButton(text="❓ Общие вопросы и F.A.Q.", callback_data="guide_faq"))
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@router.callback_query(F.data == "guide_autobooking")
async def handle_guide_autobooking(callback: CallbackQuery):
    try: await callback.answer()
    except Exception: pass
    
    text = (
        "🤖 *РУКОВОДСТВО ПО АВТОЗАПИСИ*\n\n"
        "Автозапись — это интеллектуальная система, которая ловит и бронирует смены (квесты) на сайте за вас.\n\n"
        "⏱️ *Как происходит запись по субботам:*\n"
        "1️⃣ *В 11:50 (Предпроверка):* Бот ищет смены на следующую неделю, подходящие под ваши фильтры.\n"
        "2️⃣ *В 12:00 (Штурм):* Бот моментально отправляет запросы на бронирование.\n\n"
        "⚙️ *Режимы работы:*\n"
        "• *С подтверждением:* в 11:50 бот пришлет список найденных смен. Вам нужно нажать кнопку *«Подтвердить автозапись»* до 12:00, чтобы бот записал вас.\n"
        "• *Авто-режим (без подтверждения):* бот запишет вас на все подходящие смены автоматически.\n\n"
        "🛠️ *Настройка фильтров:*\n"
        "• *Школы:* можно выбрать только определенные школы (белый список) или исключить ненужные (черный список).\n"
        "• *Станции:* порядок выбора определяет приоритет. Сначала бот пытается записать на первую выбранную станцию, если она занята — на вторую и т.д.\n"
        "• *Время:* задает рамки начала и конца квеста (например, `10:00 - 15:00`). Квесты вне этого интервала будут проигнорированы.\n"
        "• *Кол-во квестов:* лимит смен на один календарный день (от 1 до 6)."
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ К гайдам", callback_data="guides_menu"))
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
        "• *Часов:* суммарное время работы на смене (+40 минут на подготовку к каждой).\n\n"
        "💰 *Финансовый учет:*\n"
        "• Расчет ведется по ставкам: *1000 ₽* за Главаря, *500 ₽* за Игрока (или *400 ₽* при опоздании).\n"
        "• *Уже заработано:* сумма за прошедшие смены в этом месяце.\n"
        "• *В ожидании:* сумма за будущие смены, на которые вы уже записаны.\n"
        "• *Всего за месяц:* общая сумма (заработанное + ожидаемое).\n\n"
        "🗺️ *План на сегодня/завтра:*\n"
        "• Отображает список ваших смен, точное время, школы и роли на выбранный день с удобной кнопкой навигации на Яндекс Карты."
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ К гайдам", callback_data="guides_menu"))
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
    builder.row(InlineKeyboardButton(text="↩️ К гайдам", callback_data="guides_menu"))
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

async def run_saturday_user_autobooking(bot: Bot, year_group: int):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск Saturday User Auto-booking Storm для группы {year_group}...")
    confirmed = load_confirmed_bookings()
    
    # Check for "auto" mode users and find matches live
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
                user_name = linked.get(cid_str, {}).get("name", "").strip().lower()
                settings = get_auto_booking_settings(cid)
                matches = get_smart_matches(data, user_name, settings)
                if matches:
                    confirmed[cid_str] = matches

    # Filter confirmed bookings to only include users from this year_group
    confirmed_group = {}
    for c_id_str, tgts in confirmed.items():
        try:
            c_id = int(c_id_str)
        except Exception:
            continue
        if c_id in group_users:
            confirmed_group[c_id_str] = tgts

    if not confirmed_group:
        print(f"[!] Confirmed user bookings empty for group {year_group}.")
        return
        
    priority_id_str = "6871586046"
    confirmed_keys = list(confirmed_group.keys())
    ordered_keys = []
    if priority_id_str in confirmed_keys:
        ordered_keys.append(priority_id_str)
    for k in confirmed_keys:
        if k != priority_id_str:
            ordered_keys.append(k)
            
    for cid_str in ordered_keys:
        targets = confirmed_group[cid_str]
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
            time_display = "10:00" if year_group == 2 else "12:00"
            report_text = (
                f"🤖 *ОТЧЕТ ОБ АВТОЗАПИСИ (Суббота {time_display})*\n\n"
                f"Бот завершил попытку автозаписи на подтвержденные смены:\n\n"
                f"{report_lines_joined}\n\n"
                f"Записано смен: *{success_count}* из *{len(targets)}*."
            )
            try:
                await bot.send_message(chat_id=cid, text=report_text, parse_mode="Markdown")
            except Exception:
                pass
                
    # Clear only the bookings for this group from confirmed bookings
    current_confirmed = load_confirmed_bookings()
    for cid_str in confirmed_group.keys():
        current_confirmed.pop(cid_str, None)
    save_confirmed_bookings(current_confirmed)

async def saturday_scheduler_loop(bot: Bot):
    while True:
        try:
            cfg = load_scheduler_config()
            now_msk = get_msk_now()
            today_str = now_msk.strftime("%Y-%m-%d")
            
            # 5 is Saturday
            if now_msk.weekday() == 5:
                # --- Group 2 (Second year) ---
                # Precheck at 09:50
                if now_msk.hour == 9 and now_msk.minute == 50:
                    last_pre = cfg.get("last_precheck_date_g2", "")
                    if last_pre != today_str:
                        cfg["last_precheck_date_g2"] = today_str
                        save_scheduler_config(cfg)
                        asyncio.create_task(run_saturday_autobooking_precheck(bot, 2))
                        
                # Storm at 10:00
                if now_msk.hour == 10 and now_msk.minute == 0:
                    last_user_bk = cfg.get("last_user_booking_date_g2", "")
                    if last_user_bk != today_str:
                        cfg["last_user_booking_date_g2"] = today_str
                        save_scheduler_config(cfg)
                        asyncio.create_task(run_saturday_user_autobooking(bot, 2))
                        
                # --- Group 1 (First year) ---
                # Precheck at 11:50
                if now_msk.hour == 11 and now_msk.minute == 50:
                    last_pre = cfg.get("last_precheck_date_g1", "")
                    if last_pre != today_str:
                        cfg["last_precheck_date_g1"] = today_str
                        save_scheduler_config(cfg)
                        asyncio.create_task(run_saturday_autobooking_precheck(bot, 1))
                        
                # Storm at 12:00
                if now_msk.hour == 12 and now_msk.minute == 0:
                    last_user_bk = cfg.get("last_user_booking_date_g1", "")
                    if last_user_bk != today_str:
                        cfg["last_user_booking_date_g1"] = today_str
                        save_scheduler_config(cfg)
                        asyncio.create_task(run_saturday_user_autobooking(bot, 1))
            
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
    if not is_linked(cid):
        await callback.answer("🔒 Пожалуйста, сначала привяжите аккаунт", show_alert=True)
        return
    try: await callback.answer()
    except Exception: pass
    settings = get_auto_booking_settings(cid)
    active = settings.get("auto_booking_active", False)
    status_str = "🟢 АКТИВНА" if active else "🔴 ОТКЛЮЧЕНА"
    
    weekday_active = settings.get("weekday_intercept_active", False)
    weekday_status_str = "🟢 АКТИВЕН" if weekday_active else "🔴 ОТКЛЮЧЕН"
    
    mode = settings.get("auto_booking_mode", "confirm")
    
    if mode == "auto":
        desc_text = "Бот автоматически запишет вас на подходящие смены по субботам в 12:00 (и перехватит в будни при их появлении)."
        mode_display = "Автоматический (без подтверждения)"
    else:
        desc_text = "Каждую субботу в 11:50 вы будете получать уведомление со списком найденных смен для подтверждения."
        mode_display = "С подтверждением (11:50)"
        
    schools = settings.get("auto_booking_schools", [])
    exclude_mode = settings.get("auto_booking_schools_exclude_mode", False)
    if schools:
        mode_prefix = "Все, кроме: " if exclude_mode else "Только: "
        schools_str = mode_prefix + ", ".join(schools)
    else:
        schools_str = "Все школы"
    stations_data = settings.get("auto_booking_stations", {})
    stations_parts = []
    for cat, nums in stations_data.items():
        if nums:
            stations_parts.append(f"{cat}: {', '.join(map(str, sorted(nums)))}")
    stations_str = "; ".join(stations_parts) if stations_parts else "Не выбраны"
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
        f"🤖 *АВТОЗАПИСЬ НА КВЕСТЫ*\n\n"
        f"{desc_text}\n\n"
        f"ℹ️ *Субботняя автозапись:* {status_str}\n"
        f"⚡ *Фоновый перехват будней:* {weekday_status_str}\n"
        f"⚙️ *Режим записи:* {mode_display}\n"
        f"🏫 *Школы:* _{schools_str}_\n"
        f"🎯 *Станции:* _{stations_str}_\n"
        f"⏱️ *Время:* _{time_str}_\n"
        f"🎮 *Кол-во квестов:* _{max_quests_str}_\n\n"
        f"📌 *Приоритет станций:* Бот записывает сначала на те станции, которые вы выбрали первыми. "
        f"Если первая станция будет занята, бот автоматически попробует записать на вторую по приоритету и так далее."
    )
    builder = InlineKeyboardBuilder()
    toggle_btn_text = "🔴 Выкл. автозапись" if active else "🟢 Вкл. автозапись"
    toggle_weekday_text = "🔴 Выкл. перехват" if weekday_active else "🟢 Вкл. перехват"
    builder.row(
        InlineKeyboardButton(text=toggle_btn_text, callback_data="auto_booking_toggle"),
        InlineKeyboardButton(text=toggle_weekday_text, callback_data="weekday_intercept_toggle")
    )
    
    mode_btn_text = "🔄 Включить Авто-режим" if mode == "confirm" else "🔄 Включить Подтверждение"
    builder.row(InlineKeyboardButton(text=mode_btn_text, callback_data="auto_booking_mode_toggle"))
    
    builder.row(
        InlineKeyboardButton(text="🏫 Школы", callback_data="auto_booking_select_schools"),
        InlineKeyboardButton(text="🎯 Станции", callback_data="auto_booking_select_stations")
    )
    builder.row(
        InlineKeyboardButton(text="⏱️ Время", callback_data="auto_booking_select_time"),
        InlineKeyboardButton(text="🎮 Кол-во квестов", callback_data="auto_booking_select_max_quests")
    )
    builder.row(InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"))
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
        
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_menu"))
    
    mode_desc = (
        "🚫 *Режим исключения:* бот будет ловить смены во ВСЕХ школах, *кроме* отмеченных ниже галочкой.\n\n"
        if exclude_mode else
        "✅ *Режим белого списка:* бот будет ловить смены *только* в отмеченных ниже школах (если ничего не отмечено — во всех).\n\n"
    )
    
    await callback.message.edit_text(
        f"🏫 *ВЫБОР ЦЕЛЕВЫХ ШКОЛ*\n\n{mode_desc}Отметьте школы:",
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
        f"🎯 *СТАНЦИИ ДЛЯ КАТЕГОРИИ: {cat}*\n\n"
        f"{priority_text}"
        f"Нажимайте на номера станций для выбора. Порядок нажатия определяет их приоритет (первое нажатие — наивысший приоритет):",
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
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_menu"))
    
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
        "🎮 *МАКСИМУМ КВЕСТОВ В ДЕНЬ*\n\n"
        f"Текущий лимит: *{limit_display}*.\n\n"
        "Выберите максимальное количество смен (квестов), на которые бот может записать вас в течение одного дня:"
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
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="auto_booking_menu"))
    
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
    
    # Storm countdown (Saturday 12:00 MSK)
    next_storm = now_msk.replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=days_until_saturday)
    if next_storm <= now_msk:
        next_storm += timedelta(days=7)
    time_to_storm = next_storm - now_msk
    days_s = time_to_storm.days
    hours_s, remainder_s = divmod(time_to_storm.seconds, 3600)
    minutes_s, _ = divmod(remainder_s, 60)
    storm_countdown = f"{days_s}д {hours_s}ч {minutes_s}м"
    
    # Precheck countdown (Saturday 11:50 MSK)
    next_precheck = now_msk.replace(hour=11, minute=50, second=0, microsecond=0) + timedelta(days=days_until_saturday)
    if next_precheck <= now_msk:
        next_precheck += timedelta(days=7)
    time_to_precheck = next_precheck - now_msk
    days_p = time_to_precheck.days
    hours_p, remainder_p = divmod(time_to_precheck.seconds, 3600)
    minutes_p, _ = divmod(remainder_p, 60)
    precheck_countdown = f"{days_p}д {hours_p}ч {minutes_p}м"

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
            if is_leader: roles.append("👑 Ведущий")
            if is_experienced: roles.append("⭐ Опытный")
            role_str = ", ".join(roles) if roles else "🏃 Игрок"
            
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
        f"👑 *ПАНЕЛЬ АДМИНИСТРАТОРА* (v{BOT_VERSION})\n\n"
        f"📊 *Статистика бота:*\n"
        f"• Привязанных аккаунтов: *{total_linked}*\n"
        f"• Пользователей с фильтрами: *{total_filters}*\n"
        f"• Активных автозаписей: *{active_autobooking}*\n"
        f"• Смен в кэше API: *{cached_events_count}*\n"
        f"• Потребление RAM: *{ram_str}*\n"
        f"\n👥 *Список пользователей:*\n{linked_users_str}\n"
        f"\n⏳ *До субботнего штурма:*\n"
        f"• Предпроверка (11:50 MSK): *{precheck_countdown}*\n"
        f"• Автозапись (12:00 MSK): *{storm_countdown}*\n"
        f"{bot_profile_str}\n"
        f"📅 *Сводка Quest API ({cached_events_count} смен):*\n"
        f"• Всего мест/слотов: *{total_booked_slots + total_free_slots}*\n"
        f"  └ Свободно (для записи): *{total_free_slots}*\n"
        f"  └ Занято (записано): *{total_booked_slots}*\n"
        f"• Слоты по категориям:\n{cat_breakdown}\n"
        f"• Топ школ по свободным слотам:\n{school_breakdown}\n"
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
