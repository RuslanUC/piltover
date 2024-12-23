from base64 import urlsafe_b64encode, urlsafe_b64decode
from os import urandom

from piltover.app.utils.updates_manager import UpdatesManager
from piltover.db.enums import PeerType
from piltover.db.models import Peer, Dialog, Message, ApiApplication
from piltover.db.models.user import User
from piltover.enums import ReqHandlerFlags
from piltover.exceptions import ErrorRpc, InvalidConstructorException
from piltover.high_level import MessageHandler
from piltover.server import Client
from piltover.tl import Long
from piltover.tl.functions.internal import SendCode, SignIn, GetUserApp, EditUserApp, GetAvailableServers
from piltover.tl.types.internal import SentCode, Authorization, AppNotFound, AppInfo, AvailableServers, AvailableServer, \
    PublicKey
from piltover.utils.snowflake import Snowflake
from piltover.utils.utils import sec_check

handler = MessageHandler("internal")

LOGIN_MESSAGE_FMT = (
    "Web login code. Dear Ruslan, we received a request from your account to log in on my.<todo: domain>. "
    "This is your login code:\n"
    "{code}\n\n"
    "Do not give this code to anyone, even if they say they're from Piltover! "
    "This code can be used to delete your Piltover account. We never ask to send it anywhere.\n"
    "If you didn't request this code by trying to log in on my.<todo: domain>, simply ignore this message.\n"
)


@handler.on_request(SendCode, ReqHandlerFlags.AUTH_REQUIRED)
async def send_code(request: SendCode, user: User) -> SentCode:
    if user.id != 777000:
        raise InvalidConstructorException(SentCode.tlid())

    try:
        if int(request.phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=406, error_message="PHONE_NUMBER_INVALID")

    # TODO: add table for passwords (user, password, random_hash)
    rand = urandom(8)
    password = urlsafe_b64encode(rand).decode("utf8")
    print(f"Password: {password}")

    resp = SentCode(
        random_hash=rand + request.phone_number.encode("utf8")
    )

    target_user = await User.get_or_none(phone_number=request.phone_number)
    if target_user is None:
        return resp

    peer_system, _ = await Peer.get_or_create(owner=target_user, user=user, type=PeerType.USER)
    await Dialog.get_or_create(peer=peer_system)
    message = await Message.create(
        internal_id=Snowflake.make_id(),
        message=LOGIN_MESSAGE_FMT.format(code=password),
        author=user,
        peer=peer_system,
    )

    await UpdatesManager.send_message(target_user, {peer_system: message})
    return resp


@handler.on_request(SignIn, ReqHandlerFlags.AUTH_REQUIRED)
async def sign_in(request: SignIn, user: User) -> Authorization:
    if user.id != 777000:
        raise InvalidConstructorException(SignIn.tlid())

    try:
        if int(request.phone_number) < 100000:
            raise ValueError
    except ValueError:
        raise ErrorRpc(error_code=10400, error_message="PHONE_NUMBER_INVALID")

    try:
        sec_check(len(request.random_hash) == (8 + len(request.phone_number)))
        sec_check(request.random_hash.endswith(request.phone_number.encode("utf8")))
        sec_check(request.random_hash.startswith(urlsafe_b64decode(request.password)))
    except Exception:
        raise ErrorRpc(error_code=10400, error_message="PASSWORD_INVALID")

    target_user = await User.get_or_none(phone_number=request.phone_number)
    if target_user is None:
        raise ErrorRpc(error_code=10400, error_message="PASSWORD_INVALID")

    # TODO: store authorizations in table
    return Authorization(auth=Long.write(user.id))


@handler.on_request(GetUserApp, ReqHandlerFlags.AUTH_REQUIRED)
async def get_user_app(request: GetUserApp, user: User) -> AppInfo | AppNotFound:
    if user.id != 777000:
        raise InvalidConstructorException(GetUserApp.tlid())

    target_user = await User.get_or_none(id=Long.read_bytes(request.auth))
    if target_user is None:
        raise ErrorRpc(error_code=10401, error_message="USER_AUTH_INVALID")

    if (app := await ApiApplication.get_or_none(owner=target_user)) is None:
        return AppNotFound()

    return AppInfo(
        api_id=app.id,
        api_hash=app.hash,
        title=app.name,
        short_name=app.short_name,
    )


@handler.on_request(EditUserApp, ReqHandlerFlags.AUTH_REQUIRED)
async def edit_user_app(request: EditUserApp, user: User) -> bool:
    if user.id != 777000:
        raise InvalidConstructorException(EditUserApp.tlid())

    target_user = await User.get_or_none(id=Long.read_bytes(request.auth))
    if target_user is None:
        raise ErrorRpc(error_code=10401, error_message="USER_AUTH_INVALID")

    app, created = await ApiApplication.get_or_create(owner=target_user, defaults={
        "name": request.title,
        "short_name": request.short_name,
    })
    if not created:
        app.name = request.title
        app.short_name = request.short_name
        await app.save(update_fields=["name", "short_name"])

    return True


@handler.on_request(GetAvailableServers, ReqHandlerFlags.AUTH_REQUIRED)
async def get_available_servers(client: Client, user: User) -> AvailableServers:
    if user.id != 777000:
        raise InvalidConstructorException(GetAvailableServers.tlid())

    return AvailableServers(
        servers=[
            AvailableServer(
                address=client.server.host,
                port=client.server.port,
                dc_id=2,
                name="Production",
                public_keys=[
                    PublicKey(
                        key="TODO",
                        fingerprint=0x12345678
                    )
                ],
            )
        ]
    )
