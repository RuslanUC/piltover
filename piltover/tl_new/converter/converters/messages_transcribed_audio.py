from piltover.tl_new.types.messages import TranscribedAudio, TranscribedAudio_143
from piltover.tl_new.converter import ConverterBase


class TranscribedAudioConverter(ConverterBase):
    base = TranscribedAudio
    old = [TranscribedAudio_143]
    layers = [143]

    @staticmethod
    def from_143(obj: TranscribedAudio_143) -> TranscribedAudio:
        data = obj.to_dict()
        return TranscribedAudio(**data)

    @staticmethod
    def to_143(obj: TranscribedAudio) -> TranscribedAudio_143:
        data = obj.to_dict()
        del data["trial_remains_until_date"]
        del data["trial_remains_num"]
        return TranscribedAudio_143(**data)

