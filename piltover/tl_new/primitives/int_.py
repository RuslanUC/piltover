class Int(int):
    BIT_SIZE = 32
    SIZE = BIT_SIZE // 8


class Long(Int):
    BIT_SIZE = 64
    SIZE = BIT_SIZE // 8


class Int128(Int):
    BIT_SIZE = 128
    SIZE = BIT_SIZE // 8


class Int256(Int):
    BIT_SIZE = 256
    SIZE = BIT_SIZE // 8
