from piltover.app.utils.utils import telegram_hash
from piltover.cache import Cache
from piltover.db.models import Language, LanguageString
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import LangPackString, LangPackDifference, TLObjectVector
from piltover.tl.functions.langpack import GetLanguages, GetStrings, GetLangPack, GetLanguages_72, GetLanguage, \
    GetDifference, GetDifference_72, GetLangPack_72, GetStrings_72
from piltover.worker import MessageHandler

handler = MessageHandler("langpack")


@handler.on_request(GetLanguages_72, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(GetLanguages, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_languages(request: GetLanguages | GetLanguages_72):
    # Seems like only android is using old langpack methods from api layer 72 (I may be wrong tho)
    pack = request.lang_pack if isinstance(request, GetLanguages) else "android"

    languages = await Language.filter(platform=pack)
    return TLObjectVector(
        language.to_tl()
        for language in languages
    )


@handler.on_request(GetLanguage, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_language(request: GetLanguage):
    language = await Language.get_or_none(platform=request.lang_pack, lang_code=request.lang_code)
    if not language:
        raise ErrorRpc(error_code=400, error_message="LANG_CODE_NOT_SUPPORTED")

    return language.to_tl()


@handler.on_request(GetDifference_72, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(GetDifference, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_difference(request: GetDifference | GetDifference_72) -> LangPackDifference:
    # Seems like only android is using old langpack methods from api layer 72 (I may be wrong tho)
    pack = request.lang_pack if isinstance(request, GetDifference) else "android"

    language = await Language.get_or_none(platform=pack, lang_code=request.lang_code)
    if not language:
        raise ErrorRpc(error_code=400, error_message="LANG_PACK_INVALID")

    if language.version <= request.from_version:
        return LangPackDifference(
            lang_code=language.lang_code,
            from_version=request.from_version,
            version=language.version,
            strings=[],
        )

    cache_key = f"languages:diff:{language.id}:{request.from_version}-{language.version}"
    if (cached := await Cache.obj.get(cache_key)) is not None:
        return cached

    from_version = request.from_version
    last_version = await LanguageString.filter(
        language=language, version__lte=request.from_version,
    ).order_by("-version").first().values_list("version", flat=True)
    if last_version:
        from_version = last_version

    result = LangPackDifference(
        lang_code=language.lang_code,
        from_version=request.from_version,
        version=language.version,
        strings=[
            string.to_tl()
            for string in await LanguageString.filter(language=language, version__gt=from_version)
        ]
    )

    await Cache.obj.set(cache_key, result)
    return result


@handler.on_request(GetLangPack_72, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(GetLangPack, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_langpack(request: GetLangPack | GetLangPack_72) -> LangPackDifference:
    # Seems like only android is using old langpack methods from api layer 72 (I may be wrong tho)
    pack = request.lang_pack if isinstance(request, GetLangPack) else "android"

    try:
        return await get_difference(GetDifference(
            lang_pack=pack,
            lang_code=request.lang_code,
            from_version=0,
        ))
    except ErrorRpc:
        raise ErrorRpc(error_code=400, error_message="LANG_CODE_NOT_SUPPORTED")


@handler.on_request(GetStrings_72, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(GetStrings, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_strings(request: GetStrings | GetStrings_72) -> list[LangPackString]:
    # Seems like only android is using old langpack methods from api layer 72 (I may be wrong tho)
    pack = request.lang_pack if isinstance(request, GetStrings) else "android"

    language = await Language.get_or_none(platform=pack, lang_code=request.lang_code)
    if not language:
        raise ErrorRpc(error_code=400, error_message="LANG_PACK_INVALID")

    keys_hash = telegram_hash(request.keys, 64)
    cache_key = f"languages:strings:{language.id}:{language.version}:{keys_hash}"
    if (cached := await Cache.obj.get(cache_key)) is not None:
        return cached

    result = TLObjectVector([
        string.to_tl()
        for string in await LanguageString.filter(language=language, key__in=request.keys, deleted=False)
    ])

    await Cache.obj.set(cache_key, result)
    return result
