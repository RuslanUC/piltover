SIXTYFOUR: int

def xorshift128plusbounded(n: int) -> int:
    ...


def xorshift128plusrandint(lower_bound: int, upper_bound: int) -> int:
    ...


def pcg32randint(lower_bound: int, upper_bound: int) -> int:
    ...


def xorshift128plus() -> int:
    ...


def xorshift128plus_uniform() -> float:
    ...


def pcg32() -> int:
    ...


def pcg32bounded(n: int) -> int:
    ...


def pcg32_uniform() -> float:
    ...


def pcg32inc(n: int) -> None:
    ...


def pcg32_seed(seed: int) -> None:
    ...


def xorshift128plus_seed1(seed1: int) -> None:
    ...


def xorshift128plus_seed2(seed2: int) -> None:
    ...


def pcg32_bytes(n: int) -> bytes:
    ...


def xorshift128plus_bytes(n: int) -> bytes:
    ...
