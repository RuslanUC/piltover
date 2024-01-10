class Error(Exception):
    pass


class Disconnection(Error):
    def __init__(self, error: int | None = None):
        if error is not None and error > 0:
            error *= -1
        self.transport_error = error


class ErrorRpc(Error):
    def __init__(self, error_code: int, error_message: str):
        self.error_code = error_code
        self.error_message = error_message


class InvalidConstructorException(Error):
    pass
