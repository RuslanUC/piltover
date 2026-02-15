import warnings

import piltover.app.utils.updates_manager as upd
from piltover.db.enums import PeerType
from piltover.db.models import User, Peer, MessageRef


async def send_official_notification_message(user: User, text: str, entities: list | None) -> bool:
    system_user = await User.get_or_none(id=777000, system=True)
    if system_user is None:
        warnings.warn(
            "System notifications user (id 777000) does not exist. "
            "Some features (related to system notifications) won't be available."
        )
        return False

    peer_system, created = await Peer.get_or_create(owner=user, user=system_user, type=PeerType.USER)
    if not created:
        peer_system.owner = user
        peer_system.user = system_user

    message = await MessageRef.create_for_peer(
        peer_system, system_user, opposite=False, unhide_dialog=True,
        message=text, entities=entities,
    )

    await upd.send_message(user, message, False)

    return True