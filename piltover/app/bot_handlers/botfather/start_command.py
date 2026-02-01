from piltover.app.utils.formatable_text_with_entities import FormatableTextWithEntities
from piltover.db.models import Peer, MessageRef

__text, __entities = FormatableTextWithEntities("""
I can help you create and manage Telegram bots. If you're new to the Bot API, please see the manual (<a>https://core.telegram.org/bots</a>).

You can control me by sending these commands:

<c>/newbot</c> - create a new bot
<c>/mybots</c> - edit your bots

Edit Bots
<c>/setname</c> - change a bot's name
<c>/setdescription</c> - change bot description
<c>/setabouttext</c> - change bot about info
<c>/setuserpic</c> - change bot profile photo
<c>/setcommands</c> - change the list of commands
<c>/deletebot</c> - delete a bot

Bot Settings
<c>/token</c> - get authorization token
<c>/revoke</c> - revoke bot access token
<c>/setinline</c> - toggle inline mode (<a>https://core.telegram.org/bots/inline</a>)
<c>/setinlinegeo</c> - toggle inline location requests (<a>https://core.telegram.org/bots/inline#location-based-results</a>)
<c>/setinlinefeedback</c> - change inline feedback (<a>https://core.telegram.org/bots/inline#collecting-feedback</a>) settings
<c>/setjoingroups</c> - can your bot be added to groups?
<c>/setprivacy</c> - toggle privacy mode (<a>https://core.telegram.org/bots/features#privacy-mode</a>) in groups

Web Apps
<c>/myapps</c> - edit your web apps (<a>https://core.telegram.org/bots/webapps</a>)
<c>/newapp</c> - create a new web app (<a>https://core.telegram.org/bots/webapps</a>)
<c>/listapps</c> - get a list of your web apps
<c>/editapp</c> - edit a web app
<c>/deleteapp</c> - delete an existing web app

Games
<c>/mygames</c> - edit your games (<a>https://core.telegram.org/bots/games</a>)
<c>/newgame</c> - create a new game (<a>https://core.telegram.org/bots/games</a>)
<c>/listgames</c> - get a list of your games
<c>/editgame</c> - edit a game
<c>/deletegame</c> - delete an existing game
""".strip()).format()


async def botfather_start_command(peer: Peer, _: MessageRef) -> MessageRef | None:
    messages = await MessageRef.create_for_peer(peer, peer.user, opposite=False, message=__text, entities=__entities)
    return messages[peer]
