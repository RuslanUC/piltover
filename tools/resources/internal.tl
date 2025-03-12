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

internal.message_to_users#28b10372 flags:# users:flags.0?Vector<long> channel_ids:flags.1?Vector<long> key_ids:flags.2?Vector<long> obj:flags.3?Object = internal.MessageInternal;
internal.message_to_users_short#6faafc7c flags:# user:flags.0?long channel_id:flags.1?long key_id:flags.2?long obj:flags.3?Object = internal.MessageInternal;
internal.set_session_internal_push#92aeb648 key_id:long session_id:long user_id:long = internal.MessageInternal;

internal.channel_subscribe#ae808cf6 flags:# subscribe:flags.0?true user_ids:Vector<long> channel_ids:Vector<long> = internal.ChannelSubscribe;

---functions---

// For my.telegram.org alternative page

internal.send_code#bc8e37d8 phone_number:string = internal.SentCode;
internal.sign_in#53fa18be phone_number:string random_hash:bytes password:string = internal.Authorization;

internal.get_user_app#8b497a42 auth:bytes = internal.AppInfo;
internal.edit_user_app#be19f87d auth:bytes title:string short_name:string = Bool;

internal.get_available_servers#a2ed5af3 auth:bytes = internal.AvailableServers;

// Rpc calls between brokers

internal.call_rpc#35fc3df3 flags:# key_is_temp:flags.0?true auth_key_id:flags.1?long session_id:flags.2?long message_id:flags.3?long auth_id:flags.4?long user_id:flags.5?long obj:Object = internal.RpcResponse;
