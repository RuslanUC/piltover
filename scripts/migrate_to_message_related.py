# Script i used to migrate messages from old pre-models.MessageRelated related users/chats/channels to the new one.
# Script needs DB_CONNECTION_STRING to be set

import asyncio
import os

import tortoise
from loguru import logger

from piltover.db.models import Message, MessageRelated


async def main() -> None:
    database_url = os.environ["DB_CONNECTION_STRING"]

    await tortoise.Tortoise.init(db_url=database_url, modules={"models": ["piltover.db.models"]})

    offset = 0
    batch_size = 1024

    logger.info(f"Total messages: {await Message.all().count()}")
    
    while True:
        messages = await Message.all().order_by("id").limit(batch_size).offset(offset * batch_size).select_related(
            "peer", "author", "fwd_header", "fwd_header__saved_peer",
        )
        if not messages:
            break

        for message in messages:
            if await MessageRelated.filter(message=message).exists():
                logger.info(f"Skipping message {message.id} because it already has associated MessageRelated entries")
                continue

            related_user_ids = set()
            related_chat_ids = set()
            related_channel_ids = set()
            message._fill_related(related_user_ids, related_chat_ids, related_channel_ids)
            await Message._create_related_from_ids((message,), related_user_ids, related_chat_ids, related_channel_ids)

            logger.info(
                f"Got {len(related_user_ids)} users, "
                f"{len(related_chat_ids)} chats, "
                f"{len(related_channel_ids)} channels "
                f"that are related to message {message.id}"
            )
            
        offset += 1


if __name__ == "__main__":
    asyncio.new_event_loop().run_until_complete(main())


