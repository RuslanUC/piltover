from os import urandom
from time import time

import piltover.app.utils.updates_manager as upd
from piltover.app_config import AppConfig
from piltover.db.enums import PeerType
from piltover.db.models import Peer, Dialog, Message, ApiApplication, User, WebAuthorization
from piltover.exceptions import ErrorRpc, InvalidConstructorException
from piltover.tl import Long
from piltover.tl.functions.internal import SendCode, SignIn, GetUserApp, EditUserApp, GetAvailableServers
from piltover.tl.types.internal import SentCode, Authorization, AppNotFound, AppInfo, AvailableServers, AvailableServer, \
    PublicKey
from piltover.utils.snowflake import Snowflake
from piltover.worker import MessageHandler
from piltover.worker import Worker

handler = MessageHandler("internal")

LOGIN_MESSAGE_FMT = (
    "Web login code. Dear {name}, we received a request from your account to log in on my.<todo: domain>. "
    "This is your login code:\n"
    "{code}\n\n"
    f"Do not give this code to anyone, even if they say they're from {AppConfig.NAME}! "
    f"This code can be used to delete your {AppConfig.NAME} account. We never ask to send it anywhere.\n"
    "If you didn't request this code by trying to log in on my.<todo: domain>, simply ignore this message.\n"
)


@handler.on_request(SendCode)
async def send_code(request: SendCode, user: User) -> SentCode:
    if user.id != 777000:
        raise InvalidConstructorException(SentCode.tlid())

    try:
        if int(request.phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")

    random_hash = urandom(16)
    resp = SentCode(random_hash=random_hash)

    target_user = await User.get_or_none(phone_number=request.phone_number)
    if target_user is None:
        return resp

    webauth = await WebAuthorization.create(phone_number=request.phone_number, hash=random_hash.hex())
    print(f"Password: {webauth.password}")

    peer_system, _ = await Peer.get_or_create(owner=target_user, user=user, type=PeerType.USER)
    await Dialog.get_or_create(peer=peer_system)
    message = await Message.create(
        internal_id=Snowflake.make_id(),
        message=LOGIN_MESSAGE_FMT.format(code=webauth.password, name=target_user.first_name),
        author=user,
        peer=peer_system,
    )

    await upd.send_message(target_user, {peer_system: message})
    return resp


@handler.on_request(SignIn)
async def sign_in(request: SignIn, user: User) -> Authorization:
    if user.id != 777000:
        raise InvalidConstructorException(SignIn.tlid())

    try:
        if int(request.phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=10400, error_message="PHONE_NUMBER_INVALID")

    webauth = await WebAuthorization.get_or_none(
        phone_number=request.phone_number, random_hash=request.random_hash.hex(), expires_at__gt=int(time()),
        user=None, password=request.password
    )
    if webauth is None:
        raise ErrorRpc(error_code=10400, error_message="PASSWORD_INVALID")

    target_user = await User.get_or_none(phone_number=request.phone_number)
    if target_user is None:
        raise ErrorRpc(error_code=10400, error_message="PASSWORD_INVALID")

    webauth.user = target_user
    webauth.expires_at = int(time() + 60 * 60)
    auth_bytes = urandom(16)
    webauth.random_hash = auth_bytes.hex()
    await webauth.save(update_fields=["user_id", "expires_at", "random_hash"])

    return Authorization(auth=Long.write(webauth.id) + auth_bytes)


async def _auth_user(auth_bytes: bytes) -> User:
    if len(auth_bytes) < 16:
        raise ErrorRpc(error_code=10401, error_message="USER_AUTH_INVALID")

    webauth_id = Long.read_bytes(auth_bytes[:8])
    webauth = await WebAuthorization.get_or_none(
        id=webauth_id, random_hash=auth_bytes[8:].hex(), expires_at__gt=int(time()),
    ).select_related("user")
    if webauth is None or webauth.user is None:
        raise ErrorRpc(error_code=10401, error_message="USER_AUTH_INVALID")

    return webauth.user


@handler.on_request(GetUserApp)
async def get_user_app(request: GetUserApp, user: User) -> AppInfo | AppNotFound:
    if user.id != 777000:
        raise InvalidConstructorException(GetUserApp.tlid())

    target_user = await _auth_user(request.auth)
    if (app := await ApiApplication.get_or_none(owner=target_user)) is None:
        return AppNotFound()

    return AppInfo(
        api_id=app.id,
        api_hash=app.hash,
        title=app.name,
        short_name=app.short_name,
    )


@handler.on_request(EditUserApp)
async def edit_user_app(request: EditUserApp, user: User) -> bool:
    if user.id != 777000:
        raise InvalidConstructorException(EditUserApp.tlid())

    target_user = await _auth_user(request.auth)

    app, created = await ApiApplication.get_or_create(owner=target_user, defaults={
        "name": request.title,
        "short_name": request.short_name,
    })
    if not created:
        app.name = request.title
        app.short_name = request.short_name
        await app.save(update_fields=["name", "short_name"])

    return True


@handler.on_request(GetAvailableServers)
async def get_available_servers(worker: Worker, user: User) -> AvailableServers:
    if user.id != 777000:
        raise InvalidConstructorException(GetAvailableServers.tlid())

    return AvailableServers(
        servers=[
            AvailableServer(
                address=dc_option["addresses"][0]["ip"],
                port=dc_option["addresses"][0]["port"],
                dc_id=dc_option["dc_id"],
                name="Production" if dc_option["dc_id"] == AppConfig.THIS_DC_ID else "Test",
                public_keys=[
                    PublicKey(
                        key=worker.server_keys.public_key,
                        fingerprint=worker.fingerprint,
                    )
                ],
            )
            for dc_option in AppConfig.DCS
        ]
    )
