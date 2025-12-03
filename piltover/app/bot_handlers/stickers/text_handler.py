from io import BytesIO

from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.stickers.utils import send_bot_message, get_stickerset_selection_keyboard
from piltover.app.handlers.stickers import validate_png_webp, check_stickerset_short_name, make_sticker_from_file
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import StickersBotState, MediaType, StickerSetType, FileType
from piltover.db.models import Peer, Message, Stickerset, File, InstalledStickerset
from piltover.db.models.stickers_state import StickersBotUserState
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.tl import ReplyKeyboardMarkup
from piltover.tl.functions.stickers import CheckShortName
from piltover.tl.types.internal_stickersbot import StickersStateNewpack, NewpackInputSticker, StickersStateAddsticker, \
    StickersStateEditsticker, StickersStateDelpack, StickersStateRenamepack, StickersStateReplacesticker
from piltover.utils.emoji import purely_emoji

DELPACK_CONFIRMATION = "Yes, I am totally sure."

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
__newpack_send_emoji_invalid = "Please send us an emoji that best describes your sticker."
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
__addsticker_shortname_invalid = "Invalid set selected."
__addsticker_sticker_added = """
There we go. I've added your sticker to the set, it will become available to all Telegram users within an hour. 

To add another sticker, send me the next sticker.
When you're done, simply send the /done command.
""".strip()
__editsticker_send_sticker = "Please send me the sticker you want to edit."
__editsticker_not_owner = "Sorry, I can't do this. Looks like you are not the owner of the relevant set."
__editsticker_send_emoji = """
Current emoji: {current}
Please send me some new emoji that correspond to this sticker.

You can list several emoji in one message, but I recommend using no more than two per sticker. Send /cancel to keep the current emoji.
""".strip()
__editsticker_send_sticker_invalid = "Please send me the sticker."
__editsticker_saved = "I edited your sticker. Hope you like it better this way."
__delpack_confirm = f"""
OK, you selected the set {{name}}. Are you sure?

Send `{DELPACK_CONFIRMATION}` to confirm you really want to delete this set.
""".strip()
__delpack_confirm_invalid = f"""
Please enter the confirmation text exactly like this:
`{DELPACK_CONFIRMATION}`

Type /cancel to cancel the operation.
""".strip()
__delpack_deleted = "Done! The sticker set is gone."
__renamepack_send_name = """
OK, you selected the set {name}.
Now choose a new name for your set.
""".strip()
__renamepack_renamed = "Your sticker set has a new name now. Enjoy!"
__replacesticker_send_sticker = "Please send me the sticker you want to replace."
__replacesticker_replaced = """
I replaced your sticker. Hope you like it better this way. Users should be able see the new sticker within an hour or so.

Please send me the next sticker you want to replace or /done if you are done.
""".strip()


async def _invalid_set_selected(peer: Peer) -> Message:
    keyboard_rows = await get_stickerset_selection_keyboard(peer.owner)
    keyboard = ReplyKeyboardMarkup(rows=keyboard_rows, single_use=True) if keyboard_rows else None
    return await send_bot_message(peer, __addsticker_shortname_invalid, keyboard)


async def stickers_text_message_handler(peer: Peer, message: Message) -> Message | None:
    state = await StickersBotUserState.get_or_none(user=peer.owner)
    if state is None:
        return None

    if state.state is StickersBotState.NEWPACK_WAIT_NAME:
        pack_name = message.message
        if not pack_name or len(pack_name) > 64:
            return await send_bot_message(peer, __newpack_invalid_name)

        await state.update_state(
            StickersBotState.NEWPACK_WAIT_IMAGE,
            StickersStateNewpack(name=pack_name, stickers=[]).serialize(),
        )

        return await send_bot_message(peer, __newpack_send_sticker)

    if state.state in (
            StickersBotState.NEWPACK_WAIT_IMAGE, StickersBotState.ADDSTICKER_WAIT_IMAGE,
            StickersBotState.REPLACESTICKER_WAIT_IMAGE,
    ):
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

        if state.state is StickersBotState.NEWPACK_WAIT_IMAGE:
            state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
            state_data.stickers.append(NewpackInputSticker(file_id=message.media.file.id, emoji=""))
            await state.update_state(
                StickersBotState.NEWPACK_WAIT_EMOJI,
                state_data.serialize(),
            )
        elif state.state is StickersBotState.ADDSTICKER_WAIT_IMAGE:
            state_data = StickersStateAddsticker.deserialize(BytesIO(state.data))
            state_data.file_id = message.media.file.id
            await state.update_state(
                StickersBotState.ADDSTICKER_WAIT_EMOJI,
                state_data.serialize(),
            )
        elif state.state is StickersBotState.REPLACESTICKER_WAIT_IMAGE:
            state_data = StickersStateReplacesticker.deserialize(BytesIO(state.data))
            async with in_transaction:
                old_sticker = await File.get(
                    id=state_data.file_id, stickerset__owner=peer.owner,
                ).select_related("stickerset")
                stickerset = old_sticker.stickerset
                old_sticker.stickerset = None
                old_sticker.sticker_pos = None
                await old_sticker.save(update_fields=["stickerset_id", "sticker_pos"])

                await make_sticker_from_file(
                    message.media.file, stickerset, old_sticker.sticker_pos, old_sticker.sticker_alt,
                    old_sticker.sticker_is_mask, old_sticker.sticker_mask_coords,
                )
                stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
                await stickerset.save(update_fields=["hash"])

            await state.update_state(
                StickersBotState.REPLACESTICKER_WAIT_STICKER,
                StickersStateReplacesticker(set_id=stickerset.id).serialize(),
            )

            return await send_bot_message(peer, __replacesticker_replaced)
        else:
            raise Unreachable

        return await send_bot_message(peer, __newpack_send_emoji)

    if state.state in (
            StickersBotState.NEWPACK_WAIT_EMOJI, StickersBotState.ADDSTICKER_WAIT_EMOJI,
            StickersBotState.EDITSTICKER_WAIT_EMOJI,
    ):
        emoji = message.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, __newpack_send_emoji_invalid)

        if state.state is StickersBotState.NEWPACK_WAIT_EMOJI:
            state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
            state_data.stickers[-1].emoji = emoji
            await state.update_state(
                StickersBotState.NEWPACK_WAIT_IMAGE,
                state_data.serialize(),
            )
            return await send_bot_message(peer, __newpack_sticker_added.format(num=len(state_data.stickers)))
        elif state.state is StickersBotState.ADDSTICKER_WAIT_EMOJI:
            state_data = StickersStateAddsticker.deserialize(BytesIO(state.data))

            stickerset = await Stickerset.get_or_none(owner=peer.owner, id=state_data.set_id)
            if stickerset is None:
                return await send_bot_message(peer, "This stickerset does not exist.")
            file = await File.get_or_none(id=state_data.file_id)
            if file is None:
                return await send_bot_message(peer, "This file does not exist.")

            count = await File.filter(stickerset=stickerset).count()

            await make_sticker_from_file(file, stickerset, count, emoji, False, None)
            stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
            await stickerset.save(update_fields=["hash"])

            await state.update_state(
                StickersBotState.ADDSTICKER_WAIT_IMAGE,
                StickersStateAddsticker(set_id=stickerset.id, file_id=0).serialize(),
            )

            return await send_bot_message(peer, __addsticker_sticker_added)
        elif state.state is StickersBotState.EDITSTICKER_WAIT_EMOJI:
            state_data = StickersStateEditsticker.deserialize(BytesIO(state.data))
            file = await File.get_or_none(id=state_data.file_id)
            if file is None:
                return await send_bot_message(peer, "This file does not exist (???).")
            file.sticker_alt = emoji
            await file.save(update_fields=["sticker_alt"])
            await state.delete()
            return await send_bot_message(peer, __editsticker_saved)
        else:
            raise Unreachable

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

    if state.state in (
            StickersBotState.ADDSTICKER_WAIT_PACK, StickersBotState.EDITSTICKER_WAIT_PACK_OR_STICKER,
            StickersBotState.DELPACK_WAIT_PACK, StickersBotState.RENAMEPACK_WAIT_PACK,
            StickersBotState.REPLACESTICKER_WAIT_PACK_OR_STICKER,
    ):
        allow_sticker = state.state in (
            StickersBotState.EDITSTICKER_WAIT_PACK_OR_STICKER,
            StickersBotState.REPLACESTICKER_WAIT_PACK_OR_STICKER,
        )
        if allow_sticker and message.media and message.media.file and message.media.file.type is FileType.DOCUMENT_STICKER:
            sticker = message.media.file
            if sticker.stickerset.owner_id != peer.owner_id:
                return await send_bot_message(peer, __editsticker_not_owner)
            if state.state is StickersBotState.EDITSTICKER_WAIT_PACK_OR_STICKER:
                await state.update_state(
                    StickersBotState.EDITSTICKER_WAIT_EMOJI,
                    StickersStateEditsticker(set_id=None, file_id=sticker.id).serialize(),
                )
                return await send_bot_message(peer, __editsticker_send_emoji.format(current=sticker.sticker_alt))
            elif state.state is StickersBotState.REPLACESTICKER_WAIT_PACK_OR_STICKER:
                await state.update_state(
                    StickersBotState.REPLACESTICKER_WAIT_IMAGE,
                    StickersStateReplacesticker(set_id=None, file_id=sticker.id).serialize(),
                )
                return await send_bot_message(peer, __editsticker_send_emoji.format(current=sticker.sticker_alt))
            else:
                raise Unreachable
        elif allow_sticker and message.media:
            return await _invalid_set_selected(peer)

        sel_short_name = message.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer)

        if state.state is StickersBotState.ADDSTICKER_WAIT_PACK:
            await state.update_state(
                StickersBotState.ADDSTICKER_WAIT_IMAGE,
                StickersStateAddsticker(set_id=stickerset.id, file_id=0).serialize(),
            )
            return await send_bot_message(peer, __newpack_send_sticker)
        elif state.state is StickersBotState.EDITSTICKER_WAIT_PACK_OR_STICKER:
            await state.update_state(
                StickersBotState.EDITSTICKER_WAIT_STICKER,
                StickersStateEditsticker(set_id=stickerset.id, file_id=None).serialize(),
            )
            return await send_bot_message(peer, __editsticker_send_sticker)
        elif state.state is StickersBotState.DELPACK_WAIT_PACK:
            await state.update_state(
                StickersBotState.DELPACK_WAIT_CONFIRM,
                StickersStateDelpack(set_id=stickerset.id).serialize(),
            )
            return await send_bot_message(peer, __delpack_confirm.format(name=stickerset.short_name))
        elif state.state is StickersBotState.RENAMEPACK_WAIT_PACK:
            await state.update_state(
                StickersBotState.RENAMEPACK_WAIT_NAME,
                StickersStateRenamepack(set_id=stickerset.id).serialize(),
            )
            return await send_bot_message(peer, __renamepack_send_name.format(name=stickerset.title))
        elif state.state is StickersBotState.REPLACESTICKER_WAIT_PACK_OR_STICKER:
            await state.update_state(
                StickersBotState.REPLACESTICKER_WAIT_STICKER,
                StickersStateEditsticker(set_id=stickerset.id, file_id=None).serialize(),
            )
            return await send_bot_message(peer, __replacesticker_send_sticker)
        else:
            raise Unreachable

    if state.state in (StickersBotState.EDITSTICKER_WAIT_STICKER, StickersBotState.REPLACESTICKER_WAIT_STICKER):
        if not message.media or not message.media.file or message.media.file.type is not FileType.DOCUMENT_STICKER:
            return await send_bot_message(peer, __editsticker_send_sticker_invalid)

        sticker = message.media.file
        if sticker.stickerset.owner_id != peer.owner_id:
            return await send_bot_message(peer, __editsticker_not_owner)

        if state.state is StickersBotState.EDITSTICKER_WAIT_STICKER:
            await state.update_state(
                StickersBotState.EDITSTICKER_WAIT_EMOJI,
                StickersStateEditsticker(set_id=None, file_id=sticker.id).serialize(),
            )
            return await send_bot_message(peer, __editsticker_send_emoji.format(current=sticker.sticker_alt))
        elif state.state is StickersBotState.REPLACESTICKER_WAIT_STICKER:
            await state.update_state(
                StickersBotState.REPLACESTICKER_WAIT_IMAGE,
                StickersStateEditsticker(set_id=None, file_id=sticker.id).serialize(),
            )
            return await send_bot_message(peer, __newpack_send_sticker)
        else:
            raise Unreachable

    if state.state is StickersBotState.DELPACK_WAIT_CONFIRM:
        if message.message != DELPACK_CONFIRMATION:
            return await send_bot_message(peer, __delpack_confirm_invalid)

        state_data = StickersStateDelpack.deserialize(BytesIO(state.data))
        stickerset = await Stickerset.get_or_none(id=state_data.set_id, owner=peer.owner)
        if stickerset is None:
            await state.delete()
            return await send_bot_message(peer, __addsticker_shortname_invalid)

        stickerset.deleted = True
        stickerset.owner = None
        stickerset.short_name = None
        await stickerset.save(update_fields=["deleted", "owner_id", "short_name"])

        return await send_bot_message(peer, __delpack_deleted)

    if state.state is StickersBotState.RENAMEPACK_WAIT_NAME:
        pack_name = message.message
        if not pack_name or len(pack_name) > 64:
            return await send_bot_message(peer, __newpack_invalid_name)

        state_data = StickersStateRenamepack.deserialize(BytesIO(state.data))
        stickerset = await Stickerset.get_or_none(id=state_data.set_id, owner=peer.owner)
        if stickerset is None:
            await state.delete()
            return await send_bot_message(peer, __addsticker_shortname_invalid)

        if pack_name != stickerset.title:
            stickerset.title = pack_name
            await stickerset.save(update_fields=["title"])

        await state.delete()

        return await send_bot_message(peer, __renamepack_renamed)
