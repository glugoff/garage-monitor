#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import logging
from datetime import datetime
import requests


# === НАСТРОЙКИ ===
TARGET_IP = "10.0.0.2"          # IP неттопа в WireGuard
PING_INTERVAL = 15             # секунд
PING_ATTEMPTS = 2              # сколько раз подряд должен пропасть/появиться пинг

# from dotenv import load_dotenv
# load_dotenv()  # только при запуске локально

TELEGRAM_BOT_TOKEN = os.getenv("TG_BOTADMIN_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TG_CHAT_ID_BOTADMIN"))

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def format_duration(seconds):
    """Преобразует секунды в 'X час Y мин Z сек'."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours:
        parts.append(f"{hours} час" if hours == 1 else f"{hours} часа" if 2 <= hours <= 4 else f"{hours} часов")
    if minutes:
        parts.append(f"{minutes} мин")
    if secs or not parts:
        parts.append(f"{secs} сек")

    return " ".join(parts)

def ping_host(host, timeout=3):
    """Возвращает True, если хост отвечает на ping."""
    try:
        # -c 1: один пакет, -W timeout в секундах (Linux)
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Ошибка при пинге {host}: {e}")
        return False

def send_telegram_message(text):
    """Отправляет сообщение в Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"Ошибка Telegram API: {response.text}")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение: {e}")

# === ОСНОВНАЯ ЛОГИКА ===

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Состояния:
    # - "online": связь есть
    # - "offline": связь потеряна
    # - "pending_online": ожидаем подтверждения восстановления (2 пинга)
    # - "pending_offline": ожидаем подтверждения потери (2 пинга)
    state = "online"
    last_change_time = time.time()  # время последнего подтверждённого изменения состояния

    # Счётчики подряд идущих результатов
    consecutive_success = 0
    consecutive_fail = 0

    logging.info("Запуск мониторинга связи с гаражом...")

    while True:
        is_reachable = ping_host(TARGET_IP)

        if is_reachable:
            consecutive_success += 1
            consecutive_fail = 0
        else:
            consecutive_fail += 1
            consecutive_success = 0

        # Обработка переходов
        if state == "online" and consecutive_fail >= PING_ATTEMPTS:
            # Потеря связи
            downtime_start = time.time()
            uptime_duration = downtime_start - last_change_time
            msg = (
                f"⚠️ <b>Связь с гаражом пропала</b>\n"
                f"Время обрыва: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"Аптайм: {format_duration(uptime_duration)}"
            )
            logging.info("Связь потеряна. Отправка уведомления.")
            send_telegram_message(msg)
            state = "offline"
            last_change_time = downtime_start

        elif state == "offline" and consecutive_success >= PING_ATTEMPTS:
            # Восстановление связи
            uptime_start = time.time()
            downtime_duration = uptime_start - last_change_time
            msg = (
                f"✅ <b>Связь с гаражом восстановлена</b>\n"
                f"Время восстановления: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"Даунтайм: {format_duration(downtime_duration)}"
            )
            logging.info("Связь восстановлена. Отправка уведомления.")
            send_telegram_message(msg)
            state = "online"
            last_change_time = uptime_start

        time.sleep(PING_INTERVAL)

if __name__ == "__main__":
    main()