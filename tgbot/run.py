import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

from dotenv import load_dotenv
from app.handler import router
from app.database.Models import init_db
from app.Middleware import ErrorHandlerMiddleware, UpdateLastActivityMiddleware, AntiFloodMiddleware
from app.redis_client import init_redis, close_redis

load_dotenv()

bot = Bot(token=os.getenv('TOKEN'))
dp = Dispatcher()

# Подключаем middleware
dp.message.middleware(AntiFloodMiddleware(limit=2))
dp.message.middleware(UpdateLastActivityMiddleware())
dp.message.middleware(ErrorHandlerMiddleware())


async def main():
    await init_db()  
    await init_redis()  # Инициализация Redis
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await close_redis()

if __name__ == '__main__':
#    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Закрываем эту шарманку')