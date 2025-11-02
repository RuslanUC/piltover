from piltover.enums import ReqHandlerFlags
from piltover.tl import LangPackLanguage, LangPackString, LangPackDifference, LangPackLanguage_72, TLObjectVector
from piltover.tl.functions.langpack import GetLanguages, GetStrings, GetLangPack, GetLanguages_72
from piltover.worker import MessageHandler

handler = MessageHandler("langpack")


@handler.on_request(GetLanguages, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_languages():  # pragma: no cover
    return TLObjectVector([
        LangPackLanguage(
            name="Gramz",
            native_name="Le Gramz",
            lang_code="grz",
            plural_code="",
            strings_count=1,
            translated_count=1,
            translations_url="https://127.0.0.1/translations",
        ),
    ])


@handler.on_request(GetLanguages_72, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_languages_72():  # pragma: no cover
    return TLObjectVector([LangPackLanguage(
        name="Gramz",
        native_name="Le Gramz",
        lang_code="grz",
        plural_code="idk",
        strings_count=0,
        translated_count=0,
        translations_url="http://127.0.0.1"
    )])


@handler.on_request(GetLangPack, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_lang_pack():  # pragma: no cover
    return LangPackDifference(
        lang_code="US",
        from_version=1,
        version=1,
        strings=[],
    )


@handler.on_request(GetStrings, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_strings(request: GetStrings):  # pragma: no cover
    return TLObjectVector([
        LangPackString(key=key, value=key.upper()) for key in request.keys
    ])
