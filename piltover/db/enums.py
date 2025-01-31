from enum import IntEnum, IntFlag


class ChatType(IntEnum):
    PRIVATE = 0
    SAVED = 1
    #GROUP = 2
    #CHANNEL = 3


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


class MediaType(IntEnum):
    DOCUMENT = 0
    PHOTO = 1


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


class PeerType(IntEnum):
    SELF = 0
    USER = 1
    CHAT = 2


class MessageType(IntEnum):
    REGULAR = 0
    SERVICE_PIN_MESSAGE = 1
    SERVICE_CHAT_CREATE = 2
    SERVICE_CHAT_EDIT_TITLE = 3
    SERVICE_CHAT_EDIT_PHOTO = 4
    SERVICE_CHAT_USER_ADD = 5
    SERVICE_CHAT_USER_DEL = 6


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
    CHANGE_INFO = 1 << 9
    INVITE_USERS = 1 << 10
    PIN_MESSAGES = 1 << 11
    MANAGE_TOPICS = 1 << 12
    SEND_PHOTOS = 1 << 13
    SEND_VIDEOS = 1 << 14
    SEND_ROUND_VIDEOS = 1 << 15
    SEND_AUDIOS = 1 << 16
    SEND_VOICES = 1 << 17
    SEND_DOCS = 1 << 18
    SEND_PLAIN = 1 << 19
