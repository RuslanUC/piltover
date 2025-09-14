from .int_ import Int, Long, Int128, Int256, BigInt
from .float_ import Float
from .bool_ import Bool
from .str_ import Bytes, String
from .vector import Vector, IntVector, LongVector, Int128Vector, Int256Vector, FloatVector, BoolVector, BytesVector, \
    StringVector, TLObjectVector

BOOL_TRUE = b"\xb5\x75\x72\x99"
BOOL_FALSE = b"\x37\x97\x79\xbc"
VECTOR = b"\x15\xc4\xb5\x1c"
