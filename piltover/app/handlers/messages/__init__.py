from piltover.worker import MessageHandler
from . import stubs, sending, history, dialogs, other, chats, reactions, invites, saved_dialogs

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
