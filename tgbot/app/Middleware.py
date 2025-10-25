from aiogram import BaseMiddleware, types
from aiogram.types import TelegramObject, Update, CallbackQuery, Message
from typing import Callable, Dict, Any, Awaitable
from app.database.Models import User, async_session_maker
from app.general import check_referrals
from app.Keyboards import get_referral_keyboard
from datetime import datetime, timezone
from dotenv import load_dotenv

from app.database.Models import User
from app.redis_client import init_redis

import logging
import os

load_dotenv()

ADMIN_ID = int(os.getenv("ADMIN_ID"))

#logging.basicConfig(filename="bot_errors.log", level=logging.ERROR, format="%(asctime)s - %(message)s")

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            user_id = event.from_user.id

            # Проверяем, является ли пользователь администратором
            if user_id == ADMIN_ID:
                return await handler(event, data)  # Пропускаем проверки для админа

            async with async_session_maker() as session:
                user = await session.get(User, user_id)

                if not user:
                    await event.answer("🚀 Вас нет в базе данных! Введите /start")
                    return

                referral_count = await check_referrals(session, user_id)

                if referral_count < 2:
                    await event.answer(
                        "🚀 Чтобы пользоваться ботом, пригласите 2 друзей.\n"
                        "Используйте кнопку ниже 👇",
                        reply_markup=get_referral_keyboard(user_id)
                    )
                    return  # Прерываем выполнение для пользователей без доступа

        return await handler(event, data)

class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        try:
            return await handler(event, data)
        except Exception as e:
            logging.error(f"Ошибка: {e}")
            await event.bot.send_message(ADMIN_ID, f"⚠️ Бот упал! Ошибка: {e}")

class AntiFloodMiddleware(BaseMiddleware):
    """Middleware для защиты от флуда с использованием Redis."""

    def __init__(self, limit=2):  # Лимит в секундах
        self.limit = limit
        super().__init__()

    async def __call__(self, handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]], 
                       event: Message, data: Dict[str, Any]) -> Any:
        user_id = event.from_user.id
        redis = await init_redis()
        key = f"flood_{user_id}"
        last_request = await redis.get(key)

        if last_request:
            await event.answer("⛔ Вы слишком часто отправляете сообщения. Подождите немного.")
            return

        await redis.setex(key, self.limit, "1")  # Устанавливаем ограничение
        return await handler(event, data)

class UpdateLastActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        # Проверяем, является ли событие `Message` или `CallbackQuery`
        if isinstance(event, (Message, CallbackQuery)):
            from_user = event.from_user  # Теперь точно знаем, что у события есть from_user
            
            if from_user and from_user.id:
                async with async_session_maker() as session:
                    user = await session.get(User, from_user.id)

                    if not user:
                        user = User(user_id=from_user.id, last_activity=datetime.now(timezone.utc))
                        session.add(user)
                    else:
                        user.last_activity = datetime.now(timezone.utc)

                    await session.commit()

        return await handler(event, data)

class TestMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        print('Действие до обработчика')
        result = await handler(event, data)
        print('Действие после обработчика')
        return result
