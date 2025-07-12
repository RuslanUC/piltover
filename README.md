# piltover 🐳

An experimental Telegram server written from scratch in Python. Development chat (of original [piltover](https://github.com/DavideGalilei/piltover) project): linked group to [@ChameleonGram](https://t.me/ChameleonGram).

## TODO

- [ ] WebK gets stuck on `sendCode()`. (note to self: inspect the MTProto workers in `chrome://inspect/#workers`)
- [ ] MTProxy support maybe? Obfuscation is already implemented, so why not?
- [ ] HTTP/UDP support? Probably Telegram itself forgot those also exist.
- [ ] Improve the README.
- [ ] Proper read states updates (updateReadHistoryInbox, updateReadHistoryOutbox)
- [ ] Reactions
- [ ] Stickers
- [ ] Move UpdatesManager to separate worker
- [ ] Add caching of some tl objects (e.g. piltover.tl.types.User, piltover.tl.types.Chat, piltover.tl.types.Message, etc.) based on versions (i think maybe add `version` field to db models and cache to_tl method results to key `[current_user_id]:[to_tl_user_id]:[version]` or something like that)
- [x] Add proper privacy rules handling
- [x] Channels
- [ ] Supergroups
- [ ] Scheduled messages
- [ ] Bots
- [x] Dialog filters (folders)
- [x] Secret chats (https://core.telegram.org/api/end-to-end)
- [ ] Media read state (messages.readMessageContents / channels.readMessageContents and updateReadMessagesContents / updateChannelReadMessagesContents)
- [ ] Mentions read state

There is also many [`# TODO`'s](https://github.com/search?q=repo%3ARuslanUC%2Fpiltover+%23+TODO&type=code) in code that need to be done.

## Purpose

This project is currently not meant to be used to host custom Telegram
instances, as most **security measures are <u>currently</u> barely in place**.
For now, it can be used by MTProto clients developers to understand why their
code fails, whereas Telegram just closes the connection with a -404 error code.

That being said, it is planned in future to make it usable for most basic
Telegram features, including but not limited to, sending and receiving text and
media messages, media, search.

This can be really useful for bots developers that would like to have a testing
sandbox that doesn't ratelimit their bots.

Right now, project **may** (although not recommended) be used for basic features like messages/media sending.
More complex features such as group chats, profile photos, etc. may work with errors.
**Keep in mind that privacy settings may work incorrectly so any user can be texted by anyone, added to any group by anyone, etc.**

## Setup

Requirements:

- Python 3.11+
- Poetry

Setup:

1. Clone repository:
   ```shell
   git clone https://github.com/RuslanUC/piltover
   ```
2. Install dependencies:
    ```shell
    poetry install
    ```
3. Generate tl classes:
    ```shell
   poetry shell python tools/tl_gen.py
    ```
4. (Optional) Install mariadb.
5. Run:
    ```shell
    poetry run python -m piltover.app.app
    ```
   
Now wait until it loads correctly and fire a Ctrl-C to stop the process.

> **You should see a line looking like this at the beginning**
>
> ```yml
> 2023-11-05 19:52:31.171 | INFO     | __main__:main:49 - Pubkey fingerprint: -6bff292cf4837025 (9400d6d30b7c8fdb)
> ```

**Get the fingerprint hex string and save it for later (some clients need it)**.
In this case, the unsigned fingerprint is `9400d6d30b7c8fdb`, but only for this
example. Do not reuse this key fingerprint, as it will be different in your
setup.

#### **Extract public key number and exponent**

At this point, two files should have been generated in your directory. Namely,
`data/secrets/privkey.asc` and `data/secrets/pubkey.asc`. Keep in mind that some
clients might need the PKCS1 public key in the normal ascii format.

Some others like pyrogram, do not have an RSA key parser and hardcode the
number/exponent. To extract it, you can use
[this command](https://github.com/pyrogram/pyrogram/blob/b19764d5dc9e2d59a4ccbb7f520f78505800656b/pyrogram/crypto/rsa.py#L26):

```shell
$ grep -v -- - data/secrets/pubkey.asc | tr -d \\n | base64 -d | openssl asn1parse -inform DER -i
```

An example output would look like this:

```yml
  0:d=0  hl=4 l= 266 cons:  SEQUENCE          
  4:d=1  hl=4 l= 257 prim:  INTEGER           :C3AE9457FDB44F47B91B9389401933F2D0B27357FE116ED7640798784829FDBC66295169D1D323AB664FD6920EFBAAC8725DA7EACAA491D1F1EEC8259CA68E4CFE86FC6823C903A323DE46C0E64B8DD5C93A188711C1BF78FCBE0C99904227A66C9135241DD8B92A0AD88AB3A6734BC13B57FA38614BB2AA79F3EF0920D577928F7E689B7B5B0A1A8A48DA9D7E4C28F2A8F1AAEDA22AC4DA05324C1CB67538ADFE1AC3201B34A85189B0765E6C79FF443433837B540D6295BF9EE95B8CDA709868C450BE9730C9FCC7442011129AFB45187C2A1913A4974709E9666865C4F06067E981BF57950A0395B45C3A7322FD36F77D803FF97897BC00D5687A3CB575D1
265:d=1  hl=2 l=   3 prim:  INTEGER           :010001
```

**Note the exponent (`010001`) and the prime number: (`C3AE94...B575D1`). Save
those values for later.**

Also, gateway and rpc workers **may** (although such setup is not tested) be used separately (for this you need rabbitmq and redis running):
run both `piltover.app.app` and `piltover.app.worker` with `--rabbitmq-address` and `--redis-address`.

### **Pyrogram**

- `git clone --depth=1 https://github.com/pyrogram/pyrogram`
- Edit this dictionary:
  https://github.com/pyrogram/pyrogram/blob/b19764d5dc9e2d59a4ccbb7f520f78505800656b/pyrogram/crypto/rsa.py#L33
  - The key is the **server fingerprint**, the value is formed by this
    expression: `PublicKey(int(` **prime** `16), int(` **exponent** `, 16))`
  - Replace those values, (optional: delete the rest of the keys)
- Edit the datacenters ips in
  [this file](https://github.com/pyrogram/pyrogram/blob/b19764d5dc9e2d59a4ccbb7f520f78505800656b/pyrogram/session/internals/data_center.py#L22):
  - Every ip should become `"127.0.0.1"` (localhost)
  - In the `DataCenter.__new__` method below, replace every return with
    `return (ip,` **4430** `)`, instead of ports 80/443
- Install in development mode with `python3 -m pip install -e .`
- Ready to use, run the server and check if `test.py` works

### **Telethon**

- `git clone --depth=1 https://github.com/LonamiWebs/telethon`
- Edit these variables:
  https://github.com/LonamiWebs/Telethon/blob/2007c83c9e1b1c85e60e4eca8e8651fcb120ee88/telethon/client/telegrambaseclient.py#L21-L24
  - ```python
    DEFAULT_DC_ID = 2
    DEFAULT_IPV4_IP = '127.0.0.1'
    DEFAULT_IPV6_IP = '2001:67c:4e8:f002::a'
    DEFAULT_PORT = 4430
    ```
  - Just make sure that the default dc is 2, the ipv4 is localhost, and the
    default port is 4430. We don't really use ipv6 anyway...
- Add the rsa public key:
  - Edit this file:
    https://github.com/LonamiWebs/Telethon/blob/2007c83c9e1b1c85e60e4eca8e8651fcb120ee88/telethon/crypto/rsa.py#L85
  - Ideally, delete all the existing keys
  - Take your server's public key from the `data/secrets/pubkey.asc` file, and
    add it there with `add_key("""` **key here** `""", old=False)`
- Install in development mode with `python3 -m pip install -e .`
- Ready to use, run the server and check if `telethon_test.py` works

### **Telegram Desktop**

- Edit
  [this file](https://github.com/telegramdesktop/tdesktop/blob/2acedca6b740f6471b6ebe2e0c500bec32a0a94c/Telegram/SourceFiles/mtproto/mtproto_dc_options.cpp#L31-L78):
  - As always, replace every ip with `127.0.0.1` (localhost), and every port
    with `4430`
  - Remove the existing rsa keys, and replace them with your own, taken from the
    `data/secrets/pubkey.asc` file on your piltover folder. **Important:** check
    the newlines thoroughly and make sure they are there, or it won't work.
- Build the program, ideally with GitHub Actions
- Put the executable in a folder, e.g. `tdesk`
- ~~Since we don't save the auth keys, you should delete the leftover files from
  tdesktop at every run. You can do this conveniently and run your custom
  TDesktop with this command:~~

```shell
$ rm -rf tdata/ DebugLogs/ log.txt && c && ./Telegram
```

### **Telegram Android (recommended: Owlgram)**

- Clone the repo and follow the basic setup instructions
- Edit this file:
  https://github.com/OwlGramDev/OwlGram/blob/master/TMessagesProj/jni/tgnet/ConnectionsManager.cpp#L1702-L1756
  - Replace every ip with your local ip address. It can be `127.0.0.1`
    (localhost) only in the case you're running the app with an emulator on the
    same machine the server is running. Otherwise, change it with e.g.
    `192.168.1.35` (the LAN ip address of your machine).
  - Replace every port with `4430`
- Edit this file:
  https://github.com/OwlGramDev/OwlGram/blob/master/TMessagesProj/jni/tgnet/Handshake.cpp#L355-L372
  - Remove the existing rsa keys, and replace them with your own, taken from the
    `data/secrets/pubkey.asc` file on your piltover folder. **Important:** check
    the newlines thoroughly and make sure they are there, or it won't work. This
    took me way too much debugging time to realize that the missing newlines was
    the cause of the app crashes.
- Build the app, and see if it works.

### **Telegram WebK**

- Clone repo and install dependencies:
  - ```shell
    $ git clone https://github.com/morethanwords/tweb
    $ cd tweb
    $ npm i -g pnpm
    $ pnpm install
    ```
- Edit the values in this file:
  https://github.com/morethanwords/tweb/blob/f2827d9c19616a560346bd1662665ca30dc54668/src/lib/mtproto/dcConfigurator.ts#L50
  - Change `` const chosenServer = `wss://...` `` to:
  - ```typescript
    const chosenServer = `ws://127.0.0.1:3000/proxy`;
    ```
  - Change every datacenter ip and port below, respectively to `127.0.0.1`
    (localhost) and `3000` (websocket proxy port)
    https://github.com/morethanwords/tweb/blob/f2827d9c19616a560346bd1662665ca30dc54668/src/lib/mtproto/dcConfigurator.ts#L58-L70
- Edit the values in this file:
  https://github.com/morethanwords/tweb/blob/f2827d9c19616a560346bd1662665ca30dc54668/src/lib/mtproto/rsaKeysManager.ts#L69-L78
  - Change the `modulus` to the **lowercase** string of `prime` obtained previously
- Run the websocket proxy from piltover
  - ```shell
    $ poetry run python tools/websocket_proxy.py
    ```
- Run with `npm start`
- Wait some time for the app to compile
- Open the app in your browser (usually `https://0.0.0.0:8080/`)

### **Telegram WebZ**

- #TODO: WebZ instructions

### **Nimgram**

- #TODO: the client is currently under active development and refactoring, so I
  will wait until a working version is released

### Telegram X/TDLib

- #TODO: add instructions. I haven't figured out how it should be done yet.

#### _Make a pull request if you want to add instructions for your own client._


## Miscellaneous

List of other server implementations I found:

- https://github.com/teamgram/teamgram-server
- https://github.com/aykutalparslan/Telegram-Server, moved to
  https://github.com/aykutalparslan/Ferrite
- https://github.com/loyldg/mytelegram
- https://github.com/nebula-chat/telegramd (now gone, probably moved to
  teamgram: https://github.com/nebula-chat/chatengine)

Various applications similar to Telegram (probably using a custom MTProto
backend):

- https://nebula.chat/
- https://potato.im/
- https://icq.com/ (not sure about this one, but the clients are a copycat of
  Telegram's)
