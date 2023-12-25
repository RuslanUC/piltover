from piltover.server import MessageHandler, Client
from piltover.tl.types import CoreMessage
from piltover.tl_new import LangPackLanguage, LangPackString, LangPackDifference
from piltover.tl_new.functions.langpack import GetLanguages, GetStrings, GetLangPack

handler = MessageHandler("langpack")


# noinspection PyUnusedLocal
@handler.on_message(GetLanguages)
async def get_languages(client: Client, request: CoreMessage[GetLanguages], session_id: int):
    return [LangPackLanguage(name="Gramz", native_name="Le Gramz", lang_code="grz")]


# noinspection PyUnusedLocal
@handler.on_message(GetLangPack)
async def get_lang_pack(client: Client, request: CoreMessage[GetLangPack], session_id: int):
    return LangPackDifference(
        lang_code="US",
        from_version=1,
        version=1,
        strings=[],
    )


# noinspection PyUnusedLocal
@handler.on_message(GetStrings)
async def get_strings(client: Client, request: CoreMessage[GetStrings], session_id: int):
    return [
        LangPackString(key=key, value=key.upper()) for key in request.obj.keys
    ]
