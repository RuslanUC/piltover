import timeit
from io import BytesIO
from os import urandom
from typing import TypeVar, Callable

from piltover.tl import Long, Int, Int128, Int256, Float
from piltover.tl.types.internal_benchmarking import ObjectToBenchmark, NestedObject, DeeplyNestedObjectX1, \
    DeeplyNestedObjectX2, DeeplyNestedObjectX3, DeeplyNestedObjectX4, DeeplyNestedObjectX5, DeeplyNestedObjectX6, \
    DeeplyNestedObjectX7, DeeplyNestedObjectX8

T = TypeVar("T")


def _rand_int() -> int:
    return Int.read_bytes(urandom(4))


def _rand_long() -> int:
    return Long.read_bytes(urandom(8))


def _rand_int128() -> int:
    return Int128.read_bytes(urandom(16))


def _rand_int256() -> int:
    return Int256.read_bytes(urandom(32))


def _rand_float() -> float:
    return Float.read(BytesIO(urandom(8)))


def _rand_nested_obj() -> NestedObject:
    return NestedObject(
        some_int=_rand_int(),
        some_long=_rand_long(),
    )


def _rand_deeply_nested_obj() -> DeeplyNestedObjectX1:
    return DeeplyNestedObjectX1(
        some_long=_rand_long(),
        inner_object=DeeplyNestedObjectX2(
            some_string=urandom(128).hex(),
            inner_object=DeeplyNestedObjectX3(
                some_bytes=urandom(256),
                inner_object=DeeplyNestedObjectX4(
                    some_bool=True,
                    inner_object=DeeplyNestedObjectX5(
                        some_double=_rand_float(),
                        inner_object=DeeplyNestedObjectX6(
                            opt_long=_rand_long(),
                            inner_object=DeeplyNestedObjectX7(
                                some_int128=_rand_int128(),
                                inner_object=DeeplyNestedObjectX8(
                                    some_int256=_rand_int256(),
                                    nested_obj=_rand_nested_obj(),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _rand_vec_small(creator_func: Callable[[], T]) -> list[T]:
    return [
        creator_func()
        for _ in range(4)
    ]


def _rand_vec_big(creator_func: Callable[[], T]) -> list[T]:
    return [
        creator_func()
        for _ in range(128)
    ]


def make_obj_to_benchmark() -> ObjectToBenchmark:
    return ObjectToBenchmark(
        int32=_rand_int(),
        optional_int32=_rand_int(),
        int64=_rand_long(),
        optional_int64=_rand_long(),
        int128=_rand_int128(),
        optional_int128=_rand_int128(),
        int256=_rand_int256(),
        optional_int256=_rand_int256(),
        double=_rand_float(),
        optional_double=_rand_float(),
        bytes_field=urandom(32),
        optional_bytes=urandom(1024 * 32),
        string_field=urandom(16).hex(),
        optional_string=urandom(1024 * 16).hex(),
        full_bool=True,
        optional_full_bool=False,
        optional_bit_bool=False,
        nested_object=_rand_nested_obj(),
        optional_nested_object=_rand_nested_obj(),
        deeply_nested_object=_rand_deeply_nested_obj(),
        optional_deeply_nested_object=_rand_deeply_nested_obj(),
        int32_vec=_rand_vec_small(_rand_int),
        optional_int32_vec=_rand_vec_big(_rand_int),
        int64_vec=_rand_vec_small(_rand_long),
        optional_int64_vec=_rand_vec_big(_rand_long),
        int128_vec=_rand_vec_small(_rand_int128),
        optional_int128_vec=_rand_vec_small(_rand_int128),
        int256_vec=_rand_vec_small(_rand_int256),
        optional_int256_vec=_rand_vec_small(_rand_int256),
        double_vec=_rand_vec_small(_rand_float),
        optional_double_vec=_rand_vec_big(_rand_float),
        bytes_field_vec=_rand_vec_small(lambda: urandom(32)),
        optional_bytes_vec=_rand_vec_big(lambda: urandom(8)),
        string_field_vec=_rand_vec_small(lambda: urandom(8).hex()),
        optional_string_vec=_rand_vec_big(lambda: urandom(3).hex()),
        full_bool_vec=_rand_vec_big(lambda: True),
        optional_full_bool_vec=_rand_vec_small(lambda: False),
        nested_object_vec=_rand_vec_big(_rand_nested_obj),
        optional_nested_object_vec=_rand_vec_small(_rand_nested_obj),
        deeply_nested_object_vec=_rand_vec_small(_rand_deeply_nested_obj),
        optional_deeply_nested_object_vec=_rand_vec_small(_rand_deeply_nested_obj),

        int32_flags2=_rand_int(),
        optional_int32_flags2=_rand_int(),
        int64_flags2=_rand_long(),
        optional_int64_flags2=_rand_long(),
        int128_flags2=_rand_int128(),
        optional_int128_flags2=_rand_int128(),
        int256_flags2=_rand_int256(),
        optional_int256_flags2=_rand_int256(),
        double_flags2=_rand_float(),
        optional_double_flags2=_rand_float(),
        bytes_field_flags2=urandom(32),
        optional_bytes_flags2=urandom(1024 * 32),
        string_field_flags2=urandom(16).hex(),
        optional_string_flags2=urandom(1024 * 16).hex(),
        full_bool_flags2=True,
        optional_full_bool_flags2=False,
        optional_bit_bool_flags2=False,
        nested_object_flags2=_rand_nested_obj(),
        optional_nested_object_flags2=_rand_nested_obj(),
        deeply_nested_object_flags2=_rand_deeply_nested_obj(),
        optional_deeply_nested_object_flags2=_rand_deeply_nested_obj(),
        int32_vec_flags2=_rand_vec_small(_rand_int),
        optional_int32_vec_flags2=_rand_vec_big(_rand_int),
        int64_vec_flags2=_rand_vec_small(_rand_long),
        optional_int64_vec_flags2=_rand_vec_big(_rand_long),
        int128_vec_flags2=_rand_vec_small(_rand_int128),
        optional_int128_vec_flags2=_rand_vec_small(_rand_int128),
        int256_vec_flags2=_rand_vec_small(_rand_int256),
        optional_int256_vec_flags2=_rand_vec_small(_rand_int256),
        double_vec_flags2=_rand_vec_small(_rand_float),
        optional_double_vec_flags2=_rand_vec_big(_rand_float),
        bytes_field_vec_flags2=_rand_vec_small(lambda: urandom(32)),
        optional_bytes_vec_flags2=_rand_vec_big(lambda: urandom(8)),
        string_field_vec_flags2=_rand_vec_small(lambda: urandom(8).hex()),
        optional_string_vec_flags2=_rand_vec_big(lambda: urandom(3).hex()),
        full_bool_vec_flags2=_rand_vec_big(lambda: True),
        optional_full_bool_vec_flags2=_rand_vec_small(lambda: False),
        nested_object_vec_flags2=_rand_vec_big(_rand_nested_obj),
        optional_nested_object_vec_flags2=_rand_vec_small(_rand_nested_obj),
        deeply_nested_object_vec_flags2=_rand_vec_small(_rand_deeply_nested_obj),
        optional_deeply_nested_object_vec_flags2=_rand_vec_small(_rand_deeply_nested_obj),
    )


def _read_compare_obj(buf: BytesIO, orig: ObjectToBenchmark) -> bool:
    buf.seek(0)
    new_obj = ObjectToBenchmark.read(buf)
    return new_obj == orig


def main() -> None:
    iterations = 1000

    obj = make_obj_to_benchmark()
    total_time = timeit.timeit(obj.write, number=iterations)
    print(f"Write took {total_time:.2f} seconds ({total_time * 1000 / iterations:.2f} ms/it): {len(obj.write()) / 1024:.2f} KB")

    buf_to_read = BytesIO(obj.write())
    total_time = timeit.timeit(lambda: _read_compare_obj(buf_to_read, obj), number=iterations)
    print(f"Read took {total_time:.2f} seconds ({total_time * 1000 / iterations:.2f} ms/it): {len(obj.write()) / 1024:.2f} KB")


if __name__ == "__main__":
    #yappi.start()
    main()
    #yappi.get_func_stats().print_all()
