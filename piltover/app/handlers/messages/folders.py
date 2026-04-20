import piltover.app.utils.updates_manager as upd
from piltover.db.models import DialogFolder
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import DialogFilterDefault, TextWithEntities, TLObjectVector
from piltover.tl.functions.messages import GetDialogFilters, UpdateDialogFilter, UpdateDialogFiltersOrder, \
    GetDialogFilters_133
from piltover.tl.types.messages import DialogFilters
from piltover.worker import MessageHandler

handler = MessageHandler("messages.folders")


@handler.on_request(GetDialogFilters_133, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(GetDialogFilters, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_dialog_filters(user_id: int) -> DialogFilters:
    folders = TLObjectVector()
    dialog_folders = await DialogFolder.filter(
        owner_id=user_id, id_for_user__gt=0,
    ).prefetch_related("pinned_peers", "include_peers", "exclude_peers").order_by("position", "id")
    for folder in dialog_folders:
        folders.append(folder.to_tl())

    if folders:
        folders.insert(0, DialogFilterDefault())

    return DialogFilters(
        filters=folders,
        tags_enabled=False,
    )


@handler.on_request(UpdateDialogFilter, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def update_dialog_filter(request: UpdateDialogFilter, user_id: int) -> bool:
    if request.id < 2 or request.id >= (2 ** 15 - 1):
        raise ErrorRpc(error_code=400, error_message="FILTER_ID_INVALID")

    folder = await DialogFolder.get_or_none(owner_id=user_id, id_for_user=request.id)

    if request.filter is None and folder is None:
        return True
    elif request.filter is None and folder is not None:
        await folder.delete()

        await upd.update_folder(user_id, request.id, None)
        return True

    title = request.filter.title
    title_text = title.text if isinstance(title, TextWithEntities) else title
    if not title_text or len(title_text) > 12:
        raise ErrorRpc(error_code=400, error_message="FILTER_TITLE_EMPTY")

    if folder is None:
        folder = await DialogFolder.create(
            owner_id=user_id,
            name="",
            id_for_user=-1,
            position=0,
        )
        folder.id_for_user = request.id
        await folder.fill_from_tl(request.filter)
        await folder.save()

        folder = await DialogFolder.get(id=folder.id).prefetch_related("pinned_peers", "include_peers", "exclude_peers")
        await upd.update_folder(user_id, request.id, folder)
        return True

    updated_fields = folder.get_difference(request.filter)
    if not updated_fields:
        return True

    await folder.fill_from_tl(request.filter)
    await folder.save(update_fields=updated_fields)

    folder = await DialogFolder.get(id=folder.id).prefetch_related("pinned_peers", "include_peers", "exclude_peers")
    await upd.update_folder(user_id, request.id, folder)
    return True


@handler.on_request(UpdateDialogFiltersOrder, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def update_dialog_filters_order(request: UpdateDialogFiltersOrder, user_id: int) -> bool:
    folders = {
        folder.id_for_user: folder
        for folder in await DialogFolder.filter(owner_id=user_id, id_for_user__gt=0)
    }
    new_order = []

    for folder_id in request.order:
        if folder_id < 2 or folder_id >= (2 ** 15 - 1) or folder_id not in folders:
            continue
        folder = folders.pop(folder_id)
        folder.position = len(new_order)
        new_order.append(folder)

    for folder in sorted(folders.values(), key=lambda f: f.position):
        folder.position = len(new_order)
        new_order.append(folder)

    await DialogFolder.bulk_update(new_order, fields=["position"])

    folder_ids = [folder.id_for_user for folder in new_order]
    folder_ids.insert(0, 0)

    await upd.update_folders_order(user_id, folder_ids)
    return True
