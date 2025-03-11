from os import environ
from typing import TypedDict


class _ConfigDcOptionAddress(TypedDict):
    ip: str
    port: int


class _ConfigDcOption(TypedDict):
    dc_id: int
    addresses: list[_ConfigDcOptionAddress]


_dc_count = int(environ.get("DC_COUNT", 5))
_this_dc_id = int(environ.get("THIS_DC_ID", 2))
if _this_dc_id > _dc_count or _this_dc_id <= 0:
    raise ValueError(f"\"THIS_DC_ID\" must be between 1 and {_dc_count}!")

_dcs: list[_ConfigDcOption] = []
_this_dc: _ConfigDcOption | None = None
for _dc in range(1, _dc_count + 1):
    dc = {"dc_id": _dc, "addresses": []}
    _dcs.append(dc)
    if _dc == _this_dc_id:
        _this_dc = dc

    dc_address_count = int(environ.get(f"DC_{_dc}_ADDRESS_COUNT", 1))
    if not dc_address_count:
        raise ValueError(
            f"Dc {_dc} does not have any ip addresses associated with it! Add at least one or remove dc!"
            f"Note: you can just set \"DC_{_dc}_ADDRESS_COUNT\" to 1 without setting it's ip and port, "
            f"then address will be set to default value of \"127.0.0.1:4430\"."
        )
    for _addr_num in range(1, dc_address_count + 1):
        dc["addresses"].append({
            "ip": environ.get(f"DC_{_dc}_ADDRESS_{_addr_num}_IP", "127.0.0.1"),
            "port": int(environ.get(f"DC_{_dc}_ADDRESS_{_addr_num}_PORT", 4430)),
        })


if _this_dc is None:
    raise ValueError("Current dc info was not initialized!")


class AppConfig:
    NAME: str = environ.get("APP_NAME", "Piltover")
    SYS_USER_USERNAME: str = environ.get("APP_SYSTEM_USERNAME", NAME.lower())
    DCS: list[_ConfigDcOption] = _dcs
    THIS_DC_ID: int = _this_dc_id
    THIS_DC: _ConfigDcOption = _this_dc
    BASIC_GROUP_MEMBER_LIMIT = int(environ.get("BASIC_GROUP_MEMBER_LIMIT", 50))
    SUPER_GROUP_MEMBER_LIMIT = int(environ.get("SUPER_GROUP_MEMBER_LIMIT", 1000))
    EDIT_TIME_LIMIT = int(environ.get("MESSAGE_EDIT_TIME_LIMIT", 48 * 60 * 60))
    # TODO: add REVOKE_TIME_LIMIT and default it to 2 ** 31 - 1
    MAX_MESSAGE_LENGTH = int(environ.get("MAX_MESSAGE_LENGTH", 4096))
    MAX_CAPTION_LENGTH = int(environ.get("MAX_CAPTION_LENGTH", 2048))
