from enum import IntEnum


class ChatType(IntEnum):
    PRIVATE = 0
    SAVED = 1
    #CHAT = 2
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


class FileType(IntEnum):
    DOCUMENT = 0
    PHOTO = 1
