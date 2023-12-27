from piltover.utils import nameof


class Error(Exception):
    pass


class Disconnection(Error):
    pass


class InvalidConstructor(Error):
    def __init__(self, cid: int):
        super().__init__()
        self.cid = cid

    def __str__(self) -> str:
        return f"{nameof(self)}(cid=0x{self.cid:08x})"


class ErrorRpc(Error):
    def __init__(self, error_code: int, error_message: str):
        self.error_code = error_code
        self.error_message = error_message
