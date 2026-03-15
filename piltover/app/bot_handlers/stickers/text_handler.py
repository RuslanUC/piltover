from __future__ import annotations

from io import BytesIO

from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.utils import send_bot_message, get_stickerset_selection_keyboard, \
    EMOJI_PACK_TYPES_KEYBOARD
from piltover.app.handlers.stickers import validate_png_webp, check_stickerset_short_name, make_sticker_from_file, \
    validate_webm
from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import StickersBotState, MediaType, StickerSetType, FileType
from piltover.db.models import Peer, Stickerset, File, InstalledStickerset, MessageRef, MessageContent, User
from piltover.db.models.stickers_state import StickersBotUserState
from piltover.exceptions import ErrorRpc
from piltover.tl import ReplyKeyboardMarkup, ReplyKeyboardHide
from piltover.tl.functions.stickers import CheckShortName
from piltover.tl.types.internal_stickersbot import StickersStateNewpack, NewpackInputSticker, StickersStateAddsticker, \
    StickersStateEditsticker, StickersStateDelpack, StickersStateRenamepack, StickersStateReplacesticker, \
    EmojiPackTypeStatic, StickersStateNewemojipack, StickersStateAddemoji
from piltover.utils.emoji import purely_emoji

DELPACK_CONFIRMATION = "Yes, I am totally sure."

_newpack_send_sticker = """
Alright! Now send me the sticker. The image file should be in PNG or WEBP format with a transparent layer and must fit into a 512x512 square (one of the sides must be 512px and the other 512px or less).

I recommend using Telegram for Web/Desktop when uploading stickers.
""".strip()
_newpack_invalid_name = "Sorry, this title is unacceptable."
_newpack_invalid_file = "Please send me your sticker image as a file."
_newpack_send_emoji = """
Thanks! Now send me an emoji that corresponds to your first sticker.

You can list several emoji in one message, but I recommend using no more than two per sticker.
""".strip()
_newpack_send_emoji_invalid = "Please send us an emoji that best describes your sticker."
_newpack_sticker_added = FormatableTextWithEntities("""
Congratulations. Stickers in the set: {num}. To add another sticker, send me the next sticker as a .PNG or .WEBP file.

When you're done, simply send the <c>/publish</c> command.
""".strip())
_text_send_shortname, _text_send_shortname_entities = FormatableTextWithEntities("""
Please provide a short name for your set. I'll use it to create a link that you can share with friends and followers.

For example, this set has the short name 'Animals': <a>https://telegram.me/addstickers/Animals</a>
""".strip()).format()
_text_shortname_taken = "Sorry, this short name is already taken."
_text_shortname_invalid = "Sorry, this short name is unacceptable."
_text_published = FormatableTextWithEntities("""
Kaboom! I've just published your sticker set. Here's your link: <a>https://t.me/addstickers/{short_name}</a>

You can share it with other Telegram users — they'll be able to add your stickers to their sticker panel by following the link. Just make sure they're using an up to date version of the app.
""".strip())
_addsticker_shortname_invalid = "Invalid set selected."
_addsticker_sticker_added, _addsticker_sticker_added_entities = FormatableTextWithEntities("""
There we go. I've added your sticker to the set, it will become available to all Telegram users within an hour. 

To add another sticker, send me the next sticker.
When you're done, simply send the <c>/done</c> command.
""".strip()).format()
_editsticker_send_sticker = "Please send me the sticker you want to edit."
_editsticker_not_owner = "Sorry, I can't do this. Looks like you are not the owner of the relevant set."
_editsticker_send_emoji = FormatableTextWithEntities("""
Current emoji: {current}
Please send me some new emoji that correspond to this sticker.

You can list several emoji in one message, but I recommend using no more than two per sticker. Send <c>/cancel</c> to keep the current emoji.
""".strip())
_editsticker_send_sticker_invalid = "Please send me the sticker."
_editsticker_saved = "I edited your sticker. Hope you like it better this way."
_delpack_confirm = FormatableTextWithEntities(f"""
OK, you selected the set {{name}}. Are you sure?

Send `{DELPACK_CONFIRMATION}` to confirm you really want to delete this set.
""".strip())
_delpack_confirm_invalid, _delpack_confirm_invalid_entities = FormatableTextWithEntities(f"""
Please enter the confirmation text exactly like this:
`{DELPACK_CONFIRMATION}`

Type <c>/cancel</c> to cancel the operation.
""".strip()).format()
_delpack_deleted = "Done! The sticker set is gone."
_renamepack_send_name = """
OK, you selected the set {name}.
Now choose a new name for your set.
""".strip()
_renamepack_renamed = "Your sticker set has a new name now. Enjoy!"
_replacesticker_send_sticker = "Please send me the sticker you want to replace."
_replacesticker_replaced, _replacesticker_replaced_entities = FormatableTextWithEntities("""
I replaced your sticker. Hope you like it better this way. Users should be able see the new sticker within an hour or so.

Please send me the next sticker you want to replace or <c>/done</c> if you are done.
""".strip()).format()
_newemojipack_invalid_type = "Please use buttons to choose the type of custom emoji set."
_newemojipack_type_not_supported = "This emoji pack type is not supported yet :(. Please choose \"Static\"."
_newemojipack_send_name, _newemojipack_send_name_entities = FormatableTextWithEntities("""
Yay! A new set of static emoji. 

Send <c>/adaptive</c> if you want all emoji in your pack to adapt to the user's current theme, like this pack (<a>https://t.me/addemoji/EmoticonEmoji</a>). Emoji will match the color of the text in messages and the accent color when used as a status.

When ready to upload, tell me the name of your set.
""".strip()).format()
_newemojipack_send_image = """
Alright! Now send me the custom emoji. The image file should be in PNG or WEBP format with a transparent layer and must be a square of exactly 100x100 pixels.

I recommend using Telegram Desktop when uploading emojis.
""".strip()
_newemojipack_send_emoji = """
Thanks!
Send me a replacement emoji that corresponds to your custom emoji.
You can list several emoji that describe your custom one, but I recommend using no more than two per emoji.
""".strip()
_newemojipack_sticker_added = FormatableTextWithEntities("""
Congratulations. Emoji in the set: {num}. 
To add another custom emoji, send me the next emoji as a .PNG or .WEBP file.

When you're done, simply send the <c>/publish</c> command.
""".strip())
_text_send_shortname_emoji, _text_send_shortname_emoji_entities = FormatableTextWithEntities("""
Please provide a short name for your emoji set. I'll use it to create a link that you can share with friends and followers.

For example, this set has the short name 'DuckEmoji': <a>https://telegram.me/addemoji/DuckEmoji</a>
""".strip()).format()
_text_published_emoji = FormatableTextWithEntities("""
Kaboom! I've just published your emoji set. Here's your link: <a>https://t.me/addemoji/{short_name}</a>

You can share it with other Telegram users — they'll be able to add your emoji to their emoji panel by following the link. 
Just make sure they're using an up to date version of the app. At the moment, only Telegram Premium subscribers can send custom emoji.
""".strip())
_newvideo_send_sticker, _newvideo_send_sticker_entities = FormatableTextWithEntities("""
Alright! Now send me the video sticker. The video file should be in .WEBM format, encoded with the VP9 codec (<a>https://core.telegram.org/stickers/webm-vp9-encoding</a>). See this guide (<a>https://core.telegram.org/stickers/webm-vp9-encoding</a>) for details.

I recommend using Telegram Desktop when uploading stickers.

Also this ffmpeg command can be used:
`ffmpeg -i pats-4x.webm -vf scale=512x512 -b:v 400k -r 30 -an -c:v libvpx-vp9 -pix_fmt yuva420p pats-sticker.webm -y`
""".strip()).format()
_newvideo_file_invalid, _newvideo_file_invalid_entities = FormatableTextWithEntities("""
File type is invalid. Please convert your video to the .WEBM format. See this guide (<a>https://core.telegram.org/stickers#video-sticker-requirements</a>) for details.
""".strip()).format()
_newvideo_send_emoji = """
Thanks! Now send me an emoji that corresponds to your video sticker.

You can list several emoji in one message, but I recommend using no more than two per sticker.
""".strip()
_newvideo_sticker_added = FormatableTextWithEntities("""
Congratulations. Stickers in the set: {num}. To add another video sticker, send me the next sticker as a .WEBM file.

When you're done, simply send the <c>/publish</c> command.
""".strip())


async def _invalid_set_selected(peer: Peer, emoji: bool | None) -> MessageRef:
    keyboard_rows = await get_stickerset_selection_keyboard(peer.owner, emoji)
    keyboard = ReplyKeyboardMarkup(rows=keyboard_rows, single_use=True) if keyboard_rows else None
    return await send_bot_message(peer, _addsticker_shortname_invalid, keyboard)


class Text(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)

        (
            self.text().set_send_message_func(send_bot_message)

            .when(state=StickersBotState.NEWPACK_WAIT_NAME).do(self._newpack_name)
            .when(state=StickersBotState.NEWVIDEO_WAIT_NAME).do(self._newvideo_name)
            .when(state=StickersBotState.RENAMEPACK_WAIT_NAME).do(self._renamepack_name)
            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_NAME).do(self._newemojipack_name)

            .when(state=StickersBotState.NEWPACK_WAIT_IMAGE).do(self._newpack_image)
            .when(state=StickersBotState.ADDSTICKER_WAIT_IMAGE).do(self._addsticker_image)
            .when(state=StickersBotState.REPLACESTICKER_WAIT_IMAGE).do(self._replacesticker_image)
            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_IMAGE).do(self._newemojipack_image)
            .when(state=StickersBotState.ADDEMOJI_WAIT_IMAGE).do(self._addemoji_image)

            .when(state=StickersBotState.NEWVIDEO_WAIT_VIDEO).do(self._newvideo_video)

            .when(state=StickersBotState.NEWPACK_WAIT_EMOJI).do(self._newpack_emoji)
            .when(state=StickersBotState.ADDSTICKER_WAIT_EMOJI).do(self._addsticker_emoji)
            .when(state=StickersBotState.EDITSTICKER_WAIT_EMOJI).do(self._editsticker_emoji)
            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_EMOJI).do(self._newemojipack_emoji)
            .when(state=StickersBotState.ADDEMOJI_WAIT_EMOJI).do(self._addemoji_emoji)
            .when(state=StickersBotState.NEWVIDEO_WAIT_EMOJI).do(self._newvideo_emoji)

            .when(state=StickersBotState.NEWPACK_WAIT_SHORT_NAME).do(self._newpack_short_name)
            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_SHORT_NAME).do(self._newemojipack_short_name)
            .when(state=StickersBotState.NEWVIDEO_WAIT_SHORT_NAME).do(self._newvideo_short_name)

            .when(state=StickersBotState.ADDSTICKER_WAIT_PACK).do(self._addsticker_pack)
            .when(state=StickersBotState.EDITSTICKER_WAIT_PACK_OR_STICKER).do(self._editsticker_pack_or_sticker)
            .when(state=StickersBotState.DELPACK_WAIT_PACK).do(self._delpack_pack)
            .when(state=StickersBotState.RENAMEPACK_WAIT_PACK).do(self._renamepack_pack)
            .when(state=StickersBotState.REPLACESTICKER_WAIT_PACK_OR_STICKER).do(self._replacesticker_pack_or_sticker)
            .when(state=StickersBotState.ADDEMOJI_WAIT_PACK).do(self._addemoji_pack)

            .when(state=StickersBotState.EDITSTICKER_WAIT_STICKER).do(self._editsticker_sticker)
            .when(state=StickersBotState.REPLACESTICKER_WAIT_STICKER).do(self._replacesticker_sticker)

            .when(state=StickersBotState.DELPACK_WAIT_CONFIRM).do(self._delpack_confirm)

            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_TYPE).do(self._newemojipack_type)

            .when(state=StickersBotState.NEWPACK_WAIT_ICON)
            .set_state(StickersBotState.NEWPACK_WAIT_SHORT_NAME)
            .respond(_text_send_shortname, _text_send_shortname_entities)
            .ok()

            .when(state=StickersBotState.NEWEMOJIPACK_WAIT_ICON)
            .set_state(StickersBotState.NEWEMOJIPACK_WAIT_SHORT_NAME)
            .respond(_text_send_shortname_emoji, _text_send_shortname_emoji_entities)
            .ok()

            .when(state=StickersBotState.NEWVIDEO_WAIT_ICON)
            .set_state(StickersBotState.NEWVIDEO_WAIT_SHORT_NAME)
            .respond(_text_send_shortname, _text_send_shortname_entities)
            .ok()

            .register()
        )

    @staticmethod
    async def _newpack_name(peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        pack_name = message.content.message
        if not pack_name or len(pack_name) > 64:
            return await send_bot_message(peer, _newpack_invalid_name)

        await state.update_state(
            StickersBotState.NEWPACK_WAIT_IMAGE,
            StickersStateNewpack(name=pack_name, stickers=[]).serialize(),
        )
        return await send_bot_message(peer, _newpack_send_sticker)

    @staticmethod
    async def _newvideo_name(peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        pack_name = message.content.message
        if not pack_name or len(pack_name) > 64:
            return await send_bot_message(peer, _newpack_invalid_name)

        await state.update_state(
            StickersBotState.NEWVIDEO_WAIT_VIDEO,
            StickersStateNewpack(name=pack_name, stickers=[]).serialize(),
        )
        return await send_bot_message(peer, _newvideo_send_sticker, entities=_newvideo_send_sticker_entities)

    @staticmethod
    async def _renamepack_name(peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        pack_name = message.content.message
        if not pack_name or len(pack_name) > 64:
            return await send_bot_message(peer, _newpack_invalid_name)

        state_data = StickersStateRenamepack.deserialize(BytesIO(state.data))
        stickerset = await Stickerset.get_or_none(id=state_data.set_id, owner=peer.owner)
        if stickerset is None:
            await state.delete()
            return await send_bot_message(peer, _addsticker_shortname_invalid)

        if pack_name != stickerset.title:
            stickerset.title = pack_name
            await stickerset.save(update_fields=["title"])

        await state.delete()

        return await send_bot_message(peer, _renamepack_renamed)

    @staticmethod
    async def _newemojipack_name(peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        pack_name = message.content.message
        if not pack_name or len(pack_name) > 64:
            return await send_bot_message(peer, _newpack_invalid_name)

        state_data = StickersStateNewemojipack.deserialize(BytesIO(state.data))
        state_data.name = pack_name

        await state.update_state(StickersBotState.NEWEMOJIPACK_WAIT_IMAGE, state_data.serialize())
        return await send_bot_message(peer, _newemojipack_send_image)

    @staticmethod
    async def _validate_sticker_image(peer: Peer, content: MessageContent, is_emoji: bool) -> MessageRef | None:
        if content.media is None:
            return await send_bot_message(peer, _newpack_invalid_file)
        if content.media.type is not MediaType.DOCUMENT:
            return await send_bot_message(peer, _newpack_invalid_file)

        try:
            await validate_png_webp(content.media.file, is_emoji)
        except ErrorRpc:
            return await send_bot_message(peer, _newpack_invalid_file)

        if content.media.file.needs_save:
            await content.media.file.save(update_fields=["width", "height"])

    @classmethod
    async def _newpack_image(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        if (ret := await cls._validate_sticker_image(peer, message.content, False)) is not None:
            return ret

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        state_data.stickers.append(NewpackInputSticker(file_id=message.content.media.file.id, emoji=""))
        await state.update_state(
            StickersBotState.NEWPACK_WAIT_EMOJI,
            state_data.serialize(),
        )

        return await send_bot_message(peer, _newpack_send_emoji)

    @classmethod
    async def _addsticker_image(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        if (ret := await cls._validate_sticker_image(peer, message.content, False)) is not None:
            return ret

        state_data = StickersStateAddsticker.deserialize(BytesIO(state.data))
        state_data.file_id = message.content.media.file.id
        await state.update_state(
            StickersBotState.ADDSTICKER_WAIT_EMOJI,
            state_data.serialize(),
        )

        return await send_bot_message(peer, _newpack_send_emoji)

    @classmethod
    async def _replacesticker_image(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        if (ret := await cls._validate_sticker_image(peer, message.content, False)) is not None:
            return ret

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
                message.content.media.file, stickerset, old_sticker.sticker_pos, old_sticker.sticker_alt,
                old_sticker.sticker_is_mask, old_sticker.sticker_mask_coords, True, False,
            )
            stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
            await stickerset.save(update_fields=["hash"])

        await state.update_state(
            StickersBotState.REPLACESTICKER_WAIT_STICKER,
            StickersStateReplacesticker(set_id=stickerset.id).serialize(),
        )

        return await send_bot_message(peer, _replacesticker_replaced, entities=_replacesticker_replaced_entities)

    @classmethod
    async def _newemojipack_image(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        if (ret := await cls._validate_sticker_image(peer, message.content, True)) is not None:
            return ret

        state_data = StickersStateNewemojipack.deserialize(BytesIO(state.data))
        if state_data.stickers is None:
            state_data.stickers = []
        state_data.stickers.append(NewpackInputSticker(file_id=message.content.media.file.id, emoji=""))
        await state.update_state(StickersBotState.NEWEMOJIPACK_WAIT_EMOJI, state_data.serialize())

        return await send_bot_message(peer, _newemojipack_send_emoji)

    @classmethod
    async def _addemoji_image(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        if (ret := await cls._validate_sticker_image(peer, message.content, True)) is not None:
            return ret

        state_data = StickersStateAddemoji.deserialize(BytesIO(state.data))
        state_data.file_id = message.content.media.file.id
        await state.update_state(StickersBotState.ADDEMOJI_WAIT_EMOJI, state_data.serialize())

        return await send_bot_message(peer, _newpack_send_emoji)

    @classmethod
    async def _newvideo_video(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        content = message.content
        media = content.media

        if media is None:
            return await send_bot_message(peer, _newvideo_file_invalid, entities=_newvideo_file_invalid_entities)
        if media.type is not MediaType.DOCUMENT:
            return await send_bot_message(peer, _newvideo_file_invalid, entities=_newvideo_file_invalid_entities)
        if media.file.mime_type != "video/webm":
            return await send_bot_message(peer, _newvideo_file_invalid, entities=_newvideo_file_invalid_entities)

        try:
            await validate_webm(media.file, False)
        except ErrorRpc:
            return await send_bot_message(peer, _newvideo_file_invalid, entities=_newvideo_file_invalid_entities)

        if media.file.needs_save:
            await media.file.save(update_fields=["width", "height", "duration"])

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        state_data.stickers.append(NewpackInputSticker(file_id=media.file.id, emoji=""))
        await state.update_state(StickersBotState.NEWVIDEO_WAIT_EMOJI, state_data.serialize())

        return await send_bot_message(peer, _newvideo_send_emoji)

    @classmethod
    async def _newpack_emoji(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        emoji = message.content.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, _newpack_send_emoji_invalid)

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        state_data.stickers[-1].emoji = emoji
        await state.update_state(StickersBotState.NEWPACK_WAIT_IMAGE, state_data.serialize())

        text, entities = _newpack_sticker_added.format(num=len(state_data.stickers))
        return await send_bot_message(peer, text, entities=entities)

    @staticmethod
    async def _add_sticker_to_set(
            peer: Peer, set_id: int, file_id: int, emoji: str, is_emoji: bool
    ) -> tuple[MessageRef | None, Stickerset | None]:
        stickerset = await Stickerset.get_or_none(owner=peer.owner, id=set_id, emoji=is_emoji)
        if stickerset is None:
            return await send_bot_message(peer, "This stickerset does not exist."), None
        file = await File.get_or_none(id=file_id)
        if file is None:
            return await send_bot_message(peer, "This file does not exist."), None

        count = await File.filter(stickerset=stickerset).count()

        if file.mime_type.startswith("image/"):
            is_static = True
            is_webm = False
        elif file.mime_type == "video/webm":
            is_static = False
            is_webm = True
        else:
            return await send_bot_message(peer, "File is invalid. Somehow validation failed earlier."), None

        await make_sticker_from_file(file, stickerset, count, emoji, False, None, is_static, is_webm)
        stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
        await stickerset.save(update_fields=["hash"])

        return None, stickerset

    @classmethod
    async def _addsticker_emoji(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        emoji = message.content.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, _newpack_send_emoji_invalid)

        state_data = StickersStateAddsticker.deserialize(BytesIO(state.data))

        ret, stickerset = await cls._add_sticker_to_set(peer, state_data.set_id, state_data.file_id, emoji, False)
        if ret is not None:
            return ret

        await state.update_state(
            StickersBotState.ADDSTICKER_WAIT_IMAGE,
            StickersStateAddsticker(set_id=stickerset.id, file_id=0).serialize(),
        )

        return await send_bot_message(peer, _addsticker_sticker_added, entities=_addsticker_sticker_added_entities)

    @classmethod
    async def _editsticker_emoji(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        emoji = message.content.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, _newpack_send_emoji_invalid)

        state_data = StickersStateEditsticker.deserialize(BytesIO(state.data))
        file = await File.get_or_none(id=state_data.file_id)
        if file is None:
            return await send_bot_message(peer, "This file does not exist (???).")
        file.sticker_alt = emoji
        await file.save(update_fields=["sticker_alt"])
        await state.delete()

        return await send_bot_message(peer, _editsticker_saved)

    @classmethod
    async def _newemojipack_emoji(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        emoji = message.content.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, _newpack_send_emoji_invalid)

        state_data = StickersStateNewemojipack.deserialize(BytesIO(state.data))
        state_data.stickers[-1].emoji = emoji
        await state.update_state(StickersBotState.NEWEMOJIPACK_WAIT_IMAGE, state_data.serialize())

        text, entities = _newemojipack_sticker_added.format(num=len(state_data.stickers))
        return await send_bot_message(peer, text, entities=entities)

    @classmethod
    async def _addemoji_emoji(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        emoji = message.content.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, _newpack_send_emoji_invalid)

        state_data = StickersStateAddemoji.deserialize(BytesIO(state.data))

        ret, stickerset = await cls._add_sticker_to_set(peer, state_data.set_id, state_data.file_id, emoji, True)
        if ret is not None:
            return ret

        await state.update_state(
            StickersBotState.ADDEMOJI_WAIT_IMAGE,
            StickersStateAddemoji(set_id=stickerset.id, file_id=0).serialize(),
        )

        return await send_bot_message(peer, _addsticker_sticker_added, entities=_addsticker_sticker_added_entities)

    @classmethod
    async def _newvideo_emoji(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        emoji = message.content.message.strip()
        if not emoji or not purely_emoji(emoji) or len(emoji) > 4:
            return await send_bot_message(peer, _newpack_send_emoji_invalid)

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        state_data.stickers[-1].emoji = emoji
        await state.update_state(StickersBotState.NEWVIDEO_WAIT_VIDEO, state_data.serialize())
        text, entities = _newvideo_sticker_added.format(num=len(state_data.stickers))
        return await send_bot_message(peer, text, entities=entities)

    @staticmethod
    async def _validate_pack_short_name(peer: Peer, short_name: str) -> MessageRef | None:
        try:
            await check_stickerset_short_name(CheckShortName(short_name=short_name))
        except ErrorRpc as e:
            if e.error_message == "SHORT_NAME_OCCUPIED":
                return await send_bot_message(peer, _text_shortname_taken)
            return await send_bot_message(peer, _text_shortname_invalid)

    @staticmethod
    async def _publish_set(
            owner: User, name: str, short_name: str, is_emoji: bool, is_static: bool, is_webm: bool,
            stickers: list[NewpackInputSticker], state: StickersBotUserState,
    ) -> None:
        async with in_transaction():
            stickerset = await Stickerset.create(
                title=name,
                short_name=short_name,
                type=StickerSetType.STATIC,
                owner=owner,
                emoji=is_emoji,
            )

            files = {
                file.id: file
                for file in await File.filter(id__in=[sticker.file_id for sticker in stickers])
            }

            files_to_create = []
            for idx, input_sticker in enumerate(stickers):
                if not input_sticker.emoji:
                    continue
                file = files[input_sticker.file_id]
                files_to_create.append(await make_sticker_from_file(
                    file, stickerset, idx, input_sticker.emoji, False, None, is_static, is_webm, False,
                ))

            await File.bulk_create(files_to_create)

            stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
            await stickerset.save(update_fields=["owner_id", "hash"])

            await InstalledStickerset.create(set=stickerset, user=owner)

            await state.delete()

        await upd.new_stickerset(owner, stickerset)

    @classmethod
    async def _newpack_short_name(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        short_name = message.content.message.strip()
        if (ret := await cls._validate_pack_short_name(peer, short_name)) is not None:
            return ret

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        await cls._publish_set(peer.owner, state_data.name, short_name, False, True, False, state_data.stickers, state)

        text, entities = _text_published.format(short_name=short_name)
        return await send_bot_message(peer, text, entities=entities)

    @classmethod
    async def _newemojipack_short_name(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        short_name = message.content.message.strip()
        if (ret := await cls._validate_pack_short_name(peer, short_name)) is not None:
            return ret

        state_data = StickersStateNewemojipack.deserialize(BytesIO(state.data))
        await cls._publish_set(peer.owner, state_data.name, short_name, True, True, False, state_data.stickers, state)

        text, entities = _text_published_emoji.format(short_name=short_name)
        return await send_bot_message(peer, text, entities=entities)

    @classmethod
    async def _newvideo_short_name(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        short_name = message.content.message.strip()
        if (ret := await cls._validate_pack_short_name(peer, short_name)) is not None:
            return ret

        state_data = StickersStateNewpack.deserialize(BytesIO(state.data))
        await cls._publish_set(peer.owner, state_data.name, short_name, False, False, True, state_data.stickers, state)

        text, entities = _text_published.format(short_name=short_name)
        return await send_bot_message(peer, text, entities=entities)

    @classmethod
    async def _addsticker_pack(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        sel_short_name = message.content.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer, False)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer, False)

        await state.update_state(
            StickersBotState.ADDSTICKER_WAIT_IMAGE,
            StickersStateAddsticker(set_id=stickerset.id, file_id=0).serialize(),
        )
        return await send_bot_message(peer, _newpack_send_sticker)

    @classmethod
    async def _editsticker_pack_or_sticker(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        content = message.content
        media = content.media

        if media and media.file and media.file.type is FileType.DOCUMENT_STICKER:
            sticker = media.file
            if sticker.stickerset.owner_id != peer.owner_id:
                return await send_bot_message(peer, _editsticker_not_owner)
            await state.update_state(
                StickersBotState.EDITSTICKER_WAIT_EMOJI,
                StickersStateEditsticker(set_id=None, file_id=sticker.id).serialize(),
            )
            text, entities = _editsticker_send_emoji.format(current=sticker.sticker_alt)
            return await send_bot_message(peer, text, entities=entities)
        elif media:
            return await _invalid_set_selected(peer, False)

        sel_short_name = content.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer, False)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer, False)

        await state.update_state(
            StickersBotState.EDITSTICKER_WAIT_STICKER,
            StickersStateEditsticker(set_id=stickerset.id, file_id=None).serialize(),
        )
        return await send_bot_message(peer, _editsticker_send_sticker)

    @classmethod
    async def _delpack_pack(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        sel_short_name = message.content.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer, None)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer, None)

        await state.update_state(
            StickersBotState.DELPACK_WAIT_CONFIRM,
            StickersStateDelpack(set_id=stickerset.id).serialize(),
        )
        text, entities = _delpack_confirm.format(name=stickerset.short_name)
        return await send_bot_message(peer, text, entities=entities)

    @classmethod
    async def _renamepack_pack(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        sel_short_name = message.content.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer, None)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer, None)

        await state.update_state(
            StickersBotState.RENAMEPACK_WAIT_NAME,
            StickersStateRenamepack(set_id=stickerset.id).serialize(),
        )
        return await send_bot_message(peer, _renamepack_send_name.format(name=stickerset.title))

    @classmethod
    async def _replacesticker_pack_or_sticker(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        content = message.content
        media = content.media

        if media and media.file and media.file.type is FileType.DOCUMENT_STICKER:
            sticker = media.file
            if sticker.stickerset.owner_id != peer.owner_id:
                return await send_bot_message(peer, _editsticker_not_owner)

            await state.update_state(
                StickersBotState.REPLACESTICKER_WAIT_IMAGE,
                StickersStateReplacesticker(set_id=None, file_id=sticker.id).serialize(),
            )
            text, entities = _editsticker_send_emoji.format(current=sticker.sticker_alt)
            return await send_bot_message(peer, text, entities=entities)
        elif media:
            return await _invalid_set_selected(peer, False)

        sel_short_name = content.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer, False)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer, False)

        await state.update_state(
            StickersBotState.REPLACESTICKER_WAIT_STICKER,
            StickersStateEditsticker(set_id=stickerset.id, file_id=None).serialize(),
        )
        return await send_bot_message(peer, _replacesticker_send_sticker)

    @classmethod
    async def _addemoji_pack(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        sel_short_name = message.content.message.strip()
        if not sel_short_name:
            return await _invalid_set_selected(peer, True)

        stickerset = await Stickerset.get_or_none(owner=peer.owner, short_name=sel_short_name)
        if stickerset is None:
            return await _invalid_set_selected(peer, True)

        await state.update_state(
            StickersBotState.ADDEMOJI_WAIT_IMAGE,
            StickersStateAddemoji(set_id=stickerset.id, file_id=0).serialize(),
        )
        return await send_bot_message(peer, _newemojipack_send_image)

    @staticmethod
    async def _get_sticker_to_edit(peer: Peer, message: MessageRef) -> tuple[MessageRef | None, File | None]:
        media = message.content.media

        if not media or not media.file or media.file.type is not FileType.DOCUMENT_STICKER:
            return await send_bot_message(peer, _editsticker_send_sticker_invalid), None

        sticker = media.file
        if sticker.stickerset.owner_id != peer.owner_id:
            return await send_bot_message(peer, _editsticker_not_owner), None

        return None, sticker

    @classmethod
    async def _editsticker_sticker(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        ret, sticker = await cls._get_sticker_to_edit(peer, message)
        if ret is not None:
            return ret

        await state.update_state(
            StickersBotState.EDITSTICKER_WAIT_EMOJI,
            StickersStateEditsticker(set_id=None, file_id=sticker.id).serialize(),
        )
        text, entities = _editsticker_send_emoji.format(current=sticker.sticker_alt)
        return await send_bot_message(peer, text, entities=entities)

    @classmethod
    async def _replacesticker_sticker(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        ret, sticker = await cls._get_sticker_to_edit(peer, message)
        if ret is not None:
            return ret

        await state.update_state(
            StickersBotState.REPLACESTICKER_WAIT_IMAGE,
            StickersStateEditsticker(set_id=None, file_id=sticker.id).serialize(),
        )
        return await send_bot_message(peer, _newpack_send_sticker)

    @classmethod
    async def _delpack_confirm(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        if message.content.message != DELPACK_CONFIRMATION:
            return await send_bot_message(peer, _delpack_confirm_invalid, entities=_delpack_confirm_invalid_entities)

        state_data = StickersStateDelpack.deserialize(BytesIO(state.data))
        stickerset = await Stickerset.get_or_none(id=state_data.set_id, owner=peer.owner)
        if stickerset is None:
            await state.delete()
            return await send_bot_message(peer, _addsticker_shortname_invalid)

        stickerset.deleted = True
        stickerset.owner = None
        stickerset.short_name = None
        await stickerset.save(update_fields=["deleted", "owner_id", "short_name"])

        return await send_bot_message(peer, _delpack_deleted)

    @classmethod
    async def _newemojipack_type(cls, peer: Peer, message: MessageRef, state: StickersBotUserState) -> MessageRef:
        type_ = message.content.message.strip()
        if type_ == "Static emoji":
            pack_type = EmojiPackTypeStatic()
        elif type_ == "Video emoji":
            return await send_bot_message(peer, _newemojipack_type_not_supported, EMOJI_PACK_TYPES_KEYBOARD)
        elif type_ == "Animated emoji":
            return await send_bot_message(peer, _newemojipack_type_not_supported, EMOJI_PACK_TYPES_KEYBOARD)
        else:
            return await send_bot_message(peer, _newemojipack_invalid_type, EMOJI_PACK_TYPES_KEYBOARD)

        await state.update_state(
            StickersBotState.NEWEMOJIPACK_WAIT_NAME,
            StickersStateNewemojipack(type_=pack_type).serialize(),
        )
        return await send_bot_message(
            peer, _newemojipack_send_name, ReplyKeyboardHide(), _newemojipack_send_name_entities,
        )
