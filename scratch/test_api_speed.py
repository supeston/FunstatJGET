import asyncio
import time
import json
import os
import aiohttp
import sys
from datetime import datetime

# Configure stdout/stderr to use UTF-8 if possible to prevent encoding issues on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

URL_EVENTS = "https://jget-events.ru/api/events/"

def load_token():
    # Try reading from linked_accounts.json first
    if os.path.exists("linked_accounts.json"):
        try:
            with open("linked_accounts.json", "r", encoding="utf-8") as f:
                accounts = json.load(f)
                for acc in accounts.values():
                    if acc.get("token"):
                        return acc.get("token"), acc.get("name", "Unknown Account")
        except Exception as e:
            print(f"Ошибка при чтении linked_accounts.json: {e}")

    # Try reading from auth.json
    if os.path.exists("auth.json"):
        try:
            with open("auth.json", "r", encoding="utf-8") as f:
                auth_data = json.load(f)
                if isinstance(auth_data, dict) and "origins" in auth_data:
                    for origin in auth_data["origins"]:
                        if "localStorage" in origin:
                            for item in origin["localStorage"]:
                                if item.get("name") == "token":
                                    return item.get("value"), "Bot Account (auth.json)"
        except Exception as e:
            print(f"Ошибка при чтении auth.json: {e}")

    return None, None

async def test_speed():
    token, name = load_token()
    if not token:
        print("[ERROR] Токен авторизации не найден в linked_accounts.json или auth.json!")
        return

    # Using safe ASCII/Cyrillic characters without emojis to avoid encoding crashes on Windows
    print(f"[AUTH] Используется токен для: {name}")
    print(f"[START] Запускаем тест API. Интервал: 1 сек, длительность: 60 сек.")
    print("-" * 70)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Authorization": f"Token {token}"
    }

    latencies = []
    success_count = 0
    fail_count = 0
    status_codes = {}

    async with aiohttp.ClientSession(headers=headers) as session:
        for i in range(1, 1000):
            start_time = time.perf_counter()
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            try:
                # Query tab=current
                async with session.get(URL_EVENTS, params={"tab": "current"}, timeout=10) as response:
                    status = response.status
                    elapsed = time.perf_counter() - start_time
                    latencies.append(elapsed)
                    
                    status_codes[status] = status_codes.get(status, 0) + 1
                    
                    if status == 200:
                        try:
                            data = await response.json()
                            items_count = len(data)
                        except Exception:
                            items_count = "N/A"
                        success_count += 1
                        print(f"[{timestamp}] Запрос #{i:02d}: Статус {status} | Время {elapsed:.3f}с | Получено событий: {items_count}")
                    else:
                        fail_count += 1
                        try:
                            body = await response.text()
                            err_snippet = body[:100]
                        except Exception:
                            err_snippet = ""
                        print(f"[{timestamp}] Запрос #{i:02d}: Статус {status} (Ошибка!) | Время {elapsed:.3f}с | Ответ: {err_snippet}")
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                latencies.append(elapsed)
                fail_count += 1
                status_codes["Exception"] = status_codes.get("Exception", 0) + 1
                print(f"[{timestamp}] Запрос #{i:02d}: Исключение {type(e).__name__} | Время {elapsed:.3f}с | Детали: {e}")

            # Sleep to maintain exactly 1 request per second from start to start
            elapsed_total = time.perf_counter() - start_time
            sleep_time = max(0.0, 1.0 - elapsed_total)
            await asyncio.sleep(sleep_time)

    print("-" * 70)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    print(f"  Всего запросов: {success_count + fail_count}")
    print(f"  Успешно (200 OK): {success_count}")
    print(f"  Ошибок/исключений: {fail_count}")
    print(f"  Распределение статусов: {status_codes}")
    if latencies:
        print(f"  Минимальное время ответа: {min(latencies):.3f}с")
        print(f"  Максимальное время ответа: {max(latencies):.3f}с")
        print(f"  Среднее время ответа: {sum(latencies)/len(latencies):.3f}с")
    else:
        print("  Нет данных по времени ответа.")
    print("-" * 70)

if __name__ == "__main__":
    asyncio.run(test_speed())
