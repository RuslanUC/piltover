import asyncio
import random

from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton
from tortoise import Tortoise
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from piltover.app.handlers.auth import _validate_phone
from piltover.config import SYSTEM_CONFIG, APP_CONFIG, TORTOISE_ORM
from piltover.db.models import User, TelegramUser
from piltover.exceptions import ErrorRpc
from piltover.utils.utils import batched

NEW_ACCOUNT_BTN_TEXT = "Create new account"
LIST_ACCOUNTS_BTN_TEXT = "List my accounts"
BTN_TEXT_SHARE_CONTACT = "Share contact"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=NEW_ACCOUNT_BTN_TEXT)],
        [KeyboardButton(text=LIST_ACCOUNTS_BTN_TEXT)],
    ],
    is_persistent=True,
    one_time_keyboard=True,
    resize_keyboard=True,
    input_field_placeholder="Select action..."
)


class BotState(StatesGroup):
    first_name = State()
    last_name = State()
    phone_number = State()


dp = Dispatcher()


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        text=(
            f"Hello, {html.bold(message.from_user.full_name)}! "
            f"In this bot, you can manage your {html.bold(APP_CONFIG.name)} accounts."
        ),
        reply_markup=MAIN_KEYBOARD,
    )


def _make_first_name_kbd(message: Message) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=message.from_user.first_name)]],
        is_persistent=False,
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Send first name..."
    ) if message.from_user else ReplyKeyboardRemove()


def _make_last_name_kbd(message: Message) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=message.from_user.last_name)]],
        is_persistent=False,
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Send last name..."
    ) if message.from_user and message.from_user.last_name else ReplyKeyboardRemove()


def _make_phone_number_kbd() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_TEXT_SHARE_CONTACT)]],
        is_persistent=False,
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Send phone_number..."
    )


@dp.message(F.text == NEW_ACCOUNT_BTN_TEXT)
async def new_account_btn_handler(message: Message, state: FSMContext) -> None:
    max_per_user = SYSTEM_CONFIG.telegram_integration.max_accounts_per_user
    if max_per_user <= 0:
        await message.answer(
            text=f"New accounts registration is currently disabled.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    if await TelegramUser.filter(telegram_id=message.from_user.id).count() > max_per_user:
        await message.answer(
            text=f"You already have created maximum number of accounts.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    await state.set_state(BotState.first_name)
    await message.answer(
        text=f"What's the account {html.bold('first')} name will be?",
        reply_markup=_make_first_name_kbd(message),
    )


@dp.message(BotState.first_name)
async def new_account_first_name_handler(message: Message, state: FSMContext) -> None:
    if not message.text or len(message.text) > 64 or "\n" in message.text:
        await message.answer(
            text=f"Invalid first name. It should be 1-64 characters in length and be a single line.",
            reply_markup=_make_first_name_kbd(message),
        )
        return

    await state.update_data(first_name=message.text)
    await state.set_state(BotState.last_name)
    await message.answer(
        text=f"What's the account {html.bold('last')} name will be?",
        reply_markup=_make_last_name_kbd(message),
    )


@dp.message(BotState.last_name)
async def new_account_last_name_handler(message: Message, state: FSMContext) -> None:
    if not message.text or len(message.text) > 64 or "\n" in message.text:
        await message.answer(
            text=f"Invalid last name. It should be 1-64 characters in length and be a single line.",
            reply_markup=_make_last_name_kbd(message),
        )
        return

    await state.update_data(last_name=message.text)
    await state.set_state(BotState.phone_number)

    policy = SYSTEM_CONFIG.telegram_integration.phone_number_policy
    if policy == "real":
        await message.answer(
            text=f"Share your phone number with bot and it will be used to create new account.",
            reply_markup=_make_phone_number_kbd(),
        )
        return
    elif policy == "random":
        for _ in range(3):
            random_number = random.randint(0, 9999999)
            random_phone = f"999{random_number}"
            if not await User.filter(phone_number=random_phone).exists():
                break
        else:
            await state.clear()
            await message.answer(
                text=f"Failed to find a random unused phone number! Please try to create account again.",
                reply_markup=MAIN_KEYBOARD,
            )
            return

        await state.update_data(phone_number=random_phone)
    elif policy == "user-provided":
        await message.answer(
            text=f"Send phone number that will be used for new account.",
            reply_markup=_make_phone_number_kbd(),
        )
        return
    else:
        await message.answer(
            text=(
                f"Got invalid phone number policy: {policy!r}.\n\n"
                f"If you are {html.bold(APP_CONFIG.name)} user - report this to instance administrator.\n"
                f"If you are {html.bold(APP_CONFIG.name)} administrator - please check config; "
                f"if everything is correct - this is a bug, please report it."
            ),
            reply_markup=MAIN_KEYBOARD,
        )
        await state.clear()
        return

    await _create_new_user(message, state)


@dp.message(BotState.phone_number)
async def new_account_phone_number_handler(message: Message, state: FSMContext) -> None:
    if message.contact is not None:
        if message.contact.user_id != message.from_user.id:
            await message.answer(
                text=f"You need to share your own phone number with the bot.",
                reply_markup=_make_phone_number_kbd(),
            )
            return
        await state.update_data(phone_number=message.contact.phone_number)
    else:
        if SYSTEM_CONFIG.telegram_integration.phone_number_policy == "real":
            await message.answer(
                text=f"Share your phone number with bot and it will be used to create new account.",
                reply_markup=_make_phone_number_kbd(),
            )
            return

        try:
            phone_number = _validate_phone(message.text or "")
        except ErrorRpc:
            await message.answer(
                text=f"Invalid phone number. Try another one.",
                reply_markup=_make_phone_number_kbd(),
            )
            return
        else:
            await state.update_data(phone_number=phone_number)

    await _create_new_user(message, state)


async def _create_new_user(message: Message, state: FSMContext) -> None:
    data = await state.get_data()

    async with in_transaction():
        try:
            user = await User.create_new_user(data["phone_number"], data["first_name"], data["last_name"])
        except IntegrityError:
            await message.answer(
                text=(
                    f"Failed to create account (possibly because user with specified phone number already exists). "
                    f"You can try to create account again."
                ),
                reply_markup=MAIN_KEYBOARD,
            )
            await state.clear()
            return

        await TelegramUser.create(user=user, telegram_id=message.from_user.id)

    await message.answer(
        text=(
            f"Account was created successfully! "
            f"You can now log into {html.bold(APP_CONFIG.name)} instance.\n"
            f"Account details:\n"
            f"First name: {html.code(user.first_name)}\n"
            f"Last name: {html.code(user.last_name)}\n"
            f"Phone number: +{user.phone_number}"
        ),
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.clear()


@dp.message(F.text == LIST_ACCOUNTS_BTN_TEXT)
async def list_accounts_btn_handler(message: Message) -> None:
    all_users = await User.filter(
        telegramuser__telegram_id=message.from_user.id,
    ).only("id", "first_name", "last_name")

    max_per_user = SYSTEM_CONFIG.telegram_integration.max_accounts_per_user
    if max_per_user <= 0:
        can_create_accounts_text = "New accounts registration is currently disabled."
    elif not all_users:
        can_create_accounts_text = f"You can create {max_per_user} accounts."
    elif len(all_users) >= max_per_user:
        can_create_accounts_text = (
            f"You can not create any more accounts (maximum is {max_per_user}, you have {len(all_users)})."
        )
    else:
        can_create_accounts_text = f"You can create {max_per_user - len(all_users)} more accounts."

    if not all_users:
        await message.answer(
            text=f"You dont have any {APP_CONFIG.name} accounts.\n{can_create_accounts_text}",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    inline_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{user.full_name()}",
                    callback_data=f"manager-user:{user.id}",
                )
                for user in users_batch
            ]
            for users_batch in batched(all_users, 2)
        ],
    )

    s_maybe = "s" if len(all_users) > 1 else ""
    await message.answer(
        text=f"You currently have {len(all_users)} account{s_maybe}.\n{can_create_accounts_text}",
        reply_markup=inline_keyboard,
    )


async def main() -> None:
    bot = Bot(
        token=SYSTEM_CONFIG.telegram_integration.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await Tortoise.init(config=TORTOISE_ORM)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
