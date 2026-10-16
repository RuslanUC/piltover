import pytest
from pyrogram.errors import BadRequest, PeerIdInvalid, PinnedDialogsTooMuch
from pyrogram.raw.functions.messages import GetPinnedDialogs, ToggleDialogPin, ReorderPinnedDialogs
from pyrogram.raw.types import PeerChat, InputDialogPeer, InputDialogPeerFolder
from pyrogram.raw.types.messages import PeerDialogs

from tests.conftest import ClientFactory


@pytest.mark.asyncio
async def test_dialogs_get_pinned_empty(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    chats = [await client.create_group(f"chat {i}", []) for i in range(2)]
    await client.send_message("self", "test")

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    assert len(dialogs.dialogs) == 0


@pytest.mark.asyncio
async def test_dialogs_pin(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    chats = [await client.create_group(f"chat {i}", []) for i in range(5)]

    peer1 = await client.resolve_peer(chats[1].id)
    peer2 = await client.resolve_peer(chats[2].id)

    await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer1), pinned=True))
    await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer2), pinned=True))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    assert len(dialogs.dialogs) == 2
    dialog1 = dialogs.dialogs[0].peer
    assert isinstance(dialog1, PeerChat)
    assert dialog1 == peer2
    dialog2 = dialogs.dialogs[1].peer
    assert isinstance(dialog2, PeerChat)
    assert dialog2 == peer1


@pytest.mark.asyncio
async def test_dialogs_pin_history_empty(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    with pytest.raises(BadRequest, match="PEER_HISTORY_EMPTY"):
        await client.invoke(ToggleDialogPin(
            peer=InputDialogPeer(peer=await client.resolve_peer("self")),
            pinned=True,
        ))


@pytest.mark.asyncio
async def test_dialogs_pin_invalid_peer(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)

    with pytest.raises(PeerIdInvalid):
        await client.invoke(ToggleDialogPin(
            peer=await client.resolve_peer("self"),
            pinned=True,
        ))

    with pytest.raises(PeerIdInvalid):
        await client.invoke(ToggleDialogPin(
            peer=InputDialogPeerFolder(folder_id=0)
        ))


@pytest.mark.asyncio
async def test_dialogs_pin_too_much(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    chats = [await client.create_group(f"chat {i}", []) for i in range(11)]

    last = chats.pop()

    for chat in chats:
        peer = await client.resolve_peer(chat.id)
        await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer), pinned=True))

    peer = await client.resolve_peer(last.id)
    with pytest.raises(PinnedDialogsTooMuch):
        await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer), pinned=True))


@pytest.mark.asyncio
async def test_dialogs_pin_already_pinned(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    chats = [await client.create_group(f"chat {i}", []) for i in range(10)]

    for chat in chats:
        peer = await client.resolve_peer(chat.id)
        await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer), pinned=True))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    pinned_peers1 = [dialog.peer for dialog in dialogs.dialogs]

    for chat in reversed(chats):
        peer = await client.resolve_peer(chat.id)
        await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer), pinned=True))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    pinned_peers2 = [dialog.peer for dialog in dialogs.dialogs]

    assert pinned_peers1 == pinned_peers2


@pytest.mark.asyncio
async def test_dialogs_pin_unpin(client_with_auth: ClientFactory) -> None:
    client = await client_with_auth(run=True)
    chats = [await client.create_group(f"chat {i}", []) for i in range(5)]

    peer1 = await client.resolve_peer(chats[1].id)
    peer2 = await client.resolve_peer(chats[2].id)
    peer3 = await client.resolve_peer(chats[3].id)

    await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer1), pinned=True))
    await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer2), pinned=True))
    await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer3), pinned=True))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    pinned_peers = [dialog.peer for dialog in dialogs.dialogs]
    assert pinned_peers == [peer3, peer2, peer1]

    await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer2), pinned=False))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    pinned_peers = [dialog.peer for dialog in dialogs.dialogs]
    assert pinned_peers == [peer3, peer1]


@pytest.mark.parametrize(
    ("peers_num", "pinned_peers_num", "order", "force", "expected"),
    [
        (4, 3, (0, 1, 2), False, (0, 1, 2)),
        (4, 3, (1,), False, (1, 0, 2)),
        (4, 3, (1, 0), True, (1, 0)),
    ],
    ids=(
        "reorder all",
        "reorder one",
        "reorder some - force",
    )
)
@pytest.mark.asyncio
async def test_dialogs_pin_reorder(
        client_with_auth: ClientFactory, peers_num: int, pinned_peers_num: int, order: tuple[int, ...], force: bool,
        expected: tuple[int, ...],
) -> None:
    client = await client_with_auth(run=True)
    chats = [await client.create_group(f"chat {i}", []) for i in range(peers_num)]

    peers = [
        await client.resolve_peer(chat.id)
        for idx, chat in enumerate(chats)
        if idx < pinned_peers_num
    ]

    for peer in peers:
        await client.invoke(ToggleDialogPin(peer=InputDialogPeer(peer=peer), pinned=True))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    pinned_peers = [dialog.peer for dialog in dialogs.dialogs]
    assert pinned_peers == peers[::-1]

    await client.invoke(ReorderPinnedDialogs(
        folder_id=0,
        order=[
            InputDialogPeer(peer=peers[idx])
            for idx in order
        ],
        force=force,
    ))

    dialogs = await client.invoke(GetPinnedDialogs(folder_id=0))
    assert isinstance(dialogs, PeerDialogs)
    pinned_peers = [dialog.peer for dialog in dialogs.dialogs]
    assert pinned_peers == [peers[idx] for idx in expected]
