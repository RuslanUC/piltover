from datetime import datetime, UTC
from time import time
from typing import cast

from loguru import logger
from tortoise import Tortoise
from tortoise.expressions import Q, Subquery, RawSQL, F
from tortoise.functions import Max
from tortoise.query_utils import Prefetch
from tortoise.transactions import in_transaction

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.chats import resolve_input_chat_photo
from piltover.app.handlers.messages.history import format_messages_internal, read_message_contents_internal
from piltover.app.handlers.messages.invites import user_join_chat_or_channel
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.app.utils.utils import validate_username, check_password_internal
from piltover.config import APP_CONFIG
from piltover.context import request_ctx
from piltover.db.enums import MessageType, PeerType, ChatBannedRights, ChatAdminRights, PrivacyRuleKeyType, \
    AdminLogEntryAction
from piltover.db.models import User, Channel, Peer, Dialog, ChatParticipant, ReadState, PrivacyRule, \
    ChatInviteRequest, Username, ChatInvite, AvailableChannelReaction, Reaction, UserPassword, UserPersonalChannel, \
    Chat, PeerColorOption, File, SlowmodeLastMessage, AdminLogEntry, Contact, MessageRef, MessageContent, \
    ReadHistoryChunk, DefaultSendAs, Stickerset, StickersetThumb, Wallpaper, WallpaperSettings
from piltover.db.models.channel import CREATOR_RIGHTS
from piltover.db.models.message_ref import append_channel_min_message_id_to_query_maybe
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, Unreachable
from piltover.session import SessionManager
from piltover.tl import MessageActionChannelCreate, UpdateChannel, Updates, \
    InputChannelFromMessage, InputChannel, ChannelFull, PhotoEmpty, PeerNotifySettings, MessageActionChatEditTitle, \
    InputMessageID, InputMessageReplyTo, ChannelParticipantsRecent, ChannelParticipantsAdmins, \
    ChannelParticipantsSearch, ChatReactionsAll, ChatReactionsNone, ChatReactionsSome, ReactionEmoji, \
    ReactionCustomEmoji, SendAsPeer, PeerUser, MessageActionChatEditPhoto, InputUserSelf, InputUser, \
    InputUserFromMessage, PeerColor, InputPeerChannel, InputChannelEmpty, Int, ChannelParticipantsBots, \
    ChannelParticipantsContacts, ChannelParticipantsMentions, ChannelParticipantsBanned, ChannelParticipantsKicked, \
    ChannelParticipantLeft, PeerChannel, InputStickerSetEmpty, InputStickerSetID
from piltover.tl.functions.channels import GetAdminedPublicChannels, CheckUsername, \
    CreateChannel, GetChannels, GetFullChannel, EditTitle, EditPhoto, GetMessages, DeleteMessages, EditBanned, \
    EditAdmin, GetParticipants, GetParticipant, ReadHistory, InviteToChannel, InviteToChannel_133, ToggleSignatures, \
    UpdateUsername, ToggleSignatures_133, GetMessages_40, DeleteChannel, EditCreator, JoinChannel, LeaveChannel, \
    TogglePreHistoryHidden, ToggleJoinToSend, GetSendAs, GetSendAs_135, GetAdminLog, ToggleJoinRequest, \
    GetGroupsForDiscussion, SetDiscussionGroup, UpdateColor, ToggleSlowMode, ToggleParticipantsHidden, \
    ReadMessageContents, DeleteHistory, DeleteParticipantHistory, ReorderUsernames, DeactivateAllUsernames, SetStickers, \
    SetEmojiStickers
from piltover.tl.functions.messages import SetChatAvailableReactions, SetChatAvailableReactions_136, \
    SetChatAvailableReactions_145, SetChatAvailableReactions_179
from piltover.tl.types.channels import ChannelParticipants, ChannelParticipant, SendAsPeers, AdminLogResults
from piltover.tl.types.messages import Chats, ChatFull as MessagesChatFull, Messages, AffectedMessages, InvitedUsers, \
    AffectedHistory, MessagesSlice
from piltover.tl.base import InputStickerSet as TLInputStickerSetBase, ChatReactions as TLChatReactionsBase, \
    Reaction as TLReactionBase, ChannelParticipant as TLChannelParticipantBase, Updates as TLUpdatesBase
from piltover.utils.users_chats_channels import UsersChatsChannels
from piltover.worker import MessageHandler

handler = MessageHandler("channels")


@handler.on_request(CheckUsername, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def check_username(request: CheckUsername) -> bool:
    request.username = request.username.lower()
    validate_username(request.username)
    if await Username.filter(username=request.username).exists():
        raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")
    return True


@handler.on_request(UpdateUsername, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def update_username(request: UpdateUsername, user_id: int) -> bool:
    peer_type, peer_channel_id = Peer.type_and_id_from_input_raise(user_id, request.channel, "CHANNEL_PRIVATE")
    if peer_type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")
    channel = await Channel.get_or_none(id=peer_channel_id, deleted=False).select_related("username")
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant(user_id)
    if participant is None or not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    request.username = request.username.lower().strip()
    current_username = cast(Username | None, channel.username)
    if (not request.username and current_username is None) \
            or (current_username is not None and current_username.username == request.username):
        raise ErrorRpc(error_code=400, error_message="USERNAME_NOT_MODIFIED")

    if request.username:
        validate_username(request.username)
        if await Username.filter(username__iexact=request.username).exists():
            raise ErrorRpc(error_code=400, error_message="USERNAME_OCCUPIED")

    old_username = ""
    new_username = request.username

    if current_username is not None:
        old_username = current_username.username
        if not request.username:
            await current_username.delete()
            await UserPersonalChannel.filter(channel=channel).delete()
            channel._username = None
        else:
            current_username.username = request.username
            await current_username.save(update_fields=["username"])
    else:
        channel._username = await Username.create(channel=channel, username=request.username)

    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.CHANGE_USERNAME,
        prev=old_username.encode("utf8"),
        new=new_username.encode("utf8"),
        searchable=f"{old_username}\n{new_username}",
    )

    if channel.username is not None and channel.hidden_prehistory:
        channel.min_available_id = cast(
            int | None,
            cast(
                object,
                await MessageRef.filter(
                    peer__channel=channel,
                ).order_by("-id").first().values_list("id", flat=True)
            )
        )
        if channel.min_available_id is not None:
            channel.min_available_id += 1
        channel.hidden_prehistory = False
        await channel.save(update_fields=["min_available_id", "hidden_prehistory"])

    await Channel.filter(id=channel.id).update(version=F("version") + 1)
    await channel.refresh_from_db(["version"])

    await upd.update_channel(channel)
    return True


async def _create_channel(
        creator_id: int, title: str, description: str | None, is_channel: bool, is_supergroup: bool,
) -> tuple[Channel, Peer]:
    channel = await Channel.create(
        creator_id=creator_id, name=title, description=description, channel=is_channel, supergroup=is_supergroup,
    )
    peer_channel: Peer = await Peer.create(owner=None, channel=channel, type=PeerType.CHANNEL)

    return channel, peer_channel


async def _add_user_to_channel(channel: Channel, peer_channel: Peer, user_id: int) -> ChatParticipant:
    user_is_creator = channel.creator_id == user_id

    participant, _ = await ChatParticipant.update_or_create(
        channel=channel,
        user_id=user_id,
        defaults={
            "chat_channel_id": channel.make_id(),
            "left": False,
            "admin_rights": ChatAdminRights.from_tl(CREATOR_RIGHTS) if user_is_creator else ChatAdminRights.NONE,
        },
    )
    if user_is_creator:
        await channel.sync_admins_count(False)
    await Dialog.create_or_unhide(user_id, peer_channel)
    await SessionManager.subscribe_to_channel(channel.id, [user_id])

    return participant


@handler.on_request(CreateChannel, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def create_channel(request: CreateChannel, user_id: int) -> Updates:
    if not request.broadcast and not request.megagroup:
        raise ErrorRpc(error_code=400, error_message="CHANNELS_TOO_MUCH")

    title = request.title.strip()
    description = request.about.strip()
    if not title:
        raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")
    if len(title) > 64:
        raise ErrorRpc(error_code=400, error_message="CHAT_TITLE_EMPTY")
    if len(description) > 255:
        raise ErrorRpc(error_code=400, error_message="CHAT_ABOUT_TOO_LONG")

    async with in_transaction():
        channel, peer_channel = await _create_channel(user_id, title, description, request.broadcast, request.megagroup)
        await _add_user_to_channel(channel, peer_channel, user_id)

    user = await User.get(id=user_id).only("id")
    user.bot = False

    updates = await send_message_internal(
        user, peer_channel, None, None, False,
        author=user_id, type=MessageType.SERVICE_CHANNEL_CREATE,
        extra_info=MessageActionChannelCreate(title=request.title).write(),
    )

    updates.updates.insert(0, UpdateChannel(channel_id=channel.make_id()))

    return updates


@handler.on_request(GetChannels, ReqHandlerFlags.DONT_FETCH_USER)
async def get_channels(request: GetChannels, user_id: int) -> Chats:
    auth_id = cast(int, request_ctx.get().auth_id)

    channel_peers = set()
    channel_participants = set()

    for input_channel in request.id[:100]:
        if not isinstance(input_channel, (InputChannel, InputChannelFromMessage)):
            continue

        channel_id = Channel.norm_id(input_channel.channel_id)

        if isinstance(input_channel, InputChannel):
            if input_channel.access_hash == 0:
                channel_participants.add(channel_id)
            else:
                if not Channel.check_access_hash(user_id, auth_id, channel_id, input_channel.access_hash):
                    continue
                channel_peers.add(channel_id)
        elif isinstance(input_channel, InputChannelFromMessage):
            ...  # TODO: support channels from message

    if not channel_peers and not channel_participants:
        return Chats(chats=[])

    channels_q = Q(join_type=Q.OR)
    if channel_participants:
        channels_q.children = *channels_q.children, Q(id__in=channel_participants, chatparticipants__user_id=user_id)
    if channel_peers:
        channels_q.children = *channels_q.children, Q(id__in=channel_peers)

    return Chats(
        chats=await Channel.to_tl_bulk_maybecached(await Channel.filter(channels_q).only("id", "version")),
    )


@handler.on_request(GetFullChannel, ReqHandlerFlags.DONT_FETCH_USER)
async def get_full_channel(request: GetFullChannel, user_id: int) -> MessagesChatFull:
    peer_type, peer_channel_id = Peer.type_and_id_from_input_raise(user_id, request.channel, "CHANNEL_PRIVATE")
    if peer_type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    conn = Tortoise.get_connection("default")
    rows, results = await conn.execute_query(
        """
        SELECT
            channel.id __id, channel.all_reactions __all_reactions, channel.all_reactions_custom __all_reactions_custom,
            channel.hidden_prehistory __hidden_prehistory, channel.migrated_from_id __migrated_from_id,
            channel.discussion_id __discussion_id, channel.is_discussion __is_discussion, channel.slowmode_seconds __slowmode_seconds,
            channel.participants_hidden __participants_hidden, channel.supergroup __supergroup, channel.creator_id __creator_id,
            channel.description __description, channel.admins_count __admins_count, channel.pts __pts,
            channel.ttl_period_days __ttl_period_days, channel.min_available_id __min_available_id, 
            channel.min_available_id_force __min_available_id_force,
            
            peer.id peer__id, peer.out_max_read_id peer__out_max_read_id,
            
            stickerset_.id stickerset__id, stickerset_.hash stickerset__hash, stickerset_.title stickerset__title, 
            stickerset_.short_name stickerset__short_name, stickerset_.official stickerset__official, 
            stickerset_.owner_id stickerset__owner_id, stickerset_.stickers_count stickerset__stickers_count, 
            stickerset_.masks stickerset__masks, stickerset_.emoji stickerset__emoji,
            
            stickerset_thumb_file.id stickerset__thumb__file__id, stickerset_thumb_file.size stickerset__thumb__file__size,
            
            emojiset_.id emojiset__id, emojiset_.hash emojiset__hash, emojiset_.title emojiset__title, 
            emojiset_.short_name emojiset__short_name, emojiset_.official emojiset__official, 
            emojiset_.owner_id emojiset__owner_id, emojiset_.stickers_count emojiset__stickers_count, 
            emojiset_.masks emojiset__masks, emojiset_.emoji emojiset__emoji,

            emojiset_thumb_file.id emojiset__thumb__file__id, emojiset_thumb_file.size emojiset__thumb__file__size,
            
            wallpaper.id wallpaper__id, wallpaper.creator_id wallpaper__creator_id, wallpaper.dark wallpaper__dark, 
            wallpaper.slug wallpaper__slug,
            
            wallpapersettings.id wallpaper__settings__id, wallpapersettings.blur wallpaper__settings__blur,
            wallpapersettings.motion wallpaper__settings__motion, wallpapersettings.background_color wallpaper__settings__background_color,
            wallpapersettings.second_background_color wallpaper__settings__second_background_color,
            wallpapersettings.third_background_color wallpaper__settings__third_background_color,
            wallpapersettings.fourth_background_color wallpaper__settings__fourth_background_color,
            wallpapersettings.intensity wallpaper__settings__intensity, wallpapersettings.rotation wallpaper__settings__rotation,
            wallpapersettings.emoticon wallpaper__settings__emoticon,
            
            wallpaper__document.id wallpaper__document__id, wallpaper__document.created_at wallpaper__document__created_at, 
            wallpaper__document.mime_type wallpaper__document__mime_type,
            wallpaper__document.size wallpaper__document__size, wallpaper__document.type wallpaper__document__type,
            wallpaper__document.constant_access_hash wallpaper__document__constant_access_hash,
            wallpaper__document.constant_file_ref wallpaper__document__constant_file_ref,
            wallpaper__document.filename wallpaper__document__filename, wallpaper__document.width wallpaper__document__width,
            wallpaper__document.height wallpaper__document__height, wallpaper__document.duration wallpaper__document__duration,
            wallpaper__document.supports_streaming wallpaper__document__supports_streaming,
            wallpaper__document.nosound wallpaper__document__nosound, wallpaper__document.preload_prefix_size wallpaper__document__preload_prefix_size,
            wallpaper__document.photo_sizes wallpaper__document__photo_sizes, wallpaper__document.photo_stripped wallpaper__document__photo_stripped,
            wallpaper__document.photo_path wallpaper__document__photo_path,
            
            photo.id photo__id, photo.created_at photo__created_at, photo.photo_sizes photo__photo_sizes,
            photo.photo_stripped photo__photo_stripped, photo.photo_path photo__photo_path,
            photo.constant_access_hash photo__constant_access_hash, photo.constant_file_ref photo__constant_file_ref,
            
            discussion.id discussion__id, discussion.version discussion__version,
            
            discussion_channel.id discussion_channel__id, discussion_channel.version discussion_channel__version,
            
            chatparticipant.id chatparticipant__id, chatparticipant.left chatparticipant__left, 
            chatparticipant.admin_rights chatparticipant__admin_rights, chatparticipant.banned_rights chatparticipant__banned_rights, 
            chatparticipant.min_message_id chatparticipant__min_message_id,
            
            COUNT(scheduled.id) > 0 has_scheduled,
            
            min_message.id min_message__id,
            
            migrated_from_message.id migrated_from__message_id,
            
            slowmodelastmessage.last_message slowmodelastmessage__last_message,
            
            defaultsendas__channel.id defaultsendas__channel__id, defaultsendas__channel.version defaultsendas__channel__version
            
        FROM channel
            INNER JOIN peer ON peer.channel_id = channel.id
            LEFT OUTER JOIN stickerset stickerset_ ON stickerset_.id = channel.stickerset_id
            LEFT OUTER JOIN stickersetthumb stickerset__thumb ON stickerset__thumb.set_id = stickerset_.id 
            LEFT OUTER JOIN file stickerset_thumb_file ON stickerset_thumb_file.id = stickerset__thumb.file_id 
            LEFT OUTER JOIN stickerset emojiset_ ON emojiset_.id = channel.emojiset_id
            LEFT OUTER JOIN stickersetthumb emojiset__thumb ON emojiset__thumb.set_id = emojiset_.id 
            LEFT OUTER JOIN file emojiset_thumb_file ON emojiset_thumb_file.id = emojiset__thumb.file_id 
            LEFT OUTER JOIN wallpaper ON wallpaper.id = channel.wallpaper_id
            LEFT OUTER JOIN wallpapersettings ON wallpapersettings.id = wallpaper.settings_id
            LEFT OUTER JOIN file wallpaper__document ON wallpaper__document.id = wallpaper.document_id
            LEFT OUTER JOIN file photo ON photo.id = channel.photo_id
            LEFT OUTER JOIN channel discussion ON discussion.id = channel.discussion_id
            LEFT OUTER JOIN channel discussion_channel ON discussion_channel.discussion_id = channel.id
            LEFT OUTER JOIN chatparticipant ON chatparticipant.channel_id = channel.id AND chatparticipant.user_id = %s
            LEFT OUTER JOIN messageref scheduled ON scheduled.peer_id = peer.id AND scheduled.scheduled_by_user_id = %s
            LEFT OUTER JOIN messageref min_message ON min_message.id = chatparticipant.min_message_id
            LEFT OUTER JOIN peer migrated_from_peer ON migrated_from_peer.chat_id = channel.migrated_from_id AND migrated_from_peer.owner_id = %s 
            LEFT OUTER JOIN messageref migrated_from_message ON migrated_from_message.id = migrated_from_peer.last_message_id
            LEFT OUTER JOIN slowmodelastmessage ON slowmodelastmessage.channel_id = channel.id AND slowmodelastmessage.user_id = %s
            LEFT OUTER JOIN defaultsendas ON defaultsendas.group_id = channel.id AND defaultsendas.user_id = %s
            LEFT OUTER JOIN channel defaultsendas__channel ON defaultsendas__channel.id = defaultsendas.channel_id
        WHERE channel.id = %s
        """,
        [user_id, user_id, user_id, user_id, user_id, peer_channel_id]
    )

    if not results:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_PRIVATE")

    channel_row = results[0]

    peer = Peer(
        id=channel_row["peer__id"],
        type=PeerType.CHANNEL,
        chat_id=None,
        channel_id=peer_channel_id,
        out_max_read_id=channel_row["peer__out_max_read_id"],
    )

    channel = Channel(
        id=channel_row["__id"],
        all_reactions=channel_row["__all_reactions"],
        all_reactions_custom=channel_row["__all_reactions_custom"],
        hidden_prehistory=channel_row["__hidden_prehistory"],
        migrated_from_id=channel_row["__migrated_from_id"],
        discussion_id=channel_row["__discussion_id"],
        is_discussion=channel_row["__is_discussion"],
        slowmode_seconds=channel_row["__slowmode_seconds"],
        participants_hidden=channel_row["__participants_hidden"],
        supergroup=channel_row["__supergroup"],
        creator_id=channel_row["__creator_id"],
        description=channel_row["__description"],
        admins_count=channel_row["__admins_count"],
        pts=channel_row["__pts"],
        ttl_period_days=channel_row["__ttl_period_days"],
        min_available_id=channel_row["__min_available_id"],
        min_available_id_force=channel_row["__min_available_id_force"],
    )

    participant: ChatParticipant | None = None
    if channel_row["chatparticipant__id"] is not None:
        participant = ChatParticipant(
            left=channel_row["chatparticipant__left"],
            admin_rights=channel_row["chatparticipant__admin_rights"],
            banned_rights=channel_row["chatparticipant__banned_rights"],
            min_message_id=channel_row["chatparticipant__min_message_id"],
        )

    photo = PhotoEmpty(id=0)
    if channel_row["photo__id"] is not None:
        photo = File(
            id=channel_row["photo__id"],
            created_at=channel_row["photo__created_at"],
            photo_sizes=channel_row["photo__photo_sizes"],
            photo_stripped=channel_row["photo__photo_stripped"],
            photo_path=channel_row["photo__photo_path"],
            constant_access_hash=channel_row["photo__constant_access_hash"],
            constant_file_ref=channel_row["photo__constant_file_ref"],
        ).to_tl_photo()

    stickerset: Stickerset | None = None
    if channel_row["stickerset__id"] is not None:
        stickerset = Stickerset(
            id=channel_row["stickerset__id"],
            hash=channel_row["stickerset__hash"],
            title=channel_row["stickerset__title"],
            short_name=channel_row["stickerset__short_name"],
            official=channel_row["stickerset__official"],
            owner_id=channel_row["stickerset__owner_id"],
            stickers_count=channel_row["stickerset__stickers_count"],
            masks=channel_row["stickerset__masks"],
            emoji=channel_row["stickerset__emoji"],
        )

        if channel_row["stickerset__thumb__file__id"] is not None:
            thumb_file = File(
                id=channel_row["stickerset__thumb__file__id"],
                version=channel_row["stickerset__thumb__file__version"]
            )
            thumb_file._saved_in_db = True
            thumb = StickersetThumb(file_id=thumb_file.id, file=thumb_file)
            thumb._saved_in_db = True
            stickerset._thumb = thumb

    emojiset: Stickerset | None = None
    if channel_row["emojiset__id"] is not None:
        emojiset = Stickerset(
            id=channel_row["emojiset__id"],
            hash=channel_row["emojiset__hash"],
            title=channel_row["emojiset__title"],
            short_name=channel_row["emojiset__short_name"],
            official=channel_row["emojiset__official"],
            owner_id=channel_row["emojiset__owner_id"],
            stickers_count=channel_row["emojiset__stickers_count"],
            masks=channel_row["emojiset__masks"],
            emoji=channel_row["emojiset__emoji"],
        )

        if channel_row["emojiset__thumb__file__id"] is not None:
            thumb_file = File(
                id=channel_row["emojiset__thumb__file__id"],
                version=channel_row["emojiset__thumb__file__version"]
            )
            thumb_file._saved_in_db = True
            thumb = StickersetThumb(file_id=thumb_file.id, file=thumb_file)
            thumb._saved_in_db = True
            emojiset._thumb = thumb

    wallpaper: Wallpaper | None = None
    if channel_row["wallpaper__id"] is not None:
        wallpaper = Wallpaper(
            id=channel_row["wallpaper__id"],
            creator_id=channel_row["wallpaper__creator_id"],
            dark=channel_row["wallpaper__dark"],
            slug=channel_row["wallpaper__slug"],
        )
        if channel_row["wallpaper__settings__id"] is not None:
            settings = WallpaperSettings(
                id=channel_row["wallpaper__settings__id"],
                blur=channel_row["wallpaper__settings__blur"],
                motion=channel_row["wallpaper__settings__motion"],
                background_color=channel_row['wallpaper__settings__background_color'],
                second_background_color=channel_row["wallpaper__settings__second_background_color"],
                third_background_color=channel_row["wallpaper__settings__third_background_color"],
                fourth_background_color=channel_row["wallpaper__settings__fourth_background_color"],
                intensity=channel_row["wallpaper__settings__intensity"],
                rotation=channel_row["wallpaper__settings__rotation"],
                emoticon=channel_row["wallpaper__settings__emoticon"],
            )
            settings._saved_in_db = True
            wallpaper.settings = settings
        if channel_row["wallpaper__document__id"] is not None:
            document = File(
                id=channel_row["wallpaper__document__id"],
                created_at=channel_row["wallpaper__document__created_at"],
                mime_type=channel_row["wallpaper__document__mime_type"],
                size=channel_row["wallpaper__document__size"],
                type=channel_row["wallpaper__document__type"],
                constant_access_hash=channel_row["wallpaper__document__constant_access_hash"],
                constant_file_ref=channel_row["wallpaper__document__constant_file_ref"],
                filename=channel_row["wallpaper__document__filename"],
                width=channel_row["wallpaper__document__width"],
                height=channel_row["wallpaper__document__height"],
                duration=channel_row["wallpaper__document__duration"],
                supports_streaming=channel_row["wallpaper__document__supports_streaming"],
                nosound=channel_row["wallpaper__document__nosound"],
                preload_prefix_size=channel_row["wallpaper__document__preload_prefix_size"],
                photo_sizes=channel_row["wallpaper__document__photo_sizes"],
                photo_stripped=channel_row["wallpaper__document__photo_stripped"],
                photo_path=channel_row["wallpaper__document__photo_path"],
            )
            document._saved_in_db = True
            wallpaper.document = document

    invite = None
    if participant is not None \
            and not participant.left \
            and channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        invite = await ChatInvite.get_or_create_permanent(user_id, channel)
    if participant is not None and participant.banned_rights & ChatBannedRights.VIEW_MESSAGES:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    in_read_max_id, out_read_max_id, unread_count, _, _ = await ReadState.get_in_out_ids_and_unread(
        user_id, peer, True, True,
    )

    available_reactions: TLChatReactionsBase
    if channel.all_reactions:
        available_reactions = ChatReactionsAll(allow_custom=channel.all_reactions_custom)
    else:
        some: list[TLReactionBase] = [
            ReactionEmoji(emoticon=reaction.reaction)
            for reaction in await Reaction.filter(availablechannelreactions__channel=channel)
        ]
        if some:
            available_reactions = ChatReactionsSome(reactions=some)
        else:
            available_reactions = ChatReactionsNone()

    has_scheduled = False
    if participant is not None and channel.admin_has_permission(participant, ChatAdminRights.POST_MESSAGES):
        has_scheduled = await MessageRef.filter(peer=peer, scheduled_by_user_id=user_id).exists()

    can_change_info = participant is not None and channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO)

    min_message_id: int | None = None
    if channel.hidden_prehistory:
        if channel_row["min_message__id"]:
            min_message_id = channel_row["min_message__id"]
        elif participant.min_message_id:
            min_message_id = participant.min_message_id
        elif channel.min_available_id:
            min_message_id = channel.min_available_id
        if channel.min_available_id_force and min_message_id and channel.min_available_id_force > min_message_id:
            min_message_id = channel.min_available_id_force
        if not min_message_id:
            min_message_id = None

    migrated_from_chat_id = channel.migrated_from_id
    migrated_from_max_id = (channel_row["migrated_from__message_id"] or 0) if channel.migrated_from_id else None

    channels_to_tl: list[Channel] = [channel]

    linked_chat: Channel | None = None
    if channel.discussion_id:
        linked_chat = Channel(
            id=channel_row["discussion__id"],
            version=channel_row["discussion__version"],
        ) if channel_row["discussion__id"] is not None else None
    elif channel.is_discussion:
        linked_chat = Channel(
            id=channel_row["discussion_channel__id"],
            version=channel_row["discussion_channel__version"],
        ) if channel_row["discussion_channel__id"] is not None else None

    if linked_chat is not None:
        channels_to_tl.append(linked_chat)

    slowmode_next_date = None
    if channel.slowmode_seconds and (slowmode_last_date := channel_row["slowmodelastmessage__last_message"]):
        slowmode_next_date = int(slowmode_last_date.timestamp()) + channel.slowmode_seconds

    can_view_participants = not channel.participants_hidden
    if participant is not None and participant.is_admin:
        can_view_participants = True

    default_send_as = None
    if channel.supergroup and channel_row["defaultsendas__channel__id"] is not None:
        dsa_channel_id = channel_row["defaultsendas__channel__id"]
        default_send_as = PeerChannel(channel_id=Channel.make_id_from(dsa_channel_id))
        channels_to_tl.append(Channel(
            id=dsa_channel_id,
            version=channel_row["defaultsendas__channel__version"],
        ))

    return MessagesChatFull(
        full_chat=ChannelFull(
            can_view_participants=can_view_participants,
            can_set_username=can_change_info,
            can_set_stickers=(
                    channel.supergroup
                    # and participant is not None
                    # and not participant.left
                    # and channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS)
            ),
            hidden_prehistory=channel.hidden_prehistory,
            can_set_location=False,
            has_scheduled=has_scheduled,
            can_view_stats=False,
            can_delete_channel=channel.creator_id == user_id,
            antispam=False,
            participants_hidden=channel.participants_hidden,
            translations_disabled=True,
            restricted_sponsored=True,
            can_view_revenue=False,
            paid_reactions_available=False,

            id=channel.make_id(),
            about=channel.description,
            # TODO: use channel.participants_count
            participants_count=await ChatParticipant.filter(channel=channel, left=False).count(),
            admins_count=channel.admins_count,
            read_inbox_max_id=in_read_max_id,
            read_outbox_max_id=out_read_max_id,
            unread_count=unread_count,
            chat_photo=photo,
            notify_settings=PeerNotifySettings(),
            bot_info=[],
            pinned_msg_id=cast(
                int | None,
                cast(
                    object,
                    await MessageRef.filter(
                        peer=peer, pinned=True,
                    ).annotate(max_id=Max("id")).first().values_list("max_id", flat=True)
                )
            ),
            pts=channel.pts,
            exported_invite=await invite.to_tl() if invite is not None else None,
            available_reactions=available_reactions,
            ttl_period=channel.ttl_period_days * 86400 if channel.ttl_period_days else None,
            available_min_id=min_message_id,
            migrated_from_chat_id=Chat.make_id_from(migrated_from_chat_id) if migrated_from_chat_id else None,
            migrated_from_max_id=migrated_from_max_id,
            linked_chat_id=linked_chat.make_id() if linked_chat else None,
            slowmode_seconds=channel.slowmode_seconds,
            slowmode_next_send_date=slowmode_next_date,
            default_send_as=default_send_as,
            stickerset=await stickerset.to_tl(user_id) if stickerset is not None else None,
            emojiset=await emojiset.to_tl(user_id) if emojiset is not None else None,
            wallpaper=wallpaper.to_tl() if wallpaper is not None else None,
        ),
        chats=await Channel.to_tl_bulk_maybecached(channels_to_tl),
        users=[],
    )


@handler.on_request(EditTitle, ReqHandlerFlags.DONT_FETCH_USER)
async def edit_channel_title(request: EditTitle, user_id: int) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user_id, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    participant = await peer.channel.get_participant(user_id)
    if participant is None or not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    old_title = peer.channel.name
    await peer.channel.update(title=request.title)

    await AdminLogEntry.create(
        channel=peer.channel,
        user_id=user_id,
        action=AdminLogEntryAction.CHANGE_TITLE,
        prev=old_title.encode("utf8"),
        new=peer.channel.name.encode("utf8"),
        searchable=f"{old_title}\n{peer.channel.name}",
    )

    user = await User.get(id=user_id).only("id", "bot")

    updates = await upd.update_channel(peer.channel)
    updates_msg = await send_message_internal(
        user, peer, None, None, False,
        author=user_id, type=MessageType.SERVICE_CHAT_EDIT_TITLE,
        extra_info=MessageActionChatEditTitle(title=request.title).write(),
    )
    updates.updates.extend(updates_msg.updates)
    updates.users.extend(updates_msg.users)
    updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(EditPhoto, ReqHandlerFlags.DONT_FETCH_USER)
async def edit_channel_photo(request: EditPhoto, user_id: int):
    peer = await Peer.from_input_peer_raise(
        user_id, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,),
        select_related=("channel__photo",),
    )

    participant = await peer.channel.get_participant(user_id)
    if participant is None or not peer.channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel = peer.channel
    old_photo = channel.photo
    await channel.update(photo=await resolve_input_chat_photo(user_id, request.photo))

    await AdminLogEntry.create(
        channel=peer.channel,
        user_id=user_id,
        action=AdminLogEntryAction.CHANGE_PHOTO,
        old_photo=old_photo,
        new_photo=channel.photo,
    )

    user = await User.get(id=user_id).only("id", "bot")

    updates = await upd.update_channel(peer.channel)
    updates_msg = await send_message_internal(
        user, peer, None, None, False,
        author=user_id, type=MessageType.SERVICE_CHAT_EDIT_PHOTO,
        extra_info=MessageActionChatEditPhoto(
            photo=channel.photo.to_tl_photo() if channel.photo else PhotoEmpty(id=0),
        ).write(),
    )
    updates.updates.extend(updates_msg.updates)
    updates.users.extend(updates_msg.users)
    updates.chats.extend(updates_msg.chats)

    return updates


@handler.on_request(GetMessages_40, ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(GetMessages, ReqHandlerFlags.DONT_FETCH_USER)
async def get_messages(request: GetMessages, user_id: int) -> Messages | MessagesSlice:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant(user_id, True)
    participant_is_banned = participant is not None and bool(participant.banned_rights & ChatBannedRights.VIEW_MESSAGES)
    channel_is_public = channel.nojoin_allow_view or await Username.filter(channel=channel).exists()
    if (not channel_is_public and participant is None) or participant_is_banned:
        raise ErrorRpc(error_code=400, error_message="CHAT_RESTRICTED")

    ids = []
    reply_ids = []

    for message_query in request.id:
        if isinstance(message_query, InputMessageID):
            ids.append(message_query.id)
        elif isinstance(message_query, InputMessageReplyTo):
            reply_ids.append(message_query.id)

    if not ids and not reply_ids:
        return Messages(
            messages=[],
            chats=[],
            users=[],
        )

    query = Q()
    if ids:
        query |= Q(id__in=ids)
    if reply_ids:
        query |= Q(id__in=Subquery(
            MessageRef.filter(
                peer__channel=channel, id__in=reply_ids,
            ).values_list("reply_to_id", flat=True)
        ))

    query &= Q(peer__channel=channel)
    query = append_channel_min_message_id_to_query_maybe(channel, query, participant, user_id)

    return await format_messages_internal(
        user_id,
        await MessageRef.filter(query).select_related(*MessageRef.PREFETCH_MAYBECACHED)
    )


@handler.on_request(DeleteMessages, ReqHandlerFlags.DONT_FETCH_USER)
async def delete_messages(request: DeleteMessages, user_id: int) -> AffectedMessages:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.DELETE_MESSAGES):
        raise ErrorRpc(error_code=403, error_message="MESSAGE_DELETE_FORBIDDEN")

    peer = await Peer.get(channel=channel).only("id")

    ids = request.id[:100]
    ids_query = Q(id__in=ids, peer=peer)
    ids_query = append_channel_min_message_id_to_query_maybe(channel, ids_query, participant, user_id)
    message_ids = cast(
        list[int],
        cast(
            object,
            await MessageRef.filter(ids_query).values_list("id", flat=True)
        )
    )

    if not message_ids:
        return AffectedMessages(pts=channel.pts, pts_count=0)

    async with in_transaction():
        await MessageRef.filter(id__in=message_ids).delete()
        await peer.sync_last_message()

    _, pts = await upd.delete_messages_channel(channel, message_ids)

    return AffectedMessages(pts=pts, pts_count=len(message_ids))


@handler.on_request(EditBanned, ReqHandlerFlags.DONT_FETCH_USER)
async def edit_banned(request: EditBanned, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.BAN_USERS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    peer_type, target_id = Peer.type_and_id_from_input_raise(user_id, request.participant, "PARTICIPANT_ID_INVALID")
    if peer_type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    target_participant = await channel.get_participant(target_id, allow_left=True)

    new_banned_rights = ChatBannedRights.from_tl(request.banned_rights)
    banned_for = request.banned_rights.until_date - time()
    if not new_banned_rights or banned_for < 30 or banned_for > 86400 * 366:
        banned_until = datetime.fromtimestamp(0, UTC)
    else:
        banned_until = datetime.fromtimestamp(request.banned_rights.until_date, UTC)

    if target_participant is not None and target_participant.banned_rights == new_banned_rights:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    # TODO: check if target_participant is not an admin

    was_participant = target_participant is not None and not target_participant.left
    left = (
            target_participant is None
            or target_participant.left
            or bool(new_banned_rights & ChatBannedRights.VIEW_MESSAGES)
    )

    participant_tl_before: TLChannelParticipantBase = ChannelParticipantLeft(peer=PeerUser(user_id=target_id))
    if target_participant is not None:
        participant_tl_before = target_participant.to_tl_channel_with_creator(user_id, channel.creator_id)

    target_participant, created = await ChatParticipant.update_or_create(
        user_id=target_id,
        channel=channel,
        defaults={
            "banned_rights": new_banned_rights,
            "banned_until": banned_until,
            "left": left,
            "inviter_id": 0,
            "invited_at": datetime.now(UTC),
            "chat_channel_id": channel.make_id(),
            "admin_rights": ChatAdminRights.NONE,
        },
    )
    if not created:
        await channel.sync_admins_count(False)

    if new_banned_rights & ChatBannedRights.VIEW_MESSAGES:
        await ChatInviteRequest.filter(id__in=Subquery(
            ChatInviteRequest.filter(user_id=target_id, invite__channel=channel).values_list("id", flat=True)
        )).delete()

    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.PARTICIPANT_BAN,
        prev=participant_tl_before.write(),
        new=target_participant.to_tl_channel_with_creator(user_id, channel.creator_id).write(),
    )

    if was_participant:
        await upd.update_channel_for_user(channel, target_id)

    return Updates(
        updates=[UpdateChannel(channel_id=channel.make_id())],
        users=[],
        chats=[await channel.to_tl()],
        date=int(time()),
        seq=0,
    )


@handler.on_request(EditAdmin, ReqHandlerFlags.DONT_FETCH_USER)
async def edit_admin(request: EditAdmin, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    creator_id = channel.creator_id

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.ADD_ADMINS):
        raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    target_peer = await Peer.query_from_input_user_or_raise(
        user_id, request.user_id, error_message="PARTICIPANT_ID_INVALID",
    ).only("user_id")
    if target_peer.user_id == creator_id and target_peer.user_id != user_id:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")
    target_participant = await channel.get_participant(target_peer.user_id)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    new_admin_rights = ChatAdminRights.from_tl(request.admin_rights)

    if new_admin_rights > 0 \
            and not target_participant.is_admin \
            and channel.admins_count >= APP_CONFIG.channel_admin_limit:
        raise ErrorRpc(error_code=400, error_message="USERS_TOO_MUCH")

    if target_peer.user_id == creator_id:
        new_admin_rights |= ChatAdminRights.from_tl(CREATOR_RIGHTS)

    if user_id != creator_id:
        if new_admin_rights & ~participant.admin_rights:
            raise ErrorRpc(error_code=403, error_message="RIGHT_FORBIDDEN")

    if target_participant.admin_rights == new_admin_rights and target_participant.admin_rank == request.rank:
        return Updates(updates=[], users=[], chats=[], date=int(time()), seq=0)

    participant_tl_before = target_participant.to_tl_channel_with_creator(user_id, creator_id)

    update_fields = []
    if request.rank != target_participant.admin_rank:
        target_participant.admin_rank = request.rank
        update_fields.append("admin_rank")
    if new_admin_rights != target_participant.admin_rights:
        target_participant.admin_rights = new_admin_rights
        update_fields.append("admin_rights")
    if not target_participant.promoted_by_id:
        target_participant.promoted_by_id = user_id
        update_fields.append("promoted_by_id")

    await target_participant.save(update_fields=update_fields)
    await channel.sync_admins_count(False)

    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.PARTICIPANT_ADMIN,
        prev=participant_tl_before.write(),
        new=target_participant.to_tl_channel_with_creator(user_id, creator_id).write(),
    )

    await upd.update_channel_for_user(channel, user_id)
    return Updates(
        updates=[UpdateChannel(channel_id=channel.make_id())],
        users=[],
        chats=[await channel.to_tl()],
        date=int(time()),
        seq=0,
    )


@handler.on_request(GetParticipants, ReqHandlerFlags.DONT_FETCH_USER)
async def get_participants(request: GetParticipants, user_id: int) -> ChannelParticipants:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    this_participant = await channel.get_participant(user_id)
    if channel.participants_hidden and (this_participant is None or not this_participant.is_admin):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    filt = request.filter

    view_value = ChatBannedRights.VIEW_MESSAGES.value
    query = ChatParticipant.filter(channel=channel)
    if this_participant is None or not this_participant.is_admin or isinstance(filt, ChannelParticipantsMentions):
        anon_value = ChatAdminRights.ANONYMOUS.value
        query = query.annotate(check_anon=RawSQL(f"admin_rights & {anon_value}")).filter(check_anon=0)

    if isinstance(filt, ChannelParticipantsRecent):
        query = query.order_by("-invited_at")
    elif isinstance(filt, ChannelParticipantsAdmins):
        query = query.filter(admin_rights__gt=0).order_by("user_id")
    elif isinstance(filt, ChannelParticipantsSearch):
        ...  # Handled below
    elif isinstance(filt, ChannelParticipantsBots):
        query = query.filter(user__bot=True).order_by("user_id")
    elif isinstance(filt, ChannelParticipantsContacts):
        query = query.filter(
            user_id__in=Subquery(Contact.filter(owner_id=user_id).values_list("target_id", flat=True))
        )
    elif isinstance(filt, ChannelParticipantsMentions):
        if filt.top_msg_id:
            query = query.filter(user_id__in=Subquery(
                MessageRef.filter(
                    peer__channel=channel, content__reply_to_id=filt.top_msg_id,
                ).distinct().values_list("content__author_id", flat=True)
            ))
    elif isinstance(filt, ChannelParticipantsBanned):
        query = query.annotate(
            check_view_banned=RawSQL(f"banned_rights & {view_value}"),
        ).filter(banned_rights__gt=0, check_view_banned=0)
    elif isinstance(filt, ChannelParticipantsKicked):
        query = query.annotate(
            check_view_banned=RawSQL(f"banned_rights & {view_value}"),
        ).filter(check_view_banned__not=0)
    else:
        raise Unreachable

    if isinstance(filt, (
            ChannelParticipantsSearch, ChannelParticipantsContacts, ChannelParticipantsMentions,
            ChannelParticipantsBanned, ChannelParticipantsKicked,
    )):
        if filt.q:
            query = query.filter(Q(
                user__first_name__icontains=filt.q,
                user__username__username__icontains=filt.q,
            ))
        query = query.order_by("user_id")

    limit = max(min(request.limit, 100), 1)
    participants = await query.select_related("user").limit(limit).offset(request.offset)

    participants_tl: list[TLChannelParticipantBase] = []
    users_to_tl: list[User] = []

    peers_to_create: list[Peer] = []

    for participant in participants:
        if participant.user_id != user_id:
            peers_to_create.append(Peer(owner_id=user_id, user=participant.user, type=PeerType.USER))

    if peers_to_create:
        await Peer.bulk_create(peers_to_create, ignore_conflicts=True)

    for participant in participants:
        participants_tl.append(participant.to_tl_channel_with_creator(user_id, creator_id=channel.creator_id))
        users_to_tl.append(participant.user)

    return ChannelParticipants(
        count=await query.count(),
        participants=participants_tl,
        chats=[await channel.to_tl()],
        users=await User.to_tl_bulk(users_to_tl),
    )


@handler.on_request(GetParticipant, ReqHandlerFlags.DONT_FETCH_USER)
async def get_participant(request: GetParticipant, user_id: int) -> ChannelParticipant:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant(user_id)
    if participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    target_type, target_id = Peer.type_and_id_from_input_raise(user_id, request.participant, "PARTICIPANT_ID_INVALID")
    if target_type not in (PeerType.USER, PeerType.SELF):
        raise ErrorRpc(error_code=400, error_message="PARTICIPANT_ID_INVALID")

    if not channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS) \
            and target_type is not PeerType.SELF:
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    target_participant = await ChatParticipant.get_or_none(
        user_id=target_id, channel=channel,
    ).select_related("user")
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    return ChannelParticipant(
        participant=target_participant.to_tl_channel_with_creator(user_id, channel.creator_id),
        chats=[await channel.to_tl()],
        users=[await target_participant.user.to_tl()],
    )


@handler.on_request(ReadHistory, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def read_channel_history(request: ReadHistory, user_id: int) -> bool:
    # TODO: exclude messages that are not available for the user

    peer = await Peer.from_input_peer_raise(
        user_id, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    read_state, created = await ReadState.get_or_create(owner_id=user_id, peer=peer)
    if request.max_id <= read_state.last_message_id:
        return True

    unread_ids = cast(
        tuple[int, int] | None,
        cast(
            object,
            await MessageRef.filter(
                id__lte=request.max_id, peer=peer,
            ).order_by("-id").first().values_list("id", "content_id")
        )
    )
    if not unread_ids:
        return True

    unread_max_id, content_id = unread_ids

    unread_count = await MessageRef.filter(peer=peer, id__gt=unread_max_id).count()

    read_state.last_message_id = unread_max_id
    await read_state.save(update_fields=["last_message_id"])

    await ReadHistoryChunk.create(user_id=user_id, peer=peer, read_content_id=content_id)

    await upd.update_read_history_inbox_channel(user_id, peer.channel_id, unread_max_id, unread_count)

    prev_last_id = cast(
        int | None,
        cast(
            object,
            await Peer.filter(
                id=peer.id
            ).annotate(max_out=Max("out_max_read_id")).first().values_list("max_out", flat=True)
        )
    ) or 0

    read_messages_by_user_ids: dict[int, int] = dict(
        await MessageRef.filter(
            peer=peer, id__gt=prev_last_id, id__lte=unread_max_id, content__author_id__not=user_id,
        ).group_by("content__author_id").annotate(max_id=Max("id")).values_list("content__author_id", "max_id")
    )
    if read_messages_by_user_ids:
        await peer.update_max_read_id(unread_max_id)
        await upd.update_read_history_outbox_channel(peer.channel, read_messages_by_user_ids)

    return True


@handler.on_request(InviteToChannel, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def invite_to_channel(request: InviteToChannel, user_id: int) -> InvitedUsers:
    peer_type, peer_channel_id = Peer.type_and_id_from_input_raise(user_id, request.channel, "CHANNEL_PRIVATE")
    if peer_type is not PeerType.CHANNEL:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")
    peer_with_channel = await Peer.get(channel_id=peer_channel_id).select_related("channel")
    channel = cast(Channel, peer_with_channel.channel)

    participant = await channel.get_participant_raise(user_id)
    if not channel.user_has_permission(participant, ChatBannedRights.INVITE_USERS) and \
            not channel.admin_has_permission(participant, ChatAdminRights.INVITE_USERS):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    user_ids = set()
    for input_user in request.users[:100]:
        peer_type, peer_id = Peer.type_and_id_from_input_raise(user_id, input_user, "USER_ID_INVALID")
        if peer_type is not PeerType.USER:
            raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")
        user_ids.add(peer_id)

    peer_user_ids = set(cast(
        list[int],
        await Peer.filter(owner_id=user_id, user_id__in=user_ids).values_list("user_id", flat=True)
    ))
    if peer_user_ids != user_ids:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    existing_participants = {
        participant.user_id: participant
        for participant in await ChatParticipant.filter(user_id__in=user_ids, channel_id=channel.id).only("id", "left")
    }

    privacy_rules = await PrivacyRule.has_access_to_bulk(user_ids, user_id, [PrivacyRuleKeyType.CHAT_INVITE])

    added_user_ids: list[int] = []
    participants_to_create: list[ChatParticipant] = []
    participants_to_update: list[ChatParticipant] = []

    for input_user in request.users[:100]:
        _, peer_user_id = Peer.type_and_id_from_input_raise(user_id, input_user)
        existing_participant = existing_participants.get(peer_user_id)
        if existing_participant and not existing_participant.left:
            continue
        if not privacy_rules[peer_user_id][PrivacyRuleKeyType.CHAT_INVITE]:
            raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

        added_user_ids.append(peer_user_id)
        if existing_participant is None:
            participants_to_create.append(ChatParticipant(
                user_id=peer_user_id, channel=channel, chat_channel_id=channel.make_id(), inviter_id=user_id,
                min_message_id=channel.min_available_id,
            ))
        else:
            existing_participant.left = False
            participants_to_update.append(existing_participant)

    if participants_to_create:
        await ChatParticipant.bulk_create(participants_to_create, ignore_conflicts=True)
    if participants_to_update:
        await ChatParticipant.bulk_update(participants_to_update, fields=["left"])
    await ChatInviteRequest.filter(id__in=Subquery(
        ChatInviteRequest.filter(
            user_id__in=added_user_ids, invite__channel=channel,
        ).values_list("id", flat=True)
    )).delete()

    await SessionManager.subscribe_to_channel(channel.id, added_user_ids)

    for added_user_id in added_user_ids:
        await upd.update_channel_for_user(channel, added_user_id)

    return InvitedUsers(
        updates=Updates(
            updates=[UpdateChannel(channel_id=channel.make_id())],
            chats=[await channel.to_tl()],
            users=[],
            date=int(time()),
            seq=0,
        ),
        missing_invitees=[],
    )


@handler.on_request(InviteToChannel_133, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def invite_to_channel_133(request: InviteToChannel_133, user_id: int) -> Updates:
    result = await invite_to_channel(InviteToChannel(channel=request.channel, users=request.users), user_id)
    return cast(Updates, result.updates)


@handler.on_request(ToggleSignatures, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_signatures(request: ToggleSignatures, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant(user_id)
    if participant is None or not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel = channel
    if channel.signatures == request.signatures_enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    channel.signatures = request.signatures_enabled
    channel.version += 1
    await channel.save(update_fields=["signatures", "version"])

    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.TOGGLE_SIGNATURES,
        new=b"\x01" if request.signatures_enabled else b"\x00",
    )

    return await upd.update_channel(channel)


@handler.on_request(ToggleSignatures_133, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_signatures_136(request: ToggleSignatures_133, user_id: int) -> TLUpdatesBase:
    return await toggle_signatures(ToggleSignatures(
        signatures_enabled=request.enabled,
        profiles_enabled=False,
        channel=request.channel,
    ), user_id)


@handler.on_request(SetChatAvailableReactions_179, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(SetChatAvailableReactions_145, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(SetChatAvailableReactions_136, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(SetChatAvailableReactions, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def set_chat_available_reactions(request: SetChatAvailableReactions, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.peer)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant(user_id)
    if participant is None or not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    reactions = request.available_reactions
    if isinstance(reactions, ChatReactionsAll):
        if channel.all_reactions and reactions.allow_custom == channel.all_reactions_custom:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

        channel.all_reactions = True
        channel.all_reactions_custom = reactions.allow_custom
    elif isinstance(reactions, ChatReactionsNone):
        some_available = await AvailableChannelReaction.filter(channel=channel).exists()
        if not channel.all_reactions and not some_available:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

        channel.all_reactions = False
        await AvailableChannelReaction.filter(channel=channel).delete()
    elif isinstance(reactions, ChatReactionsSome):
        if not reactions.reactions:
            raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")  # TODO: or set to ChatReactionsNone?

        reactions_emoticons = []

        for tl_reaction in reactions.reactions:
            if isinstance(tl_reaction, ReactionEmoji):
                reactions_emoticons.append(Reaction.reaction_to_uuid(tl_reaction.emoticon))
            elif isinstance(tl_reaction, ReactionCustomEmoji):
                # TODO: allow custom reactions
                raise ErrorRpc(error_code=400, error_message="REACTION_INVALID")

        new_reactions = await Reaction.filter(reaction_id__in=reactions_emoticons)
        current_reactions = dict(await AvailableChannelReaction.filter(
            channel=channel,
        ).values_list("reaction_id", "id"))

        to_create_reactions = []

        for reaction in new_reactions:
            if reaction.id not in current_reactions:
                to_create_reactions.append(AvailableChannelReaction(channel=channel, reaction=reaction))
            else:
                del current_reactions[reaction.id]

        to_delete_ids = list(current_reactions.values())

        if not to_create_reactions and not to_delete_ids:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

        if to_create_reactions:
            await AvailableChannelReaction.bulk_create(to_create_reactions)
        if to_delete_ids:
            await AvailableChannelReaction.filter(id__in=to_delete_ids).delete()
    else:
        raise Unreachable

    channel.version += 1
    await channel.save(update_fields=["all_reactions", "all_reactions_custom", "version"])

    return await upd.update_channel(channel)


async def _unlink_channel_maybe(channel: Channel) -> None:
    if channel.is_discussion:
        await Channel.filter(discussion=channel).update(discussion=None)
    elif channel.discussion_id:
        await Channel.filter(id=channel.discussion_id).update(is_discussion=False)


@handler.on_request(DeleteChannel, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def delete_channel(request: DeleteChannel, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if channel.creator_id != user_id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    channel.deleted = True
    channel.version += 1
    await channel.save(update_fields=["deleted", "version"])

    await UserPersonalChannel.filter(channel=channel).delete()
    await _unlink_channel_maybe(channel)
    # TODO: delete channel peers, dialogs, participants and messages lazily or in background

    return await upd.update_channel(channel)


@handler.on_request(EditCreator, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def edit_creator(request: EditCreator, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if channel.creator_id != user_id:
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    participant = await channel.get_participant(user_id)
    if participant is None:
        # what
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    password = await UserPassword.get_or_none(user_id=user_id)
    if password is None or password.password is None:
        raise ErrorRpc(error_code=400, error_message="PASSWORD_MISSING")

    await check_password_internal(password, request.password)

    peer_type, target_id = Peer.type_and_id_from_input_raise(user_id, request.user_id, "PEER_ID_INVALID")
    if peer_type is not PeerType.USER:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    target_participant = await channel.get_participant(target_id)
    if target_participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_ID_INVALID")

    async with in_transaction():
        channel.creator_id = target_id
        channel.version += 1
        await channel.save(update_fields=["creator_id", "version"])

        participant.admin_rights = ChatAdminRights(0)
        target_participant.admin_rights = ChatAdminRights.from_tl(CREATOR_RIGHTS)
        await ChatParticipant.bulk_update([participant, target_participant], fields=["admin_rights"])
        await channel.sync_admins_count(False)

        await _unlink_channel_maybe(channel)

    return await upd.update_channel(channel, send_to_users=[user_id, target_id])


CHANNEL_PRIVATE_ERR = ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")


@handler.on_request(JoinChannel, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def join_channel(request: JoinChannel, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await ChatParticipant.get_or_none(channel=channel, user_id=user_id)
    if participant is not None:
        if not participant.left:
            raise ErrorRpc(error_code=400, error_message="USER_ALREADY_PARTICIPANT")
        if participant.banned_rights & ChatBannedRights.VIEW_MESSAGES:
            raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE", reason="banned")

    if not await Username.filter(channel=channel).exists():
        if not channel.is_discussion:
            raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE", reason="not a discussion")
        linked_channel = await Channel.get_or_none(
            deleted=False, discussion_id=channel.id,
        ).select_related("username")
        if linked_channel is None:
            raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE", reason="no linked channel")
        linked_participant = await linked_channel.get_participant(user_id, True)
        if not linked_channel.can_view_messages(linked_participant):
            raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE", reason="cant access linked channel")

    user = await User.get(id=user_id).only("id")
    user.bot = False

    return await user_join_chat_or_channel(channel, user, None)


@handler.on_request(LeaveChannel, ReqHandlerFlags.DONT_FETCH_USER)
async def leave_channel(request: LeaveChannel, user_id: int) -> Updates:
    peer = await Peer.from_input_peer_raise(
        user_id, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
    )

    if peer.channel.creator_id == user_id:
        raise ErrorRpc(error_code=400, error_message="USER_CREATOR")

    participant = await peer.channel.get_participant(user_id)
    if participant is None:
        raise ErrorRpc(error_code=400, error_message="USER_NOT_PARTICIPANT")

    async with in_transaction():
        participant.left = True
        await participant.save(update_fields=["left"])
        await ChatInvite.filter(channel=peer.channel, user_id=user_id).update(revoked=True)
        await Dialog.hide(user_id, peer)
        await MessageContent.filter(id__in=Subquery(
            MessageRef.filter(peer=peer, scheduled_by_user_id=user_id).values_list("content_id", flat=True)
        )).delete()
        await AdminLogEntry.create(
            channel=peer.channel,
            user_id=user_id,
            action=AdminLogEntryAction.PARTICIPANT_LEAVE,
        )

    return await upd.update_channel_for_user(peer.channel, user_id)


@handler.on_request(GetAdminedPublicChannels, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_admined_public_channels(request: GetAdminedPublicChannels, user_id: int) -> Chats:
    query = Channel.filter(deleted=False, creator_id=user_id, chatparticipants__user_id=user_id, username__isnull=False)

    if request.check_limit and await query.count() >= APP_CONFIG.public_channels_limit:
        raise ErrorRpc(error_code=400, error_message="CHANNELS_ADMIN_PUBLIC_TOO_MUCH")

    return Chats(
        chats=await Channel.to_tl_bulk(await query),
    )


@handler.on_request(TogglePreHistoryHidden, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_pre_history_hidden(request: TogglePreHistoryHidden, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if channel.is_discussion:
        raise ErrorRpc(error_code=400, error_message="CHAT_LINK_EXISTS")

    if channel.hidden_prehistory == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    if await Username.filter(channel=channel).exists():
        raise ErrorRpc(error_code=400, error_message="CHAT_LINK_EXISTS")

    channel.min_available_id = cast(
        int | None,
        cast(
            object,
            # TODO: use Max("id") instead of .order_by("id").first() ?
            await MessageRef.filter(
                peer__channel=channel,
            ).order_by("-id").first().values_list("id", flat=True)
        )
    )
    if channel.min_available_id is not None:
        channel.min_available_id += 1
    channel.hidden_prehistory = request.enabled
    channel.version += 1
    await channel.save(update_fields=["hidden_prehistory", "min_available_id", "version"])
    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.PREHISTORY_HIDDEN,
        new=b"\x01" if request.enabled else b"\x00"
    )

    return await upd.update_channel(channel)


@handler.on_request(ToggleJoinToSend, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_join_to_send(request: ToggleJoinToSend, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if not request.enabled and not channel.is_discussion:
        # As per https://core.telegram.org/constructor/channel,
        # "Whether a user needs to join the supergroup before they can send messages:
        # can be false only for discussion groups"
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    if channel.join_to_send == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel.join_to_send = request.enabled
    channel.version += 1
    await channel.save(update_fields=["join_to_send", "version"])

    return await upd.update_channel(channel)


@handler.on_request(GetSendAs_135, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(GetSendAs, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_send_as(request: GetSendAs | GetSendAs_135, user: User) -> SendAsPeers:
    channel = await Channel.get_from_input(user, request.peer)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if not channel.supergroup:
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    # TODO: figure out how telegram selects channels for SendAs
    send_as = await Channel.filter(
        channel=True, deleted=False, creator=user, chatparticipants__user=user, username__isnull=False,
    )
    send_as_peers = [SendAsPeer(peer=user.to_tl_peer())]
    for channel in send_as:
        send_as_peers.append(SendAsPeer(peer=channel.to_tl_peer()))

    return SendAsPeers(
        peers=send_as_peers,
        chats=await Channel.to_tl_bulk(send_as),
        users=[await user.to_tl()],
    )


@handler.on_request(GetAdminLog, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_admin_log(request: GetAdminLog, user_id: int) -> AdminLogResults:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO) \
            or not channel.admin_has_permission(participant, ChatAdminRights.OTHER):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    events_q = Q(channel=channel)

    event_filter_flags = Int.read_bytes(request.events_filter.serialize()) if request.events_filter is not None else 0
    if request.events_filter is not None and event_filter_flags != 0:
        actions_q = Q()
        if request.events_filter.info:
            actions_q |= Q(action=AdminLogEntryAction.CHANGE_TITLE) \
                         | Q(action=AdminLogEntryAction.CHANGE_ABOUT) \
                         | Q(action=AdminLogEntryAction.CHANGE_USERNAME) \
                         | Q(action=AdminLogEntryAction.CHANGE_PHOTO) \
                         | Q(action=AdminLogEntryAction.EDIT_PEER_COLOR) \
                         | Q(action=AdminLogEntryAction.EDIT_PEER_COLOR_PROFILE) \
                         | Q(action=AdminLogEntryAction.LINKED_CHAT) \
                         | Q(action=AdminLogEntryAction.EDIT_HISTORY_TTL) \
                         | Q(action=AdminLogEntryAction.TOGGLE_SLOWMODE) \
                         | Q(action=AdminLogEntryAction.EDIT_STICKERSET) \
                         | Q(action=AdminLogEntryAction.EDIT_EMOJISET)
        if request.events_filter.join:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_JOIN)
        if request.events_filter.leave:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_LEAVE)
        if request.events_filter.settings:
            actions_q |= Q(action=AdminLogEntryAction.TOGGLE_SIGNATURES) \
                         | Q(action=AdminLogEntryAction.TOGGLE_NOFORWARDS) \
                         | Q(action=AdminLogEntryAction.DEFAULT_BANNED_RIGHTS) \
                         | Q(action=AdminLogEntryAction.PREHISTORY_HIDDEN)
        if request.events_filter.promote or request.events_filter.demote:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_ADMIN)
        if request.events_filter.ban or request.events_filter.unban:
            actions_q |= Q(action=AdminLogEntryAction.PARTICIPANT_BAN)

        if not actions_q.filters and not actions_q.children:
            return AdminLogResults(events=[], users=[], chats=[])

        events_q &= actions_q

    if request.admins:
        admin_ids = []
        for input_admin in request.admins:
            if isinstance(input_admin, InputUserSelf):
                admin_ids.append(user_id)
            elif isinstance(input_admin, (InputUser, InputUserFromMessage)):
                admin_ids.append(input_admin.user_id)

        if not admin_ids:
            return AdminLogResults(events=[], users=[], chats=[])

        events_q &= Q(user_id__in=admin_ids)

    if request.max_id:
        events_q &= Q(id__lt=request.max_id)
    if request.min_id:
        events_q &= Q(id__gt=request.min_id)

    search_query = request.q.strip()
    if search_query:
        events_q &= Q(searchable__icontains=search_query)

    limit = max(1, min(100, request.limit))

    events = []
    ucc = UsersChatsChannels()

    for event in await AdminLogEntry.filter(events_q).limit(limit).order_by("-id").select_related(
            "user", "old_photo", "new_photo",
    ):
        if (event_tl := event.to_tl(ucc)) is None:
            continue
        events.append(event_tl)

    users, chats, channels = await ucc.resolve()

    return AdminLogResults(
        events=events,
        users=users,
        chats=[*chats, *channels],
    )


@handler.on_request(ToggleJoinRequest, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_join_request(request: ToggleJoinRequest, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if channel.join_request == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel.join_request = request.enabled
    channel.version += 1
    await channel.save(update_fields=["join_to_send", "version"])

    return await upd.update_channel(channel)


@handler.on_request(GetGroupsForDiscussion, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def get_groups_for_discussion(user_id: int) -> Chats:
    chats = await Chat.filter(creator_id=user_id, migrated=False, deleted=False).order_by("-id")
    channels = await Channel.filter(creator_id=user_id, supergroup=True, is_discussion=False).order_by("-id")

    return Chats(
        chats=[
            *await Channel.to_tl_bulk(channels),
            *await Chat.to_tl_bulk(chats),
        ],
    )


@handler.on_request(SetDiscussionGroup, ReqHandlerFlags.DONT_FETCH_USER)
async def set_discussion_group(request: SetDiscussionGroup, user_id: int) -> bool:
    channel = await Channel.get_from_input(user_id, request.broadcast).select_related("discussion")
    if channel is None:
        raise ErrorRpc(error_code=400, error_message="BROADCAST_ID_INVALID")

    channel_participant = await channel.get_participant_raise(user_id, "CHAT_ADMIN_REQUIRED")
    if not channel.check_rights(channel_participant, ChatAdminRights.CHANGE_INFO, ChatBannedRights.VIEW_MESSAGES):
        raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

    if isinstance(request.group, (InputChannel, InputPeerChannel)):
        group = await Channel.get_from_input(user_id, request.group)
        if group is None:
            raise ErrorRpc(error_code=406, error_message="MEGAGROUP_ID_INVALID")

        group_participant = await group.get_participant_raise(user_id, "CHAT_ADMIN_REQUIRED")
        if not group.check_rights(group_participant, ChatAdminRights.CHANGE_INFO, ChatBannedRights.VIEW_MESSAGES):
            raise ErrorRpc(error_code=400, error_message="CHAT_ADMIN_REQUIRED")

        if not group.supergroup or group.is_discussion:
            raise ErrorRpc(error_code=400, error_message="MEGAGROUP_ID_INVALID")
        if group.hidden_prehistory:
            raise ErrorRpc(error_code=400, error_message="MEGAGROUP_PREHISTORY_HIDDEN")

        if group.id == channel.discussion_id:
            raise ErrorRpc(error_code=400, error_message="MEGAGROUP_ID_INVALID")
    elif isinstance(request.group, InputChannelEmpty):
        group = None
    else:
        raise ErrorRpc(error_code=400, error_message="MEGAGROUP_ID_INVALID")

    if channel.discussion_id is None and group is None:
        raise ErrorRpc(error_code=400, error_message="LINK_NOT_MODIFIED")
    if group is not None and channel.discussion_id == group.id:
        raise ErrorRpc(error_code=400, error_message="LINK_NOT_MODIFIED")

    old_group = channel.discussion
    channel.discussion = group
    channel.version += 1
    if old_group is not None:
        old_group.is_discussion = False
        old_group.version += 1
    if group is not None:
        group.is_discussion = True
        group.version += 1

    channels_to_update = [channel]
    if old_group is not None:
        channels_to_update.append(old_group)
    if group is not None:
        channels_to_update.append(group)

    admin_log_to_create = [
        AdminLogEntry(
            channel=channel,
            user_id=user_id,
            action=AdminLogEntryAction.LINKED_CHAT,
            old_channel=old_group,
            new_channel=group,
            searchable=f"{old_group.name if old_group is not None else ''}\n{group.name if group is not None else ''}",
        )
    ]
    if old_group is not None:
        admin_log_to_create.append(AdminLogEntry(
            channel=old_group,
            user_id=user_id,
            action=AdminLogEntryAction.LINKED_CHAT,
            old_channel=channel,
            new_channel=None,
            searchable=f"{channel.name}",
        ))
    if group is not None:
        admin_log_to_create.append(AdminLogEntry(
            channel=group,
            user_id=user_id,
            action=AdminLogEntryAction.LINKED_CHAT,
            old_channel=None,
            new_channel=channel,
            searchable=f"{channel.name}",
        ))

    async with in_transaction():
        await Channel.bulk_update(channels_to_update, fields=["discussion_id", "is_discussion", "version"])
        await AdminLogEntry.bulk_create(admin_log_to_create)

    await upd.update_channel(channel)
    if old_group is not None:
        await upd.update_channel(old_group)
    if group is not None:
        await upd.update_channel(group)

    return True


@handler.on_request(UpdateColor, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def update_color(request: UpdateColor, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    changed = []

    old_color = channel.profile_color_id if request.for_profile else channel.accent_color_id
    old_emoji = channel.profile_emoji_id if request.for_profile else channel.accent_emoji_id
    new_color = old_color
    new_emoji = old_emoji

    if request.color is None and request.for_profile and channel.profile_color_id is not None:
        channel.profile_color = new_color = None
        changed.append("profile_color_id")
    elif request.color is None and not request.for_profile and channel.accent_color_id is not None:
        channel.accent_color = new_color = None
        changed.append("accent_color_id")
    elif request.color is not None:
        if (peer_color := await PeerColorOption.get_or_none(id=request.color, is_profile=request.for_profile)) is None:
            raise ErrorRpc(error_code=400, error_message="COLOR_INVALID")
        new_color = peer_color.id
        if request.for_profile:
            channel.profile_color = peer_color
            changed.append("profile_color_id")
        else:
            channel.accent_color = peer_color
            changed.append("accent_color_id")

    if request.background_emoji_id is None and request.for_profile and channel.profile_emoji_id is not None:
        channel.profile_emoji = new_emoji = None
        changed.append("profile_emoji_id")
    elif request.background_emoji_id is None and not request.for_profile and channel.accent_emoji_id is not None:
        channel.accent_emoji = new_emoji = None
        changed.append("accent_emoji_id")
    elif request.background_emoji_id is not None:
        emoji = await File.get_or_none(
            id=request.background_emoji_id, stickerset__installedstickersets__user_id=user_id,
        )
        if emoji is None:
            raise ErrorRpc(error_code=400, error_message="DOCUMENT_INVALID")
        new_emoji = emoji.id
        if request.for_profile:
            channel.profile_emoji = emoji
            changed.append("profile_emoji_id")
        else:
            channel.accent_emoji = emoji
            changed.append("accent_emoji_id")

    if not changed:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_NOT_MODIFIED")

    await channel.save(update_fields=changed)

    if request.for_profile:
        action = AdminLogEntryAction.EDIT_PEER_COLOR_PROFILE
    else:
        action = AdminLogEntryAction.EDIT_PEER_COLOR
    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=action,
        prev=PeerColor(color=old_color, background_emoji_id=old_emoji).serialize(),
        new=PeerColor(color=new_color, background_emoji_id=new_emoji).serialize(),
    )

    return await upd.update_channel(channel)


@handler.on_request(ToggleSlowMode, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_slowmode(request: ToggleSlowMode, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    new_seconds = request.seconds or None
    if channel.slowmode_seconds == request.seconds:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
    if new_seconds is not None and (new_seconds < 0 or new_seconds > 60 * 60):
        raise ErrorRpc(error_code=400, error_message="SECONDS_INVALID")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    old_seconds = channel.slowmode_seconds
    channel.slowmode_seconds = new_seconds
    channel.version += 1
    await channel.save(update_fields=["slowmode_seconds", "version"])

    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.TOGGLE_SLOWMODE,
        prev=Int.write(old_seconds or 0),
        new=Int.write(new_seconds or 0),
    )

    return await upd.update_channel(channel)


@handler.on_request(ToggleParticipantsHidden, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def toggle_participants_hidden(request: ToggleParticipantsHidden, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if channel.participants_hidden == request.enabled:
        raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    channel.participants_hidden = request.enabled
    channel.version += 1
    await channel.save(update_fields=["participants_hidden", "version"])

    return await upd.update_channel(channel)


@handler.on_request(ReadMessageContents, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def read_message_contents(request: ReadMessageContents, user_id: int) -> bool:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    if not request.id:
        return True

    valid_refs = await MessageRef.filter(
        peer__channel=channel, id__in=request.id[:100],
    ).select_related("peer", "content", "content__media", "content__media__file")

    message_ids = await read_message_contents_internal(user_id, valid_refs)
    if message_ids is None:
        return True

    await upd.read_channel_messages_contents(user_id, channel, message_ids)

    return True


@handler.on_request(DeleteHistory, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def delete_history(request: DeleteHistory, user_id: int) -> Updates:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant_raise(user_id)

    new_min_available_id = cast(
        int | None,
        cast(
            object,
            # TODO: use Max("id") instead of .order_by("-id").first() ?
            await MessageRef.filter(
                peer__channel=channel, id__lte=request.max_id,
            ).order_by("-id").first().values_list("id", flat=True),
        )
    ) or 0

    if not request.for_everyone:
        if new_min_available_id < (participant.min_message_id or 0):
            return upd.UpdatesWithDefaults(updates=[])
        participant.min_message_id = new_min_available_id or None
        await participant.save(update_fields=["min_message_id"])
        return await upd.update_channel_participant_available_message(user_id, channel, new_min_available_id)

    if not channel.admin_has_permission(participant, ChatAdminRights.DELETE_MESSAGES):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    peer = await Peer.get(channel=channel).only("id")

    message_ids = cast(
        list[int],
        await MessageRef.filter(
            peer=peer, id__lte=request.max_id,
        ).order_by("-id").limit(APP_CONFIG.channel_delete_history_min_id_threshold + 1).values_list("id", flat=True)
    )
    if len(message_ids) > APP_CONFIG.channel_delete_history_min_id_threshold:
        channel.min_available_id = channel.min_available_id_force = message_ids[0]
        await channel.save(update_fields=["min_available_id", "min_available_id_force"])
        return await upd.update_channel_available_messages(channel, new_min_available_id)

    message_ids.pop(0)
    async with in_transaction():
        await MessageRef.filter(id__in=message_ids).delete()
        await peer.sync_last_message()
    updates, _ = await upd.delete_messages_channel(channel, message_ids)
    return updates


@handler.on_request(DeleteParticipantHistory, ReqHandlerFlags.BOT_NOT_ALLOWED | ReqHandlerFlags.DONT_FETCH_USER)
async def delete_participant_history(request: DeleteParticipantHistory, user_id: int) -> AffectedHistory:
    channel = await Channel.get_from_input(user_id, request.channel)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.DELETE_MESSAGES):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    peer_type, target_id = Peer.type_and_id_from_input_raise(user_id, request.participant, "PARTICIPANT_ID_INVALID")
    if peer_type not in (PeerType.SELF, PeerType.USER):
        raise ErrorRpc(error_code=400, error_message="PEER_ID_INVALID")

    peer = await Peer.get(channel=channel).only("id")

    messages_to_delete = cast(
        list[int],
        await MessageRef.filter(
            peer=peer, content__author_id=target_id,
        ).order_by("-id").limit(1001).values_list("id", flat=True),
    )

    if not messages_to_delete:
        return AffectedHistory(pts=channel.pts, pts_count=0, offset=0)

    offset_id = 0
    if len(messages_to_delete) > 1000:
        offset_id = messages_to_delete.pop()

    async with in_transaction():
        await MessageRef.filter(id__in=messages_to_delete).delete()
        await peer.sync_last_message()

    _, new_pts = await upd.delete_messages_channel(channel, messages_to_delete)
    return AffectedHistory(
        pts=new_pts,
        pts_count=len(messages_to_delete),
        offset=offset_id,
    )


@handler.on_request(ReorderUsernames, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def reorder_usernames() -> bool:
    raise ErrorRpc(error_code=400, error_message="ORDER_INVALID")


@handler.on_request(DeactivateAllUsernames, ReqHandlerFlags.AUTH_NOT_REQUIRED | ReqHandlerFlags.BOT_NOT_ALLOWED)
async def deactivate_all_usernames() -> bool:
    return False


@handler.on_request(SetEmojiStickers, ReqHandlerFlags.DONT_FETCH_USER)
@handler.on_request(SetStickers, ReqHandlerFlags.DONT_FETCH_USER)
async def set_stickers(request: SetStickers | SetEmojiStickers, user_id: int) -> bool:
    is_emoji = isinstance(request, SetEmojiStickers)

    field_name = "emojiset_id" if is_emoji else "stickerset_id"
    select_related_name = "channel__emojiset" if is_emoji else "channel__stickerset"

    channel = await Channel.get_from_input(user_id, request.channel).select_related(select_related_name)
    if channel is None:
        raise ErrorRpc(error_code=406, error_message="CHANNEL_PRIVATE")
    if not channel.supergroup:
        raise ErrorRpc(error_code=400, error_message="CHANNEL_INVALID")

    participant = await channel.get_participant_raise(user_id)
    if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
        raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")

    old_stickerset: TLInputStickerSetBase
    if is_emoji:
        if channel.emojiset_id is None:
            old_stickerset = InputStickerSetEmpty()
        else:
            old_stickerset = InputStickerSetID(id=channel.emojiset_id, access_hash=-1)
    else:
        if channel.stickerset_id is None:
            old_stickerset = InputStickerSetEmpty()
        else:
            old_stickerset = InputStickerSetID(id=channel.stickerset_id, access_hash=-1)

    new_stickerset_tl: TLInputStickerSetBase
    if isinstance(request.stickerset, InputStickerSetEmpty):
        new_stickerset_tl = InputStickerSetEmpty()
        new_stickerset = None

        if is_emoji and channel.emojiset_id is None:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
        if not is_emoji and channel.stickerset_id is None:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
    else:
        auth_id = cast(int, request_ctx.get().auth_id)
        new_stickerset = await Stickerset.from_input(user_id, auth_id, request.stickerset)
        if new_stickerset is None or new_stickerset.official or new_stickerset.emoji != is_emoji:
            raise ErrorRpc(error_code=406, error_message="STICKERSET_INVALID")

        new_stickerset_tl = InputStickerSetID(id=new_stickerset.id, access_hash=-1)

        if not is_emoji and channel.stickerset_id == new_stickerset.id:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
        if is_emoji and channel.emojiset_id == new_stickerset.id:
            raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")

    if is_emoji:
        channel.emojiset = new_stickerset
    else:
        channel.stickerset = new_stickerset

    channel.version += 1
    await channel.save(update_fields=[field_name, "version"])

    await AdminLogEntry.create(
        channel=channel,
        user_id=user_id,
        action=AdminLogEntryAction.EDIT_EMOJISET if is_emoji else AdminLogEntryAction.EDIT_STICKERSET,
        prev=old_stickerset.write(),
        new=new_stickerset_tl.write(),
    )

    await upd.update_channel(channel)
    return True


# @handler.on_request(UpdateEmojiStatus, ReqHandlerFlags.BOT_NOT_ALLOWED)
# async def update_emoji_status(request: UpdateEmojiStatus, user: User) -> Updates:
#     peer = await Peer.from_input_peer_raise(
#         user, request.channel, message="CHANNEL_PRIVATE", code=406, peer_types=(PeerType.CHANNEL,)
#     )
#
#     channel = peer.channel
#
#     if channel.participants_hidden == request.enabled:
#         raise ErrorRpc(error_code=400, error_message="CHAT_NOT_MODIFIED")
#
#     participant = await channel.get_participant_raise(user)
#     if not channel.admin_has_permission(participant, ChatAdminRights.CHANGE_INFO):
#         raise ErrorRpc(error_code=403, error_message="CHAT_ADMIN_REQUIRED")
#
#     channel.participants_hidden = request.enabled
#     channel.version += 1
#     await channel.save(update_fields=["participants_hidden", "version"])
#
#     return await upd.update_channel(channel, user)
