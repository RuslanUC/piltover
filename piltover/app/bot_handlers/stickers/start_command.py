from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.models import Peer, Message

__text = FormatableTextWithEntities("""
Hello, I'm the Sticker Bot! I can create sticker sets and emoji packs from pictures and give you usage stats for your stickers. See this manual for details on creating stickers and emoji:
<a>https://core.telegram.org/stickers</a>

Use these commands to control me:

Emoji
<c>/newemojipack</c> — make a set of emoji (<a>https://core.telegram.org/stickers#custom-emoji</a>) - TODO

Stickers & Masks
<c>/newpack</c> – make a static PNG / WEBP sticker set (<a>https://core.telegram.org/stickers#static-stickers</a>)
<c>/newvideo</c> – make a set of WEBM video stickers (<a>https://core.telegram.org/stickers#video-stickers</a>) - TODO
<c>/newanimated</c> – make an animated TGS sticker set (<a>https://core.telegram.org/stickers#animated-stickers</a>) - TODO
<c>/newmasks</c> – make a static set of masks - TODO

<c>/addsticker</c> – add a sticker to an existing set
<c>/editsticker</c> – change emoji or coordinates
<c>/replacesticker</c> – replace stickers in a set
<c>/ordersticker</c> – reorder stickers in a set - TODO
<c>/delsticker</c> – remove a sticker from an existing set - TODO
<c>/setpackicon</c> – set a sticker set icon - TODO
<c>/renamepack</c> – rename a set
<c>/delpack</c> – delete a set

Stats
<c>/stats</c> – get stats for a sticker - TODO
<c>/top</c> – get top stickers - TODO
<c>/packstats</c> – get stats for a sticker set - TODO
<c>/packtop</c> – get top sticker sets - TODO
<c>/topbypack</c> – get top stickers in a set - TODO
<c>/packusagetop</c> – get usage stats for your set - TODO

<c>/cancel</c> – cancel the current operation
""".strip())
__text, __entities = __text.format()


async def stickers_start_command(peer: Peer, _: Message) -> Message | None:
    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__text, entities=__entities)
    return messages[peer]
