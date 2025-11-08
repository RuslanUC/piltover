from piltover.worker import MessageHandler
from . import stubs, sending, history, dialogs, other, chats, reactions, invites, saved_dialogs, polls, folders, \
    secret, wallpaper, scheduled, bot_callbacks

handler = MessageHandler("messages")
handler.register_handler(stubs.handler)
handler.register_handler(other.handler)
handler.register_handler(sending.handler)
handler.register_handler(history.handler)
handler.register_handler(dialogs.handler)
handler.register_handler(chats.handler)
handler.register_handler(reactions.handler)
handler.register_handler(invites.handler)
handler.register_handler(saved_dialogs.handler)
handler.register_handler(polls.handler)
handler.register_handler(folders.handler)
handler.register_handler(secret.handler)
handler.register_handler(wallpaper.handler)
handler.register_handler(scheduled.handler)
handler.register_handler(bot_callbacks.handler)
