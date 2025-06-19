import re
import time
import random
import datetime
import asyncio
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError, UserNotMutualContactError, InputUserDeactivatedError
)
from telethon.tl import functions
from telethon.tl.types import InputPhoneContact

# === Параметры подключения ===
# Здесь указываются данные для подключения к Telegram API.
api_id = 'your_api'  # найдете на my.telegram.org
api_hash = 'your_hash'  # найдете на my.telegram.org
session_name = 'inviter_session'  # Имя сессии для подключения
source_channel = 'https://t.me/source_channel'  # Канал-источник для получения сообщений
target_channel = 'https://t.me/target_channel'  # Канал, в который будем приглашать
target_group = 'https://t.me/target_group'  # Группа, в которую будем приглашать
report_user = '@report_username'  # Пользователь, которому будет отправляться отчет

# === Настройки ===
# Устанавливаются параметры, такие как лимит на количество приглашений в день и список обработанных сообщений.
DAILY_LIMIT = 3  # Лимит на количество приглашений в день
invites_sent_today = 0  # Счетчик приглашений, отправленных сегодня
last_reset_date = datetime.date.today()  # Дата последнего сброса лимита
processed_messages = set()  # Множество для хранения ID обработанных сообщений
invited_users = set()  # Множество для хранения пользователей, которых уже пригласили

# === Функция для сброса лимита ===
# Эта функция сбрасывает счетчик приглашений, если наступил новый день.
def reset_daily_limit():
    global invites_sent_today, last_reset_date
    today = datetime.date.today()
    if today > last_reset_date:  # Если дата изменилась
        invites_sent_today = 0  # Обнуляем счетчик приглашений
        last_reset_date = today  # Обновляем дату последнего сброса
        print("Дневной лимит приглашений обнулен.")

# === Функция для отправки отчета ===
# Функция отправляет отчет о выполнении в Telegram-канал/пользователю.
async def send_report(client, message):
    try:
        if message.strip():  # Проверяем, не пустое ли сообщение
            print("Отправляем отчёт...")
            await client.send_message(report_user, message)  # Отправляем сообщение
            print("Отчёт успешно отправлен.")
        else:
            print("Отчёт пустой. Нечего отправлять.")
    except Exception as e:
        print(f"Ошибка при отправке отчёта: {e}")

# === Функция для получения сообщений с канала ===
# Эта функция получает последние 10 сообщений с канала-источника.
async def get_channel_posts(client):
    posts = []
    async for message in client.iter_messages(source_channel, limit=10):  # Получаем 10 последних сообщений
        posts.append(message)
    return posts  # Возвращаем список сообщений

# === Функция для извлечения информации из сообщения ===
# Эта функция извлекает юзернейм и номер телефона из текста сообщения.
def extract_user_info(message):
    username_pattern = re.compile(r'@([a-zA-Z0-9_]+)')  # Паттерн для поиска юзернейма
    phone_pattern = re.compile(r'\b\d{10,15}\b')  # Паттерн для поиска номера телефона

    # Ищем совпадения по паттернам
    username_match = username_pattern.search(message.text)
    phone_match = phone_pattern.search(message.text)

    username = username_match.group(1) if username_match else None  # Если найден юзернейм
    phone = phone_match.group(0) if phone_match else None  # Если найден номер телефона

    return username, phone  # Возвращаем результаты

# === Функция для проверки присутствия пользователя в группе ===
# Эта функция проверяет, добавлен ли пользователь в канал/группу после отправки приглашения.
async def check_user_in_group(client, username, target_channel):
    try:
        participants = await client.get_participants(target_channel, limit=100)  # Получаем участников канала
        for participant in participants:  # Проходим по всем участникам
            if participant.username == username:  # Проверяем, есть ли пользователь с таким юзернеймом
                return True  # Если есть, возвращаем True
        return False  # Если нет, возвращаем False
    except Exception as e:
        print(f"Ошибка при проверке участников: {e}")
        return False  # В случае ошибки возвращаем False

# === Основной процесс приглашения ===
# Главная асинхронная функция, которая выполняет всю логику приглашений.
async def invite_users():
    global invites_sent_today
    client = TelegramClient(session_name, api_id, api_hash)  # Создаем клиента
    await client.start()  # Подключаемся
    print("Аккаунт подключен...")

    report_message = ""  # Переменная для хранения отчета

    while True:
        reset_daily_limit()  # Проверяем, не нужно ли сбросить лимит

        try:
            posts = await get_channel_posts(client)  # Получаем сообщения с канала

            if not posts:  # Если сообщений нет, ждем и повторяем попытку
                print("Нет новых сообщений. Ожидаем...")
                await asyncio.sleep(10)
                continue

            for post in posts:  # Проходим по всем полученным сообщениям
                if post.id in processed_messages:  # Если сообщение уже обработано, пропускаем его
                    continue

                if invites_sent_today >= DAILY_LIMIT:  # Если лимит на количество приглашений достигнут
                    print("Дневной лимит достигнут. Ожидаем.")
                    await send_report(client, report_message)  # Отправляем отчет
                    report_message = ""  # Очищаем отчет
                    await asyncio.sleep(3600)  # Ждем 1 час перед продолжением
                    continue

                username, phone = extract_user_info(post)  # Извлекаем информацию из сообщения

                if not username and not phone:  # Если нет юзернейма и телефона, пропускаем сообщение
                    continue

                # Исключаем пользователей с юзернеймом, содержащим "veterinar"
                if username and 'veterinar' in username.lower():
                    print(f"Пропускаем аккаунт @{username}, содержащий 'veterinar'.")
                    continue

                if username and username not in invited_users and not username.endswith("bot"):
                    try:
                        print(f"Приглашаем @{username}...")
                        await client(functions.channels.InviteToChannelRequest(target_channel, [username]))  # Приглашаем в канал
                        await client(functions.channels.InviteToChannelRequest(target_group, [username]))  # Приглашаем в группу
                        print(f"Пользователь @{username} успешно приглашен.")

                        # Проверяем, добавлен ли пользователь в группу
                        if not await check_user_in_group(client, username, target_channel):
                            print(f"Пользователь @{username} не был добавлен. Ограничения на добавление в группы.")
                            report_message += f"Пользователь @{username} не был добавлен. Ограничения на добавление в группы.\n"
                        else:
                            report_message += f"Пользователь @{username} успешно приглашен.\n"
                        
                        invited_users.add(username)  # Добавляем пользователя в список приглашенных
                    except Exception as e:
                        print(f"Ошибка при приглашении @{username}: {e}")
                        report_message += f"Ошибка при приглашении @{username}: {e}\n"

                elif phone and phone not in invited_users:
                    try:
                        print(f"Добавляем контакт с номером {phone}...")
                        contact = InputPhoneContact(client_id=0, phone=phone, first_name="User", last_name="")  # Создаем контакт
                        result = await client(functions.contacts.ImportContactsRequest([contact]))  # Импортируем контакт
                        if result.users:  # Если контакт успешно добавлен
                            user_id = result.users[0].id  # Получаем ID пользователя
                            await client(functions.channels.InviteToChannelRequest(target_channel, [user_id]))  # Приглашаем в канал
                            await client(functions.channels.InviteToChannelRequest(target_group, [user_id]))  # Приглашаем в группу
                            print(f"Пользователь с номером {phone} успешно приглашен.")
                            
                            # Проверяем, добавлен ли пользователь с номером
                            if not await check_user_in_group(client, phone, target_channel):
                                print(f"Пользователь с номером {phone} не был добавлен. Ограничения на добавление в группы.")
                                report_message += f"Пользователь с номером {phone} не был добавлен. Ограничения на добавление в группы.\n"
                            else:
                                report_message += f"Пользователь с номером {phone} успешно приглашен.\n"
                            
                            invited_users.add(phone)  # Добавляем телефон в список приглашенных
                        else:
                            print(f"Не удалось добавить контакт с номером {phone}. Пропускаем.")
                    except Exception as e:
                        print(f"Ошибка при приглашении с номером {phone}: {e}")
                        report_message += f"Ошибка при приглашении с номером {phone}: {e}\n"

                invites_sent_today += 1  # Увеличиваем счетчик приглашений
                processed_messages.add(post.id)  # Добавляем ID сообщения в список обработанных
                await asyncio.sleep(random.randint(5, 15))  # Пауза перед следующим запросом

        except FloodWaitError as e:  # Обработка ошибок, связанных с ограничениями Telegram
            print(f"FloodWait! Пауза {e.seconds} секунд.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"Ошибка: {e}")
            report_message += f"Ошибка: {e}\n"

    await send_report(client, report_message)  # Отправляем финальный отчет
    await client.disconnect()  # Закрываем подключение

# === Запуск ===
# Запуск основного процесса
if __name__ == "__main__":
    asyncio.run(invite_users())  # Запускаем асинхронную функцию приглашений
