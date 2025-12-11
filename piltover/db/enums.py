from __future__ import annotations
from enum import IntEnum, IntFlag, StrEnum
from io import BytesIO

from piltover.tl import ChatBannedRights as TLChatBannedRights, Int, ChatAdminRights as TLChatAdminRights


class PrivacyRuleKeyType(IntEnum):
    STATUS_TIMESTAMP = 0
    CHAT_INVITE = 1
    PHONE_CALL = 2
    PHONE_P2P = 3
    FORWARDS = 4
    PROFILE_PHOTO = 5
    PHONE_NUMBER = 6
    ADDED_BY_PHONE = 7
    VOICE_MESSAGE = 8
    ABOUT = 9
    BIRTHDAY = 10


class PrivacyRuleValueType(IntEnum):
    ALLOW_CONTACTS = 0
    ALLOW_ALL = 1
    ALLOW_USERS = 2
    DISALLOW_CONTACTS = 3
    DISALLOW_ALL = 4
    DISALLOW_USERS = 5

    ALLOW_CHATS = 6
    DISALLOW_CHATS = 7


class FileType(IntEnum):
    DOCUMENT = 0
    PHOTO = 1

    DOCUMENT_GIF = 3
    DOCUMENT_VIDEO = 4
    DOCUMENT_AUDIO = 5
    DOCUMENT_VOICE = 6
    DOCUMENT_VIDEO_NOTE = 7
    DOCUMENT_STICKER = 8
    DOCUMENT_EMOJI = 9

    ENCRYPTED = 100


class MediaType(IntEnum):
    DOCUMENT = 0
    PHOTO = 1
    POLL = 2
    CONTACT = 3
    GEOPOINT = 4


class UpdateType(IntEnum):
    # related_id is a message id
    MESSAGE_DELETE = 0
    # related_id is a message id
    MESSAGE_EDIT = 1
    # Should (probably) be only one update of this type per chat
    # related_id is a chat id
    READ_HISTORY_INBOX = 2
    DIALOG_PIN = 3
    DRAFT_UPDATE = 4
    DIALOG_PIN_REORDER = 5
    MESSAGE_PIN_UPDATE = 6
    USER_UPDATE = 7
    CHAT_CREATE = 8
    USER_UPDATE_NAME = 9
    UPDATE_CONTACT = 10
    UPDATE_BLOCK = 11
    UPDATE_CHAT = 12
    UPDATE_DIALOG_UNREAD_MARK = 13
    READ_INBOX = 14
    READ_OUTBOX = 15
    FOLDER_PEERS = 16
    UPDATE_CHAT_BANNED_RIGHTS = 17
    UPDATE_CHANNEL = 18
    UPDATE_POLL = 19
    UPDATE_FOLDER = 20
    FOLDERS_ORDER = 21
    UPDATE_ENCRYPTION = 22
    UPDATE_CONFIG = 23
    UPDATE_RECENT_REACTIONS = 24
    NEW_AUTHORIZATION = 25
    NEW_STICKERSET = 26
    UPDATE_STICKERSETS = 27
    UPDATE_STICKERSETS_ORDER = 28
    UPDATE_CHAT_WALLPAPER = 29
    READ_MESSAGES_CONTENTS = 30
    NEW_SCHEDULED_MESSAGE = 31
    DELETE_SCHEDULED_MESSAGE = 32
    UPDATE_HISTORY_TTL = 33
    BOT_CALLBACK_QUERY = 34
    UPDATE_PHONE = 35
    UPDATE_PEER_NOTIFY_SETTINGS = 36
    SAVED_GIFS = 37
    BOT_INLINE_QUERY = 38
    UPDATE_RECENT_STICKERS = 39
    UPDATE_FAVED_STICKERS = 40
    SAVED_DIALOG_PIN = 41
    SAVED_DIALOG_PIN_REORDER = 42


class SecretUpdateType(IntEnum):
    NEW_MESSAGE = 1
    HISTORY_READ = 3


class PeerType(IntEnum):
    SELF = 0
    USER = 1
    CHAT = 2
    CHANNEL = 3


class MessageType(IntEnum):
    REGULAR = 0
    SERVICE_PIN_MESSAGE = 1
    SERVICE_CHAT_CREATE = 2
    SERVICE_CHAT_EDIT_TITLE = 3
    SERVICE_CHAT_EDIT_PHOTO = 4
    SERVICE_CHAT_USER_ADD = 5
    SERVICE_CHAT_USER_DEL = 6
    SERVICE_CHAT_USER_INVITE_JOIN = 7
    SERVICE_CHAT_USER_REQUEST_JOIN = 8
    SERVICE_CHANNEL_CREATE = 9
    SERVICE_CHAT_UPDATE_WALLPAPER = 10
    SERVICE_CHAT_UPDATE_TTL = 11
    SERVICE_CHAT_MIGRATE_TO = 12
    SERVICE_CHAT_MIGRATE_FROM = 13
    SCHEDULED = 100


class UserStatus(IntEnum):
    # Idk why
    OFFLINE = 0
    ONLINE = 1


class ChatBannedRights(IntFlag):
    VIEW_MESSAGES = 1 << 0
    SEND_MESSAGES = 1 << 1
    SEND_MEDIA = 1 << 2
    SEND_STICKERS = 1 << 3
    SEND_GIFS = 1 << 4
    SEND_GAMES = 1 << 5
    SEND_INLINE = 1 << 6
    EMBED_LINKS = 1 << 7
    SEND_POLLS = 1 << 8
    CHANGE_INFO = 1 << 10
    INVITE_USERS = 1 << 15
    PIN_MESSAGES = 1 << 17
    MANAGE_TOPICS = 1 << 18
    SEND_PHOTOS = 1 << 19
    SEND_VIDEOS = 1 << 20
    SEND_ROUNDVIDEOS = 1 << 21
    SEND_AUDIOS = 1 << 22
    SEND_VOICES = 1 << 23
    SEND_DOCS = 1 << 24
    SEND_PLAIN = 1 << 25

    @classmethod
    def from_tl(cls, banned_rights: TLChatBannedRights) -> ChatBannedRights:
        flags = Int.read_bytes(banned_rights.serialize()[:4])
        return ChatBannedRights(flags)

    def to_tl(self) -> TLChatBannedRights:
        flags = Int.write(self.value)
        # TODO: until_date
        return TLChatBannedRights.deserialize(BytesIO(flags + Int.write(2 ** 31 - 1)))


class ChannelUpdateType(IntEnum):
    UPDATE_CHANNEL = 0
    NEW_MESSAGE = 1
    EDIT_MESSAGE = 2
    DELETE_MESSAGES = 3


class DialogFolderId(IntEnum):
    ALL = 0
    ARCHIVE = 1


class ChatAdminRights(IntFlag):
    CHANGE_INFO = 1 << 0
    POST_MESSAGES = 1 << 1
    EDIT_MESSAGES = 1 << 2
    DELETE_MESSAGES = 1 << 3
    BAN_USERS = 1 << 4
    INVITE_USERS = 1 << 5
    PIN_MESSAGES = 1 << 7
    ADD_ADMINS = 1 << 9
    ANONYMOUS = 1 << 10
    MANAGE_CALL = 1 << 11
    OTHER = 1 << 12
    MANAGE_TOPICS = 1 << 13
    POST_STORIES = 1 << 14
    EDIT_STORIES = 1 << 15
    DELETE_STORIES = 1 << 16

    @classmethod
    def from_tl(cls, admin_rights: TLChatAdminRights) -> ChatAdminRights:
        flags = Int.read_bytes(admin_rights.serialize())
        return ChatAdminRights(flags)

    def to_tl(self) -> TLChatAdminRights:
        flags = Int.write(self.value)
        return TLChatAdminRights.deserialize(BytesIO(flags))

    @classmethod
    def all(cls) -> ChatAdminRights:
        all_ = cls.CHANGE_INFO
        for right in cls:
            all_ |= right
        return all_


class PushTokenType(IntEnum):
    APPLE = 1
    FIREBASE = 2
    MICROSOFT = 3
    SIMPLE_PUSH = 4
    UBUNTU = 5
    BLACKBERRY = 6
    INTERNAL = 7
    WINDOWS = 8
    APPLE_VOIP = 9
    WEB = 10
    MICROSOFT_VOIP = 11
    TIZEN = 12
    HUAWEI = 13


class StickerSetType(IntEnum):
    STATIC = 0
    ANIMATED = 1
    VIDEO = 2


class BotFatherState(IntEnum):
    NEWBOT_WAIT_NAME = 1
    NEWBOT_WAIT_USERNAME = 2
    EDITBOT_WAIT_NAME = 3


BOTFATHER_STATE_TO_COMMAND_NAME = {
    BotFatherState.NEWBOT_WAIT_NAME: "newbot",
    BotFatherState.NEWBOT_WAIT_USERNAME: "newbot",
    BotFatherState.EDITBOT_WAIT_NAME: "mybots",
    None: None,
}


class StickersBotState(IntEnum):
    NEWPACK_WAIT_NAME = 1
    NEWPACK_WAIT_IMAGE = 2
    NEWPACK_WAIT_EMOJI = 3
    NEWPACK_WAIT_ICON = 4
    NEWPACK_WAIT_SHORT_NAME = 5
    ADDSTICKER_WAIT_PACK = 6
    ADDSTICKER_WAIT_IMAGE = 7
    ADDSTICKER_WAIT_EMOJI = 8
    EDITSTICKER_WAIT_PACK_OR_STICKER = 9
    EDITSTICKER_WAIT_STICKER = 10
    EDITSTICKER_WAIT_EMOJI = 11
    DELPACK_WAIT_PACK = 12
    DELPACK_WAIT_CONFIRM = 13
    RENAMEPACK_WAIT_PACK = 14
    RENAMEPACK_WAIT_NAME = 15
    REPLACESTICKER_WAIT_PACK_OR_STICKER = 16
    REPLACESTICKER_WAIT_STICKER = 17
    REPLACESTICKER_WAIT_IMAGE = 18
    NEWEMOJIPACK_WAIT_TYPE = 19
    NEWEMOJIPACK_WAIT_NAME = 20
    NEWEMOJIPACK_WAIT_IMAGE = 21
    NEWEMOJIPACK_WAIT_EMOJI = 22
    NEWEMOJIPACK_WAIT_ICON = 23
    NEWEMOJIPACK_WAIT_SHORT_NAME = 24
    ADDEMOJI_WAIT_PACK = 25
    ADDEMOJI_WAIT_IMAGE = 26
    ADDEMOJI_WAIT_EMOJI = 27


STICKERS_STATE_TO_COMMAND_NAME = {
    StickersBotState.NEWPACK_WAIT_NAME: "newpack",
    StickersBotState.NEWPACK_WAIT_IMAGE: "newpack",
    StickersBotState.NEWPACK_WAIT_EMOJI: "newpack",
    StickersBotState.NEWPACK_WAIT_ICON: "newpack",
    StickersBotState.NEWPACK_WAIT_SHORT_NAME: "newpack",
    StickersBotState.ADDSTICKER_WAIT_PACK: "addsticker",
    StickersBotState.ADDSTICKER_WAIT_IMAGE: "addsticker",
    StickersBotState.ADDSTICKER_WAIT_EMOJI: "addsticker",
    StickersBotState.EDITSTICKER_WAIT_PACK_OR_STICKER: "editsticker",
    StickersBotState.EDITSTICKER_WAIT_STICKER: "editsticker",
    StickersBotState.EDITSTICKER_WAIT_EMOJI: "editsticker",
    StickersBotState.DELPACK_WAIT_PACK: "delpack",
    StickersBotState.DELPACK_WAIT_CONFIRM: "delpack",
    StickersBotState.RENAMEPACK_WAIT_PACK: "renamepack",
    StickersBotState.RENAMEPACK_WAIT_NAME: "renamepack",
    StickersBotState.REPLACESTICKER_WAIT_PACK_OR_STICKER: "replacesticker",
    StickersBotState.REPLACESTICKER_WAIT_STICKER: "replacesticker",
    StickersBotState.REPLACESTICKER_WAIT_IMAGE: "replacesticker",
    StickersBotState.NEWEMOJIPACK_WAIT_TYPE: "newemojipack",
    StickersBotState.NEWEMOJIPACK_WAIT_NAME: "newemojipack",
    StickersBotState.NEWEMOJIPACK_WAIT_IMAGE: "newemojipack",
    StickersBotState.NEWEMOJIPACK_WAIT_EMOJI: "newemojipack",
    StickersBotState.NEWEMOJIPACK_WAIT_ICON: "newemojipack",
    StickersBotState.NEWEMOJIPACK_WAIT_SHORT_NAME: "newemojipack",
    StickersBotState.ADDEMOJI_WAIT_PACK: "addemoji",
    StickersBotState.ADDEMOJI_WAIT_IMAGE: "addemoji",
    StickersBotState.ADDEMOJI_WAIT_EMOJI: "addemoji",
    None: None,
}


class NotifySettingsNotPeerType(IntEnum):
    USERS = 0
    CHATS = 1
    CHANNELS = 2


class InlineQueryPeer(IntEnum):
    UNKNOWN = 0
    USER = 1
    BOT = 2
    SAME_BOT = 3
    CHAT = 4
    CHANNEL = 5
    SUPERGROUP = 6


class InlineQueryResultType(StrEnum):
    PHOTO = "photo"
    STICKER = "sticker"
    GIF = "gif"
    VOICE = "voice"
    VENUE = "venue"
    VIDEO = "video"
    CONTACT = "contact"
    AUDIO = "audio"
    LOCATION = "location"
    ARTICLE = "article"
    FILE = "file"

