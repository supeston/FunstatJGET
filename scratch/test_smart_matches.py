import os
os.environ["PYTHON_UPDATED"] = "true"

import sys
sys.path.append("..")

# Import helpers from main
from main import get_smart_matches

# Test case 1: Multiple schools with large gap (should allow both)
data_large_gap = [
    {
        "id": 1,
        "date": "2026-07-25",
        "start_time": "09:30:00",
        "end_time": "10:30:00",
        "title": "Школа №41",
        "event_type_name": "Школьный спасатель",
        "participants": [],
        "available_stations": [{"id": 101, "name": "Седьмая станция", "is_available": True}]
    },
    {
        "id": 2,
        "date": "2026-07-25",
        "start_time": "11:30:00",
        "end_time": "12:30:00",
        "title": "Школа №48",
        "event_type_name": "Бриллианты",
        "participants": [],
        "available_stations": [{"id": 102, "name": "Вторая станция", "is_available": True}]
    }
]

settings = {
    "auto_booking_active": True,
    "auto_booking_schools": [],
    "auto_booking_stations": {
        "Спасатель": [7],
        "Бриллианты": [2]
    },
    "auto_booking_time_mode": "any",
    "auto_booking_max_quests": 6
}

m1 = get_smart_matches(data_large_gap, "test", settings)
assert len(m1) == 2, f"Expected 2 matches for large gap, got {len(m1)}"

# Test case 2: Multiple schools with small gap (e.g. 15 minutes) (should only choose the higher priority one, i.e. Спасатель 7)
data_small_gap = [
    {
        "id": 1,
        "date": "2026-07-25",
        "start_time": "09:30:00",
        "end_time": "10:30:00",
        "title": "Школа №41",
        "event_type_name": "Школьный спасатель",
        "participants": [],
        "available_stations": [{"id": 101, "name": "Седьмая станция", "is_available": True}]
    },
    {
        "id": 2,
        "date": "2026-07-25",
        "start_time": "10:45:00",
        "end_time": "11:45:00",
        "title": "Школа №48",
        "event_type_name": "Бриллианты",
        "participants": [],
        "available_stations": [{"id": 102, "name": "Вторая станция", "is_available": True}]
    }
]

m2 = get_smart_matches(data_small_gap, "test", settings)
assert len(m2) == 1, f"Expected 1 match for small gap (since they are different schools with only 15 min gap), got {len(m2)}"
assert m2[0]["school"] == "Школа №41", f"Expected School 41 due to higher priority, got {m2[0]['school']}"

print("All get_smart_matches travel time tests passed successfully!")
