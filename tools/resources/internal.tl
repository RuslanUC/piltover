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

internal.rpc_response#22be0328 flags:# transport_error:flags.0?int obj:flags.1?Object = internal.RpcResponse;

// Message exchange between gateway and brokers

internal.message_to_users#96d8b547 flags:# users:flags.0?Vector<long> channel_ids:flags.1?Vector<long> key_ids:flags.2?Vector<long> auth_ids:flags.4?Vector<long> ignore_auth_id:flags.5?Vector<long> obj:flags.3?Object = internal.MessageInternal;
internal.message_to_users_short#e49a2c2a flags:# user:flags.0?long channel_id:flags.1?long key_id:flags.2?long auth_id:flags.4?long ignore_auth_id:flags.5?long obj:flags.3?Object = internal.MessageInternal;
internal.set_session_internal_push#92aeb648 key_id:long session_id:long user_id:long = internal.MessageInternal;

internal.channel_subscribe#ae808cf6 flags:# subscribe:flags.0?true user_ids:Vector<long> channel_ids:Vector<long> = internal.ChannelSubscribe;

internal.lazy_user#f6eb7088 user_id:long = internal.LazyField;
internal.lazy_chat#229eb582 chat_id:long = internal.LazyField;
internal.lazy_channel#20803892 channel_id:long = internal.LazyField;
internal.lazy_message#e51fc740 message_id:long = internal.LazyField;
internal.lazy_encrypted_chat#b6696ef8 chat_id:long = internal.LazyField;
internal.object_with_lazy_fields#d836c6b8 object:Object fields:Vector<string> = internal.LazyObject;

internal.field_with_layer_requirement#d9594f1f field:string min_layer:int max_layer:int = internal.FieldWithLayerRequirement;
internal.object_with_layer_requirement#7678a3 object:Object fields:Vector<internal.FieldWithLayerRequirement> = internal.ObjectWithLayerRequirement;

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

// Service messages

internal.message_action_process_set_chat_wallpaper#ba5f701a flags:# same:flags.0?true for_both:flags.1?true wallpaper_id:long = internal.MessageActionNeedsProcessing;

---functions---

// For my.telegram.org alternative page

internal.send_code#bc8e37d8 phone_number:string = internal.SentCode;
internal.sign_in#53fa18be phone_number:string random_hash:bytes password:string = internal.Authorization;

internal.get_user_app#8b497a42 auth:bytes = internal.AppInfo;
internal.edit_user_app#be19f87d auth:bytes title:string short_name:string = Bool;

internal.get_available_servers#a2ed5af3 auth:bytes = internal.AvailableServers;

// Rpc calls between brokers

internal.call_rpc#ead5e531 flags:# auth_key_id:flags.1?long perm_auth_key_id:flags.0?long session_id:flags.2?long message_id:flags.3?long auth_id:flags.4?long user_id:flags.5?long layer:int obj:Object = internal.RpcResponse;
