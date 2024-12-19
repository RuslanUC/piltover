from dataclasses import dataclass
from hashlib import sha1

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@dataclass(slots=True)
class Keys:
    public_key: str
    private_key: str


def write_bytes(value: bytes) -> bytes:
    length = len(value)

    if length <= 253:
        return bytes([length]) + value + bytes(-(length + 1) % 4)

    return bytes([254]) + length.to_bytes(3, "little") + value + bytes(-length % 4)


def get_public_key_fingerprint(public_key: str, signed: bool = False) -> int:
    # https://core.telegram.org/mtproto/auth_key#dh-exchange-initiation
    # server_public_key_fingerprints is a list of public RSA key fingerprints
    # (64 lower-order bits of SHA1 (server_public_key);

    key = load_public_key(public_key=public_key)
    num = key.public_numbers()  # type: ignore
    n, e = num.n, num.e  # type: ignore

    n_bytes = n.to_bytes((n.bit_length() + 7) // 8, "big", signed=False)
    e_bytes = e.to_bytes((e.bit_length() + 7) // 8, "big", signed=False)

    rsa_public_key = write_bytes(n_bytes) + write_bytes(e_bytes)
    return int.from_bytes(sha1(rsa_public_key).digest()[-8:], "little", signed=signed)


def load_private_key(private_key: str):
    return serialization.load_pem_private_key(private_key.encode(), password=None)


def load_public_key(public_key: str):
    return serialization.load_pem_public_key(public_key.encode())


def gen_keys() -> Keys:
    # https://dev.to/aaronktberry/generating-encrypted-key-pairs-in-python-69b

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    unencrypted_pem_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pem_public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.PKCS1
    )

    private_key = unencrypted_pem_private_key.decode().strip()
    public_key = pem_public_key.decode().strip()

    return Keys(
        private_key=private_key,
        public_key=public_key,
    )
