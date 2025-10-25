from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, ForeignKey, Integer, UniqueConstraint, DateTime, Boolean, func, text, Index
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# Подключение к PostgreSQL
DATABASE_URL = os.getenv("SQL_ALCHEMY_URL")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(50), nullable=True)
    invited_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0)
    access_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    referrals = relationship(
        "Referral",
        back_populates="inviter",
        foreign_keys="Referral.inviter_id",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('ix_user_user_id', 'user_id'),
        Index('ix_user_invited_by', 'invited_by'),
        Index('ix_user_referral_count', 'referral_count'),  # Добавлен индекс на referral_count
        Index('ix_user_last_activity', 'last_activity'),
        Index('ix_user_access_granted', 'access_granted'),  # Добавлен индекс на access_granted
    )

class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    invited_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), unique=True)

    inviter = relationship("User", back_populates="referrals", foreign_keys=[inviter_id])

    __table_args__ = (
        UniqueConstraint('inviter_id', 'invited_id', name='unique_referral_pair'),
        Index('ix_referral_inviter_id', 'inviter_id'),  # Добавлен индекс на inviter_id
        Index('ix_referral_invited_id', 'invited_id'),  # Добавлен индекс на invited_id
    )

async def migrate_db():
    async with engine.begin() as conn:
        # Преобразуем поле access_granted в BOOLEAN для корректной работы с PostgreSQL
        await conn.execute(text(
            "ALTER TABLE users ALTER COLUMN access_granted TYPE BOOLEAN USING access_granted::BOOLEAN;"
        ))
        await conn.execute(text(
            "ALTER TABLE users ALTER COLUMN is_admin TYPE BOOLEAN USING is_admin::BOOLEAN;"
        ))

        # Установим значение по умолчанию для created_at, чтобы избежать ошибок при вставке
        await conn.execute(text(
            "ALTER TABLE users ALTER COLUMN created_at SET DEFAULT NOW();"
        ))
        # Убедимся, что поле не принимает NULL значения
        await conn.execute(text(
            "ALTER TABLE users ALTER COLUMN created_at SET NOT NULL;"
        ))


async def init_db():
    async with engine.begin() as conn:
        await migrate_db()
        await conn.run_sync(Base.metadata.create_all)  # Создаём таблицы, если их нет