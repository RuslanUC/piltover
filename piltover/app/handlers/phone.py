import json

import piltover.app.utils.updates_manager as upd
from piltover.context import request_ctx
from piltover.db.enums import PeerType, PrivacyRuleKeyType, CallDiscardReason
from piltover.db.models import User, Peer, PrivacyRule, UserAuthorization, PhoneCall
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import DataJSON
from piltover.tl.functions.phone import GetCallConfig, RequestCall
from piltover.tl.types.phone import PhoneCall as PhonePhoneCall
from piltover.worker import MessageHandler

handler = MessageHandler("phone")

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


@handler.on_request(RequestCall, ReqHandlerFlags.BOT_NOT_ALLOWED)
async def request_call(request: RequestCall, user: User) -> PhonePhoneCall:
    if request.protocol.min_layer > request.protocol.max_layer:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_LAYER_INVALID")
    if request.protocol.min_layer < 65 or request.protocol.max_layer > 92:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_LAYER_INVALID")

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
    target_authorizations = await UserAuthorization.filter(user=peer.user, allow_call_requests=True).values_list("id")

    call = await PhoneCall.create(
        from_user=user,
        from_sess=this_auth,
        to_user=peer.user,
        to_sess=None,
        g_a_hash=request.g_a_hash,
        discard_reason=None if target_authorizations else CallDiscardReason.MISSED,
    )

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
