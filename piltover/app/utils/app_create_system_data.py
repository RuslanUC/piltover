from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from fastrand import xorshift128plus_bytes
from loguru import logger
from tortoise.expressions import Q

from piltover.app_config import AppConfig
from piltover.tl import Long, BaseThemeClassic, BaseThemeDay, BaseThemeNight, BaseThemeArctic, BaseThemeTinted

if TYPE_CHECKING:
    from piltover.db.models import File
    from piltover.app.app import ArgsNamespace


async def _upload_doc(args: ArgsNamespace, base_dir: Path, idx: int, doc: dict) -> File:
    from datetime import datetime
    from pytz import UTC

    from piltover.tl.types import DocumentAttributeImageSize, DocumentAttributeSticker, DocumentAttributeFilename
    from piltover.db.models import File
    from piltover.db.enums import FileType
    from piltover.app.utils.utils import PHOTOSIZE_TO_INT

    cls_name_to_cls = {
        "types.DocumentAttributeImageSize": DocumentAttributeImageSize,
        "types.DocumentAttributeSticker": DocumentAttributeSticker,
        "types.DocumentAttributeFilename": DocumentAttributeFilename,
    }

    ext = doc["mime_type"].split("/")[-1]
    base_files_dir = base_dir / "files"

    photo_path = None
    for thumb in doc["thumbs"]:
        if thumb["_"] != "types.PhotoPathSize" or thumb["_"] != "j":
            continue
        with open(base_files_dir / f"{doc['id']}-{idx}-thumb-j.bin", "rb") as f:
            photo_path = f.read()
        break

    # TODO: dont create new file if it already exists
    file = File(
        created_at=datetime.fromtimestamp(doc["date"], UTC),
        mime_type=doc["mime_type"],
        size=doc["size"],
        type=FileType.DOCUMENT_STICKER,
        photo_path=photo_path,
        photo_sizes=[],
        constant_access_hash=Long.read_bytes(xorshift128plus_bytes(8)),
        constant_file_ref=UUID(bytes=xorshift128plus_bytes(16)),
    )
    await file.parse_attributes_from_tl([
        cls_name_to_cls[attr.pop("_")](**attr)
        for attr in doc["attributes"]
    ])
    await file.save()

    photos_dir = args.data_dir / "photos"
    docs_dir = args.data_dir / "documents"

    with open(base_files_dir / f"{doc['id']}-{idx}.{ext}", "rb") as f_in:
        with open(docs_dir / f"{file.physical_id}", "wb") as f_out:
            f_out.write(f_in.read())

    for thumb in doc["thumbs"]:
        if thumb["_"] != "types.PhotoSize":
            continue
        width = PHOTOSIZE_TO_INT[thumb["type"]]
        with open(base_files_dir / f"{doc['id']}-{idx}-thumb-{thumb['type']}.{ext}", "rb") as f_in:
            with open(photos_dir / f"{file.physical_id}-{width}", "wb") as f_out:
                f_out.write(f_in.read())

        file.photo_sizes.append({
            "type_": thumb["type"],
            "w": thumb["w"],
            "h": thumb["h"],
            "size": thumb["size"],
        })

    await file.save(update_fields=["photo_sizes"])

    return file


async def _create_reactions(args: ArgsNamespace) -> None:
    reactions_dir = args.reactions_dir
    reactions_files_dir = reactions_dir / "files"
    if not reactions_dir.exists() or not reactions_files_dir.exists():
        return

    from os import listdir
    import json

    from piltover.db.models import Reaction

    logger.info("Creating (or updating) reactions...")
    for reaction_file in listdir(reactions_dir):
        if not reaction_file.endswith(".json") or not reaction_file.split(".")[0].isdigit():
            continue

        try:
            reaction_index = int(reaction_file.split(".")[0])
        except ValueError:
            continue

        with open(reactions_dir / reaction_file) as f:
            reaction_info = json.load(f)

        defaults = {"title": reaction_info["title"], "reaction": reaction_info["reaction"]}

        for doc_name in (
                "static_icon", "appear_animation", "select_animation", "activate_animation", "effect_animation",
                "around_animation", "center_icon",
        ):
            if doc_name not in reaction_info:
                continue
            defaults[doc_name] = await _upload_doc(args, reactions_dir, reaction_index, reaction_info[doc_name])

        reaction, created = await Reaction.get_or_create(
            reaction_id=Reaction.reaction_to_uuid(reaction_info["reaction"]), defaults=defaults,
        )
        if created:
            logger.info(
                f"Created reaction \"{reaction.title}\" (\"{reaction.reaction}\" / \"{reaction_info['reaction']}\")")
        else:
            logger.info(
                f"Updating reaction \"{reaction.title}\" (\"{reaction.reaction}\" / \"{reaction_info['reaction']}\")")
            await reaction.update_from_dict(defaults).save()


async def _create_chat_themes(args: ArgsNamespace) -> None:
    chat_themes_dir = args.chat_themes_dir
    chat_themes_files_dir = chat_themes_dir / "files"
    if not chat_themes_dir.exists() or not chat_themes_files_dir.exists():
        return

    from os import listdir
    import json

    from piltover.db.models import Theme, ThemeSettings, Wallpaper, WallpaperSettings, BaseTheme

    logger.info("Creating (or updating) chat themes...")
    for chat_theme_file in listdir(chat_themes_dir):
        if not chat_theme_file.endswith(".json") or not chat_theme_file.split(".")[0].isdigit():
            continue

        try:
            theme_index = int(chat_theme_file.split(".")[0])
        except ValueError:
            continue

        with open(chat_themes_dir / chat_theme_file) as f:
            theme_info = json.load(f)

        defaults = {
            "creator": None,
            "title": theme_info["title"],
            "for_chat": theme_info["for_chat"],
            "emoticon": theme_info["emoticon"],
            "document": None,  # TODO: can chat themes have documents?
        }

        theme, created = await Theme.get_or_create(slug=theme_info["slug"], defaults=defaults)

        base_theme_name_to_tl = {
            "types.BaseThemeClassic": BaseThemeClassic(),
            "types.BaseThemeDay": BaseThemeDay(),
            "types.BaseThemeNight": BaseThemeNight(),
            "types.BaseThemeTinted": BaseThemeTinted(),
            "types.BaseThemeArctic": BaseThemeArctic(),
        }

        await ThemeSettings.filter(theme=theme).delete()
        for settings_json in theme_info["settings"]:
            message_colors = settings_json["message_colors"] or []

            wallpaper = None
            if settings_json.get("wallpaper"):
                wp = settings_json["wallpaper"]

                wallpaper_settings = await WallpaperSettings.create(
                    blur=wp["settings"]["blur"],
                    motion=wp["settings"]["motion"],
                    background_color=wp["settings"]["background_color"],
                    second_background_color=wp["settings"]["second_background_color"],
                    third_background_color=wp["settings"]["third_background_color"],
                    fourth_background_color=wp["settings"]["fourth_background_color"],
                    intensity=wp["settings"]["intensity"],
                    rotation=wp["settings"]["rotation"],
                    emoticon=wp["settings"].get("emoticon"),
                )

                wp_defaults = {
                    "creator": None,
                    "pattern": wp["pattern"],
                    "dark": wp["dark"],
                    "document": None,
                    "settings": wallpaper_settings,
                }

                if wp["document"]:
                    wp_defaults["document"] = await _upload_doc(args, chat_themes_dir, theme_index, wp["document"])

                wallpaper, wp_created = await Wallpaper.get_or_create(slug=wp["slug"], defaults=wp_defaults)
                if not wp_created:
                    wallpaper.settings = wallpaper_settings
                    await wallpaper.update_from_dict(wp_defaults).save()

            await ThemeSettings.create(
                theme=theme,
                base_theme=BaseTheme.from_tl(base_theme_name_to_tl[settings_json["base_theme"]["_"]]),
                accent_color=settings_json["accent_color"],
                outbox_accent_color=settings_json.get("outbox_accent_color"),
                message_colors_animated=settings_json["message_colors_animated"],
                message_color_1=message_colors[0] if len(message_colors) > 0 else None,
                message_color_2=message_colors[1] if len(message_colors) > 1 else None,
                message_color_3=message_colors[2] if len(message_colors) > 2 else None,
                message_color_4=message_colors[3] if len(message_colors) > 3 else None,
                wallpaper=wallpaper,
            )

        if created:
            logger.info(f"Created theme \"{theme.title}\" ")
        else:
            logger.info(f"Updating reaction \"{theme.title}\"")
            await theme.update_from_dict(defaults).save()


async def _create_or_update_peer_color(
        is_profile: bool,
        color1: int,
        color2: int | None,
        color3: int | None,
        color4: int | None,
        color5: int | None,
        color6: int | None,
        dark_color1: int | None,
        dark_color2: int | None,
        dark_color3: int | None,
        dark_color4: int | None,
        dark_color5: int | None,
        dark_color6: int | None,
        hidden: bool,
        color_id: int,
) -> None:
    from piltover.db.models import PeerColorOption

    peer_color, created = await PeerColorOption.get_or_create(
        is_profile=is_profile,
        color1=color1,
        color2=color2,
        color3=color3,
        color4=color4,
        color5=color5,
        color6=color6,
        dark_color1=dark_color1,
        dark_color2=dark_color2,
        dark_color3=dark_color3,
        dark_color4=dark_color4,
        dark_color5=dark_color5,
        dark_color6=dark_color6,
        defaults={"hidden": hidden}
    )

    if not created:
        peer_color.hidden = hidden
        await peer_color.save(update_fields=["hidden"])

    if created:
        logger.info(f"Created accent color \"{color_id}\" ")
    else:
        logger.info(f"Updated accent color \"{color_id}\" ")


async def _create_peer_colors(args: ArgsNamespace) -> None:
    accent_dir = args.peer_colors_dir / "accent"
    profile_dir = args.peer_colors_dir / "profile"
    if not args.peer_colors_dir.exists() or not accent_dir.exists() or not profile_dir.exists():
        return

    from os import listdir
    import json

    from piltover.db.models import PeerColorOption

    for color_id in range(6 + 1):
        await PeerColorOption.get_or_create(id=color_id, defaults={"is_profile": False, "color1": 0})

    logger.info("Creating (or updating) peer accent colors...")
    for accent_file in listdir(accent_dir):
        if not accent_file.endswith(".json") or not accent_file.split(".")[0].isdigit():
            continue

        with open(accent_dir / accent_file) as f:
            color_info = json.load(f)

        colors = color_info["colors"]["colors"]
        color1 = colors[0]
        color2 = colors[1] if len(colors) > 1 else None
        color3 = colors[2] if len(colors) > 2 else None
        color4 = color5 = color6 = None

        dark_colors = color_info["dark_colors"]["colors"] if color_info.get("dark_colors") else None
        dark_color1 = dark_colors[0] if dark_colors else None
        dark_color2 = dark_colors[1] if dark_colors and len(dark_colors) > 1 else None
        dark_color3 = dark_colors[2] if dark_colors and len(dark_colors) > 2 else None
        dark_color4 = dark_color5 = dark_color6 = None

        await _create_or_update_peer_color(
            is_profile=False,
            color1=color1,
            color2=color2,
            color3=color3,
            color4=color4,
            color5=color5,
            color6=color6,
            dark_color1=dark_color1,
            dark_color2=dark_color2,
            dark_color3=dark_color3,
            dark_color4=dark_color4,
            dark_color5=dark_color5,
            dark_color6=dark_color6,
            hidden=color_info.get("hidden", False),
            color_id=color_info["color_id"],
        )

    logger.info("Creating (or updating) peer profile colors...")
    for profile_file in listdir(profile_dir):
        if not profile_file.endswith(".json") or not profile_file.split(".")[0].isdigit():
            continue

        with open(profile_dir / profile_file) as f:
            color_info = json.load(f)

        colors = color_info["colors"]
        color1 = colors["palette_colors"][0]
        color2 = colors["palette_colors"][1] if len(colors["palette_colors"]) > 1 else None
        color3 = colors["bg_colors"][0]
        color4 = colors["bg_colors"][1] if len(colors["bg_colors"]) > 1 else None
        color5 = colors["story_colors"][0]
        color6 = colors["story_colors"][1]

        dark_colors = color_info["colors"] if color_info.get("dark_colors") else None
        dark_color1 = dark_colors["palette_colors"][0] if dark_colors else None
        dark_color2 = dark_colors["palette_colors"][1] if dark_colors and len(colors["palette_colors"]) > 1 else None
        dark_color3 = dark_colors["bg_colors"][0] if dark_colors else None
        dark_color4 = dark_colors["bg_colors"][1] if dark_colors and len(colors["bg_colors"]) > 1 else None
        dark_color5 = dark_colors["story_colors"][0] if dark_colors else None
        dark_color6 = dark_colors["story_colors"][1] if dark_colors else None

        await _create_or_update_peer_color(
            is_profile=True,
            color1=color1,
            color2=color2,
            color3=color3,
            color4=color4,
            color5=color5,
            color6=color6,
            dark_color1=dark_color1,
            dark_color2=dark_color2,
            dark_color3=dark_color3,
            dark_color4=dark_color4,
            dark_color5=dark_color5,
            dark_color6=dark_color6,
            hidden=color_info.get("hidden", False),
            color_id=color_info["color_id"],
        )


async def _create_system_user() -> None:
    logger.info("Creating system user...")

    from piltover.db.models import User, Username

    sys_user, _ = await User.update_or_create(id=777000, defaults={
        "phone_number": "42777",
        "first_name": AppConfig.NAME,
        "system": True,
    })

    await Username.filter(Q(user=sys_user) | Q(username=AppConfig.SYS_USER_USERNAME)).delete()
    await Username.create(user=sys_user, username=AppConfig.SYS_USER_USERNAME)


async def _create_builtin_bots(bots: list[tuple[str, str]]) -> None:
    logger.info("Creating builtin bots...")

    from piltover.db.models import User, Username

    for bot_username, bot_name in bots:
        logger.debug(f"Creating bot \"{bot_name}\" (@{bot_username})...")

        bot = await User.get_or_none(usernames__username=bot_username, system=True)
        if bot is None:
            bot = await User.create(phone_number=None, first_name=bot_name, bot=True, system=True)
        else:
            bot.phone_number = None
            bot.first_name = bot_name
            bot.bot = bot.system = True
            await bot.save(update_fields=["phone_number", "first_name", "bot", "system"])

        await Username.filter(Q(user=bot) | Q(username=bot_username)).delete()
        await Username.create(user=bot, username=bot_username)


async def create_system_data(
        args: ArgsNamespace,
        system_users: bool = True, countries_list: bool = True, reactions: bool = True, chat_themes: bool = True,
        peer_colors: bool = True,
) -> None:
    if system_users:
        await _create_system_user()
        await _create_builtin_bots([
            ("test_bot", "Test Bot"),
            ("botfather", "BotFather"),
        ])

    if countries_list and args.auth_countries_file.exists():
        logger.info("Creating auth countries...")

        import json
        from piltover.db.models import AuthCountry, AuthCountryCode

        with open(args.auth_countries_file) as f:
            countries = json.load(f)

        for country in countries:
            auth_country, _ = await AuthCountry.get_or_create(iso2=country["iso2"], defaults={
                "name": country["name"],
                "hidden": country["hidden"],
            })
            for code in country["codes"]:
                await AuthCountryCode.get_or_create(country=auth_country, code=code["code"], defaults={
                    "prefixes": code["prefixes"],
                    "patterns": code["patterns"],
                })

    if reactions:
        await _create_reactions(args)

    if chat_themes:
        await _create_chat_themes(args)

    if peer_colors:
        await _create_peer_colors(args)