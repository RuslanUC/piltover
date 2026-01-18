import json
from time import time

from piltover.db.enums import PeerType
from piltover.db.models import User, Peer
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc
from piltover.tl import DataJSON, PhoneCallWaiting, PhoneCallProtocol
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
    return None

    if request.protocol.min_layer > request.protocol.max_layer:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_LAYER_INVALID")
    if request.protocol.min_layer < 65 or request.protocol.max_layer > 92:
        raise ErrorRpc(error_code=400, error_message="CALL_PROTOCOL_LAYER_INVALID")

    peer = await Peer.from_input_peer_raise(
        user, request.user_id, "USER_ID_INVALID", peer_types=(PeerType.USER,)
    )
    if peer.blocked_at:
        raise ErrorRpc(error_code=403, error_message="USER_IS_BLOCKED")

    return PhonePhoneCall(
        phone_call=PhoneCallWaiting(
            video=False,
            id=1,
            access_hash=1,
            date=int(time()),
            admin_id=user.id,
            participant_id=peer.user_id,
            protocol=PhoneCallProtocol(
                udp_p2p=False,
                udp_reflector=False,
                min_layer=request.protocol.min_layer,
                max_layer=request.protocol.max_layer,
                library_versions=request.protocol.library_versions,
            ),
            receive_date=None,
            conference_call=None,
        ),
        users=[
            await user.to_tl(),
            await peer.user.to_tl(),
        ],
    )
