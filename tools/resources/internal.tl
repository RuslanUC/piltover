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

---functions---

// For my.telegram.org alternative page

internal.send_code#bc8e37d8 phone_number:string = internal.SentCode;
internal.sign_in#53fa18be phone_number:string random_hash:bytes password:string = internal.Authorization;

internal.get_user_app#8b497a42 auth:bytes = internal.AppInfo;
internal.edit_user_app#be19f87d auth:bytes title:string short_name:string = Bool;

internal.get_available_servers#a2ed5af3 auth:bytes = internal.AvailableServers;
