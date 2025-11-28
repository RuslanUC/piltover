from piltover.db.models import Peer, Message

__text = """
Hello, I'm the Sticker Bot! I can create sticker sets and emoji packs from pictures and give you usage stats for your stickers. See this manual for details on creating stickers and emoji:
https://core.telegram.org/stickers

Use these commands to control me:

Emoji
/newemojipack — make a set of emoji (https://core.telegram.org/stickers#custom-emoji)

Stickers & Masks
/newpack – make a static PNG / WEBP sticker set (https://core.telegram.org/stickers#static-stickers)
/newvideo – make a set of WEBM video stickers (https://core.telegram.org/stickers#video-stickers)
/newanimated – make an animated TGS sticker set (https://core.telegram.org/stickers#animated-stickers)
/newmasks – make a static set of masks

/addsticker – add a sticker to an existing set
/editsticker – change emoji or coordinates
/replacesticker – replace stickers in a set - TODO
/ordersticker – reorder stickers in a set - TODO
/delsticker – remove a sticker from an existing set - TODO
/setpackicon – set a sticker set icon - TODO
/renamepack – rename a set - TODO
/delpack – delete a set

Stats
/stats – get stats for a sticker
/top – get top stickers
/packstats – get stats for a sticker set
/packtop – get top sticker sets
/topbypack – get top stickers in a set
/packusagetop – get usage stats for your set

/cancel – cancel the current operation
""".strip()


async def stickers_start_command(peer: Peer, _: Message) -> Message | None:
    messages = await Message.create_for_peer(peer, None, None, peer.user, False, message=__text)
    return messages[peer]
