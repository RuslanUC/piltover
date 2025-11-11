from enum import IntFlag


class ReqHandlerFlags(IntFlag):
    AUTH_NOT_REQUIRED = 1 << 0
    ALLOW_MFA_PENDING = 1 << 1
    BOT_NOT_ALLOWED = 1 << 2
    REFRESH_SESSION = 1 << 3
    USER_NOT_ALLOWED = 1 << 4
