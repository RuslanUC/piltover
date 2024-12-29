from time import time
from typing import cast

from tortoise.queryset import QuerySet

from piltover.context import request_ctx, RequestContext
from piltover.db.enums import UpdateType, PeerType
from piltover.db.models import User, Message, State, UpdateV2, MessageDraft, Peer, Dialog
from piltover.session_manager import SessionManager
from piltover.tl import Updates, UpdateShortSentMessage, UpdateShortMessage, UpdateNewMessage, UpdateMessageID, \
    UpdateReadHistoryInbox, UpdateEditMessage, UpdateDialogPinned, DraftMessageEmpty, UpdateDraftMessage, \
    UpdatePinnedDialogs, DialogPeer, UpdatePinnedMessages
from piltover.tl.functions.messages import SendMessage
from piltover.utils.utils import SingletonMeta


class UpdatesManager(metaclass=SingletonMeta):
    @staticmethod
    async def send_message(
            user: User, messages: dict[Peer, Message], has_media: bool = False
    ) -> Updates | UpdateShortSentMessage:
        ctx: RequestContext[SendMessage] = request_ctx.get()
        client = ctx.client

        result = None

        for peer, message in messages.items():
            if isinstance(peer.owner, QuerySet):
                await peer.fetch_related("owner")

            is_current_user = peer.owner == user

            if peer.type is PeerType.SELF and (not has_media or is_current_user):
                updates = Updates(
                    updates=[
                        UpdateNewMessage(
                            message=await message.to_tl(user),
                            pts=await State.add_pts(user, 1),
                            pts_count=1,
                        ),
                        UpdateReadHistoryInbox(
                            peer=peer.to_tl(),
                            max_id=message.id,
                            still_unread_count=0,
                            pts=await State.add_pts(user, 1),
                            pts_count=1,
                        )
                    ],
                    users=[await user.to_tl(user)],
                    chats=[],
                    date=int(time()),
                    seq=0,
                )

                if message.random_id:
                    updates.updates.insert(0, UpdateMessageID(id=message.id, random_id=message.random_id))

                # TODO: also create this update if peer.type is not self
                read_history_inbox_args = {
                    "update_type": UpdateType.READ_HISTORY_INBOX, "user": user, "related_id": 0,
                }
                await UpdateV2.filter(**read_history_inbox_args).delete()
                await UpdateV2.create(
                    **read_history_inbox_args, pts=updates.updates[-1].pts, related_ids=[message.id, 0]
                )

                await SessionManager().send(updates, user.id, exclude=[client])
                if is_current_user:
                    result = updates
            elif has_media:
                updates = Updates(
                    updates=[UpdateNewMessage(
                        message=await message.to_tl(peer.owner),
                        pts=await State.add_pts(peer.owner, 1),
                        pts_count=1,
                    )],
                    users=[await upd_peer.user.to_tl(peer.owner) for upd_peer in messages.keys()],
                    chats=[],
                    date=message.utime(),
                    seq=0,
                )
                await SessionManager().send(updates, peer.owner.id)
            elif peer.type is PeerType.USER:
                msg_tl = await message.to_tl(peer.owner)

                update = UpdateShortMessage(
                    out=True,
                    id=message.id,
                    user_id=peer.user_id,
                    message=message.message,
                    pts=await State.add_pts(peer.owner, 1),
                    pts_count=1,
                    date=message.utime(),
                    reply_to=msg_tl.reply_to,
                )
                await SessionManager().send(update, peer.owner.id, exclude=[client])
                sent_pts = update.pts

                if is_current_user:
                    result = UpdateShortSentMessage(
                        out=True, id=message.id, pts=sent_pts, pts_count=1, date=message.utime()
                    )

        return result

    @staticmethod
    async def delete_messages(user: User, messages: dict[User, list[int]]) -> int:
        updates_to_create = []

        for update_user, message_ids in messages.items():
            if user == update_user:
                continue

            pts_count = len(message_ids)
            pts = await State.add_pts(update_user, pts_count)

            update = UpdateV2(
                user=update_user,
                update_type=UpdateType.MESSAGE_DELETE,
                pts=pts,
                related_id=None,
                related_ids=message_ids,
            )
            updates_to_create.append(update)

            await SessionManager().send(
                Updates(
                    updates=[await update.to_tl(update_user)],
                    users=[],
                    chats=[],
                    date=int(time()),
                    seq=0,
                ),
                update_user.id
            )

        all_ids = [i for ids in messages.values() for i in ids]
        new_pts = await State.add_pts(user, len(all_ids))
        update = UpdateV2(
            user=user,
            update_type=UpdateType.MESSAGE_DELETE,
            pts=new_pts,
            related_id=None,
            related_ids=all_ids,
        )
        updates_to_create.append(update)

        await UpdateV2.filter(related_id__in=all_ids).delete()
        await UpdateV2.bulk_create(updates_to_create)

        updates = Updates(updates=[await update.to_tl(user)], users=[], chats=[], date=int(time()), seq=0)
        await SessionManager().send(updates, user.id)

        return new_pts

    @staticmethod
    async def edit_message(user: User, messages: dict[Peer, Message]) -> Updates:
        updates_to_create = []
        result_update = None

        for peer, message in messages.items():
            if isinstance(peer.owner, QuerySet):
                await peer.fetch_related("owner")

            pts = await State.add_pts(peer.owner, 1)

            updates_to_create.append(
                UpdateV2(
                    user=peer.owner,
                    update_type=UpdateType.MESSAGE_EDIT,
                    pts=pts,
                    related_id=message.id,
                )
            )

            update = Updates(
                updates=[
                    UpdateEditMessage(
                        message=await message.to_tl(peer.owner),
                        pts=pts,
                        pts_count=1,
                    )
                ],
                users=[await message.author.to_tl(peer.owner)],
                chats=[],
                date=int(time()),
                seq=0,
            )

            if user.id == peer.owner.id:
                result_update = update

            await SessionManager().send(update, peer.owner.id)

        await UpdateV2.bulk_create(updates_to_create)
        return result_update

    @staticmethod
    async def pin_dialog(user: User, peer: Peer) -> None:
        new_pts = await State.add_pts(user, 1)
        update = await UpdateV2.create(
            user=user,
            update_type=UpdateType.DIALOG_PIN,
            pts=new_pts,
            related_id=peer.user.id,
        )

        users = {user.id: user}
        tl_update = await update.to_tl(user, users)

        updates = Updates(
            updates=[cast(UpdateDialogPinned, tl_update)],
            users=[await other.to_tl(user) for other in users.values()],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager().send(updates, user.id)

    @staticmethod
    async def update_draft(user: User, peer: Peer, draft: MessageDraft | None) -> None:
        if isinstance(draft, MessageDraft):
            draft = draft.to_tl()
        elif draft is None:
            draft = DraftMessageEmpty()

        new_pts = await State.add_pts(user, 1)
        await UpdateV2.create(
            user=user,
            update_type=UpdateType.DRAFT_UPDATE,
            pts=new_pts,
            related_id=peer.id,
        )

        updates = Updates(
            updates=[UpdateDraftMessage(peer=peer.to_tl(), draft=draft)],
            users=[await user.to_tl(user)],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager().send(updates, user.id)

    @staticmethod
    async def reorder_pinned_dialogs(user: User, dialogs: list[Dialog]) -> None:
        new_pts = await State.add_pts(user, 1)

        await UpdateV2.create(
            user=user,
            update_type=UpdateType.DIALOG_PIN_REORDER,
            pts=new_pts,
            related_id=None,
        )

        updates = Updates(
            updates=[
                UpdatePinnedDialogs(
                    order=[
                        DialogPeer(peer=dialog.peer.to_tl())
                        for dialog in dialogs
                    ],
                )
            ],
            users=[await user.to_tl(user)],
            chats=[],
            date=int(time()),
            seq=0,
        )

        await SessionManager().send(updates, user.id)

    @staticmethod
    async def pin_message(user: User, messages: dict[Peer, Message]) -> Updates:
        updates_to_create = []
        result_update = None

        for peer, message in messages.items():
            if isinstance(peer.owner, QuerySet):
                await peer.fetch_related("owner")

            pts = await State.add_pts(peer.owner, 1)

            updates_to_create.append(
                UpdateV2(
                    user=peer.owner,
                    update_type=UpdateType.MESSAGE_PIN_UPDATE,
                    pts=pts,
                    related_id=message.id,
                )
            )

            update = Updates(
                updates=[
                    UpdatePinnedMessages(
                        pinned=message.pinned,
                        peer=message.peer.to_tl(),
                        messages=[message.id],
                        pts=pts,
                        pts_count=1,
                    )
                ],
                users=[await message.author.to_tl(peer.owner)],
                chats=[],
                date=int(time()),
                seq=0,
            )

            if user.id == peer.owner.id:
                result_update = update

            await SessionManager().send(update, peer.owner.id)

        await UpdateV2.bulk_create(updates_to_create)
        return result_update
