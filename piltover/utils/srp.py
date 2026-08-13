import hashlib

from piltover.utils import gen_safe_prime


def btoi(b: bytes) -> int:
    return int.from_bytes(b, "big")


def itob(i: int) -> bytes:
    return i.to_bytes(256, "big")


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


p, g = gen_safe_prime()
SRP_K = btoi(sha256d(itob(p) + itob(g)))
