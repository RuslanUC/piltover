import hashlib
import json
from datetime import datetime, UTC

from loguru import logger
from tortoise.expressions import Q

import piltover.app.utils.updates_manager as upd
from piltover.app.handlers.messages.sending import send_message_internal
from piltover.context import request_ctx
from piltover.db.enums import PeerType, PrivacyRuleKeyType, CallDiscardReason, MessageType, CALL_DISCARD_REASON_TO_TL
from piltover.db.models import User, Peer, PrivacyRule, UserAuthorization, PhoneCall
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import DataJSON, Updates, PhoneCallDiscardReasonDisconnect, PhoneCallProtocol, MessageActionPhoneCall
from piltover.tl.functions.phone import GetCallConfig, RequestCall, DiscardCall, AcceptCall, ConfirmCall, \
    RequestCall_133
from piltover.tl.types.phone import PhoneCall as PhonePhoneCall
from piltover.worker import MessageHandler

handler = MessageHandler("phone")

SUPPORTED_LIBRARY_VERSIONS = {
    "2.4.4",  # protocol V0?
    "2.7.7",  # protocol V0, signaling V0? (seq + ??? + type? + length + raw sdp parts)
    "5.0.0",  # protocol V1, signaling V0? (seq + ??? + type? + length + raw sdp parts)
    "7.0.0",  # protocol V2, signaling V1 (seq + json)
    "8.0.0",  # protocol V2, signaling V2 (seq(+flags) + type + length + json)
    "9.0.0",  # protocol V2, signaling V2 (seq(+flags) + type + length + json)
    "11.0.0",  # protocol V2, signaling V2.5/V3?
    "12.0.0",  # protocol V2, signaling V3, not supported on tdesktop 5.13 so no idea
    "13.0.0",  # protocol V2, signaling V3, not supported on tdesktop 5.13 so no idea
}
CALL_CONFIG = json.dumps({
    "enable_vp8_encoder": True,
    "enable_vp8_decoder": True,
    "enable_vp9_encoder": True,
    "enable_vp9_decoder": True,
    "enable_h265_encoder": True,
    "enable_h265_decoder": True,
    "enable_h264_encoder": True,
    "enable_h264_decoder": True,
    "audio_frame_size": 60,
    "jitter_min_delay_60": 2,
    "jitter_max_delay_60": 10,
    "jitter_max_slots_60": 20,
    "jitter_losses_to_reset": 20,
    "jitter_resync_threshold": 0.5,
    "audio_congestion_window": 1024,
    "audio_max_bitrate": 20000,
    "audio_max_bitrate_edge": 16000,
    "audio_max_bitrate_gprs": 8000,
    "audio_max_bitrate_saving": 8000,
    "audio_init_bitrate": 16000,
    "audio_init_bitrate_edge": 8000,
    "audio_init_bitrate_gprs": 8000,
    "audio_init_bitrate_saving": 8000,
    "audio_bitrate_step_incr": 1000,
    "audio_bitrate_step_decr": 1000,
    "use_system_ns": True,
    "use_system_aec": True,
    "force_tcp": True,
    "jitter_initial_delay_60": 2,
    "adsp_good_impls": "(Qualcomm Fluence)",
    "bad_call_rating": True,
    "use_ios_vpio_agc": False,
    "use_tcp": True,
    "audio_medium_fec_bitrate": 20000,
    "audio_medium_fec_multiplier": 0.1,
    "audio_strong_fec_bitrate": 7000
})


@handler.on_request(GetCallConfig, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def get_call_config() -> DataJSON:
    return DataJSON(data=CALL_CONFIG)


def _check_protocol(protocol: PhoneCallProtocol) -> None:
    if not protocol.udp_p2p and not protocol.udp_reflector:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_FLAGS_INVALID")

    if protocol.min_layer > protocol.max_layer:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_LAYER_INVALID")
    if protocol.min_layer < 65 or protocol.max_layer > 92:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_LAYER_INVALID")

    versions = list(set(protocol.library_versions) & SUPPORTED_LIBRARY_VERSIONS)
    if not versions:
        versions = ["2.4.4"]

    protocol.library_versions = versions


def _merge_protocols(a: PhoneCallProtocol, b: PhoneCallProtocol):
    merged_min_layer = max(a.min_layer, b.min_layer)
    merged_max_layer = min(a.max_layer, b.max_layer)
    if merged_min_layer > merged_max_layer:
        raise ErrorRpc(error_code=406, error_message="CALL_PROTOCOL_COMPAT_LAYER_INVALID")

    versions = list(set(a.library_versions) & set(b.library_versions))
    if not versions:
        versions = ["2.4.4"]

    return PhoneCallProtocol(
        # TODO: figure out how this is calculated by telegram
        udp_p2p=True,
        udp_reflector=True,
        min_layer=merged_min_layer,
        max_layer=merged_max_layer,
        library_versions=versions,
    )


@handler.on_request(RequestCall_133, ReqHandlerFlags.BOT_NOT_ALLOWED)
@handler.on_request(RequestCall, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def request_call(request: RequestCall | RequestCall_133, user: User) -> PhonePhoneCall:
    _check_protocol(request.protocol)

    if len(request.g_a_hash) != 32:
        raise ErrorRpc(error_code=400, error_message="G_A_HASH_INVALID")

    peer = await Peer.from_input_peer_raise(
        user, request.user_id, "USER_ID_INVALID", peer_types=(PeerType.USER,)
    )
    if peer.blocked_at:
        raise ErrorRpc(error_code=403, error_message="USER_IS_BLOCKED")
    if not await PrivacyRule.has_access_to(user, peer.user, PrivacyRuleKeyType.PHONE_CALL):
        raise ErrorRpc(error_code=403, error_message="USER_PRIVACY_RESTRICTED")

    ctx = request_ctx.get()
    this_auth = await UserAuthorization.get(user=user, id=ctx.auth_id)
    target_authorizations = await UserAuthorization.filter(
        user=peer.user, allow_call_requests=True
    ).values_list("id", flat=True)

    # TODO: save random_id
    call = await PhoneCall.create(
        from_user=user,
        from_sess=this_auth,
        to_user=peer.user,
        to_sess=None,
        g_a_hash=request.g_a_hash,
        discard_reason=None if target_authorizations else CallDiscardReason.MISSED,
        protocol=request.protocol.write(),
    )

    logger.info(f"Sending phone call update to authorizations: {target_authorizations}")

    # TODO: send service message if discard_reason is not None

    await upd.phone_call_update(user, call, [])
    await upd.phone_call_update(peer.user, call, target_authorizations)

    return PhonePhoneCall(
        phone_call=call.to_tl(),
        users=[
            await user.to_tl(),
            await peer.user.to_tl(),
        ],
    )


@handler.on_request(DiscardCall, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def discard_call(request: DiscardCall, user: User) -> Updates:
    ctx = request_ctx.get()
    call = await PhoneCall.get_or_none(
        Q(from_user=user, from_sess__id=ctx.auth_id) | Q(to_user=user),
        id=request.peer.id, access_hash=request.peer.access_hash, discard_reason__isnull=True,
    ).select_related("from_user", "to_user")
    if call is None:
        raise ErrorRpc(error_code=400, error_message="CALL_PEER_INVALID")

    if call.to_sess_id is None:
        target_authorizations = await UserAuthorization.filter(
            user=call.to_user, allow_call_requests=True,
        ).values_list("id")
        if user.id == call.from_user_id:
            reason = CallDiscardReason.MISSED
        else:
            reason = CallDiscardReason.BUSY
    else:
        target_authorizations = [call.to_sess_id]
        if isinstance(request.reason, PhoneCallDiscardReasonDisconnect):
            reason = CallDiscardReason.DISCONNECT
        else:
            reason = CallDiscardReason.HANGUP

    call.discard_reason = reason
    if call.started_at:
        call.duration = int((datetime.now(UTC) - call.started_at).total_seconds())
    await call.save(update_fields=["discard_reason"])

    peer, _ = await Peer.get_or_create(owner=user, user=call.other_user(user), defaults={"type": PeerType.USER})
    peer.owner = user
    peer.user = call.other_user(user)
    await send_message_internal(
        user, peer, None, None, False, author=call.from_user, type=MessageType.SERVICE_PHONE_CALL,
        extra_info=MessageActionPhoneCall(
            call_id=call.id,
            reason=CALL_DISCARD_REASON_TO_TL[reason],
            duration=call.duration,
        ).write(),
    )

    await upd.phone_call_update(call.to_user, call, target_authorizations)
    return await upd.phone_call_update(user, call, [])


@handler.on_request(AcceptCall, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def accept_call(request: AcceptCall, user: User) -> PhonePhoneCall:
    call = await PhoneCall.get_or_none(
        to_user=user, id=request.peer.id, access_hash=request.peer.access_hash,
    ).select_related("from_user", "to_user")
    if call is None:
        raise ErrorRpc(error_code=400, error_message="CALL_PEER_INVALID")

    if call.discard_reason is not None:
        raise ErrorRpc(error_code=400, error_message="CALL_ALREADY_DECLINED")
    if call.g_b is not None:
        raise ErrorRpc(error_code=400, error_message="CALL_ALREADY_ACCEPTED")

    _check_protocol(request.protocol)

    ctx = request_ctx.get()
    call.to_sess = await UserAuthorization.get(user=user, id=ctx.auth_id)
    call.g_b = request.g_b
    call.protocol = _merge_protocols(call.protocol_tl(), request.protocol).write()
    await call.save(update_fields=["to_sess_id", "g_b", "protocol"])

    target_authorizations = await UserAuthorization.filter(
        user=call.to_user, allow_call_requests=True,
    ).values_list("id")

    await upd.phone_call_update(user, call, target_authorizations)
    await upd.phone_call_update(call.from_user, call, [call.from_sess_id])

    return PhonePhoneCall(
        phone_call=call.to_tl(),
        users=[
            await user.to_tl(),
            await call.from_user.to_tl(),
        ],
    )


@handler.on_request(ConfirmCall, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def confirm_call(request: ConfirmCall, user: User) -> PhonePhoneCall:
    call = await PhoneCall.get_or_none(
        from_user=user, id=request.peer.id, access_hash=request.peer.access_hash,
    ).select_related("to_user", "from_user")
    if call is None:
        raise ErrorRpc(error_code=400, error_message="CALL_PEER_INVALID")

    if call.discard_reason is not None:
        raise ErrorRpc(error_code=400, error_message="CALL_ALREADY_DECLINED")
    if call.g_b is not None:
        raise ErrorRpc(error_code=400, error_message="CALL_PEER_INVALID")

    _check_protocol(request.protocol)

    if hashlib.sha256(request.g_a).digest() != call.g_a_hash:
        raise ErrorRpc(error_code=400, error_message="G_A_INVALID")

    call.g_a = request.g_a
    call.key_fp = request.key_fingerprint
    call.protocol = _merge_protocols(call.protocol_tl(), request.protocol).write()
    await call.save(update_fields=["g_a", "key_fp", "protocol"])

    await upd.phone_call_update(user, call, [])
    await upd.phone_call_update(call.to_user, call, [call.to_sess_id])

    # TODO: add connections to call

    return PhonePhoneCall(
        phone_call=call.to_tl(),
        users=[
            await user.to_tl(),
            await call.from_user.to_tl(),
        ],
    )


# TODO: ReceivedCall
