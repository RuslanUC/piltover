### This are my thoughts on how channels access should be implemented

First of all, we have `Peer`s and `ChatParticipant`s.
Channel info request (`GetChannels`, `GetFullChannel`, etc.) should only check for `Peer` existence.
`Channel`.`to_tl` should check **only** for `Peer` as well.
When requesting messages (`GetHistory`, `GetMessages`, etc.), we should check for `Peer` and if `ChatParticipant` is banned.
If `ChatParticipant` exists, but not banned - allow, if does not exist - also allow.
Same logic should be applied to reactions (requesting, sending).

Now, for sending messages, we need to check for **both** `Peer` and `ChatParticipant` + for user rights in channel:
  - if _creator_ - allow
  - if _channel_ and _user_ - disallow
  - if _channel_ and _admin_ and _has **admin** permission to send messages_ - allow
  - if _channel_ and _admin_ and _does not have **admin** permission to send messages_ - disallow
  - if _supergroup_ and _user_ and _send messages is banned_ - disallow
  - if _supergroup_ and _user_ and _send messages is not banned_ - allow
  - if _supergroup_ and _admin_ and _send messages is banned_ and _does not have **admin** permission to send messages_ - disallow
  - if _supergroup_ and _admin_ and _send messages is banned_ and _has **admin** permission to send messages_ - allow
