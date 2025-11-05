from contextlib import AsyncExitStack
from typing import cast

import pytest
from pyrogram.raw.functions.langpack import GetLanguages
from pyrogram.raw.types import LangPackLanguage

from piltover.app.app import args as app_args
from tests.client import TestClient


@pytest.mark.asyncio
async def test_get_languages_empty(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    languages = cast(list[LangPackLanguage], await client.invoke(GetLanguages(lang_pack="android")))
    assert len(languages) == 0


@pytest.mark.skipif(
    not app_args.languages_dir.exists() or not (app_args.languages_dir / "android").exists(),
    reason="No language files available for platform \"android\""
)
@pytest.mark.create_languages
@pytest.mark.asyncio
async def test_get_available_languages_android(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    languages = cast(list[LangPackLanguage], await client.invoke(GetLanguages(lang_pack="android")))
    assert len(languages) >= 2
