
from mistralai import Mistral
import os
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.Models import User, Referral
from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import text
import logging

from dotenv import load_dotenv
from app.redis_client import init_redis

load_dotenv()

#logging.basicConfig(filename="admin_logs.log", level=logging.INFO, format="%(asctime)s - %(message)s")

async def add_referral(session: AsyncSession, inviter_id: int, invited_id: int, bot: Bot):
    inviter = await session.get(User, inviter_id)
    invited = await session.get(User, invited_id)

    if not inviter or not invited:
        return

    # Проверяем, не был ли пользователь уже засчитан как чей-то реферал
    if invited.invited_by:
        inviter_user = await session.get(User, invited.invited_by)
        inviter_name = inviter_user.username if inviter_user and inviter_user.username else invited.invited_by
        await bot.send_message(invited_id, f"⛔ Вы уже являетесь рефералом пользователя {inviter_name}!")
        return

    invited.invited_by = inviter_id
    inviter.referral_count += 1
    session.add(Referral(inviter_id=inviter_id, invited_id=invited_id))

    await bot.send_message(invited_id, "✅ Вы были зарегистрированы как реферал!")
    
    if inviter.referral_count >= 2:
        inviter.access_granted = 1  # Даем доступ
        await bot.send_message(inviter_id, "🎉 Поздравляю! Вы пригласили 2-х друзей и теперь можете пользоваться ботом!")
    else:
        await bot.send_message(inviter_id, f"✅ {inviter.referral_count}/2 рефералов приглашены!")

    await session.commit()

async def check_referrals(session: AsyncSession, user_id: int) -> int:
    redis = await init_redis()
    
    # Проверяем кеш
    referral_count = await redis.get(f"user:{user_id}:referral_count")
    if referral_count is not None:
        return int(referral_count)
    
    # Если в кеше нет, запрашиваем из БД
    result = await session.execute(
        text("SELECT COUNT(*) FROM referrals WHERE inviter_id = :user_id"),
        {"user_id": user_id}
    )
    referral_count = result.scalar() or 0

    # Кешируем на 10 минут
    await redis.setex(f"user:{user_id}:referral_count", 600, referral_count)
    return referral_count


#async def log_action(message: Message, admin_id: int, action: str):
#    logging.info(f"Админ {admin_id}: {action}")

async def general(content):
    s = Mistral(
        api_key=os.getenv('AI_TOKEN'),
    )
    res = await s.chat.complete_async(model="mistral-small-latest", messages=[
        {
            "content": content,
            "role": "user",
        },
    ])
    if res is not None:
        return res