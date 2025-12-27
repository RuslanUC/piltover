import pytest
from pyrogram.raw.types import InputPrivacyKeyPhoneNumber, InputPrivacyValueDisallowAll, InputPrivacyValueDisallowUsers, \
    InputPrivacyValueAllowUsers

from piltover.tl import InputPrivacyValueAllowAll, InputPrivacyValueAllowContacts
from tests.client import TestClient

CHECK_PHONE_NUMBER = "123456789"


async def _set_usernames(clients: list[TestClient], prefix: str = "client", resolve: bool = False) -> None:
    for num, client in enumerate(clients, start=1):
        username = f"{prefix}{num}"
        await client.set_username(username)
        if not resolve:
            continue
        for other_client in clients:
            if other_client == client:
                continue
            await other_client.resolve_peer(username)


@pytest.mark.asyncio
async def test_check_privacy_allow_all() -> None:
    async with TestClient(phone_number=CHECK_PHONE_NUMBER) as client1, TestClient(phone_number="123456780") as client2:
        await _set_usernames([client1, client2])

        await client1.set_privacy(
            key=InputPrivacyKeyPhoneNumber(),
            rules=[
                InputPrivacyValueAllowAll(),
            ]
        )

        user11 = await client1.get_users("client1")
        assert user11.phone_number == CHECK_PHONE_NUMBER

        user12 = await client2.get_users("client1")
        assert user12.phone_number == CHECK_PHONE_NUMBER


@pytest.mark.asyncio
async def test_check_privacy_allow_contacts() -> None:
    async with (
        TestClient(phone_number=CHECK_PHONE_NUMBER) as client1,
        TestClient(phone_number="123456780") as client2,
        TestClient(phone_number="123456781") as client3,
    ):
        await _set_usernames([client1, client2, client3])

        await client1.set_privacy(
            key=InputPrivacyKeyPhoneNumber(),
            rules=[
                InputPrivacyValueDisallowAll(),
                InputPrivacyValueAllowContacts(),
            ]
        )

        await client1.add_contact("client3", "idk")

        user11 = await client1.get_users("client1")
        assert user11.phone_number == CHECK_PHONE_NUMBER

        user12 = await client2.get_users("client1")
        assert user12.phone_number is None

        user13 = await client3.get_users("client1")
        assert user13.phone_number == CHECK_PHONE_NUMBER


@pytest.mark.asyncio
async def test_check_privacy_disallow_all() -> None:
    async with TestClient(phone_number=CHECK_PHONE_NUMBER) as client1, TestClient(phone_number="123456780") as client2:
        await _set_usernames([client1, client2])

        await client1.set_privacy(
            key=InputPrivacyKeyPhoneNumber(),
            rules=[
                InputPrivacyValueDisallowAll(),
            ]
        )

        user11 = await client1.get_users("client1")
        assert user11.phone_number == CHECK_PHONE_NUMBER

        user12 = await client2.get_users("client1")
        assert user12.phone_number is None


@pytest.mark.asyncio
async def test_check_privacy_allow_all_disallow_user() -> None:
    async with (
        TestClient(phone_number=CHECK_PHONE_NUMBER) as client1,
        TestClient(phone_number="123456780") as client2,
        TestClient(phone_number="123456781") as client3,
    ):
        await _set_usernames([client1, client2, client3])

        await client1.set_privacy(
            key=InputPrivacyKeyPhoneNumber(),
            rules=[
                InputPrivacyValueAllowAll(),
                InputPrivacyValueDisallowUsers(users=[
                    await client1.resolve_peer("client3")
                ]),
            ]
        )

        user11 = await client1.get_users("client1")
        assert user11.phone_number == CHECK_PHONE_NUMBER

        user12 = await client2.get_users("client1")
        assert user12.phone_number == CHECK_PHONE_NUMBER

        user13 = await client3.get_users("client1")
        assert user13.phone_number is None


@pytest.mark.asyncio
async def test_check_privacy_disallow_all_allow_user() -> None:
    async with (
        TestClient(phone_number=CHECK_PHONE_NUMBER) as client1,
        TestClient(phone_number="123456780") as client2,
        TestClient(phone_number="123456781") as client3,
    ):
        await _set_usernames([client1, client2, client3])

        await client1.set_privacy(
            key=InputPrivacyKeyPhoneNumber(),
            rules=[
                InputPrivacyValueDisallowAll(),
                InputPrivacyValueAllowUsers(users=[
                    await client1.resolve_peer("client3")
                ]),
            ]
        )

        user11 = await client1.get_users("client1")
        assert user11.phone_number == CHECK_PHONE_NUMBER

        user12 = await client2.get_users("client1")
        assert user12.phone_number is None

        user13 = await client3.get_users("client1")
        assert user13.phone_number == CHECK_PHONE_NUMBER


@pytest.mark.asyncio
async def test_check_privacy_allow_contacts_disallow_user() -> None:
    async with (
        TestClient(phone_number=CHECK_PHONE_NUMBER) as client1,
        TestClient(phone_number="123456780") as client2,
        TestClient(phone_number="123456781") as client3,
        TestClient(phone_number="123456782") as client4,
    ):
        await _set_usernames([client1, client2, client3, client4])

        await client1.set_privacy(
            key=InputPrivacyKeyPhoneNumber(),
            rules=[
                InputPrivacyValueDisallowAll(),
                InputPrivacyValueAllowContacts(),
                InputPrivacyValueDisallowUsers(users=[
                    await client1.resolve_peer("client3")
                ]),
            ]
        )

        await client1.add_contact("client3", "idk3")
        await client1.add_contact("client4", "idk4")

        user11 = await client1.get_users("client1")
        assert user11.phone_number == CHECK_PHONE_NUMBER

        user12 = await client2.get_users("client1")
        assert user12.phone_number is None

        user13 = await client3.get_users("client1")
        assert user13.phone_number is None

        user14 = await client4.get_users("client1")
        assert user14.phone_number == CHECK_PHONE_NUMBER
