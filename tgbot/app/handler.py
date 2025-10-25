from aiogram import F, Router, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import StateFilter
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from sqlalchemy import func, update
from sqlalchemy.sql import text
from sqlalchemy.future import select

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

import os
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

import app.Keyboards as kb
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton)

from app.Keyboards import get_referral_keyboard
from app.Middleware import TestMiddleware
from app.general import general, add_referral, check_referrals
from app.database.Models import User, async_session_maker
from app.redis_client import init_redis

router = Router()

load_dotenv()

# Настройка ротации логов
log_file = "admin_logs.log"
log_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))

# Применяем настройки ротации логов
logging.basicConfig(handlers=[log_handler], level=logging.INFO)

router.message.outer_middleware(TestMiddleware())
ADMIN_ID = (os.getenv("ADMIN_ID"))  # Убедись, что ID задан в .env

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class Reg(StatesGroup):
    name = State()
    number = State()

class Work(StatesGroup):
    process = State()

class APIKeyChange(StatesGroup):
    waiting_for_new_api = State()

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user_id = message.from_user.id
    args = message.text.split()

    async with async_session_maker() as session:
        user = await session.get(User, user_id)

        if user is None:
            user = User(user_id=user_id)
            session.add(user)
            await session.commit()

        # Обработка реферального кода
        if len(args) > 1 and args[1].isdigit():
            inviter_id = int(args[1])
            
            if inviter_id == user_id:
                await message.answer("⛔ Нельзя приглашать самого себя!")
                return
            
            if user.invited_by is not None:
                inviter = await session.get(User, user.invited_by)
                inviter_name = inviter.username if inviter and inviter.username else user.invited_by
                await message.answer(f"⛔ Вы уже зарегистрированы как реферал у {inviter_name}!")
                return
            
            existing_referral = await session.execute(
                text("SELECT 1 FROM referrals WHERE invited_id = :user_id"),
                {"user_id": user_id}
            )
            if existing_referral.scalar():
                await message.answer("⛔ Вы уже засчитаны как чей-то реферал!")
                return

            # Добавляем реферала
            await add_referral(session, inviter_id, user_id, bot)

        # Проверяем количество приглашенных рефералов
        referral_count = await check_referrals(session, user_id)

        start_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Начать диалог")]], resize_keyboard=True
        )

        if referral_count >= 2:
            await message.answer(
                "🎉 Поздравляю! Вы можете пользоваться ботом!\n"
                "Нажмите 'Начать диалог', чтобы задать вопрос.", reply_markup=start_keyboard
            )
        else:
            await message.reply(
                "Добро пожаловать! 😊\n"
                "🎁 Можете задать 1-й тестовый вопрос, чтобы убедиться в качестве ответов\n"
                "Чтобы получить полный доступ, пригласите 2 друзей.\n"
                "Используя бота, вы поддерживаете его бесплатность ❤️",
                reply_markup=kb.get_referral_keyboard(user_id)
            )

@router.message(F.text == "Начать диалог")
async def start_dialog(message: Message):
    user_id = message.from_user.id

    async with async_session_maker() as session:
        referral_count = await check_referrals(session, user_id)

        if referral_count < 2:
            await message.answer(
                "⛔ У вас недостаточно рефералов! Пригласите 2-х друзей, чтобы получить доступ.",
                reply_markup=get_referral_keyboard(user_id)
            )
            return

    await message.answer(
        "Напишите мне любой вопрос — о учёбе, личной жизни, кулинарии или чем угодно. Я помогу! 😊"
    )

@router.message(Command("admin"))
async def admin_panel(message: Message, bot: Bot):
    user_id = message.from_user.id
    if user_id != int(ADMIN_ID):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    # Проверка на админа, если пользователь админ, показываем админ-панель
    await message.answer("📊 Добро пожаловать в админ-панель!\n"
                         "Выберите действие:\n"
                         "1️⃣ Статистика\n"
                         "2️⃣ Рассылка\n"
                         "3️⃣ Логи\n"
                         "4️⃣ Сменить API",
                         reply_markup=kb.admin_keyboard())

@router.message(F.text == "📊 Статистика")
async def user_stats(message: Message):
    user_id = message.from_user.id
    if user_id != int(ADMIN_ID):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    #await log_action(message, message.chat.id, "Запросил статистику пользователей")  # Логируем действие

    redis = await init_redis()  # Подключение к Redis
    stats_cache = await redis.get("stats")

    if stats_cache:
        await message.answer(stats_cache)  # Отправляем кэшированные данные и не нагружаем БД
        return

    async with async_session_maker() as session:
        total_users = await session.scalar(select(func.count(User.user_id)))
        now = datetime.now(timezone.utc)
        active_today = await session.scalar(select(func.count(User.user_id)).where(User.last_activity >= now - timedelta(days=1)))
        active_week = await session.scalar(select(func.count(User.user_id)).where(User.last_activity >= now - timedelta(weeks=1)))
        active_month = await session.scalar(select(func.count(User.user_id)).where(User.last_activity >= now - timedelta(days=30)))
        new_today = await session.scalar(select(func.count(User.user_id)).where(User.created_at >= now - timedelta(days=1)))
        new_week = await session.scalar(select(func.count(User.user_id)).where(User.created_at >= now - timedelta(weeks=1)))
        new_month = await session.scalar(select(func.count(User.user_id)).where(User.created_at >= now - timedelta(days=30)))

        total_users, active_today, active_week, active_month, new_today, new_week, new_month = map(lambda x: x or 0, [total_users, active_today, active_week, active_month, new_today, new_week, new_month])

        text = (
            f"👥 Всего пользователей: {total_users}\n"
            f"📅 Активных сегодня: {active_today}\n"
            f"📆 Активных за неделю: {active_week}\n"
            f"📅 Активных за месяц: {active_month}\n\n"
            f"🆕 Новых сегодня: {new_today}\n"
            f"🆕 Новых за неделю: {new_week}\n"
            f"🆕 Новых за месяц: {new_month}"
        )

        await redis.setex("stats", 600, text)  # Кэшируем статистику на 10 минут (600 секунд)

        await message.answer(text)
@router.message(F.text == "📢 Рассылка")
async def start_broadcast(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id != int(ADMIN_ID):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    await message.answer("Отправьте текст сообщения или фото/видео с подписью.")
    await state.set_state(BroadcastState.waiting_for_message)

@router.message(StateFilter(BroadcastState.waiting_for_message))
async def send_broadcast(message: Message, bot: Bot, state: FSMContext):
    redis = await init_redis()  # Получаем подключение к Redis

    if await redis.get('broadcast_in_progress'):
        # Проверяем, идет ли рассылка дольше 30 минут (1800 секунд)
        last_update = await redis.get('broadcast_timestamp')
    
        if last_update and (datetime.now().timestamp() - float(last_update)) > 1800:
            await redis.delete('broadcast_in_progress')  # Удаляем зависший флаг
            await redis.delete('broadcast_timestamp')  # Удаляем устаревший таймстамп
        else:
            await message.answer("⏳ Рассылка уже выполняется. Подождите завершения.")
            return

        await redis.set('broadcast_in_progress', '1')
        await redis.set('broadcast_timestamp', datetime.now().timestamp())  # Фиксируем время начала

    async with async_session_maker() as session:
        users = await session.execute(select(User.user_id))
        users = [user[0] for user in users]

    # Помечаем, что рассылка началась
    await redis.set('broadcast_in_progress', '1')

    await message.answer(f"📤 Рассылка началась! Всего {len(users)} пользователей.")
    await state.clear()

    # Запускаем параллельную рассылку в фоне
    asyncio.create_task(process_broadcast(bot, message, users))

    # После завершения рассылки снимаем флаг
    await redis.delete('broadcast_in_progress')


async def process_broadcast(bot: Bot, message: Message, users: list):
    sent, blocked = 0, 0

    async def send_message(user_id):
        nonlocal sent, blocked
        try:
            if message.photo:
                await bot.send_photo(user_id, photo=message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(user_id, video=message.video.file_id, caption=message.caption)
            else:
                await bot.send_message(user_id, text=message.text)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)  # Ждем, если Telegram требует задержку
            await send_message(user_id)  # Пробуем снова
        except Exception:
            blocked += 1

    # Обрабатываем пользователей партиями по 20
    for i in range(0, len(users), 20):  # Отправляем по 20 сообщений за раз
        tasks = [send_message(user_id) for user_id in users[i:i + 20]]
        await asyncio.gather(*tasks)
        await asyncio.sleep(1)  # Лимитируем скорость рассылки

    await message.answer(f"📤 Рассылка завершена!\n✅ Отправлено: {sent}\n❌ Недоступны: {blocked}")

@router.message(F.text == "📜 Логи")
async def send_logs(message: Message, bot: Bot):
    user_id = message.from_user.id
    if user_id != int(ADMIN_ID):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    if not os.path.exists(log_file):
        await message.answer("⛔ Логи отсутствуют!")
        return

    try:
        # Закрываем обработчик логирования на время работы с файлом
        logging.getLogger().removeHandler(log_handler)

        # Создаем FSInputFile для отправки лога
        document = FSInputFile(log_file)

        # Отправляем лог-файл администратору
        await bot.send_document(chat_id=user_id, document=document)

        # Логируем успешную отправку
        logging.info("Логи успешно отправлены администратору.")

        # Закрытие файла перед его удалением
        os.remove(log_file)  # Удаляем старый файл лога после отправки
        await message.answer("✅ Логи отправлены и успешно удалены с сервера.")
    except Exception as e:
        logging.error(f"Ошибка при отправке логов: {e}")
        await message.answer("❌ Ошибка при отправке логов.")
    finally:
        # Включаем обработчик логирования снова после отправки и удаления
        logging.getLogger().addHandler(log_handler)

        # Создаём новый пустой лог-файл для продолжения работы
        with open(log_file, "w"): pass  # Создаём новый файл для записи


@router.message(F.text == "🔑 Сменить API")
async def request_new_api_key(message: Message, state: FSMContext):
    if message.from_user.id != int(ADMIN_ID):
        return await message.answer("⛔ У вас нет доступа!")
    
    await message.answer("🔑 Введите новый API-ключ:")
    await state.set_state(APIKeyChange.waiting_for_new_api)

@router.message(StateFilter(APIKeyChange.waiting_for_new_api))
async def update_api_key(message: Message, state: FSMContext):
    new_api_key = message.text.strip()

    if not new_api_key or len(new_api_key) < 20:  # Минимальная проверка ключа
        return await message.answer("⛔ Некорректный API-ключ! Попробуйте еще раз.")

    # Читаем и обновляем файл .env
    env_file = ".env"
    with open(env_file, "r") as f:
        lines = f.readlines()

    with open(env_file, "w") as f:
        for line in lines:
            if line.startswith("AI_TOKEN="):
                f.write(f"AI_TOKEN='{new_api_key}'\n")
            else:
                f.write(line)

    # Перезагружаем переменные окружения без перезапуска бота
    os.environ["AI_TOKEN"] = new_api_key

    await message.answer("✅ API-ключ успешно обновлен!")
    await state.clear()

@router.message(F.text)
async def handle_message(message: Message, bot: Bot):
    if message.from_user.id == (await bot.me()).id:
        return
    redis = await init_redis()

    user_id = message.from_user.id

    async with async_session_maker() as session:
        user = await session.get(User, user_id)

        if not user:
            await message.answer("⛔️ Вас нет в пользователях! Введите /start")
            return

        # Проверяем наличие ключа в Redis для первого вопроса
        redis_key = f"first_question:{user_id}"
        if not await redis.exists(redis_key):
            # Разрешаем задать первый вопрос
            await redis.set(redis_key, "asked", ex=86400)  # Ключ действует 24 часа
            response = await general(message.text)
            response_text = response.choices[0].message.content if response and response.choices else "Ошибка: пустой ответ от ИИ."
            await message.answer(response_text)
            return

        # Проверяем количество рефералов
        referral_count = await check_referrals(session, user_id)
        if referral_count < 2:
            await message.answer(
                "⛔️ У вас недостаточно рефералов! Пригласите 2-х друзей, чтобы получить доступ.",
                reply_markup=get_referral_keyboard(user_id)
            )
            return

        # Получаем ответ от ИИ
        response = await general(message.text)
        response_text = response.choices[0].message.content if response and response.choices else "Ошибка: пустой ответ от ИИ."
        await message.answer(response_text)

@router.callback_query(F.data == 'dialog')
async def catalog(callback: CallbackQuery, state: FSMContext):
    await callback.answer('Искуственный Интеллект запущен')
    await callback.message.answer('Напиши сообщением всё, что вы хотите у меня спросить, будь то вопрос связанный с учёбой, личный вопрос, помочь с изобретением рецепта, или любой абсолютно другой вопрос который вас интересует', reply_markup=kb.menu)

@router.message(Work.process)
async def stop(message: Message):
    await message.answer('Не спешите отправлять следующее сообщение, дождитесь ответа на ваше прошлое сообщение...')

@router.message()
async def ai(message: Message, state: FSMContext):
    if message.text:  # Проверяем, что это текстовое сообщение
        await state.set_state(Work.process)
        res = await general(message.text)
        response_text = res.choices[0].message.content if res and res.choices else "Ошибка: пустой ответ от ИИ."
        await message.answer(response_text)
        await state.clear()
    else:
        await message.answer("⛔ Бот принимает только текстовые сообщения.")

