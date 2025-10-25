from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton)

def get_referral_keyboard(user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎯 Поделиться реферальной ссылкой",
                switch_inline_query=f"Присоединяйтесь к самому лучшему, быстрому, точному и бесплатному GPT боту в Телеграме! 🎁\n"
                                   f"Пользуйся по моей ссылке: (url)?start={user_id}"
            )]
        ]
    )

def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="📜 Логи")],
            [KeyboardButton(text="🔑 Сменить API")]
        ],
        resize_keyboard=True

    )
