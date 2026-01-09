from contextlib import AsyncExitStack
from typing import cast

import pytest
from pyrogram.raw.functions.langpack import GetLanguages, GetLanguage, GetDifference, GetStrings, GetLangPack
from pyrogram.raw.types import LangPackLanguage, LangPackDifference, LangPackString, LangPackStringPluralized

from tests.client import TestClient


@pytest.mark.asyncio
async def test_get_languages_empty(exit_stack: AsyncExitStack) -> None:
    client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))

    languages = cast(list[LangPackLanguage], await client.invoke(GetLanguages(lang_pack="test")))
    assert len(languages) == 0


@pytest.mark.create_languages
@pytest.mark.asyncio
async def test_get_available_languages_for_test_platform() -> None:
    client: TestClient = TestClient(phone_number="123456789")
    await client.connect()

    languages = cast(list[LangPackLanguage], await client.invoke(GetLanguages(lang_pack="test")))
    assert len(languages) == 2
    assert {language.lang_code for language in languages} == {"tst", "tst2"}

    await client.disconnect()


@pytest.mark.create_languages
@pytest.mark.asyncio
async def test_get_test_language() -> None:
    client: TestClient = TestClient(phone_number="123456789")
    await client.connect()

    language = cast(LangPackLanguage, await client.invoke(GetLanguage(lang_pack="test", lang_code="tst")))
    assert language.official
    assert language.lang_code == "tst"

    await client.disconnect()


@pytest.mark.create_languages
@pytest.mark.asyncio
async def test_get_test_langpack() -> None:
    client: TestClient = TestClient(phone_number="123456789")
    await client.connect()

    language = cast(LangPackDifference, await client.invoke(GetLangPack(lang_pack="test", lang_code="tst")))
    assert language.from_version == 0
    assert language.version >= 1
    assert len(language.strings) == 3
    assert {s.key for s in language.strings} == {
        "TestLanguageKey", "TestAnotherLanguageKey", "TestPluralizedLanguageKey"
    }

    await client.disconnect()


@pytest.mark.create_languages
@pytest.mark.asyncio
async def test_get_test_strings() -> None:
    client: TestClient = TestClient(phone_number="123456789")
    await client.connect()

    strings = cast(
        list[LangPackString | LangPackStringPluralized],
        await client.invoke(GetStrings(
            lang_pack="test",
            lang_code="tst",
            keys=[
                "TestLanguageKey",
                "TestPluralizedLanguageKey",
            ],
        ))
    )
    assert len(strings) == 2
    if strings[0].key == "TestLanguageKey":
        regular, plural = strings
    else:
        plural, regular = strings

    assert regular.key == "TestLanguageKey"
    assert regular.value == "some test string"
    assert plural.key == "TestPluralizedLanguageKey"
    assert plural.other_value == "%1$d other"

    await client.disconnect()
