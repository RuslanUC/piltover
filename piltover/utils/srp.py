import hashlib

from piltover.utils import gen_safe_prime


def btoi(b: bytes) -> int:
    return int.from_bytes(b, "big")


def itob(i: int) -> bytes:
    return i.to_bytes(256, "big")


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def salted_hash(data: bytes, salt: bytes) -> bytes:
    return sha256d(salt + data + salt)


def PH1(password: bytes, salt1: bytes, salt2: bytes) -> bytes:
    return salted_hash(salted_hash(password, salt1), salt2)


def PH2(password: bytes, salt1: bytes, salt2: bytes) -> bytes:
    return salted_hash(hashlib.pbkdf2_hmac("sha512", PH1(password, salt1, salt2), salt1, 100000), salt2)


p, g = gen_safe_prime()
SRP_K = btoi(sha256d(itob(p) + itob(g)))
