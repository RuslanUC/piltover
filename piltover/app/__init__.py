from time import time

from piltover.tl_new import User, PeerUser, UserStatusOnline, Message

durov = User(
    is_self=True,
    contact=False,
    mutual_contact=False,
    deleted=False,
    bot=False,
    verified=True,
    restricted=False,
    min=False,
    support=False,
    scam=False,
    apply_min_photo=False,
    fake=False,
    bot_attach_menu=False,
    premium=False,
    attach_menu_enabled=False,
    id=42123,
    access_hash=0,
    first_name="Pavel",
    last_name="Durov",
    username="durov7",
    phone="+4442123",
    status=UserStatusOnline(expires=int(time() + 9000)),
    lang_code="en",
)

durov_message = Message(
    id=456,
    peer_id=PeerUser(user_id=durov.id),
    date=int(time() - 150),
    message="Приветик"
)

