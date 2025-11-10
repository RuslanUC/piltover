import gzip
import json
from asyncio import sleep
from base64 import b85encode
from uuid import UUID

from fastrand import xorshift128plus_bytes
from loguru import logger
from tortoise.expressions import Q, F
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.utils.utils import telegram_hash, get_image_dims
from piltover.context import request_ctx
from piltover.db.enums import FileType, StickerSetType
from piltover.db.models import User, Stickerset, File, InstalledStickerset, StickersetThumb
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import Long, StickerSetCovered, StickerSetNoCovered, InputStickerSetItem, InputDocument, \
    InputStickerSetEmpty, InputStickerSetID, InputStickerSetShortName, MaskCoords, InputDocumentEmpty, \
    InputStickerSetAnimatedEmoji, StickerSet
from piltover.tl.functions.messages import GetMyStickers, GetStickerSet, GetAllStickers, InstallStickerSet, \
    UninstallStickerSet, ReorderStickerSets, GetArchivedStickers, ToggleStickerSets
from piltover.tl.functions.stickers import CreateStickerSet, CheckShortName, ChangeStickerPosition, RenameStickerSet, \
    DeleteStickerSet, ChangeSticker, AddStickerToSet, ReplaceSticker, RemoveStickerFromSet, SetStickerSetThumb
from piltover.tl.types.messages import StickerSet as MessagesStickerSet, MyStickers, StickerSetNotModified, \
    AllStickers, AllStickersNotModified, StickerSetInstallResultSuccess, StickerSetInstallResultArchive, \
    ArchivedStickers
from piltover.utils.emoji import purely_emoji
from piltover.worker import MessageHandler

handler = MessageHandler("messages.stickers")


ord_a = ord("a")
ord_z = ord("z")
ord_0 = ord("0")
ord_9 = ord("9")
allowed_mimes = ["image/png", "image/webp", "video/webm", "application/x-tgsticker"]
set_types_to_mimes = {
    StickerSetType.STATIC: ("image/png", "image/webp"),
    StickerSetType.ANIMATED: ("application/x-tgsticker",),
    StickerSetType.VIDEO: ("video/webm",),
    StickerSetType.EMOJIS: ("image/png", "image/webp", "video/webm", "application/x-tgsticker"),
    StickerSetType.MASKS: ("image/png", "image/webp", "application/x-tgsticker"),
}


@handler.on_request(CheckShortName, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def check_stickerset_short_name(request: CheckShortName, prefix: str = "") -> bool:
    if not request.short_name or len(request.short_name) > 64:
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_INVALID")

    short_name = request.short_name.lower()
    if ord(short_name[0]) < ord_a or ord(short_name[0]) > ord_z:
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_INVALID")

    if not all(ord_0 <= ord(char) <= ord_9 or ord_a <= ord(char) <= ord_z or char == "_" for char in short_name) \
            or "__" in short_name:
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_INVALID")

    if await Stickerset.filter(short_name=request.short_name).exists():
        raise ErrorRpc(error_code=400, error_message=f"{prefix}SHORT_NAME_OCCUPIED")

    return True


# https://core.telegram.org/stickers


async def _validate_png_webp(file: File) -> None:
    if file.size > 512 * 1024:
        raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

    if file.width is None or file.height is None:
        storage = request_ctx.get().storage
        dims = await get_image_dims(storage, file.physical_id)
        if dims is None:
            raise ErrorRpc(error_code=400, error_message="STICKER_PNG_NOPNG")
        else:
            file.width, file.height = dims
            file.needs_save = True

    dims = (file.width, file.height)
    if 512 not in dims or any(dim > 512 for dim in dims):
        raise ErrorRpc(error_code=400, error_message="STICKER_PNG_DIMENSIONS")


async def _validate_tgs_layer_items(items: list, shapes: bool = True) -> bool:
    if not items:
        return True

    for item in items:
        await sleep(0)
        if item.get("ty") in ("rp", "sr", "mm", "gs"):
            return False

        if shapes and not await _validate_tgs_layer_items(item.get("id"), False):
            return False

    return True


async def _validate_tgs_layers(layers: list) -> bool:
    if not layers:
        return True

    for layer in layers:
        await sleep(0)
        if bool(layer.get("ddd")) or layer.get("sr") != 1 or layer.get("tm") is not None \
                or layer.get("ty") in (1, 2, 5) or layer.get("hasMask") or layer.get("maskProperties") is not None \
                or layer.get("tt") is not None or layer.get("ao") == 1 or layer.get("ef") is not None:
            return False

        if not await _validate_tgs_layer_items(layer.get("shapes")):
            return False

    return True


async def _validate_tgs(file: File) -> None:
    if file.size > 64 * 1024:
        raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

    storage = request_ctx.get().storage
    data = await storage.documents.get_part(file.physical_id, 0, 64 * 1024)
    try:
        data = gzip.decompress(data)
        tgs = json.loads(data)
    except (gzip.BadGzipFile, json.JSONDecodeError):
        raise ErrorRpc(error_code=400, error_message="STICKER_TGS_NOTGS")

    try:
        if tgs["tgs"] != "1" or tgs["fr"] != 60 or tgs["w"] != 512 or tgs["h"] != 512 or (tgs["op"] - tgs["ip"]) > 180\
                or bool(tgs.get("ddd")):
            raise ErrorRpc(error_code=400, error_message="STICKER_TGS_NOTGS")

        assets = tgs.get("assets") or []
        for asset in assets:
            if not await _validate_tgs_layers(asset["layers"]):
                raise ErrorRpc(error_code=400, error_message="STICKER_TGS_NOTGS")

        if not await _validate_tgs_layers(tgs["layers"]):
            raise ErrorRpc(error_code=400, error_message="STICKER_TGS_NOTGS")
    except (TypeError, ValueError, KeyError):
        raise ErrorRpc(error_code=400, error_message="STICKER_TGS_NOTGS")

    # https://github.com/TelegramMessenger/bodymovin-extension/commit/2e1dd0517a8d8346afe9fbd88cda235c4afe2c64#diff-dab7e98d55cf2baf67bc546b9d3b17846f2ef57f99eedc32d110f3f620292cbc
    # TODO: validate "Objects must not leave the canvas."
    # TODO: validate "All animations must be looped."


async def _get_sticker_files(
        stickers: list[InputStickerSetItem], user: User, set_type: StickerSetType | None,
) -> tuple[dict[int, File], StickerSetType]:
    files_q = Q()

    for input_sticker in stickers:
        emoji = input_sticker.emoji.strip()
        if not emoji or not purely_emoji(emoji):
            raise ErrorRpc(error_code=400, error_message="STICKER_EMOJI_INVALID")

        input_doc = input_sticker.document
        valid, const = File.is_file_ref_valid(input_doc.file_reference, user.id, input_doc.id)
        if not valid:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

        base_q = Q(
            id=input_doc.id, type__in=[FileType.DOCUMENT_STICKER, FileType.DOCUMENT], mime_type__in=allowed_mimes,
            stickerset=None,
        )
        if const:
            files_q |= base_q & Q(
                constant_access_hash=input_doc.access_hash, constant_file_ref=input_doc.file_reference,
            )
        else:
            ctx = request_ctx.get()
            if not File.check_access_hash(user.id, ctx.auth_id, input_doc.id, input_doc.access_hash):
                raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

    files = {file.id: file for file in await File.filter(files_q)}

    for input_sticker in stickers:
        file = files.get(input_sticker.document.id)
        if file is None:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

        if set_type is None:
            if file.mime_type in ("image/png", "image/webp"):
                set_type = StickerSetType.STATIC
            elif file.mime_type == "video/webm":
                set_type = StickerSetType.VIDEO
            elif file.mime_type == "application/x-tgsticker":
                set_type = StickerSetType.ANIMATED
            else:
                raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

        if file.mime_type not in set_types_to_mimes[set_type]:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

        if file.mime_type in ("image/png", "image/webp"):
            await _validate_png_webp(file)
        elif file.mime_type == "video/webm":
            # TODO: support video stickers
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")
        elif file.mime_type == "application/x-tgsticker":
            await _validate_tgs(file)
        else:
            raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

    return files, set_type


async def _get_sticker_thumb(input_doc: InputDocument, user: User, set_type: StickerSetType) -> File:
    file_q = Q()

    valid, const = File.is_file_ref_valid(input_doc.file_reference, user.id, input_doc.id)
    if not valid:
        raise ErrorRpc(error_code=400, error_message="STICKER_FILE_INVALID")

    base_q = Q(
        id=input_doc.id, type=FileType.DOCUMENT, mime_type__in=allowed_mimes, stickerset=None,
    )
    if const:
        file_q |= base_q & Q(
            constant_access_hash=input_doc.access_hash, constant_file_ref=input_doc.file_reference,
        )
    else:
        file_q |= base_q & Q(
            fileaccesss__user=user, fileaccesss__access_hash=input_doc.access_hash,
        )

    if (file := await File.get_or_none(file_q)) is None:
        raise ErrorRpc(error_code=400, error_message="STICKER_THUMB_PNG_NOPNG")

    if file.mime_type not in set_types_to_mimes[set_type]:
        raise ErrorRpc(error_code=400, error_message="STICKER_THUMB_PNG_NOPNG")

    if file.mime_type in ("image/png", "image/webp"):
        await _validate_png_webp(file)
    elif file.mime_type == "video/webm":
        # TODO: support video stickers
        raise ErrorRpc(error_code=400, error_message="STICKER_THUMB_PNG_NOPNG")
    elif file.mime_type == "application/x-tgsticker":
        await _validate_tgs(file)
    else:
        raise ErrorRpc(error_code=400, error_message="STICKER_THUMB_PNG_NOPNG")

    return file


async def _make_sticker_from_file(
        file: File, stickerset: Stickerset, pos: int, alt: str, mask: bool, mask_coords: MaskCoords | None,
        create: bool = True,
) -> File:
    new_file = File(
        physical_id=file.physical_id,
        created_at=file.created_at,
        mime_type=file.mime_type,
        size=file.size,
        type=FileType.DOCUMENT_STICKER,
        constant_access_hash=Long.read_bytes(xorshift128plus_bytes(8)),
        constant_file_ref=UUID(bytes=xorshift128plus_bytes(16)),
        filename=file.filename,
        width=file.width,
        height=file.height,
        duration=file.duration,
        nosound=file.nosound,
        stickerset=stickerset,
        sticker_pos=pos,
        sticker_alt=alt.strip(),
        sticker_mask=mask,
        sticker_mask_coords=b85encode(mask_coords.serialize()).decode("utf8") if mask and mask_coords else None,
    )

    if create:
        await new_file.save(force_create=True)

    return new_file


async def _make_stickerset_thumb_from_file(file: File) -> File:
    return await File.create(
        physical_id=file.physical_id,
        created_at=file.created_at,
        mime_type=file.mime_type,
        size=file.size,
        type=FileType.DOCUMENT,
        constant_access_hash=Long.read_bytes(xorshift128plus_bytes(8)),
        constant_file_ref=UUID(bytes=xorshift128plus_bytes(16)),
        filename=file.filename,
        width=file.width,
        height=file.height,
        duration=file.duration,
        nosound=file.nosound,
    )


@handler.on_request(CreateStickerSet)
async def create_sticker_set(request: CreateStickerSet, user: User) -> MessagesStickerSet:
    if not request.title or len(request.title) > 64:
        raise ErrorRpc(error_code=400, error_message="PACK_TITLE_INVALID")

    # TODO: handle request.user_id if current user is a bot

    await check_stickerset_short_name(CheckShortName(short_name=request.short_name), "PACK_")

    if not request.stickers:
        raise ErrorRpc(error_code=400, error_message="STICKERS_EMPTY")
    if len(request.stickers) > 120:
        raise ErrorRpc(error_code=400, error_message="STICKERS_TOO_MUCH")

    set_type = None
    if request.masks:
        set_type = StickerSetType.MASKS
    elif request.emojis:
        set_type = StickerSetType.EMOJIS

    files, set_type = await _get_sticker_files(request.stickers, user, set_type)
    files_to_create = []

    files_to_save = [file for file in files.values() if file.needs_save]
    if files_to_save:
        await File.bulk_update(files_to_save, fields=["width", "height"])

    stickerset = await Stickerset.create(
        title=request.title,
        short_name=request.short_name,
        type=set_type,
        owner=None,
    )

    if isinstance(request.thumb, InputDocument):
        try:
            thumb_file = await _get_sticker_thumb(request.thumb, user, set_type)
        except:
            await stickerset.delete()
            raise

        thumb_new_file = await _make_stickerset_thumb_from_file(thumb_file)
        await StickersetThumb.create(set=stickerset, file=thumb_new_file)

    for idx, input_sticker in enumerate(request.stickers):
        file = files[input_sticker.document.id]
        files_to_create.append(
            await _make_sticker_from_file(
                file, stickerset, idx, input_sticker.emoji, request.masks, input_sticker.mask_coords, False,
            )
        )

    try:
        await File.bulk_create(files_to_create)
    except Exception as e:
        logger.opt(exception=e).error("Failed to create stickerset files")
        await stickerset.delete()
        raise

    stickerset.owner = user
    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["owner_id", "hash"])

    await InstalledStickerset.create(set=stickerset, user=user)
    await upd.new_stickerset(user, stickerset)

    return await stickerset.to_tl_messages(user)


async def _get_sticker_with_set(sticker: InputDocument, user: User) -> tuple[File, Stickerset]:
    valid, const = File.is_file_ref_valid(sticker.file_reference, user.id, sticker.id)
    if not valid or not const:
        raise ErrorRpc(error_code=400, error_message="STICKER_INVALID")

    file = await File.get_or_none(
        id=sticker.id, constant_access_hash=sticker.access_hash, constant_file_ref=sticker.file_reference,
        stickerset__owner=user,
    ).select_related("stickerset")

    if file is None:
        raise ErrorRpc(error_code=400, error_message="STICKER_INVALID")

    return file, file.stickerset


@handler.on_request(ChangeStickerPosition)
async def change_sticker_position(request: ChangeStickerPosition, user: User) -> MessagesStickerSet:
    file, stickerset = await _get_sticker_with_set(request.sticker, user)

    min_pos = 0
    max_pos = await stickerset.documents_query().count() - 1
    new_pos = max(min_pos, min(max_pos, request.position))
    old_pos = request.position

    if old_pos == new_pos:
        return await stickerset.to_tl_messages(user)

    # if sticker position is, for example, 5, new position is 10 and there is 15 stickers, then we need to:
    #  1) subtract 1 from stickers with positions 6-10 (current_pos + 1, new_pos)
    #  2) change sticker position from 5 to 10
    # if sticker position is, for example, 10, new position is 5 and there is 15 stickers, then we need to:
    #  1) add 1 to stickers with positions 5-9 (new_pos, current_pos - 1)
    #  2) change sticker position from 10 to 5

    file.sticker_pos = new_pos
    if new_pos > old_pos:
        update_query = File.filter(
            stickerset=stickerset, sticker_pos__gt=old_pos, sticker_pos__lte=new_pos,
        ).update(sticker_pos=F("sticker_pos") - 1)
    else:
        update_query = File.filter(
            stickerset=stickerset, sticker_pos__gte=new_pos, sticker_pos__lt=old_pos,
        ).update(sticker_pos=F("sticker_pos") + 1)

    async with in_transaction():
        await update_query
        await file.save(update_fields=["sticker_pos"])

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(RenameStickerSet)
async def rename_stickerset(request: RenameStickerSet, user: User) -> MessagesStickerSet:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=400, error_message="STICKERSET_INVALID")

    if not request.title or len(request.title) > 64:
        raise ErrorRpc(error_code=400, error_message="STICKERSET_INVALID")

    stickerset.title = request.title
    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["title", "hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(DeleteStickerSet)
async def delete_stickerset(request: DeleteStickerSet, user: User) -> bool:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=400, error_message="STICKERSET_INVALID")

    await stickerset.delete()

    return True


async def _make_covered_list(sets: list[Stickerset], user: User) -> list[StickerSetCovered | StickerSetNoCovered]:
    sets_ids = [sset.id for sset in sets]
    covers = {file.stickerset_id: file for file in await File.filter(stickerset__id__in=sets_ids, sticker_pos=0)}

    result = []
    for stickerset in sets:
        if stickerset.id in covers:
            result.append(StickerSetCovered(
                set=await stickerset.to_tl(user),
                cover=await covers[stickerset.id].to_tl_document(user),
            ))
        else:
            result.append(StickerSetNoCovered(
                set=await stickerset.to_tl(user),
            ))

    return result


@handler.on_request(GetMyStickers, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_my_stickers(request: GetMyStickers, user: User) -> MyStickers:
    limit = max(1, min(50, request.limit))
    id_filter = Q(set__lt=request.offset_id) if request.offset_id else Q()
    stickersets = await Stickerset.filter(id_filter, owner=user).order_by("-id").limit(limit)

    return MyStickers(
        sets=await _make_covered_list(stickersets, user),
        count=await Stickerset.filter(owner=user).count(),
    )


@handler.on_request(ChangeSticker)
async def change_sticker(request: ChangeSticker, user: User) -> MessagesStickerSet:
    file, stickerset = await _get_sticker_with_set(request.sticker, user)

    update_fields = []

    if request.emoji is not None and request.emoji != file.sticker_alt:
        file.sticker_alt = request.emoji
        update_fields.append("sticker_alt")

    if request.mask_coords is not None and request.mask_coords != file.sticker_mask_coords_tl \
            and stickerset.type is StickerSetType.MASKS and file.sticker_is_mask:
        file.sticker_mask_coords = b85encode(request.mask_coords.serialize()).decode("utf8")
        update_fields.append("sticker_mask_coords")

    # TODO: keywords

    if not update_fields:
        return await stickerset.to_tl_messages(user)

    await file.save(update_fields=update_fields)

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(GetStickerSet)
async def get_stickerset(request: GetStickerSet, user: User) -> MessagesStickerSet | StickerSetNotModified:
    if isinstance(request.stickerset, InputStickerSetAnimatedEmoji):
        return MessagesStickerSet(
            set=StickerSet(
                id=1,
                access_hash=1,
                title="Telegram For Android, stfu",
                short_name="animatedemojiorwhatever",
                official=True,
                creator=False,
                installed_date=None,
                archived=False,
                count=0,
                hash=0,
                masks=False,
                emojis=False,
                thumbs=None,
                thumb_dc_id=None,
                thumb_version=None,
                thumb_document_id=None,
                text_color=False,
                channel_emoji_status=False,
            ),
            packs=[],
            keywords=[],
            documents=[],
        )

    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None:
        raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

    if request.hash == stickerset.hash:
        return StickerSetNotModified()

    return await stickerset.to_tl_messages(user)


@handler.on_request(AddStickerToSet)
async def add_sticker_to_set(request: AddStickerToSet, user: User) -> MessagesStickerSet:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

    files, _ = await _get_sticker_files([request.sticker], user, stickerset.type)
    file = files[request.sticker.document.id]

    count = await File.filter(stickerset=stickerset).count()
    if count >= 120:
        raise ErrorRpc(error_code=400, error_message="STICKERS_TOO_MUCH")

    await _make_sticker_from_file(
        file, stickerset, count, request.sticker.emoji, stickerset.type is StickerSetType.MASKS,
        request.sticker.mask_coords,
    )

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(ReplaceSticker)
async def replace_sticker(request: ReplaceSticker, user: User) -> MessagesStickerSet:
    old_file, stickerset = await _get_sticker_with_set(request.sticker, user)

    files, _ = await _get_sticker_files([request.new_sticker], user, stickerset.type)
    file = files[request.new_sticker.document.id]

    old_file.stickerset = None
    old_file.sticker_pos = None
    await old_file.save(update_fields=["stickerset_id", "sticker_pos"])

    await _make_sticker_from_file(
        file, stickerset, old_file.sticker_pos, request.new_sticker.emoji, stickerset.type is StickerSetType.MASKS,
        request.new_sticker.mask_coords
    )

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(RemoveStickerFromSet)
async def remove_sticker_from_set(request: RemoveStickerFromSet, user: User) -> MessagesStickerSet:
    file, stickerset = await _get_sticker_with_set(request.sticker, user)

    async with in_transaction():
        await file.delete()
        await File.filter(
            stickerset=stickerset, sticker_pos__gt=file.sticker_pos,
        ).update(sticker_pos=F("sticker_pos") - 1)

    stickerset.hash = telegram_hash(stickerset.gen_for_hash(await stickerset.documents_query()), 32)
    await stickerset.save(update_fields=["hash"])

    return await stickerset.to_tl_messages(user)


@handler.on_request(GetAllStickers, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_all_stickers(request: GetAllStickers, user: User) -> AllStickers | AllStickersNotModified:
    sets = await InstalledStickerset.filter(user=user, archived=False)\
        .order_by("pos", "-installed_at")\
        .select_related("set")
    sets_hash = telegram_hash((stickerset.set.id for stickerset in sets), 64)

    if sets_hash == request.hash:
        return AllStickersNotModified()

    return AllStickers(
        hash=sets_hash,
        sets=[
            await stickerset.set.to_tl(user)
            for stickerset in sets
        ]
    )


@handler.on_request(InstallStickerSet, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def install_stickerset(
        request: InstallStickerSet, user: User,
) -> StickerSetInstallResultSuccess | StickerSetInstallResultArchive:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

    installed, created = await InstalledStickerset.get_or_create(set=stickerset, user=user, defaults={
        "archived": request.archived,
    })
    if not created and installed.archived != request.archived:
        installed.archived = request.archived
        await installed.save(update_fields=["archived"])

    # TODO: archive unused stickersets so maximum number of InstalledStickerset
    #  would be 25 (?, what is the telegram's limit)

    await upd.new_stickerset(user, stickerset)

    if installed.archived:
        return StickerSetInstallResultArchive(
            sets=await _make_covered_list([stickerset], user),
        )

    return StickerSetInstallResultSuccess()


@handler.on_request(UninstallStickerSet, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def uninstall_stickerset(request: UninstallStickerSet, user: User) -> bool:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

    installed = await InstalledStickerset.get_or_none(set=stickerset, user=user)
    if installed is None:
        return True

    await installed.delete()

    await upd.update_stickersets(user)

    return True


@handler.on_request(ReorderStickerSets, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def reorder_sticker_sets(request: ReorderStickerSets, user: User) -> bool:
    sets: list[InstalledStickerset | None] = await InstalledStickerset.filter(user=user, archived=False) \
        .order_by("pos", "-installed_at").select_related("set")
    by_ids = {
        installed.set.id: (installed, idx)
        for idx, installed in enumerate(sets)
    }

    new_order = []
    for set_id in request.order:
        if set_id not in by_ids:
            continue
        stickerset, idx = by_ids[set_id]
        sets[idx] = None
        stickerset.pos = len(new_order)
        new_order.append(stickerset)

    for left_set in sets:
        if left_set is None:
            continue
        left_set.pos = len(new_order)
        new_order.append(left_set)

    await InstalledStickerset.bulk_update(new_order, fields=["pos"])

    await upd.update_stickersets_order(user, [installed.set.id for installed in new_order])

    return True


@handler.on_request(GetArchivedStickers, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_archived_stickers(request: GetArchivedStickers, user: User) -> ArchivedStickers:
    limit = max(1, min(50, request.limit))
    id_filter = Q(set__id__lt=request.offset_id) if request.offset_id else Q()
    installed_sets = await InstalledStickerset.filter(id_filter, user=user, archived=True)\
        .select_related("set")\
        .order_by("-set__id")\
        .limit(limit)

    return ArchivedStickers(
        count=await InstalledStickerset.filter(user=user, archived=True).count(),
        sets=await _make_covered_list([installed.set for installed in installed_sets], user)
    )


@handler.on_request(ToggleStickerSets, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def toggle_sticker_sets(request: ToggleStickerSets, user: User) -> bool:
    if not request.uninstall and not request.archive and not request.unarchive:
        return True
    if not request.stickersets:
        return True

    sets_q = Q()

    for input_set in request.stickersets:
        if isinstance(input_set, InputStickerSetEmpty):
            continue
        elif isinstance(input_set, InputStickerSetID):
            sets_q |= Q(set__id=input_set.id, set__access_hash=input_set.access_hash)
        elif isinstance(input_set, InputStickerSetShortName):
            sets_q |= Q(set__short_name=input_set.short_name)

        # TODO: support other InputStickerSet* constructors

    sets = await InstalledStickerset.filter(sets_q, user=user)
    if not sets:
        return True

    changed_sets = []

    if request.uninstall:
        await InstalledStickerset.filter(id__in=[installed.id for installed in sets]).delete()
    elif request.archive:
        for installed in sets:
            if not installed.archived:
                installed.archived = True
                changed_sets.append(installed)
    elif request.unarchive:
        for installed in sets:
            if installed.archived:
                installed.archived = False
                changed_sets.append(installed)

    if changed_sets:
        await InstalledStickerset.bulk_update(changed_sets, fields=["archived"])

    if request.uninstall or changed_sets:
        await upd.update_stickersets(user)

    return True


@handler.on_request(SetStickerSetThumb)
async def set_stickerset_thumb(request: SetStickerSetThumb, user: User) -> MessagesStickerSet:
    stickerset = await Stickerset.from_input(request.stickerset)
    if stickerset is None or stickerset.owner_id != user.id:
        raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

    if request.thumb is None:
        raise ErrorRpc(error_code=406, error_message="STICKER_THUMB_PNG_NOPNG")

    if isinstance(request.thumb, InputDocumentEmpty):
        await StickersetThumb.filter(set=stickerset).delete()
    elif isinstance(request.thumb, InputDocument):
        thumb_file = await _get_sticker_thumb(request.thumb, user, stickerset.type)
        thumb_new_file = await _make_stickerset_thumb_from_file(thumb_file)
        thumb = await StickersetThumb.create(set=stickerset, file=thumb_new_file)
        await StickersetThumb.filter(set=stickerset, id__lt=thumb.id).delete()
    else:
        raise RuntimeError("Unreachable")

    return await stickerset.to_tl_messages(user)


# working with stickersets:
# TODO: GetStickers

# working with recent stickers:
# TODO: GetRecentStickers
# TODO: ClearRecentStickers
# TODO: SaveRecentSticker

# working with faved stickers:
# TODO: FaveSticker
# TODO: GetFavedStickers
