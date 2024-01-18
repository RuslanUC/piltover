from enum import Enum, auto, IntEnum


class Transport(Enum):
    Abridged = auto()
    Intermediate = auto()
    PaddedIntermediate = auto()
    Full = auto()
    Obfuscated = auto()


class ReqHandlerFlags(IntEnum):
    AUTH_REQUIRED = 1
    ALLOW_MFA_PENDING = 2
