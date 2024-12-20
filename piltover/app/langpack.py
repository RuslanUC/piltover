from piltover.high_level import MessageHandler
from piltover.tl import LangPackLanguage, LangPackString, LangPackDifference, LangPackLanguage_72
from piltover.tl.functions.langpack import GetLanguages, GetStrings, GetLangPack, GetLanguages_72

handler = MessageHandler("langpack")


@handler.on_request(GetLanguages)
async def get_languages():
    return [LangPackLanguage(
        name="Gramz",
        native_name="Le Gramz",
        lang_code="grz",
        plural_code="",
        strings_count=1,
        translated_count=1,
        translations_url="https://127.0.0.1/translations",
    )]


@handler.on_request(GetLanguages_72)
async def get_languages_72():
    return [LangPackLanguage_72(name="Gramz", native_name="Le Gramz", lang_code="grz")]


@handler.on_request(GetLangPack)
async def get_lang_pack():
    return LangPackDifference(
        lang_code="US",
        from_version=1,
        version=1,
        strings=[],
    )


@handler.on_request(GetStrings)
async def get_strings(request: GetStrings):
    return [
        LangPackString(key=key, value=key.upper()) for key in request.keys
    ]
