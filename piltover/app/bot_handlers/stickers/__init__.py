from piltover.app.bot_handlers.interaction_handler import BotInteractionHandler
from piltover.app.bot_handlers.stickers.addemoji_command import AddEmoji
from piltover.app.bot_handlers.stickers.addsticker_command import AddSticker
from piltover.app.bot_handlers.stickers.cancel_command import Cancel
from piltover.app.bot_handlers.stickers.done_command import Done
from piltover.app.bot_handlers.stickers.editsticker_command import EditSticker
from piltover.app.bot_handlers.stickers.newemojipack_command import NewEmojiPack
from piltover.app.bot_handlers.stickers.newpack_command import NewPack
from piltover.app.bot_handlers.stickers.newvideo_command import NewVideo
from piltover.app.bot_handlers.stickers.publish_command import Publish
from piltover.app.bot_handlers.stickers.renamepack_command import RenamePack
from piltover.app.bot_handlers.stickers.replacesticker_command import ReplaceSticker
from piltover.app.bot_handlers.stickers.skip_command import Skip
from piltover.app.bot_handlers.stickers.start_command import Start
from piltover.db.enums import StickersBotState
from piltover.db.models import StickersBotUserState


class StickersBotInteractionHandler(BotInteractionHandler[StickersBotState, StickersBotUserState]):
    def __init__(self) -> None:
        super().__init__(StickersBotUserState)

        self.include(Skip())
        self.include(AddEmoji())
        self.include(AddSticker())
        self.include(Cancel())
        self.include(Done())
        self.include(EditSticker())
        self.include(NewEmojiPack())
        self.include(NewPack())
        self.include(NewVideo())
        self.include(Publish())
        self.include(RenamePack())
        self.include(ReplaceSticker())
        self.include(Start())
