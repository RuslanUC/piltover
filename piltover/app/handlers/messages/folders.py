from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.models import User, DialogFolder
from piltover.exceptions import ErrorRpc
from piltover.tl import DialogFilterDefault, DialogFilter, DialogFilterChatlist
from piltover.tl.functions.messages import GetDialogFilters, UpdateDialogFilter, UpdateDialogFiltersOrder
from piltover.tl.types.messages import DialogFilters
from piltover.worker import MessageHandler

handler = MessageHandler("messages.stubs")

@handler.on_request(GetDialogFilters)
async def get_dialog_filters(user: User) -> DialogFilters:
    folders: list[DialogFilter | DialogFilterDefault | DialogFilterChatlist]
    folders = [
        await folder.to_tl()
        for folder in await DialogFolder.filter(owner=user).order_by("position", "id")
    ]
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

        await UpdatesManager.update_folder(user, request.id, None)
        return True

    if not request.filter.title or len(request.filter.title) > 12:
        raise ErrorRpc(error_code=400, error_message="FILTER_TITLE_EMPTY")

    if folder is None:
        folder = DialogFolder(
            owner=user,
            name="",
            id_for_user=request.id,
            position=0,
        )
        # TODO: fill pinned_peers, include_peers, and exclude_peers
        folder.fill_from_tl(request.filter)
        await folder.save()

        await UpdatesManager.update_folder(user, request.id, folder)
        return True

    updated_fields = folder.get_difference(request.filter)
    if not updated_fields:
        return True

    # TODO: fill pinned_peers, include_peers, and exclude_peers
    folder.fill_from_tl(request.filter)
    await folder.save(update_fields=updated_fields)

    await UpdatesManager.update_folder(user, request.id, folder)
    return True


@handler.on_request(UpdateDialogFiltersOrder)
async def update_dialog_filters_order(request: UpdateDialogFiltersOrder, user: User) -> bool:
    folders = {
        folder.id_for_user: folder
        for folder in await DialogFolder.filter(owner=user)
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

    await UpdatesManager.update_folders_order(user, folder_ids)
    return True