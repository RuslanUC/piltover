///////////////////////////////
/// Piltover internal types and functions
///////////////////////////////

---types---

// For my.telegram.org alternative page

internal.sent_code#0aebc70a random_hash:bytes = internal.SentCode;
internal.authorization#2c80fe90 auth:bytes = internal.Authorization;

internal.app_info#c5785da2 api_id:int api_hash:string title:string short_name:string = internal.AppInfo;
internal.app_not_found#235e45e5 = internal.AppInfo;

internal.public_key#1b3bde32 key:string fingerprint:long = internal.PublicKey;

internal.available_server#acc487b7 address:string port:int dc_id:int name:string public_keys:Vector<internal.PublicKey> = internal.AvailableServer;
internal.available_servers#58d5526f servers:Vector<internal.AvailableServer> = internal.AvailableServers;

// Rpc calls between brokers

internal.rpc_response#22be0328 flags:# refresh_auth:flags.2?true transport_error:flags.0?int obj:flags.1?Object = internal.RpcResponse;

// Message exchange between gateway and brokers

internal.message_to_users#96d8b547 flags:# users:flags.0?Vector<long> channel_ids:flags.1?Vector<long> key_ids:flags.2?Vector<long> auth_ids:flags.4?Vector<long> ignore_auth_id:flags.5?Vector<long> obj:flags.3?Object min_layer:flags.6?int = internal.MessageInternal;
internal.message_to_users_short#e49a2c2a flags:# user:flags.0?long channel_id:flags.1?long key_id:flags.2?long auth_id:flags.4?long ignore_auth_id:flags.5?long obj:flags.3?Object min_layer:flags.6?int = internal.MessageInternal;
internal.set_session_internal_push#92aeb648 key_id:long session_id:long user_id:long = internal.MessageInternal;

internal.channel_subscribe#ae808cf6 flags:# subscribe:flags.0?true user_ids:Vector<long> channel_ids:Vector<long> = internal.ChannelSubscribe;

internal.field_with_layer_requirement#d9594f1f field:string min_layer:int max_layer:int = internal.FieldWithLayerRequirement;
internal.object_with_layer_requirement#7678a3 object:Object fields:Vector<internal.FieldWithLayerRequirement> = internal.ObjectWithLayerRequirement;

internal.needs_context_values#b3e50ad9 flags:# obj:Object poll_answers:flags.0?Vector<long> chat_participants:flags.1?Vector<long> channel_participants:flags.2?Vector<long> users:flags.3?Vector<long> messages:flags.4?Vector<long> = internal.NeedsContextValues;

// Vectors with concrete types

internal.tagged_int_vector#f12bae38 vec:Vector<int> = internal.TaggedVector;
internal.tagged_long_vector#d3264171 vec:Vector<long> = internal.TaggedVector;
internal.tagged_int128_vector#ab8ac0d8 vec:Vector<Int128> = internal.TaggedVector;
internal.tagged_int256_vector#625ff3a1 vec:Vector<Int256> = internal.TaggedVector;
internal.tagged_float_vector#457a9f22 vec:Vector<double> = internal.TaggedVector;
internal.tagged_bool_vector#cb98721a vec:Vector<Bool> = internal.TaggedVector;
internal.tagged_bytes_vector#8d538c0f vec:Vector<bytes> = internal.TaggedVector;
internal.tagged_string_vector#492bec2d vec:Vector<string> = internal.TaggedVector;
internal.tagged_object_vector#b002bb63 vec:Vector<Object> = internal.TaggedVector;

// For benchmarking only

internal_benchmarking.nested_object#d5525aa8 some_int:int some_long:long = internal_benchmarking.NestedObject;

internal_benchmarking.deeply_nested_object_x8#88ab7760 some_int256:int256 nested_obj:internal_benchmarking.NestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x7#f5a1d88a some_int128:int128 inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x6#17b5ec16 flags:# opt_long:flags.0?long inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x5#524e6a6a some_double:double inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x4#c9bfbfd0 some_bool:Bool inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x3#11bdcd0b some_bytes:bytes inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x2#bfffaeb7 some_string:string inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;
internal_benchmarking.deeply_nested_object_x1#1c0441df some_long:long inner_object:internal_benchmarking.DeeplyNestedObject = internal_benchmarking.DeeplyNestedObject;

//internal_benchmarking.object_to_benchmark
//    flags:#
//
//    int32:int
//    optional_int32:flags.0?int
//    int64:long
//    optional_int64:flags.1?long
//    int128:int128
//    optional_int128:flags.2?int128
//    int256:int256
//    optional_int256:flags.3?int256
//    double:double
//    optional_double:flags.4?double
//    bytes_field:bytes
//    optional_bytes:flags.5?bytes
//    string_field:string
//    optional_string:flags.6?string
//    full_bool:Bool
//    optional_full_bool:flags.7?Bool
//    optional_bit_bool:flags.8?true
//    nested_object:internal_benchmarking.NestedObject
//    optional_nested_object:flags.9?internal_benchmarking.NestedObject
//    deeply_nested_object:internal_benchmarking.DeeplyNestedObject
//    optional_deeply_nested_object:flags.10?internal_benchmarking.DeeplyNestedObject
//
//    int32_vec:Vector<int>
//    optional_int32_vec:flags.11?Vector<int>
//    int64_vec:Vector<long>
//    optional_int64_vec:flags.12?Vector<long>
//    int128_vec:Vector<int128>
//    optional_int128_vec:flags.13?Vector<int128>
//    int256_vec:Vector<int256>
//    optional_int256_vec:flags.14?Vector<int256>
//    double_vec:Vector<double>
//    optional_double_vec:flags.15?Vector<double>
//    bytes_field_vec:Vector<bytes>
//    optional_bytes_vec:flags.16?Vector<bytes>
//    string_field_vec:Vector<string>
//    optional_string_vec:flags.17?Vector<string>
//    full_bool_vec:Vector<Bool>
//    optional_full_bool_vec:flags.18?Vector<Bool>
//    nested_object_vec:Vector<internal_benchmarking.NestedObject>
//    optional_nested_object_vec:flags.19?Vector<internal_benchmarking.NestedObject>
//    deeply_nested_object_vec:Vector<internal_benchmarking.DeeplyNestedObject>
//    optional_deeply_nested_object_vec:flags.20?Vector<internal_benchmarking.DeeplyNestedObject>
//
//    flags2:#
//
//    int32_flags2:int
//    optional_int32_flags2:flags2.0?int
//    int64_flags2:long
//    optional_int64_flags2:flags2.1?long
//    int128_flags2:int128
//    optional_int128_flags2:flags2.2?int128
//    int256_flags2:int256
//    optional_int256_flags2:flags2.3?int256
//    double_flags2:double
//    optional_double_flags2:flags2.4?double
//    bytes_field_flags2:bytes
//    optional_bytes_flags2:flags2.5?bytes
//    string_field_flags2:string
//    optional_string_flags2:flags2.6?string
//    full_bool_flags2:Bool
//    optional_full_bool_flags2:flags2.7?Bool
//    optional_bit_bool_flags2:flags2.8?true
//    nested_object_flags2:internal_benchmarking.NestedObject
//    optional_nested_object_flags2:flags2.9?internal_benchmarking.NestedObject
//    deeply_nested_object_flags2:internal_benchmarking.DeeplyNestedObject
//    optional_deeply_nested_object_flags2:flags2.10?internal_benchmarking.DeeplyNestedObject
//
//    int32_vec_flags2:Vector<int>
//    optional_int32_vec_flags2:flags2.11?Vector<int>
//    int64_vec_flags2:Vector<long>
//    optional_int64_vec_flags2:flags2.12?Vector<long>
//    int128_vec_flags2:Vector<int128>
//    optional_int128_vec_flags2:flags2.13?Vector<int128>
//    int256_vec_flags2:Vector<int256>
//    optional_int256_vec_flags2:flags2.14?Vector<int256>
//    double_vec_flags2:Vector<double>
//    optional_double_vec_flags2:flags2.15?Vector<double>
//    bytes_field_vec_flags2:Vector<bytes>
//    optional_bytes_vec_flags2:flags2.16?Vector<bytes>
//    string_field_vec_flags2:Vector<string>
//    optional_string_vec_flags2:flags2.17?Vector<string>
//    full_bool_vec_flags2:Vector<Bool>
//    optional_full_bool_vec_flags2:flags2.18?Vector<Bool>
//    nested_object_vec_flags2:Vector<internal_benchmarking.NestedObject>
//    optional_nested_object_vec_flags2:flags2.19?Vector<internal_benchmarking.NestedObject>
//    deeply_nested_object_vec_flags2:Vector<internal_benchmarking.DeeplyNestedObject>
//    optional_deeply_nested_object_vec_flags2:flags2.20?Vector<internal_benchmarking.DeeplyNestedObject>
//
//    = internal_benchmarking.ObjectToBenchmark;
internal_benchmarking.object_to_benchmark#96be42f flags:# int32:int optional_int32:flags.0?int int64:long optional_int64:flags.1?long int128:int128 optional_int128:flags.2?int128 int256:int256 optional_int256:flags.3?int256 double:double optional_double:flags.4?double bytes_field:bytes optional_bytes:flags.5?bytes string_field:string optional_string:flags.6?string full_bool:Bool optional_full_bool:flags.7?Bool optional_bit_bool:flags.8?true nested_object:internal_benchmarking.NestedObject optional_nested_object:flags.9?internal_benchmarking.NestedObject deeply_nested_object:internal_benchmarking.DeeplyNestedObject optional_deeply_nested_object:flags.10?internal_benchmarking.DeeplyNestedObject int32_vec:Vector<int> optional_int32_vec:flags.11?Vector<int> int64_vec:Vector<long> optional_int64_vec:flags.12?Vector<long> int128_vec:Vector<int128> optional_int128_vec:flags.13?Vector<int128> int256_vec:Vector<int256> optional_int256_vec:flags.14?Vector<int256> double_vec:Vector<double> optional_double_vec:flags.15?Vector<double> bytes_field_vec:Vector<bytes> optional_bytes_vec:flags.16?Vector<bytes> string_field_vec:Vector<string> optional_string_vec:flags.17?Vector<string> full_bool_vec:Vector<Bool> optional_full_bool_vec:flags.18?Vector<Bool> nested_object_vec:Vector<internal_benchmarking.NestedObject> optional_nested_object_vec:flags.19?Vector<internal_benchmarking.NestedObject> deeply_nested_object_vec:Vector<internal_benchmarking.DeeplyNestedObject> optional_deeply_nested_object_vec:flags.20?Vector<internal_benchmarking.DeeplyNestedObject> flags2:# int32_flags2:int optional_int32_flags2:flags2.0?int int64_flags2:long optional_int64_flags2:flags2.1?long int128_flags2:int128 optional_int128_flags2:flags2.2?int128 int256_flags2:int256 optional_int256_flags2:flags2.3?int256 double_flags2:double optional_double_flags2:flags2.4?double bytes_field_flags2:bytes optional_bytes_flags2:flags2.5?bytes string_field_flags2:string optional_string_flags2:flags2.6?string full_bool_flags2:Bool optional_full_bool_flags2:flags2.7?Bool optional_bit_bool_flags2:flags2.8?true nested_object_flags2:internal_benchmarking.NestedObject optional_nested_object_flags2:flags2.9?internal_benchmarking.NestedObject deeply_nested_object_flags2:internal_benchmarking.DeeplyNestedObject optional_deeply_nested_object_flags2:flags2.10?internal_benchmarking.DeeplyNestedObject int32_vec_flags2:Vector<int> optional_int32_vec_flags2:flags2.11?Vector<int> int64_vec_flags2:Vector<long> optional_int64_vec_flags2:flags2.12?Vector<long> int128_vec_flags2:Vector<int128> optional_int128_vec_flags2:flags2.13?Vector<int128> int256_vec_flags2:Vector<int256> optional_int256_vec_flags2:flags2.14?Vector<int256> double_vec_flags2:Vector<double> optional_double_vec_flags2:flags2.15?Vector<double> bytes_field_vec_flags2:Vector<bytes> optional_bytes_vec_flags2:flags2.16?Vector<bytes> string_field_vec_flags2:Vector<string> optional_string_vec_flags2:flags2.17?Vector<string> full_bool_vec_flags2:Vector<Bool> optional_full_bool_vec_flags2:flags2.18?Vector<Bool> nested_object_vec_flags2:Vector<internal_benchmarking.NestedObject> optional_nested_object_vec_flags2:flags2.19?Vector<internal_benchmarking.NestedObject> deeply_nested_object_vec_flags2:Vector<internal_benchmarking.DeeplyNestedObject> optional_deeply_nested_object_vec_flags2:flags2.20?Vector<internal_benchmarking.DeeplyNestedObject> = internal_benchmarking.ObjectToBenchmark;

// BotFather state

internal_botfather.botfather_state_newbot#bcb2c294 name:string = internal_botfather.BotFatherState;
internal_botfather.botfather_state_editbot#ad2641a6 bot_id:long = internal_botfather.BotFatherState;

// @Stickers state

internal_stickersbot.newpack_input_sticker#fe36b3bd file_id:long emoji:string = internal_stickersbot.NewpackInputSticker;

internal_stickersbot.emoji_pack_type_static#371ef88f = internal_stickersbot.EmojiPackType;
internal_stickersbot.emoji_pack_type_video#be690159 = internal_stickersbot.EmojiPackType;
internal_stickersbot.emoji_pack_type_animated#100a52c = internal_stickersbot.EmojiPackType;

internal_stickersbot.stickers_state_newpack#70a163dd name:string stickers:Vector<internal_stickersbot.NewpackInputSticker> = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_addsticker#adc6611f set_id:long file_id:long = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_editsticker#d3add072 flags:# set_id:flags.0?long file_id:flags.1?long = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_delpack#1852c118 set_id:long = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_renamepack#b4b529e2 set_id:long = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_replacesticker#dce7b0f5 flags:# set_id:flags.0?long file_id:flags.1?long = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_newemojipack#3d1302b7 flags:# type:internal_stickersbot.EmojiPackType name:flags.0?string stickers:flags.1?Vector<internal_stickersbot.NewpackInputSticker> = internal_stickersbot.StickersBotState;
internal_stickersbot.stickers_state_addemoji#c7087987 set_id:long file_id:long = internal_stickersbot.StickersBotState;

// Access hashes
internal_access.access_hash_payload_user#916e7528 this_user_id:long user_id:long auth_id:long = internal_access.AccessHashPayload;
internal_access.access_hash_payload_channel#8195bf26 this_user_id:long channel_id:long auth_id:long = internal_access.AccessHashPayload;
internal_access.access_hash_payload_file#4c9a07fe this_user_id:long file_id:long auth_id:long = internal_access.AccessHashPayload;
internal_access.access_hash_payload_encrypted_chat#a773e2af this_user_id:long chat_id:long auth_id:long = internal_access.AccessHashPayload;
internal_access.access_hash_payload_stickerset#8009da5b this_user_id:long set_id:long auth_id:long = internal_access.AccessHashPayload;
internal_access.access_hash_payload_wallpaper#cb83392e this_user_id:long wallpaper_id:long auth_id:long = internal_access.AccessHashPayload;
internal_access.access_hash_payload_theme#1c9a2a19 this_user_id:long theme_id:long auth_id:long = internal_access.AccessHashPayload;

internal_access.file_reference_payload#af4f0049 file_id:long created_at:int = internal_access.FileReferencePayload;

// Generated "*ToFormat" constructors

wallPaperToFormatInternal#68dda86b flags:# id:long creator_id:long pattern:flags.0?true dark:flags.1?true slug:string document:Document settings:flags.2?WallPaperSettings = WallPaper;
messageServiceToFormatInternal#efce62cb flags:# author_id:long id:int from_id:flags.0?Peer peer_id:Peer reply_to:flags.1?MessageReplyHeader date:int action:MessageAction ttl_period:flags.2?int = Message;
themeToFormatInternal#150039e1 flags:# creator_id:flags.0?long for_chat:flags.5?true id:long slug:string title:string document:flags.2?Document settings:flags.3?Vector<ThemeSettings> emoticon:flags.6?string = Theme;
chatToFormatInternal#afe6f89 flags:# creator_id:long deactivated:flags.0?true noforwards:flags.1?true id:long title:string photo:flags.2?ChatPhoto participants_count:int date:long version:long migrated_to:flags.3?long default_banned_rights:ChatBannedRights = Chat;
channelToFormatInternal#89ce0d3a flags:# creator_id:long noforwards:flags.0?true id:long title:string photo:flags.1?ChatPhoto created_at:long default_banned_rights:ChatBannedRights broadcast:flags.2?true megagroup:flags.3?true signatures:flags.4?true has_link:flags.5?true slowmode_enabled:flags.6?true join_to_send:flags.7?true join_request:flags.8?true username:flags.9?string color:flags.10?PeerColor profile_color:flags.11?PeerColor nojoin_allow_view:flags.12?true = Chat;
userToFormatInternal#276511f3 flags:# id:long first_name:string last_name:flags.0?string username:flags.1?string phone:flags.2?string lang_code:string photo:flags.3?UserProfilePhoto bot:flags.4?true bot_info_version:flags.5?long color:flags.6?PeerColor profile_color:flags.6?PeerColor = User;
encryptedChatToFormatInternal#44045474 flags:# id:long access_hash:long date:long admin_id:long participant_id:long admin_sess_id:long participant_sess_id:flags.0?long g_a:bytes g_b:flags.1?bytes key_fingerprint:flags.2?long = EncryptedChat;
dumbChannelMessageToFormatInternal#6afa05f5 id:long = Message;
pollResultsToFormatInternal#fb007fa4 flags:# id:long results:Vector<PollAnswerVoters> total_voters:int solution:flags.0?string solution_entities:flags.0?Vector<MessageEntities> = PollResults;
pollAnswerVotersToFormatInternal#a6ad847b flags:# id:long poll_id:long correct:flags.0?true option:bytes voters:int = PollAnswerVoters;

---functions---

// For my.telegram.org alternative page

internal.send_code#bc8e37d8 phone_number:string = internal.SentCode;
internal.sign_in#53fa18be phone_number:string random_hash:bytes password:string = internal.Authorization;

internal.get_user_app#8b497a42 auth:bytes = internal.AppInfo;
internal.edit_user_app#be19f87d auth:bytes title:string short_name:string = Bool;

internal.get_available_servers#a2ed5af3 auth:bytes = internal.AvailableServers;

// Rpc calls between brokers

// TODO: tl id is not updated
internal.call_rpc#ead5e531 flags:# is_bot:flags.6?true mfa_pending:flags.7?true auth_key_id:flags.1?long perm_auth_key_id:flags.0?long session_id:flags.2?long message_id:flags.3?long auth_id:flags.4?long user_id:flags.5?long layer:int obj:Object = internal.RpcResponse;
