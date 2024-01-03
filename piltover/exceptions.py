class Error(Exception):
    pass


class Disconnection(Error):
    pass


class ErrorRpc(Error):
    def __init__(self, error_code: int, error_message: str):
        self.error_code = error_code
        self.error_message = error_message


class InvalidConstructorException(Error):
    pass
