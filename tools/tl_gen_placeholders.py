access_hash_calc = {
    "access_hash": {
        "self.access_hash == -1": "_calc",
    },
}
access_hash_and_file_ref_calc = {
    "access_hash": {
        "self.access_hash == -1": "_calc",
    },
    "file_reference": {
        "self.file_reference.startswith(b\"I\\x00O\\xaf\")": "_calc",
    },
}


PLACEHOLDERS = {
    # ChannelForbidden
    0x17d493d5: access_hash_calc,
    
    # Channel
    0x7482147e: access_hash_calc,
    # Channel_133
    0x8261ac61: access_hash_calc,
    # Channel_148
    0x83259464: access_hash_calc,
    # Channel_164
    0x94f592db: access_hash_calc,
    # Channel_166
    0x1981ea7e: access_hash_calc,
    # Channel_167
    0x8e87ccd8: access_hash_calc,
    # Channel_168
    0xaadfc8f: access_hash_calc,
    # Channel_186
    0xfe4478bd: access_hash_calc,
    # Channel_196
    0xe00998b7: access_hash_calc,
    
    # User
    0x20b1422: access_hash_calc,
    # User_133
    0x3ff6ecb0: access_hash_calc,
    # User_145
    0x5d99adee: access_hash_calc,
    # User_148
    0x8f97c628: access_hash_calc,
    # User_160
    0xabb5f120: access_hash_calc,
    # User_166
    0xeb602f25: access_hash_calc,
    # User_167
    0x215c4438: access_hash_calc,
    # User_185
    0x83314fca: access_hash_calc,
    # User_196
    0x4b46c37e: access_hash_calc,

    # TODO: make actual functions

    # InputPeerUser
    0xdde8a54c: access_hash_calc,
    # InputUser
    0xf21158c6: access_hash_calc,

    # InputPeerChannel
    0x27bcbbfc: access_hash_calc,

    # InputPhoto
    0x3bb3b94a: access_hash_and_file_ref_calc,

    # InputEncryptedFileLocation
    0xf5235d55: access_hash_calc,
    # InputDocumentFileLocation
    0xbad07584: access_hash_and_file_ref_calc,
    # InputSecureFileLocation
    0xcbc7ee28: access_hash_calc,
    # InputPhotoFileLocation
    0x40181ffe: access_hash_and_file_ref_calc,

    # Photo
    0xfb197a65: access_hash_and_file_ref_calc,

    # WallPaper
    0xa437c3ed: access_hash_calc,

    # EncryptedChatWaiting
    0x66b25953: access_hash_calc,

    # EncryptedChatRequested
    0x48f1d94c: access_hash_calc,

    # EncryptedChat
    0x61f0d4c7: access_hash_calc,

    # EncryptedFile
    0xa8008cd8: access_hash_calc,
    # EncryptedFile_133
    0x4a70994c: access_hash_calc,

    # Document
    0x8fd4c4d8: access_hash_and_file_ref_calc,
    # Document_133
    0x1e87342b: access_hash_and_file_ref_calc,

    # StickerSet
    0x2dd14edc: access_hash_calc,
    # StickerSet_133
    0xd7df217a: access_hash_calc,

    # InputChannel
    0xf35aec28: access_hash_calc,

    # Theme
    0xa00e67d6: access_hash_calc,
    # Theme_133
    0xe802b8dc: access_hash_calc,
}
