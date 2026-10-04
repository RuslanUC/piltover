class AuthData:
    __slots__ = ("auth_key_id", "auth_key", "is_temp", "perm_auth_key_id",)

    def __init__(
            self, auth_key_id: int, auth_key: bytes, perm_auth_key_id: int | None,
    ) -> None:
        self.auth_key_id = auth_key_id
        self.auth_key = auth_key
        self.is_temp = auth_key_id != perm_auth_key_id
        self.perm_auth_key_id = perm_auth_key_id


class GenAuthData(AuthData):
    __slots__ = (
        "p", "q", "server_nonce", "new_nonce", "dh_prime", "server_nonce_bytes", "tmp_aes_key", "tmp_aes_iv", "a",
        "expires_in",
    )

    auth_key_id: int | None
    auth_key: bytes | None

    def __init__(self, p: int, q: int, server_nonce: int) -> None:
        super().__init__(0, b"", None)

        self.auth_key_id = None
        self.auth_key = None

        self.p = p
        self.q = q
        self.server_nonce = server_nonce
        self.new_nonce: bytes | None = None
        self.server_nonce_bytes: bytes | None = None
        self.tmp_aes_key: bytes | None = None
        self.tmp_aes_iv: bytes | None = None
        self.a: int | None = None
        self.expires_in: int = 0
