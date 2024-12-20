[**Authorization Key**](https://core.telegram.org/mtproto/auth_key) generation:
  - Generate random prime numbers for `pq` decomposition, a proof of work to avoid clients' DoS to the server
  - Either use an old algorithm or `RSA_PAD` to encrypt the inner data payload
  - The server checks the stuff it needs to check, the client too
  - If everything went correctly, we are authorized
  - It is worth noting that every auth key has its own id (the 8 lower order bytes of `SHA1(auth_key)`)
  - Then key must be registered. It is done by creating auth_key_set server event, which should be overriden in your app (it gives ability to save auth keys anywhere you want (dict, database, etc.)).
  - Apart from the auth key id, every session has its own arbitrary (client provided) session_id, bound to the auth key.