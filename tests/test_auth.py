import pytest
from pyrogram.raw.types.help import CountriesList, CountriesListNotModified
from pyrogram.raw.functions.help import GetCountriesList

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_signup() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert await client.storage.user_id() is not None


@pytest.mark.asyncio
async def test_signin() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me
        user_id = client.me.id

    async with TestClient(phone_number="123456789") as client:
        assert client.me
        assert client.me.id == user_id


@pytest.mark.asyncio
async def test_enable_disable_cloud_password() -> None:
    async with TestClient(phone_number="123456789") as client:
        assert client.me
        user_id = client.me.id

        assert await client.enable_cloud_password("test_passw0rd")

    async with TestClient(phone_number="123456789", password="test_passw0rd") as client:
        assert client.me
        assert client.me.id == user_id

        assert await client.change_cloud_password("test_passw0rd", "test_passw0rd_new")
        assert await client.remove_cloud_password("test_passw0rd_new")


@pytest.mark.asyncio
async def test_get_countries_list() -> None:
    async with TestClient(phone_number="123456789") as client:
        countries1: CountriesList = await client.invoke(GetCountriesList(lang_code="en", hash=0))
        assert len(countries1.countries) > 0
        assert countries1.hash != 0

        countries2: CountriesList = await client.invoke(GetCountriesList(lang_code="en", hash=0))
        assert countries1 == countries2

        countries3: CountriesList = await client.invoke(GetCountriesList(lang_code="en", hash=countries1.hash))
        assert isinstance(countries3, CountriesListNotModified)
