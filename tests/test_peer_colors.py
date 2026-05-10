from contextlib import contextmanager, AsyncExitStack

import pytest

from piltover.app.app import args as app_args
from piltover.tl.functions.help import GetPeerColors
from piltover.tl.types.help import PeerColorsNotModified
from tests._peer_colors_compat import GetPeerColorsCompat, PeerColorsCompat, PeerColorOptionCompat, \
    PeerColorOption_167Compat, PeerColorSetCompat, PeerColorProfileSetCompat, GetPeerProfileColorsCompat, \
    PeerColorsNotModifiedCompat
from tests.client import TestClient


@contextmanager
def add_compat_to_pyrogram():
    from pyrogram.raw.all import objects as pyrogram_objects

    to_add = (
        GetPeerColorsCompat,
        GetPeerProfileColorsCompat,
        PeerColorsCompat,
        PeerColorsNotModifiedCompat,
        PeerColorOptionCompat,
        PeerColorOption_167Compat,
        PeerColorSetCompat,
        PeerColorProfileSetCompat,
    )

    bak = {}
    for cls in to_add:
        tlid = cls.tlid()
        if tlid in pyrogram_objects:
            bak[tlid] = pyrogram_objects[tlid]
        pyrogram_objects[tlid] = cls

    yield

    pyrogram_objects.update(bak)


@pytest.mark.asyncio
async def test_get_available_peer_colors_empty(exit_stack: AsyncExitStack) -> None:
    with add_compat_to_pyrogram():
        client: TestClient = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
        colors = await client.invoke_p(GetPeerColors(hash=1), with_layer=167)
        assert len(colors.colors) == 7

        colors = await client.invoke_p(GetPeerColors(hash=colors.hash), with_layer=167)
        assert isinstance(colors, PeerColorsNotModified)


accent_files_dir = app_args.peer_colors_dir / "accent"
profile_files_dir = app_args.peer_colors_dir / "profile"


@pytest.mark.skipif(
    not app_args.peer_colors_dir.exists() or not accent_files_dir.exists() or not profile_files_dir.exists(),
    reason="No peer color files available"
)
@pytest.mark.create_peer_colors
@pytest.mark.asyncio
async def test_get_available_peer_accent_colors(exit_stack: AsyncExitStack) -> None:
    with add_compat_to_pyrogram():
        client = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
        colors = await client.invoke_p(GetPeerColors(hash=0), with_layer=167)
        assert len(colors.colors) > 7
