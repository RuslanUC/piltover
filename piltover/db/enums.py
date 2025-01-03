from enum import IntEnum


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


class MediaType(IntEnum):
    DOCUMENT = 0
    PHOTO = 1
    GIF = 1


class UpdateType(IntEnum):
    # related_id is a message id
    MESSAGE_DELETE = 0
    # related_id is a message id
    MESSAGE_EDIT = 1
    # Should (probably) be only one update of this type per chat
    # related_it is a chat id
    READ_HISTORY_INBOX = 2
    DIALOG_PIN = 3
    DRAFT_UPDATE = 4
    DIALOG_PIN_REORDER = 5
    MESSAGE_PIN_UPDATE = 6
    USER_UPDATE = 7
    CHAT_CREATE = 8
    USER_UPDATE_NAME = 9


class PeerType(IntEnum):
    SELF = 0
    USER = 1
    CHAT = 2


class MessageType(IntEnum):
    REGULAR = 0
    SERVICE_PIN_MESSAGE = 1
    SERVICE_CHAT_CREATE = 2


class UserStatus(IntEnum):
    # Idk why
    OFFLINE = 0
    ONLINE = 1
