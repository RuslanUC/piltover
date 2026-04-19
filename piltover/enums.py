from enum import IntFlag


class ReqHandlerFlags(IntFlag):
    AUTH_NOT_REQUIRED = 1 << 0
    ALLOW_MFA_PENDING = 1 << 1
    BOT_NOT_ALLOWED = 1 << 2
    REFRESH_SESSION = 1 << 3
    USER_NOT_ALLOWED = 1 << 4
    INTERNAL = 1 << 5
    DONT_FETCH_USER = 1 << 6
    FETCH_USER_WITH_USERNAME = 1 << 7
