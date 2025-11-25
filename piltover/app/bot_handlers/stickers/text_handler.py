from io import BytesIO

from loguru import logger
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.stickers.utils import send_bot_message
from piltover.app.handlers.stickers import validate_png_webp, check_stickerset_short_name, make_sticker_from_file
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import StickersBotState, MediaType, StickerSetType
from piltover.db.models import Peer, Message, Stickerset, File, InstalledStickerset
from piltover.db.models.stickers_state import StickersBotUserState
from piltover.exceptions import ErrorRpc
from piltover.tl.functions.stickers import CheckShortName
from piltover.tl.types.internal_stickersbot import StickersStateNewpack, NewpackInputSticker
from piltover.utils.emoji import purely_emoji

__newpack_send_sticker = """
Alright! Now send me the sticker. The image file should be in PNG or WEBP format with a transparent layer and must fit into a 512x512 square (one of the sides must be 512px and the other 512px or less).

I recommend using Telegram for Web/Desktop when uploading stickers.
""".strip()
__newpack_invalid_name = "Sorry, this title is unacceptable."
__newpack_invalid_file = "Please send me your sticker image as a file."
__newpack_send_emoji = """
Thanks! Now send me an emoji that corresponds to your first sticker.

You can list several emoji in one message, but I recommend using no more than two per sticker.
""".strip()
__newpack_sticker_added = """
Congratulations. Stickers in the set: {num}. To add another sticker, send me the next sticker as a .PNG or .WEBP file.

When you're done, simply send the /publish command.
""".strip()
__text_send_shortname = """
Please provide a short name for your set. I'll use it to create a link that you can share with friends and followers.

For example, this set has the short name 'Animals': https://telegram.me/addstickers/Animals
""".strip()
__text_shortname_taken = "Sorry, this short name is already taken."
__text_shortname_invalid = "Sorry, this short name is unacceptable."
__text_published = """
Kaboom! I've just published your sticker set. Here's your link: https://t.me/addstickers/{short_name}

You can share it with other Telegram users — they'll be able to add your stickers to their sticker panel by following the link. Just make sure they're using an up to date version of the app.
""".strip()


async def stickers_text_message_handler(peer: Peer, message: Message) -> Message | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None:
        return None

    if state.state is StickersBotState.NEWPACK_WAIT_NAME:
        pack_name = message.message
        if len(pack_name) > 64:
            return await send_bot_message(peer, __newpack_invalid_name)

        await state.update_state(
            StickersBotState.NEWPACK_WAIT_IMAGE,
            StickersStateNewpack(name=pack_name, stickers=[]).serialize(),
        )

        return await send_bot_message(peer, __newpack_send_sticker)

    if state.state is StickersBotState.NEWPACK_WAIT_IMAGE:
        if message.media is None:
            return await send_bot_message(peer, __newpack_invalid_file)
        if message.media.type is not MediaType.DOCUMENT:
            return await send_bot_message(peer, __newpack_invalid_file)

        try:
            await validate_png_webp(message.media.file)
        except ErrorRpc:
            return await send_bot_message(peer, __newpack_invalid_file)

        if message.media.file.needs_save:
            await message.media.file.save(update_fields=["width", "height"])

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        state_data.stickers.append(NewpackInputSticker(file_id=message.media.file.id, emoji=""))

        await state.update_state(
            StickersBotState.NEWPACK_WAIT_EMOJI,
            state_data.serialize(),
        )

        return await send_bot_message(peer, __newpack_send_emoji)

    if state.state is StickersBotState.NEWPACK_WAIT_EMOJI:
        emoji = message.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, "Send emoji")  # TODO: correct text

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        state_data.stickers[-1].emoji = emoji

        await state.update_state(
            StickersBotState.NEWPACK_WAIT_IMAGE,
            state_data.serialize(),
        )

        return await send_bot_message(peer, __newpack_sticker_added.format(num=len(state_data.stickers)))

    if state.state is StickersBotState.NEWPACK_WAIT_ICON:
        await state.update_state(StickersBotState.NEWPACK_WAIT_SHORT_NAME, None)
        return await send_bot_message(peer, __text_send_shortname)

    if state.state is StickersBotState.NEWPACK_WAIT_SHORT_NAME:
        short_name = message.message.strip()

        try:
            await check_stickerset_short_name(CheckShortName(short_name=short_name))
        except ErrorRpc as e:
            if e.error_message == "SHORT_NAME_OCCUPIED":
                return await send_bot_message(peer, __text_shortname_taken)
            return await send_bot_message(peer, __text_shortname_invalid)

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))

        async with in_transaction():
            stickerset = await Stickerset.create(
                title=state_data.name,
                short_name=short_name,
                type=StickerSetType.STATIC,
                owner=peer.owner,
            )

            files = {
                file.id: file
                for file in await File.filter(id__in=[sticker.file_id for sticker in state_data.stickers])
            }

            files_to_create = []
            for idx, input_sticker in enumerate(state_data.stickers):
                if not input_sticker.emoji:
                    continue
                file = files[input_sticker.file_id]
                files_to_create.append(
                    await make_sticker_from_file(file, stickerset, idx, input_sticker.emoji, False, None, False)
                )

            await File.bulk_create(files_to_create)

            stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
            await stickerset.save(update_fields=["owner_id", "hash"])

            await InstalledStickerset.create(set=stickerset, user=peer.owner)

            await state.delete()

        await upd.new_stickerset(peer.owner, stickerset)
        return await send_bot_message(peer, __text_published.format(short_name=short_name))
