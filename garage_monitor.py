#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import logging
import requests
import threading
from datetime import datetime

# === НАСТРОЙКИ ===
TARGET_IP = "10.0.0.2"          # IP неттопа в WireGuard
PING_INTERVAL = 15             # секунд
PING_ATTEMPTS = 2              # подряд для смены состояния

# Устройства для команды /ping
DEVICES = {
    "192.168.1.2": "📹 Камера",
    "192.168.1.100": "🌐 Основной роутер",
    "192.168.1.50": "🌐 Доп. роутер",
    "192.168.1.25": "🖥️ Неттоп",
    "192.168.1.15": "💻 Нетбук",
    "192.168.1.154": "📡 Антенна (балкон)",
    "192.168.1.254": "📡 Антенна (гараж)",
}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def format_duration(seconds):
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
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Ошибка при пинге {host}: {e}")
        return False

def send_telegram_message(text, chat_id=None):
    """Отправляет сообщение.
    Если chat_id=None — отправляет в группу (из настроек).
    Иначе — в указанный чат (например, личку)."""
    bot_token = os.getenv("TG_BOTADMIN_TOKEN")
    if not bot_token:
        logging.error("TG_BOTADMIN_TOKEN не задан!")
        return

    target_chat = chat_id if chat_id is not None else int(os.getenv("TG_CHAT_ID_BOTADMIN", 0))
    if target_chat == 0:
        logging.error("TG_CHAT_ID_BOTADMIN не задан!")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"Ошибка Telegram API: {response.text}")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение: {e}")

# === ОБРАБОТКА КОМАНД В ЛИЧКЕ ===

def handle_telegram_commands():
    """Фоновый поток: слушает команды в личных сообщениях."""
    bot_token = os.getenv("TG_BOTADMIN_TOKEN")
    if not bot_token:
        logging.error("Невозможно запустить обработку команд: TG_BOTADMIN_TOKEN не задан")
        return

    offset = None
    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            params = {"timeout": 30, "offset": offset}
            response = requests.get(url, params=params, timeout=35)
            if response.status_code != 200:
                time.sleep(5)
                continue

            data = response.json()
            if not data.get("ok"):
                time.sleep(5)
                continue

            for update in data["result"]:
                offset = update["update_id"] + 1

                message = update.get("message")
                if not message:
                    continue

                text = message.get("text")
                chat = message["chat"]
                chat_id = chat["id"]
                chat_type = chat["type"]

                # Только личные сообщения
                if chat_type != "private":
                    continue

                if text == "/ping":
                    lines = ["🔍 Статус гаражных устройств:\n"]
                    for ip, name in DEVICES.items():
                        status = "✅" if ping_host(ip) else "❌"
                        lines.append(f"{status} {name} ({ip})")
                    reply = "\n".join(lines)
                    send_telegram_message(reply, chat_id=chat_id)

                elif text == "/start":
                    send_telegram_message(
                        "Привет! Я бот для мониторинга гаража.\n"
                        "Отправь /ping, чтобы проверить доступность всех устройств.",
                        chat_id=chat_id
                    )

        except Exception as e:
            logging.error(f"Ошибка в обработке команд: {e}")
            time.sleep(5)

# === ОСНОВНОЙ МОНИТОРИНГ СВЯЗИ ===

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Запуск обработчика команд в фоне
    cmd_thread = threading.Thread(target=handle_telegram_commands, daemon=True)
    cmd_thread.start()

    state = "online"
    last_change_time = time.time()
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

        if state == "online" and consecutive_fail >= PING_ATTEMPTS:
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