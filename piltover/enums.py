from enum import IntEnum


class ReqHandlerFlags(IntEnum):
    AUTH_REQUIRED = 1
    ALLOW_MFA_PENDING = 2
