from enum import IntFlag


class ReqHandlerFlags(IntFlag):
    AUTH_NOT_REQUIRED = 1
    ALLOW_MFA_PENDING = 2
    BOT_NOT_ALLOWED = 3
    REFRESH_SESSION = 4
