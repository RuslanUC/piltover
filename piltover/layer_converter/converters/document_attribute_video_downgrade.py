from piltover.layer_converter.converters.base import AutoDowngrader
from piltover.tl import DocumentAttributeVideo, DocumentAttributeVideo_133, DocumentAttributeVideo_160, \
    DocumentAttributeVideo_185


class DocumentAttributeVideoDowngradeTo133(AutoDowngrader):
    BASE_TYPE = DocumentAttributeVideo
    TARGET_TYPE = DocumentAttributeVideo_133
    TARGET_LAYER = 133
    REMOVE_FIELDS = {"nosound", "preload_prefix_size", "video_start_ts", "video_codec"}


class DocumentAttributeVideoDowngradeTo160(AutoDowngrader):
    BASE_TYPE = DocumentAttributeVideo
    TARGET_TYPE = DocumentAttributeVideo_160
    TARGET_LAYER = 160
    REMOVE_FIELDS = {"video_start_ts", "video_codec"}


class DocumentAttributeVideoDowngradeTo185(AutoDowngrader):
    BASE_TYPE = DocumentAttributeVideo
    TARGET_TYPE = DocumentAttributeVideo_185
    TARGET_LAYER = 185
    REMOVE_FIELDS = {"video_codec"}


class DocumentAttributeVideoDontDowngrade(AutoDowngrader):
    BASE_TYPE = DocumentAttributeVideo
    TARGET_TYPE = DocumentAttributeVideo
    TARGET_LAYER = 201
    REMOVE_FIELDS = set()
