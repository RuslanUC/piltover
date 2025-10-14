from contextlib import contextmanager, AsyncExitStack

import pytest
from pyrogram.raw.all import objects as pyrogram_objects

from piltover.app.app import args as app_args
from piltover.tl.functions.help import GetPeerColors
from piltover.tl.types.help import PeerColorsNotModified
from tests._peer_colors_compat import GetPeerColorsCompat, PeerColorsCompat, PeerColorOptionCompat, \
    PeerColorOption_167Compat, PeerColorSetCompat, PeerColorProfileSetCompat, GetPeerProfileColorsCompat, \
    PeerColorsNotModifiedCompat
from tests.conftest import TestClient


@contextmanager
def add_peer_colors_to_pyrogram():
    pyrogram_objects[GetPeerColorsCompat.tlid()] = GetPeerColorsCompat
    pyrogram_objects[GetPeerProfileColorsCompat.tlid()] = GetPeerProfileColorsCompat
    pyrogram_objects[PeerColorsCompat.tlid()] = PeerColorsCompat
    pyrogram_objects[PeerColorsNotModifiedCompat.tlid()] = PeerColorsNotModifiedCompat
    pyrogram_objects[PeerColorOptionCompat.tlid()] = PeerColorOptionCompat
    pyrogram_objects[PeerColorOption_167Compat.tlid()] = PeerColorOption_167Compat
    pyrogram_objects[PeerColorSetCompat.tlid()] = PeerColorSetCompat
    pyrogram_objects[PeerColorProfileSetCompat.tlid()] = PeerColorProfileSetCompat
    yield


@pytest.mark.asyncio
async def test_get_available_peer_colors_empty(exit_stack: AsyncExitStack) -> None:
    with add_peer_colors_to_pyrogram():
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
    with add_peer_colors_to_pyrogram():
        client = await exit_stack.enter_async_context(TestClient(phone_number="123456789"))
        colors = await client.invoke_p(GetPeerColors(hash=0), with_layer=167)
        assert len(colors.colors) > 7
