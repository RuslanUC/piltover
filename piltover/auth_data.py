from piltover.db.models import TempAuthKey


class AuthData:
    __slots__ = ("auth_key_id", "auth_key", "is_temp",)

    def __init__(self, auth_key_id: int | None = None, auth_key: bytes | None = None, is_temp: bool = False):
        self.auth_key_id = auth_key_id
        self.auth_key = auth_key
        self.is_temp = is_temp

    def check_key(self, expected_auth_key_id: int) -> bool:
        if self.auth_key is None or expected_auth_key_id is None:
            return False
        return self.auth_key_id == expected_auth_key_id

    async def get_perm_id(self) -> int | None:
        if self.auth_key_id is None:
            return None
        if not self.is_temp:
            return self.auth_key_id

        temp = await TempAuthKey.get_or_none(id=str(self.auth_key_id)).select_related("perm_key")
        if temp is not None and temp.perm_key is not None:
            return int(temp.perm_key.id)


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
