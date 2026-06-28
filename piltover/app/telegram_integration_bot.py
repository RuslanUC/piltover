import asyncio
import random

from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from tortoise import Tortoise

from piltover.config import SYSTEM_CONFIG, APP_CONFIG, TORTOISE_ORM
from piltover.db.models import User

NEW_ACCOUNT_BTN_TEXT = "Create new account"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text=NEW_ACCOUNT_BTN_TEXT),
        ],
        [
            KeyboardButton(text="List my accounts"),
        ],
    ],
    is_persistent=True,
    one_time_keyboard=True,
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


@dp.message(F.text == NEW_ACCOUNT_BTN_TEXT)
async def new_account_btn_handler(message: Message, state: FSMContext) -> None:
    # TODO: check if user can create new account

    await state.set_state(BotState.first_name)
    await message.answer(
        text=f"What's the account {html.bold('first')} name will be?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text=message.from_user.first_name,
                    ),
                ],
            ],
            is_persistent=False,
            one_time_keyboard=True,
            input_field_placeholder="Send first name..."
        ) if message.from_user else ReplyKeyboardRemove(),
    )


@dp.message(BotState.first_name)
async def new_account_first_name_handler(message: Message, state: FSMContext) -> None:
    # TODO: validate first name
    await state.update_data(first_name=message.text)
    await state.set_state(BotState.last_name)
    await message.answer(
        text=f"What's the account {html.bold('last')} name will be?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text=message.from_user.last_name,
                    ),
                ],
            ],
            is_persistent=False,
            one_time_keyboard=True,
            input_field_placeholder="Send first name..."
        ) if message.from_user and message.from_user.last_name else ReplyKeyboardRemove(),
    )


@dp.message(BotState.last_name)
async def new_account_last_name_handler(message: Message, state: FSMContext) -> None:
    # TODO: validate last name
    await state.update_data(last_name=message.text)
    await state.set_state(BotState.phone_number)

    policy = SYSTEM_CONFIG.telegram_integration.phone_number_policy
    if policy == "real":
        ...  # TODO: request user contact
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
        ...  # TODO: ask user for phone number
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

    data = await state.get_data()
    # TODO: handle exception when user with phone number already exists
    user = await User.create_new_user(data["phone_number"], data["first_name"], data["last_name"])
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


async def main() -> None:
    bot = Bot(
        token=SYSTEM_CONFIG.telegram_integration.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await Tortoise.init(config=TORTOISE_ORM)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
