import pytest
from pyrogram.raw.functions.messages import UpdateDialogFilter, GetDialogFilters, UpdateDialogFiltersOrder
from pyrogram.raw.types import DialogFilter, DialogFilterDefault, UpdateDialogFilter as UpdateDialogFilter_, \
    UpdateDialogFilterOrder

from tests.conftest import TestClient


@pytest.mark.asyncio
async def test_get_dialog_filters_empty() -> None:
    async with TestClient(phone_number="123456789") as client:
        resp: list[DialogFilter] = await client.invoke(GetDialogFilters())
        assert len(resp) == 0


@pytest.mark.asyncio
async def test_create_delete_dialog_filter() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateDialogFilter_):
            assert await client.invoke(UpdateDialogFilter(
                id=2,
                filter=DialogFilter(
                    id=2,
                    title="test folder",
                    pinned_peers=[],
                    include_peers=[],
                    exclude_peers=[],
                    groups=True,
                ),
            ))

        resp: list[DialogFilter | DialogFilterDefault] = await client.invoke(GetDialogFilters())
        assert len(resp) == 2
        assert isinstance(resp[0], DialogFilterDefault)
        assert isinstance(resp[1], DialogFilter)
        assert resp[1].id == 2
        assert resp[1].title == "test folder"

        async with client.expect_updates_m(UpdateDialogFilter_):
            assert await client.invoke(UpdateDialogFilter(
                id=2,
                filter=None,
            ))

        resp: list[DialogFilter | DialogFilterDefault] = await client.invoke(GetDialogFilters())
        assert len(resp) == 0


@pytest.mark.asyncio
async def test_update_dialog_filter() -> None:
    async with TestClient(phone_number="123456789") as client:
        async with client.expect_updates_m(UpdateDialogFilter_):
            assert await client.invoke(UpdateDialogFilter(
                id=2,
                filter=DialogFilter(
                    id=2,
                    title="test folder",
                    pinned_peers=[],
                    include_peers=[],
                    exclude_peers=[],
                    groups=True,
                ),
            ))

        resp: list[DialogFilter | DialogFilterDefault] = await client.invoke(GetDialogFilters())
        assert len(resp) == 2
        assert isinstance(resp[0], DialogFilterDefault)
        assert isinstance(resp[1], DialogFilter)
        assert resp[1].id == 2
        assert resp[1].title == "test folder"
        assert resp[1].groups
        assert not resp[1].contacts

        async with client.expect_updates_m(UpdateDialogFilter_):
            assert await client.invoke(UpdateDialogFilter(
                id=2,
                filter=DialogFilter(
                    id=2,
                    title="folder 1",
                    pinned_peers=[],
                    include_peers=[],
                    exclude_peers=[],
                    contacts=True,
                ),
            ))

        resp: list[DialogFilter | DialogFilterDefault] = await client.invoke(GetDialogFilters())
        assert len(resp) == 2
        assert isinstance(resp[0], DialogFilterDefault)
        assert isinstance(resp[1], DialogFilter)
        assert resp[1].id == 2
        assert resp[1].title == "folder 1"
        assert not resp[1].groups
        assert resp[1].contacts


@pytest.mark.asyncio
async def test_update_dialog_filters_order() -> None:
    async with TestClient(phone_number="123456789") as client:
        for folder_id in (2, 3, 4):
            async with client.expect_updates_m(UpdateDialogFilter_):
                assert await client.invoke(UpdateDialogFilter(
                    id=folder_id,
                    filter=DialogFilter(
                        id=folder_id,
                        title=f"folder {folder_id}",
                        pinned_peers=[],
                        include_peers=[],
                        exclude_peers=[],
                        groups=True,
                    ),
                ))

        resp: list[DialogFilter | DialogFilterDefault] = await client.invoke(GetDialogFilters())
        assert len(resp) == 4
        assert isinstance(resp[0], DialogFilterDefault)
        assert isinstance(resp[1], DialogFilter)
        assert isinstance(resp[2], DialogFilter)
        assert isinstance(resp[3], DialogFilter)
        assert resp[1].id == 2
        assert resp[2].id == 3
        assert resp[3].id == 4

        async with client.expect_updates_m(UpdateDialogFilterOrder):
            assert await client.invoke(UpdateDialogFiltersOrder(order=[2, 4, 3, 0]))

        resp: list[DialogFilter | DialogFilterDefault] = await client.invoke(GetDialogFilters())
        assert len(resp) == 4
        assert isinstance(resp[0], DialogFilterDefault)
        assert isinstance(resp[1], DialogFilter)
        assert isinstance(resp[2], DialogFilter)
        assert isinstance(resp[3], DialogFilter)
        assert resp[1].id == 2
        assert resp[2].id == 4
        assert resp[3].id == 3
