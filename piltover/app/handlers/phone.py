import json

from piltover.enums import ReqHandlerFlags
from piltover.tl import DataJSON
from piltover.tl.functions.phone import GetCallConfig
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
    return DataJSON(
        data=CALL_CONFIG,
    )
