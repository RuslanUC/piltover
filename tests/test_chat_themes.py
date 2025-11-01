from typing import cast

import pytest
from pyrogram.raw.functions.account import GetChatThemes
from pyrogram.raw.types.account import Themes, ThemesNotModified

from piltover.app.app import args as app_args
from tests.client import TestClient


@pytest.mark.asyncio
async def test_get_available_chat_themes_empty() -> None:
    async with TestClient(phone_number="123456789") as client:
        themes = cast(Themes, await client.invoke(GetChatThemes(hash=1)))
        assert len(themes.themes) == 0
        assert themes.hash == 0

        themes = await client.invoke(GetChatThemes(hash=0))
        assert isinstance(themes, ThemesNotModified)


themes_files_dir = app_args.chat_themes_dir / "files"


@pytest.mark.skipif(
    not app_args.chat_themes_dir.exists() or not themes_files_dir.exists(),
    reason="No chat theme files available"
)
@pytest.mark.create_chat_themes
@pytest.mark.asyncio
async def test_get_available_chat_themes() -> None:
    async with TestClient(phone_number="123456789") as client:
        themes = cast(Themes, await client.invoke(GetChatThemes(hash=0)))
        assert len(themes.themes) > 0
