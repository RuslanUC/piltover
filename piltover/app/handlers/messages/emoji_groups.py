from piltover.app.utils.utils import telegram_hash
from piltover.db.enums import EmojiGroupCategory
from piltover.db.models import EmojiGroup
from piltover.enums import ReqHandlerFlags
from piltover.tl.functions.messages import GetEmojiStickerGroups, GetEmojiGroups, GetEmojiStatusGroups, \
    GetEmojiProfilePhotoGroups
from piltover.tl.types.messages import EmojiGroups, EmojiGroupsNotModified
from piltover.tl.base.messages import EmojiGroups as BaseEmojiGroups
from piltover.worker import MessageHandler

# TODO: cache everything in here
handler = MessageHandler("messages.emoji_groups")


async def _get_emoji_groups_by_category(category: EmojiGroupCategory, hash_: int) -> BaseEmojiGroups:
    groups = await EmojiGroup.filter(category=category).order_by("position")
    groups_hash = telegram_hash((group.id for group in groups), 32)

    if groups_hash == hash_:
        return EmojiGroupsNotModified()

    return EmojiGroups(
        hash=groups_hash,
        groups=[
            group.to_tl()
            for group in groups
        ]
    )


@handler.on_request(GetEmojiStickerGroups, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_sticker_groups(request: GetEmojiStickerGroups) -> BaseEmojiGroups:
    return await _get_emoji_groups_by_category(EmojiGroupCategory.STICKER, request.hash)


@handler.on_request(GetEmojiGroups, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_groups(request: GetEmojiGroups) -> BaseEmojiGroups:
    return await _get_emoji_groups_by_category(EmojiGroupCategory.REGULAR, request.hash)


@handler.on_request(GetEmojiStatusGroups, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_status_groups(request: GetEmojiStatusGroups) -> BaseEmojiGroups:
    return await _get_emoji_groups_by_category(EmojiGroupCategory.STATUS, request.hash)


@handler.on_request(GetEmojiProfilePhotoGroups, ReqHandlerFlags.AUTH_NOT_REQUIRED)
async def get_emoji_profile_photo_groups(request: GetEmojiProfilePhotoGroups) -> BaseEmojiGroups:
    return await _get_emoji_groups_by_category(EmojiGroupCategory.PROFILE_PHOTO, request.hash)
