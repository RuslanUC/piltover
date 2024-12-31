from piltover.high_level import MessageHandler
from . import stubs, sending, history, dialogs, other, chats

handler = MessageHandler("messages")
handler.register_handler(stubs.handler)
handler.register_handler(other.handler)
handler.register_handler(sending.handler)
handler.register_handler(history.handler)
handler.register_handler(dialogs.handler)
handler.register_handler(chats.handler)
