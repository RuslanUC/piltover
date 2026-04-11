from __future__ import annotations

import hashlib
import hmac
from asyncio import Queue, Event
from time import time
from typing import cast, TYPE_CHECKING

from loguru import logger
from tortoise.expressions import F, Q

import piltover
from piltover.auth_data import AuthData
from piltover.cache import Cache
from piltover.context import ContextValues, SerializationContext
from piltover.db.enums import PrivacyRuleKeyType
from piltover.db.models import UserAuthorization, AuthKey, ChatParticipant, PollVote, Contact, PrivacyRule, Presence, \
    Peer, MessageRef, InstalledStickerset
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import Updates, Long, Int
from piltover.tl.core_types import TLObject, Message, MsgContainer
from piltover.tl.types.internal import ObjectWithLayerRequirement, TaggedLongVector, NeedsContextValues
from piltover.tl.utils import is_content_related
from piltover.utils.debug import measure_time

if TYPE_CHECKING:
    from piltover.gateway import Client


class Salt:
    __slots__ = ("salt", "valid_at",)

    def __init__(self, salt: bytes, valid_at: int) -> None:
        self.salt = salt
        self.valid_at = valid_at


class MsgIdValues:
    __slots__ = ("last_time", "offset",)

    def __init__(self, last_time: int = 0, offset: int = 0) -> None:
        self.last_time = last_time
        self.offset = offset


# TODO: store sessions in redis or something (with non-acked messages) to be able to restore session after reconnect
class Session:
    __slots__ = (
        "client", "session_id", "auth_data", "min_msg_id", "user_id", "auth_id", "channel_ids", "auth_loaded_at",
        "channels_loaded_at", "salt_now", "salt_prev", "no_updates", "layer", "is_bot", "mfa_pending", "msg_id_values",
        "out_seq_no", "message_queue", "message_available",
    )

    def __init__(self, session_id: int, client: Client | None = None, auth_data: AuthData | None = None) -> None:
        self.client = client
        self.session_id = session_id
        self.auth_data = auth_data

        self.min_msg_id = 0
        self.msg_id_values = MsgIdValues()
        self.out_seq_no = 0

        self.user_id: int | None = None
        self.auth_id: int | None = None
        self.is_bot = False
        self.mfa_pending = False
        self.auth_loaded_at = 0.

        self.channel_ids: list[int] = []
        self.channels_loaded_at = 0.

        self.salt_now = Salt(b"\x00" * 8, 0)
        self.salt_prev = Salt(b"\x00" * 8, 0)

        self.no_updates = False
        self.layer = 133

        self.message_queue = Queue()
        self.message_available: Event | None = None

        # TODO: store request states (i.e. received, processing, acked, etc.)
        # TODO: store whole session in redis or something

    def uniq_id(self) -> tuple[int, int]:
        key_id = 0 if self.auth_data is None else self.auth_data.auth_key_id
        return key_id, self.session_id

    def __hash__(self) -> int:
        return hash(self.uniq_id)

    # TODO: rewrite
    def connect(self, client: Client) -> None:
        # TODO: raise AuthKeyDuplicated if self.client is not None
        self.client = client
        self.message_available = client.message_available
        if not self.message_queue.empty():
            self.message_available.set()
        piltover.session.SessionManager.broker.subscribe(self)

    # TODO: rewrite
    def disconnect(self) -> None:
        self.client = None
        self.message_available = None
        # TODO: clear message_queue
        piltover.session.SessionManager.broker.unsubscribe(self)
        piltover.session.SessionManager.cleanup(self)

    @staticmethod
    def _get_attr_or_element(obj: TLObject | list, field_name: str) -> TLObject | list:
        if isinstance(obj, list):
            return obj[int(field_name)]
        else:
            return getattr(obj, field_name)

    async def enqueue(self, obj: TLObject, in_reply: bool) -> None:
        if self.client is None:
            return

        if isinstance(obj, ObjectWithLayerRequirement):
            field_paths = obj.fields
            obj = obj.object

            for field_path in field_paths:
                if field_path.min_layer <= self.layer <= field_path.max_layer:
                    continue

                field_path = field_path.field.split(".")
                parent = obj
                for field_name in field_path[:-1]:
                    parent = self._get_attr_or_element(parent, field_name)

                if not isinstance(parent, list):
                    continue

                del parent[int(field_path[-1])]

        context_values = None
        if isinstance(obj, NeedsContextValues):
            with measure_time("._resolve_context_values(...)"):
                context_values = await self._resolve_context_values(obj)
            obj = obj.obj

        # TODO: use *ToFormat?
        if isinstance(obj, Updates) and self.auth_id is not None:
            await UserAuthorization.filter(id=self.auth_id).update(upd_seq=F("upd_seq") + 1)
            seq_and_qts = await UserAuthorization.get_or_none(id=self.auth_id).values_list("upd_seq", "upd_qts")
            if seq_and_qts is None:
                upd_seq = upd_qts = 0
            else:
                upd_seq, upd_qts = seq_and_qts
            logger.trace(f"setting seq to {upd_seq} for user {self.user_id}, auth {self.auth_id}")
            obj.seq = upd_seq
            obj.qts = upd_qts

        with measure_time("session.pack_message(...)"):
            message = self.pack_message(obj, in_reply)

        logger.debug(f"Queueing message {message.message_id} to {self.session_id}: {message!r}")
        logger.debug(f"SerializationContext: {self.user_id=}, {self.auth_id=}")

        with measure_time("<serialize message>"):
            with SerializationContext(
                    auth_id=self.auth_id, user_id=self.user_id, layer=self.layer, values=context_values
            ).use():
                self.message_queue.put_nowait((message.message_id, message.seq_no, message.obj.write()))

        if self.message_available is not None:
            self.message_available.set()

        if isinstance(obj, Updates):
            obj.seq = 0
            obj.qts = 0

    @staticmethod
    def make_salt(salt_key: bytes, auth_key_id: int, timestamp: int) -> bytes:
        return hmac.new(salt_key, Long.write(auth_key_id) + Int.write(timestamp), hashlib.sha1).digest()[:8]

    # TODO: store salt_key in session?
    def update_salts_maybe(self, salt_key: bytes, force: bool = False) -> None:
        if self.auth_data is None or self.auth_data.auth_key_id is None:
            self.salt_now = self.salt_prev = (b"\x00" * 8, 0)
            return

        now = int(time() // (30 * 60))
        if self.salt_now.valid_at == now and not force:
            return

        self.salt_now.salt = self.make_salt(salt_key, self.auth_data.auth_key_id, now)
        self.salt_now.valid_at = now

        self.salt_prev.salt = self.make_salt(salt_key, self.auth_data.auth_key_id, now - 1)
        self.salt_now.valid_at = now - 1

    async def fetch_layer(self) -> None:
        if self.auth_data.perm_auth_key_id is None:
            return

        perm_key_layer = cast(
            int | None,
            await AuthKey.get_or_none(id=self.auth_data.perm_auth_key_id).values_list("layer", flat=True),
        )
        if perm_key_layer is not None:
            self.layer = perm_key_layer

    def _reset_auth(self) -> None:
        piltover.session.SessionManager.broker.unsubscribe_auth(self.auth_id, self)
        piltover.session.SessionManager.broker.unsubscribe_user(self.user_id, self)
        piltover.session.SessionManager.broker.channels_diff_update(self, self.channel_ids, [])

        self.user_id = None
        self.auth_id = None
        self.is_bot = False
        self.mfa_pending = False
        self.channel_ids.clear()

    async def refresh_auth_maybe(self, force_refresh_auth: bool = False) -> None:
        if force_refresh_auth:
            self.auth_data = await AuthKey.get_auth_data(self.auth_data.auth_key_id)

        auth_key_id = self.auth_data.auth_key_id
        perm_auth_key_id = self.auth_data.perm_auth_key_id

        old_user_id = self.user_id
        old_auth_id = self.auth_id

        if auth_key_id is None or perm_auth_key_id is None:
            self._reset_auth()
            return

        # TODO: dont try to refetch auth every time if it is None?
        if (time() - self.auth_loaded_at) > 60 or force_refresh_auth or self.auth_id is None:
            logger.trace("Refreshing auth...")
            self.auth_loaded_at = time()

            auth = await UserAuthorization.get_or_none(
                key_id=perm_auth_key_id,
            ).select_related("user").annotate(is_bot=F("user__bot")).only("id", "user_id", "mfa_pending", "is_bot")
            if auth is not None:
                self.user_id = auth.user_id
                self.auth_id = auth.id
                self.is_bot = auth.is_bot
                self.mfa_pending = auth.mfa_pending
            else:
                self._reset_auth()
                return

        if self.auth_id is not None and not self.mfa_pending and (time() - self.channels_loaded_at) > 60 * 5:
            logger.trace("Refreshing channels...")
            self.channels_loaded_at = time()

            channel_ids: TaggedLongVector | None = await Cache.obj.get(f"channels:{self.user_id}")
            if channel_ids is None:
                channel_ids = TaggedLongVector(
                    vec=await ChatParticipant.filter(
                        channel_id__not_isnull=True, user_id=self.user_id, left=False,
                    ).values_list("channel_id", flat=True),
                )
                await Cache.obj.set(f"channels:{self.user_id}", channel_ids, ttl=60 * 10)

            channel_ids: list[int] = channel_ids.vec
            old_channels = set(self.channel_ids)
            new_channels = set(channel_ids)
            channels_to_delete = old_channels - new_channels
            channels_to_add = new_channels - old_channels

            self.channel_ids = new_channels
            piltover.session.SessionManager.broker.channels_diff_update(self, channels_to_delete, channels_to_add)

        if old_user_id != self.user_id:
            if old_user_id:
                piltover.session.SessionManager.broker.unsubscribe_user(old_user_id, self)
            piltover.session.SessionManager.broker.subscribe_user(self.user_id, self)
        if old_auth_id != self.auth_id:
            if old_auth_id:
                piltover.session.SessionManager.broker.unsubscribe_auth(old_auth_id, self)
            piltover.session.SessionManager.broker.subscribe_auth(self.auth_id, self)

    # https://core.telegram.org/mtproto/description#message-identifier-msg-id
    def msg_id(self, in_reply: bool) -> int:
        # Client message identifiers are divisible by 4, server message
        # identifiers modulo 4 yield 1 if the message is a response to
        # a client message, and 3 otherwise.

        now = int(time())
        self.msg_id_values.offset = (self.msg_id_values.offset + 4) if now == self.msg_id_values.last_time else 0
        self.msg_id_values.last_time = now
        msg_id = (now * 2 ** 32) + self.msg_id_values.offset + (1 if in_reply else 3)

        assert msg_id % 4 in [1, 3], f"Invalid server msg_id: {msg_id}"
        return msg_id

    def get_outgoing_seq_no(self, obj: TLObject) -> int:
        ret = self.out_seq_no * 2
        if is_content_related(obj):
            self.out_seq_no += 1
            ret += 1
        return ret

    def pack_message(self, obj: TLObject, in_reply: bool) -> Message:
        try:
            downgraded_maybe = LayerConverter.downgrade(obj, self.layer)
        except Exception as e:
            logger.opt(exception=e).error("Failed to downgrade object")
            raise

        return Message(
            message_id=self.msg_id(in_reply=in_reply),
            seq_no=self.get_outgoing_seq_no(obj),
            obj=downgraded_maybe,
        )

    def pack_container(self, objects: list[tuple[TLObject, bool]]) -> Message:
        container = MsgContainer(messages=[
            Message(
                message_id=self.msg_id(in_reply=in_reply),
                seq_no=self.get_outgoing_seq_no(obj),
                obj=obj,
            )
            for obj, in_reply in objects
        ])

        return self.pack_message(container, False)

    async def _resolve_context_values(self, values: NeedsContextValues) -> ContextValues:
        result = ContextValues()

        # TODO: cache fetched values

        if values.poll_answers:
            selected_answers = await PollVote.filter(
                answer__poll_id__in=values.poll_answers, user_id=self.user_id,
            ).values_list("answer__poll_id", "answer_id")
            for poll_id, answer_id in selected_answers:
                if poll_id not in result.poll_answers:
                    result.poll_answers[poll_id] = set()
                result.poll_answers[poll_id].add(answer_id)

        peers_q = Q()

        if values.chat_participants or values.channel_participants:
            if values.chat_participants:
                peers_q |= Q(chat_id__in=values.chat_participants)
            if values.channel_participants:
                peers_q |= Q(channel_id__in=values.channel_participants)

            participants = await ChatParticipant.filter(peers_q, user_id=self.user_id).only(
                "chat_id", "channel_id", "admin_rights", "banned_rights", "invited_at", "left",
            )
            for participant in participants:
                if participant.chat_id is not None:
                    result.chat_participants[participant.chat_id] = participant
                else:
                    result.channel_participants[participant.channel_id] = participant

        if values.users:
            peers_q |= Q(user_id__in=values.users)

            contact_ids = set()
            for contact in await Contact.filter(
                Q(owner_id=self.user_id, target_id__in=values.users)
                | Q(owner_id__in=values.users, target_id=self.user_id)
            ):
                result.contacts[(contact.owner_id, contact.target_id)] = contact
                if contact.owner_id != self.user_id:
                    contact_ids.add(contact.owner_id)

            # NOTE (for future me refactoring this): this overwrites existing rules in context variables btw
            result.privacyrules = await PrivacyRule.has_access_to_bulk(
                users=values.users,
                user=self.user_id,
                keys=[
                    PrivacyRuleKeyType.PHONE_NUMBER,
                    PrivacyRuleKeyType.PROFILE_PHOTO,
                    PrivacyRuleKeyType.STATUS_TIMESTAMP,
                ],
                contacts=contact_ids,
            )

            for presence in await Presence.filter(user_id__in=values.users).only("user_id", "last_seen"):
                result.presences[presence.user_id] = presence

        if peers_q.children:
            result.peers.update({
                (peer.type, peer.target_id_raw()): peer
                for peer in await Peer.filter(
                    peers_q, owner_id=self.user_id,
                ).only("type", "user_id", "chat_id", "channel_id")
            })

        if values.channel_messages:
            messages = await MessageRef.filter(id__in=values.channel_messages).select_related(
                "peer", "peer__channel", "content", "content__media", "content__media__file",
            )
            mentioned_media_unreads = await MessageRef.get_mentioned_media_unread_bulk(messages, self.user_id)
            reactionss = await MessageRef.to_tl_reactions_bulk(messages, self.user_id)
            for message, mmu, reactions in zip(messages, mentioned_media_unreads, reactionss):
                result.channel_messages[message.id] = (reactions, mmu[0], mmu[1])

        if values.stickersets:
            for installed in await InstalledStickerset.filter(set_id__in=values.stickersets, user_id=self.user_id):
                result.stickersets[installed.set_id] = installed

        return result
