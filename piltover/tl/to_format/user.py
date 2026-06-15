from time import time

from piltover.context import NeedContextValuesContext
from piltover.tl import types
from piltover.tl.serialization_context import EMPTY_SERIALIZATION_CONTEXT, SerializationContext


class UserToFormat(types.UserToFormatInternal):
    def _write(self, ctx: SerializationContext) -> bytes:
        from piltover.db.enums import PrivacyRuleKeyType
        from piltover.db.models.presence import Presence, EMPTY as PRESENCE_EMPTY

        presence = PRESENCE_EMPTY
        has_access_to_phone = False
        has_access_to_photo = False
        has_access_to_status = False

        contact = ctx.values.contacts.get((ctx.user_id, self.id), None)
        current_is_contact = (self.id, ctx.user_id) in ctx.values.contacts
        if self.id in ctx.values.privacyrules:
            rules = ctx.values.privacyrules[self.id]
            has_access_to_phone = rules[PrivacyRuleKeyType.PHONE_NUMBER]
            has_access_to_photo = rules[PrivacyRuleKeyType.PROFILE_PHOTO]
            has_access_to_status = rules[PrivacyRuleKeyType.STATUS_TIMESTAMP]

        if self.last_seen is not None:
            presence = Presence.to_tl_from_last_seen(self.last_seen, has_access_to_status)

        is_contact = contact is not None

        phone_number = None
        if (contact is not None and contact.known_phone_number == self.phone) or has_access_to_phone:
            phone_number = self.phone

        photo = types.UserProfilePhotoEmpty()
        if has_access_to_photo and self.photo is not None:
            photo = self.photo

        emoji_status = self.emoji_status
        if isinstance(emoji_status, types.EmojiStatus) \
                and emoji_status.until is not None \
                and emoji_status.until < time():
            emoji_status = None

        return types.User(
            id=self.id,
            first_name=self.first_name if contact is None or not contact.first_name else contact.first_name,
            last_name=self.last_name if contact is None or not contact.last_name else contact.last_name,
            username=self.username,
            phone=phone_number,
            lang_code=self.lang_code,
            is_self=self.id == ctx.user_id,
            photo=photo,
            access_hash=-1,
            status=presence,
            contact=is_contact,
            bot=self.bot,
            bot_info_version=self.bot_info_version,
            color=self.color,
            profile_color=self.profile_color,
            mutual_contact=is_contact and current_is_contact,
            emoji_status=emoji_status,

            # TODO: this is True only because custom emojis are not available (like at all, missing in emoji list)
            #  for non-premium users.
            #  Need to figure out how official telegram allows custom emojis to be visible to non-premium users.
            premium=not self.bot,
        ).write(ctx)

    def write(self, ctx: SerializationContext = EMPTY_SERIALIZATION_CONTEXT) -> bytes:
        if ctx.dont_format:
            return super().write(ctx)
        return self._write(ctx)

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.users.add(self.id)
