class AuthData:
    __slots__ = ("auth_key_id", "auth_key", "is_temp", "perm_auth_key_id",)

    def __init__(
            self, auth_key_id: int | None = None, auth_key: bytes | None = None, perm_auth_key_id: int | None = None,
    ) -> None:
        self.auth_key_id = auth_key_id
        self.auth_key = auth_key
        self.is_temp = auth_key_id != perm_auth_key_id
        self.perm_auth_key_id = perm_auth_key_id

    def check_key(self, expected_auth_key_id: int) -> bool:
        if self.auth_key is None or expected_auth_key_id is None:
            return False
        return self.auth_key_id == expected_auth_key_id


class GenAuthData(AuthData):
    __slots__ = (
        "p", "q", "server_nonce", "new_nonce", "dh_prime", "server_nonce_bytes", "tmp_aes_key", "tmp_aes_iv", "a",
        "expires_in",
    )

    def __init__(self):
        super().__init__()

        self.p: int | None = None
        self.q: int | None = None
        self.server_nonce: int | None = None
        self.new_nonce: bytes | None = None
        self.server_nonce_bytes: ... | None = None
        self.tmp_aes_key: bytes | None = None
        self.tmp_aes_iv: bytes | None = None
        self.a: int | None = None
        self.expires_in: int = 0
