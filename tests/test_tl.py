from io import BytesIO
from typing import Optional

from piltover.tl.primitives.int_ import Int, Long, Int128, Int256
from piltover.tl.tl_object import TLObject
from piltover.tl.all import objects


def test_builtin_types():
    @tl_object(id=0x01, name="test1")
    class TestType1(TLObject):
        int_field: Int = TLField()
        long_field: Long = TLField()
        int128_field: Int128 = TLField()
        int256_field: Int256 = TLField()
        bool_field: bool = TLField()
        float_field: float = TLField()
        bytes_field: bytes = TLField()
        string_field: str = TLField()

    objects[0x01] = TestType1

    obj = TestType1(
        int_field=123456,
        long_field=123456789,
        int128_field=987654321,
        int256_field=987321654,
        bool_field=True,
        float_field=15.25,
        bytes_field=b"test bytes",
        string_field="test string",
    )
    serialized = obj.write()
    assert len(serialized) == 100

    deserialized = TestType1.read(BytesIO(serialized))
    assert obj == deserialized


def test_vectors():
    @tl_object(id=0x02, name="test2")
    class TestType2(TLObject):
        int_vector: list[Int] = TLField()

    objects[0x02] = TestType2

    obj = TestType2(int_vector=[123456, 123, 456])
    serialized = obj.write()

    deserialized = TestType2.read(BytesIO(serialized))
    assert obj == deserialized


def test_flags():
    @tl_object(id=0x03, name="test3")
    class TestType3(TLObject):
        flags: Int = TLField(is_flags=True)
        required: str = TLField()
        flags2: Int = TLField(is_flags=True, flagnum=2)
        optional_bool1: bool = TLField(flag=0b01)
        optional_bool2: Optional[bool] = TLField(flag=0b1, flagnum=2, flag_serializable=True)

    objects[0x03] = TestType3

    obj = TestType3(required="a")
    assert obj == TestType3(
        flags=0,
        required="a",
        flags2=0,
        optional_bool1=None,
        optional_bool2=None,
    )

    obj = TestType3(required="a", optional_bool1=True, optional_bool2=False)
    serialized = obj.write()

    deserialized = TestType3.read(BytesIO(serialized))
    assert deserialized.flags == 0b01
    assert deserialized.flags2 == 0
    assert deserialized.required == "a"
    assert deserialized.optional_bool1

