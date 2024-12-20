The client connects with TCP sockets to the server (websockets for web clients)

The first bytes sent within a new connection determine the used [transport](https://core.telegram.org/mtproto/mtproto-transports):
  - `0xef`: Abridged
  - `0xeeeeeeee`: Intermediate
  - `0xdddddddd`: Padded Intermediate
  - `[length: 4 bytes][0x00000000]`: TCP Full, distinguishable by the empty `seq_no` (`0x00000000`)
  - `[presumably random bytes]`: _Usually_ an [Obfuscated](https://core.telegram.org/mtproto/mtproto-transports#transport-obfuscation) transport
  - To distinguish between `TCP Full` and `Obfuscated` transports, a buffered reader is needed, to allow for peeking the stream without consuming it.

> [!NOTE]  
> Current implementation of transports is moved out to [MTProto](https://github.com/RuslanUC/mtproto) project to make it reusable.

Currently, there are three types of packets supported:
  - `Message`: regular mtproto packet that contains (usually) tl-encoded object. It's encoding for different protocols:
    - `Abridged`: length of payload is divided by 4, message is encoded like this: `[length divided by 4: 1 byte][payload]` 
      if `length divided by 4` is less than 127 and like `0x7f[length divided by 4: 3 bytes][payload]` otherwise.
      This transport supports quick-acks: if client wants to request quick-ack, it adds 0x80 (sets first bit to 1) to `length divided by 4`.
    - `Intermediate`: message is encoded like this: `[length: 4 bytes][payload]` 
      This transport supports quick-acks: if client wants to request quick-ack, it adds 0x80000000 (sets first bit to 1) to length.
    - `Padded Intermediate`: message is encoded like this: `[length: 4 bytes][payload][padding: random bytes up to 4?]`.
      Minimal `payload + padding` size needs to be bigger than 16 bytes.
      This transport supports quick-acks: if client wants to request quick-ack, it adds 0x80000000 (sets first bit to 1) to length.
    - `Full`: message is encoded like this: `[length: 4 bytes][seq_no: 4 bytes][payload][crc: 4 bytes]`.
      This transport does not support quick-acks.
  - `Error` (in the following examples error_code is 404): 
    - `Abridged`: negative error code is encoded as 4 bytes, like this: `[length divided by 4: 1 byte: 0x01][error_code: 0x6cfeffff]`.
    - `Intermediate`: negative error code is encoded as 4 bytes, like this: `[length: 4 bytes: 0x04000000][error_code: 0x6cfeffff]`.
    - `Padded Intermediate`: negative error code is encoded as first 4 bytes of payload, bytes 4-8 are random, like this: `[length: 8 bytes: 0x08000000][error_code: 0x6cfeffff][random valud: 4 bytes]`.
    - `Full`: negative error code is encoded as 4 bytes, like this: `[length: 4 bytes][seq_no: 4 bytes][error_code: 0x6cfeffff][crc: 4 bytes]`.
  - `QuickAck` (sent by server only): TODO