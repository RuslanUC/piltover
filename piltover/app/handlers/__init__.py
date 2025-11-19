from piltover.app.handlers import auth, updates, users, stories, account, messages, photos, contacts, langpack, \
    channels, upload, internal, help as help_, stickers, stubs, phone
from piltover.worker import Worker


def register_handlers(worker_: Worker) -> None:
    worker_.register_handler(stubs.handler)
    worker_.register_handler(help_.handler)
    worker_.register_handler(auth.handler)
    worker_.register_handler(updates.handler)
    worker_.register_handler(users.handler)
    worker_.register_handler(stories.handler)
    worker_.register_handler(account.handler)
    worker_.register_handler(messages.handler)
    worker_.register_handler(photos.handler)
    worker_.register_handler(contacts.handler)
    worker_.register_handler(langpack.handler)
    worker_.register_handler(channels.handler)
    worker_.register_handler(upload.handler)
    worker_.register_handler(internal.handler)
    worker_.register_handler(stickers.handler)
    worker_.register_handler(phone.handler)
