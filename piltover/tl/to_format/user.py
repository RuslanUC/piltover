from piltover.context import serialization_ctx, NeedContextValuesContext
from piltover.layer_converter.manager import LayerConverter
from piltover.tl import types


class UserToFormat(types.UserToFormatInternal):
    def _write(self) -> bytes:
        from piltover.db.enums import PeerType, PrivacyRuleKeyType
        from piltover.db.models.presence import EMPTY as PRESENCE_EMPTY

        ctx = serialization_ctx.get()

        if self.id == ctx.user_id:
            peer_exists = True
        else:
            peer_exists = ctx.values is not None and (PeerType.USER, self.id) in ctx.values.peers

        presence = PRESENCE_EMPTY
        has_access_to_phone = False
        has_access_to_photo = False
        has_access_to_status = False

        if ctx.values is not None:
            contact = ctx.values.contacts.get((ctx.user_id, self.id), None)
            current_is_contact = (self.id, ctx.user_id) in ctx.values.contacts
            if self.id in ctx.values.privacyrules:
                rules = ctx.values.privacyrules[self.id]
                has_access_to_phone = rules[PrivacyRuleKeyType.PHONE_NUMBER]
                has_access_to_photo = rules[PrivacyRuleKeyType.PROFILE_PHOTO]
                has_access_to_status = rules[PrivacyRuleKeyType.STATUS_TIMESTAMP]

            if self.id in ctx.values.presences:
                presence = ctx.values.presences[self.id].to_tl_noprivacycheck(has_access_to_status)
        else:
            contact = None
            current_is_contact = False

        is_contact = contact is not None

        phone_number = None
        if (contact is not None and contact.known_phone_number == self.phone) or has_access_to_phone:
            phone_number = self.phone

        photo = types.UserProfilePhotoEmpty()
        if has_access_to_photo and self.photo is not None:
            photo = self.photo

        return LayerConverter.downgrade(
            obj=types.User(
                id=self.id,
                first_name=self.first_name if contact is None or not contact.first_name else contact.first_name,
                last_name=self.last_name if contact is None or not contact.last_name else contact.last_name,
                username=self.username,
                phone=phone_number,
                lang_code=self.lang_code,
                is_self=self.id == ctx.user_id,
                photo=photo,
                access_hash=-1 if peer_exists else 0,
                status=presence,
                contact=is_contact,
                bot=self.bot,
                bot_info_version=self.bot_info_version,
                color=self.color,
                profile_color=self.profile_color,
                mutual_contact=is_contact and current_is_contact,

                # TODO: this is True only because custom emojis are not available (like at all, missing in emoji list)
                #  for non-premium users.
                #  Need to figure out how official telegram allows custom emojis to be visible to non-premium users.
                premium=not self.bot,
            ),
            to_layer=ctx.layer,
        ).write()

    def write(self) -> bytes:
        ctx = serialization_ctx.get()
        if ctx is None or ctx.dont_format:
            return super().write()
        return self._write()

    def check_for_ctx_values(self, values: NeedContextValuesContext) -> None:
        values.users.add(self.id)