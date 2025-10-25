import aioredis
import logging
import asyncio

redis = None  # Глобальный объект Redis

async def init_redis():
    global redis
    if redis is None:
        try:
            redis = await aioredis.from_url("redis://localhost", decode_responses=True)
            logging.info("Redis подключен!")
        except aioredis.exceptions.ConnectionError as e:
            logging.error(f"Ошибка подключения к Redis: {e}. Повторная попытка подключения...")
            await asyncio.sleep(5)  # Пауза перед повторной попыткой
            return await init_redis()  # Рекурсивный вызов для повторного подключения
        except Exception as e:
            logging.error(f"Неизвестная ошибка при подключении к Redis: {e}")
            await asyncio.sleep(5)  # Пауза перед повторной попыткой
            return await init_redis()  # Рекурсивный вызов для повторного подключения
    return redis

async def close_redis():
    global redis
    if redis:
        try:
            await redis.close()
            redis = None
            logging.info("Redis соединение закрыто.")
        except Exception as e:
            logging.error(f"Ошибка при закрытии соединения с Redis: {e}")