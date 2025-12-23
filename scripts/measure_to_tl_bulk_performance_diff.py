import os
from asyncio import new_event_loop
from itertools import islice
from typing import Iterable, TypeVar, Generator, cast

from loguru import logger
from tortoise import Tortoise
from tortoise.contrib.sqlite.functions import Random

os.environ["DEBUG_MEASURETIME_LOG"] = "INFO"
os.environ["DEBUG_MEASURETIME_END_LOG"] = "SUCCESS"

from piltover.db.enums import PeerType
from piltover.db.models import User, Channel, Peer, ChatParticipant, Username
from piltover.utils.debug import measure_time, measure_time_with_result

T = TypeVar("T")

NUM_CHANNELS = 1000


def batched(iterable: Iterable[T], n: int) -> Generator[tuple[T, ...], None, None]:
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


async def main() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["piltover.db.models"]},
        _create_db=True,
    )
    await Tortoise.generate_schemas()

    with measure_time("create users"):
        creator = await User.create(phone_number=None, first_name="channels creator")
        user = await User.create(phone_number=None, first_name="test idk")

    with measure_time("create channels"):
        await Channel.bulk_create([
            Channel(creator=creator, channel=True, name=f"test channel #{num}")
            for num in range(NUM_CHANNELS)
        ])

    random_channel_query = Channel.all().annotate(order=Random()).order_by("order").limit(NUM_CHANNELS // 2)

    with measure_time("create peers and participants"):
        await Peer.bulk_create([
            Peer(owner=user, channel=channel, type=PeerType.CHANNEL)
            for channel in await random_channel_query
        ])

        await ChatParticipant.bulk_create([
            ChatParticipant(user=user, channel=peer.channel)
            for peer in await Peer.filter(type=PeerType.CHANNEL, owner=user).select_related("channel")
        ])

    with measure_time("create usernames"):
        await Username.bulk_create([
            Username(channel=channel, username=f"channel_{channel.id}")
            for channel in await random_channel_query
        ])

    logger.info("-" * 32)

    channels = await Channel.all()
    with measure_time_with_result("[to_tl] one channel at a time") as fut:
        for channel in channels:
            await channel.to_tl(user)

    to_tl_one_at_a_time = await fut

    channels = await Channel.all()
    with measure_time_with_result("[to_tl_bulk] all channels at once") as fut:
        await Channel.to_tl_bulk(channels, user)

    to_tl_bulk_all_at_once = await fut

    channels = await Channel.all()
    with measure_time_with_result("[to_tl_bulk] one channel at a time") as fut:
        for channel in channels:
            await Channel.to_tl_bulk([channel], user)

    to_tl_bulk_one_at_a_time = await fut

    channels = await Channel.all()
    with measure_time_with_result("[to_tl_bulk] two channels at a time") as fut:
        for batch in batched(channels, 2):
            await Channel.to_tl_bulk(cast(list[Channel], batch), user)

    to_tl_bulk_two_at_a_time = await fut

    logger.info("-" * 32)

    all_ratio = to_tl_one_at_a_time / to_tl_bulk_all_at_once
    one_ratio = to_tl_one_at_a_time / to_tl_bulk_one_at_a_time
    two_ratio = to_tl_one_at_a_time / to_tl_bulk_two_at_a_time

    logger.info(
        f"For processing {NUM_CHANNELS} channels: "
        f"to_tl_bulk is {all_ratio:.1f}x {'slower' if all_ratio < 1 else 'faster'} than to_tl"
    )
    logger.info(
        f"For processing 1 channel at a time: "
        f"to_tl_bulk is {one_ratio:.1f}x {'slower' if one_ratio < 1 else 'faster'} than to_tl"
    )
    logger.info(
        f"For processing 2 channels at a time: "
        f"to_tl_bulk is {two_ratio:.1f}x {'slower' if two_ratio < 1 else 'faster'} than to_tl"
    )

    await Tortoise.close_connections()


if __name__ == "__main__":
    new_event_loop().run_until_complete(main())
