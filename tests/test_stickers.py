import os
from contextlib import AsyncExitStack
from io import BytesIO
from typing import cast

import pytest
from PIL import Image
from fastrand import xorshift128plus_bytes
from pyrogram.errors import StickerPngDimensions, StickerPngNopng, StickerFileInvalid
from pyrogram.file_id import FileId, FileType
from pyrogram.raw.functions.messages import UploadMedia, GetAllStickers
from pyrogram.raw.functions.stickers import CheckShortName, CreateStickerSet
from pyrogram.errors.exceptions.bad_request_400 import BadRequest, PackShortNameOccupied
from pyrogram.raw.types import InputStickerSetItem, InputPeerSelf, InputMediaUploadedDocument, DocumentAttributeSticker, \
    InputStickerSetEmpty, Document, InputDocument, InputUserSelf, StickerSet, InputPeerUser
from pyrogram.raw.types.messages import StickerSet as MessagesStickerSet

from tests.client import TestClient
from tests.conftest import ClientFactory
from tests.utils import color_is_near

PHOTO_COLOR = (128, 128, 0)


@pytest.mark.asyncio
async def test_check_stickerset_short_name_unoccupied(exit_stack: AsyncExitStack) -> None:
    await exit_stack.enter_async_context(client := TestClient(phone_number="123456789"))
    assert await client.invoke(CheckShortName(short_name="test_sticker_set"))


@pytest.mark.asyncio
async def test_check_stickerset_short_name_invalid(exit_stack: AsyncExitStack) -> None:
    await exit_stack.enter_async_context(client := TestClient(phone_number="123456789"))
    # Using BadRequest and match because Pyrogram does not have SHORT_NAME_INVALID
    for invalid_name in (
        "_test_sticker_set",
        "1test_sticker_set",
        "test__sticker_set",
        "test_sticker_set" * 8,
    ):
        with pytest.raises(BadRequest, match="SHORT_NAME_INVALID"):
            await client.invoke(CheckShortName(short_name=invalid_name))


async def _make_input_stickerset_item(client: TestClient, file: BytesIO, emoji: str) -> InputStickerSetItem:
    input_file = await client.save_file(file)
    media = await client.invoke(UploadMedia(
        peer=InputPeerSelf(),
        media=InputMediaUploadedDocument(
            file=input_file,
            force_file=True,
            mime_type="image/png",
            attributes=[
                DocumentAttributeSticker(
                    alt=emoji,
                    stickerset=InputStickerSetEmpty(),
                )
            ]
        ),
    ))

    doc = cast(Document, media.document)
    return InputStickerSetItem(
        document=InputDocument(
            id=doc.id,
            access_hash=doc.access_hash,
            file_reference=doc.file_reference,
        ),
        emoji=emoji,
    )


@pytest.mark.asyncio
async def test_create_stickerset(exit_stack: AsyncExitStack) -> None:
    await exit_stack.enter_async_context(client := TestClient(phone_number="123456789"))

    sticker = Image.new(mode="RGB", size=(512, 512), color=PHOTO_COLOR)
    sticker_file = BytesIO()
    setattr(sticker_file, "name", "sticker.png")
    sticker.save(sticker_file, format="PNG")

    sticker = await _make_input_stickerset_item(client, sticker_file, "👍")
    stickerset: MessagesStickerSet = await client.invoke(CreateStickerSet(
        user_id=InputUserSelf(),
        title="Test stickerset",
        short_name="test_stickerset_idk",
        stickers=[sticker],
    ))

    assert isinstance(stickerset, MessagesStickerSet)
    actual_set = cast(StickerSet, stickerset.set)

    assert len(stickerset.documents) == 1
    assert not actual_set.emojis
    assert not actual_set.masks
    assert actual_set.title == "Test stickerset"
    assert actual_set.short_name == "test_stickerset_idk"

    doc = cast(Document, stickerset.documents[0])
    file_id = FileId(
        file_type=FileType.STICKER,
        dc_id=doc.dc_id,
        file_reference=doc.file_reference,
        media_id=doc.id,
        access_hash=doc.access_hash,
        sticker_set_id=actual_set.id,
        sticker_set_access_hash=actual_set.access_hash,
    )

    downloaded_photo_file = await client.download_media(file_id.encode(), in_memory=True)
    downloaded_photo_file.seek(0)
    downloaded_photo = Image.open(downloaded_photo_file)
    assert color_is_near(PHOTO_COLOR, cast(tuple[int, int, int], downloaded_photo.getpixel((0, 0))))


@pytest.mark.asyncio
async def test_create_stickerset_name_occupied(exit_stack: AsyncExitStack) -> None:
    await exit_stack.enter_async_context(client := TestClient(phone_number="123456789"))

    sticker = Image.new(mode="RGB", size=(512, 512), color=PHOTO_COLOR)
    sticker_file = BytesIO()
    setattr(sticker_file, "name", "sticker.png")
    sticker.save(sticker_file, format="PNG")

    sticker = await _make_input_stickerset_item(client, sticker_file, "👍")
    stickerset: MessagesStickerSet = await client.invoke(CreateStickerSet(
        user_id=InputUserSelf(),
        title="Test stickerset",
        short_name="test_stickerset_idk",
        stickers=[sticker],
    ))
    assert isinstance(stickerset, MessagesStickerSet)

    with pytest.raises(PackShortNameOccupied):
        await client.invoke(CreateStickerSet(
            user_id=InputUserSelf(),
            title="Test stickerset",
            short_name="test_stickerset_idk",
            stickers=[sticker],
        ))


@pytest.mark.asyncio
async def test_create_stickerset_invalid_png_dims(exit_stack: AsyncExitStack) -> None:
    await exit_stack.enter_async_context(client := TestClient(phone_number="123456789"))

    for dims in (
            (256, 256),
            (512, 513),
            (513, 512),
    ):
        sticker = Image.new(mode="RGB", size=dims, color=PHOTO_COLOR)
        sticker_file = BytesIO()
        setattr(sticker_file, "name", "sticker.png")
        sticker.save(sticker_file, format="PNG")

        sticker = await _make_input_stickerset_item(client, sticker_file, "👍")
        with pytest.raises(StickerPngDimensions):
            await client.invoke(CreateStickerSet(
                user_id=InputUserSelf(),
                title="Test stickerset",
                short_name="test_stickerset_idk",
                stickers=[sticker],
            ))


@pytest.mark.asyncio
async def test_create_stickerset_not_png(exit_stack: AsyncExitStack) -> None:
    await exit_stack.enter_async_context(client := TestClient(phone_number="123456789"))

    sticker_file = BytesIO(xorshift128plus_bytes(1024 * 32))
    setattr(sticker_file, "name", "sticker.png")

    sticker = await _make_input_stickerset_item(client, sticker_file, "👍")
    with pytest.raises((StickerPngNopng, StickerFileInvalid)):
        await client.invoke(CreateStickerSet(
            user_id=InputUserSelf(),
            title="Test stickerset",
            short_name="test_stickerset_idk",
            stickers=[sticker],
        ))


@pytest.mark.asyncio
async def test_create_stickerset_via_bot(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    stickers_peer = await client.resolve_peer("stickers")
    assert isinstance(stickers_peer, InputPeerUser)
    stickersbot_id = stickers_peer.user_id

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/newpack", 1.5)
    assert "A new sticker set" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "test stickerpack", 1.5)
    assert "Now send me the sticker" in message.message

    sticker = client.make_image((512, 512), PHOTO_COLOR, "sticker.png")
    waiter = client.wait_for_message_from_user(stickers_peer.user_id, None, 3)
    await client.send_document("stickers", sticker, force_document=True)
    message = await waiter
    assert "Now send me an emoji" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "\U0001f408", 1.5)
    assert "Stickers in the set: 1." in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/publish", 1.5)
    assert "You can set an icon for your sticker set." in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/skip", 1.5)
    assert "Please provide a short name for your set." in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "test_stickerset_idk", 1.5)
    assert "addstickers/test_stickerset_idk" in message.message

    stickersets = await client.invoke(GetAllStickers(hash=0))
    assert len(stickersets.sets) == 1
    assert stickersets.sets[0].title == "test stickerpack"
    assert stickersets.sets[0].short_name == "test_stickerset_idk"
    assert stickersets.sets[0].count == 1


@pytest.mark.asyncio
async def test_create_stickerset_via_bot_invalid_name(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    stickers_peer = await client.resolve_peer("stickers")
    assert isinstance(stickers_peer, InputPeerUser)
    stickersbot_id = stickers_peer.user_id

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/newpack", 1.5)
    assert "A new sticker set" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "test stickerpack"*5, 1.5)
    assert "title is unacceptable." in message.message


@pytest.mark.asyncio
async def test_create_stickerset_via_bot_invalid_name_not_text(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    stickers_peer = await client.resolve_peer("stickers")
    assert isinstance(stickers_peer, InputPeerUser)
    stickersbot_id = stickers_peer.user_id

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/newpack", 1.5)
    assert "A new sticker set" in message.message

    sticker = client.make_image((512, 512), PHOTO_COLOR, "sticker.png")
    waiter = client.wait_for_message_from_user(stickers_peer.user_id, None, 3)
    await client.send_document("stickers", sticker, force_document=True)
    message = await waiter
    assert "title is unacceptable." in message.message


@pytest.mark.asyncio
async def test_create_stickerset_via_bot_sticker_no_media(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    stickers_peer = await client.resolve_peer("stickers")
    assert isinstance(stickers_peer, InputPeerUser)
    stickersbot_id = stickers_peer.user_id

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/newpack", 1.5)
    assert "A new sticker set" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "test stickerpack", 1.5)
    assert "Now send me the sticker" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "asdqwe", 1.5)
    assert "Please send me your sticker image as a file." in message.message


@pytest.mark.asyncio
async def test_create_stickerset_via_bot_sticker_not_image(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    stickers_peer = await client.resolve_peer("stickers")
    assert isinstance(stickers_peer, InputPeerUser)
    stickersbot_id = stickers_peer.user_id

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/newpack", 1.5)
    assert "A new sticker set" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "test stickerpack", 1.5)
    assert "Now send me the sticker" in message.message

    file = BytesIO(os.urandom(32 * 1024))
    file.name = "idk.png"
    waiter = client.wait_for_message_from_user(stickers_peer.user_id, None, 3)
    await client.send_document("stickers", file, force_document=True)
    message = await waiter
    assert "Please send me your sticker image as a file." in message.message


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (512, 513),
        (511, 511),
    ],
    ids=[
        "height is too big",
        "width and height are too small",
    ],
)
@pytest.mark.asyncio
async def test_create_stickerset_via_bot_invalid_dims(client_with_auth: ClientFactory, width: int, height: int) -> None:
    client = await client_with_auth(run=True)

    stickers_peer = await client.resolve_peer("stickers")
    assert isinstance(stickers_peer, InputPeerUser)
    stickersbot_id = stickers_peer.user_id

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "/newpack", 1.5)
    assert "A new sticker set" in message.message

    _, message = await client.send_message_to_user_and_get_reply(stickersbot_id, "test stickerpack", 1.5)
    assert "Now send me the sticker" in message.message

    sticker = client.make_image((width, height), PHOTO_COLOR, "sticker.png")
    waiter = client.wait_for_message_from_user(stickers_peer.user_id, None, 3)
    await client.send_document("stickers", sticker, force_document=True)
    message = await waiter
    assert "Please send me your sticker image as a file." in message.message
