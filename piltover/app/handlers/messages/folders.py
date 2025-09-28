import piltover.app.utils.updates_manager as upd
from piltover.db.models import User, DialogFolder
from piltover.exceptions import ErrorRpc
from piltover.tl import DialogFilterDefault, TextWithEntities, TLObjectVector
from piltover.tl.functions.messages import GetDialogFilters, UpdateDialogFilter, UpdateDialogFiltersOrder, \
    GetDialogFilters_133
from piltover.tl.types.messages import DialogFilters
from piltover.worker import MessageHandler

handler = MessageHandler("messages.folders")


@handler.on_request(GetDialogFilters_133)
@handler.on_request(GetDialogFilters)
async def get_dialog_filters(user: User) -> DialogFilters:
    folders = TLObjectVector()
    for folder in await DialogFolder.filter(owner=user, id_for_user__gt=0).order_by("position", "id"):
        folders.append(await folder.to_tl())

    if folders:
        folders.insert(0, DialogFilterDefault())

    return DialogFilters(
        filters=folders,
        tags_enabled=False,
    )


@handler.on_request(UpdateDialogFilter)
async def update_dialog_filter(request: UpdateDialogFilter, user: User) -> bool:
    if request.id < 2 or request.id >= (2 ** 15 - 1):
        raise ErrorRpc(error_code=400, error_message="FILTER_ID_INVALID")

    folder = await DialogFolder.get_or_none(owner=user, id_for_user=request.id)

    if request.filter is None and folder is None:
        return True
    elif request.filter is None and folder is not None:
        await folder.delete()

        await upd.update_folder(user, request.id, None)
        return True

    title = request.filter.title
    title_text = title.text if isinstance(title, TextWithEntities) else title
    if not title_text or len(title_text) > 12:
        raise ErrorRpc(error_code=400, error_message="FILTER_TITLE_EMPTY")

    if folder is None:
        folder = await DialogFolder.create(
            owner=user,
            name="",
            id_for_user=-1,
            position=0,
        )
        folder.id_for_user = request.id
        await folder.fill_from_tl(request.filter)
        await folder.save()

        await upd.update_folder(user, request.id, folder)
        return True

    updated_fields = folder.get_difference(request.filter)
    if not updated_fields:
        return True

    await folder.fill_from_tl(request.filter)
    await folder.save(update_fields=updated_fields)

    await upd.update_folder(user, request.id, folder)
    return True


@handler.on_request(UpdateDialogFiltersOrder)
async def update_dialog_filters_order(request: UpdateDialogFiltersOrder, user: User) -> bool:
    folders = {
        folder.id_for_user: folder
        for folder in await DialogFolder.filter(owner=user, id_for_user__gt=0)
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

    await upd.update_folders_order(user, folder_ids)
    return True