from __future__ import annotations

from tortoise import fields, Model

from piltover.db import models
from piltover.db.enums import PrivacyRuleKeyType, PrivacyRuleValueType, PeerType
from piltover.tl import PrivacyValueAllowContacts, PrivacyValueAllowAll, PrivacyValueAllowUsers, \
    PrivacyValueDisallowContacts, PrivacyValueDisallowAll, PrivacyValueDisallowUsers, InputPrivacyKeyStatusTimestamp, \
    InputPrivacyKeyChatInvite, InputPrivacyKeyPhoneCall, InputPrivacyKeyPhoneP2P, InputPrivacyKeyForwards, \
    InputPrivacyKeyProfilePhoto, InputPrivacyKeyPhoneNumber, InputPrivacyKeyAddedByPhone, \
    InputPrivacyKeyVoiceMessages, InputPrivacyValueAllowContacts, InputPrivacyValueAllowAll, \
    InputPrivacyValueAllowUsers, InputPrivacyValueDisallowContacts, InputPrivacyValueDisallowAll, \
    InputPrivacyValueDisallowUsers, InputUserSelf, InputUser, InputPrivacyKeyAbout, InputPrivacyKeyBirthday

PRIVACY_ENUM_TO_TL = {
    PrivacyRuleValueType.ALLOW_CONTACTS: PrivacyValueAllowContacts,
    PrivacyRuleValueType.ALLOW_ALL: PrivacyValueAllowAll,
    PrivacyRuleValueType.ALLOW_USERS: PrivacyValueAllowUsers,
    PrivacyRuleValueType.DISALLOW_CONTACTS: PrivacyValueDisallowContacts,
    PrivacyRuleValueType.DISALLOW_ALL: PrivacyValueDisallowAll,
    PrivacyRuleValueType.DISALLOW_USERS: PrivacyValueDisallowUsers,
}
TL_TO_PRIVACY_ENUM = {
    InputPrivacyValueAllowContacts: PrivacyRuleValueType.ALLOW_CONTACTS,
    InputPrivacyValueAllowAll: PrivacyRuleValueType.ALLOW_ALL,
    InputPrivacyValueAllowUsers: PrivacyRuleValueType.ALLOW_USERS,
    InputPrivacyValueDisallowContacts: PrivacyRuleValueType.DISALLOW_CONTACTS,
    InputPrivacyValueDisallowAll: PrivacyRuleValueType.DISALLOW_ALL,
    InputPrivacyValueDisallowUsers: PrivacyRuleValueType.DISALLOW_USERS,
}
TL_KEY_TO_PRIVACY_ENUM = {
    InputPrivacyKeyStatusTimestamp: PrivacyRuleKeyType.STATUS_TIMESTAMP,
    InputPrivacyKeyChatInvite: PrivacyRuleKeyType.CHAT_INVITE,
    InputPrivacyKeyPhoneCall: PrivacyRuleKeyType.PHONE_CALL,
    InputPrivacyKeyPhoneP2P: PrivacyRuleKeyType.PHONE_P2P,
    InputPrivacyKeyForwards: PrivacyRuleKeyType.FORWARDS,
    InputPrivacyKeyProfilePhoto: PrivacyRuleKeyType.PROFILE_PHOTO,
    InputPrivacyKeyPhoneNumber: PrivacyRuleKeyType.PHONE_NUMBER,
    InputPrivacyKeyAddedByPhone: PrivacyRuleKeyType.ADDED_BY_PHONE,
    InputPrivacyKeyVoiceMessages: PrivacyRuleKeyType.VOICE_MESSAGE,
    InputPrivacyKeyAbout: PrivacyRuleKeyType.ABOUT,
    InputPrivacyKeyBirthday: PrivacyRuleKeyType.BIRTHDAY,
}


def _inputusers_to_uids(user: models.User, input_users: list[InputUserSelf | InputUser]) -> set[int]:
    result = set()
    for input_user in input_users:
        if isinstance(input_user, InputUserSelf):
            result.add(user.id)
        elif isinstance(input_user, InputUser):
            result.add(input_user.user_id)

    return result


class PrivacyRule(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
    key: PrivacyRuleKeyType = fields.IntEnumField(PrivacyRuleKeyType)
    value: PrivacyRuleValueType = fields.IntEnumField(PrivacyRuleValueType)
    users = fields.ManyToManyField("models.User", related_name="privacy_rules")

    # TODO: chats

    @classmethod
    async def update_from_tl(cls, user: models.User, rule_key: PrivacyRuleKeyType, rules: list) -> None:
        #existing_rules = {rule.value: rule for rule in await PrivacyRule.filter(user=user, key=rule_key)}
        await PrivacyRule.filter(user=user, key=rule_key).delete()
        new_rules = {}
        for rule in rules:
            type_ = type(rule)
            if type_ not in TL_TO_PRIVACY_ENUM:
                continue
            value = TL_TO_PRIVACY_ENUM[type_]
            new_rules[value] = rule

        for key, rule in new_rules.items():
            if (key in {PrivacyRuleValueType.ALLOW_USERS, PrivacyRuleValueType.DISALLOW_USERS} or
                    (key == PrivacyRuleValueType.ALLOW_CONTACTS and PrivacyRuleValueType.ALLOW_ALL in new_rules) or
                    (key == PrivacyRuleValueType.DISALLOW_CONTACTS and PrivacyRuleValueType.DISALLOW_ALL in new_rules) or
                    (key == PrivacyRuleValueType.ALLOW_ALL and PrivacyRuleValueType.DISALLOW_ALL in new_rules)):
                #if key in existing_rules:
                #    await existing_rules[key].delete()
                continue
            await PrivacyRule.create(user=user, key=rule_key, value=key)

        async def _fill_users_rule(val: PrivacyRuleValueType, users: set[int]) -> None:
            rule_ = await PrivacyRule.create(user=user, key=rule_key, value=val)
            await rule_.users.add(*await models.User.filter(id__in=users))

        disallow = set()
        if PrivacyRuleValueType.DISALLOW_USERS in new_rules:
            disallow = _inputusers_to_uids(user, new_rules[PrivacyRuleValueType.DISALLOW_USERS].users)
            await _fill_users_rule(PrivacyRuleValueType.DISALLOW_USERS, disallow)
        if PrivacyRuleValueType.ALLOW_USERS in new_rules:
            allow = disallow - _inputusers_to_uids(user, new_rules[PrivacyRuleValueType.ALLOW_USERS].users)
            await _fill_users_rule(PrivacyRuleValueType.ALLOW_USERS, allow)

    async def to_tl(self):
        tl_cls = PRIVACY_ENUM_TO_TL[self.value]
        if self.value in {PrivacyRuleValueType.ALLOW_USERS, PrivacyRuleValueType.DISALLOW_USERS}:
            user_ids = await self.users.all().values_list("id", flat=True)
            return tl_cls(users=user_ids)

        return tl_cls()

    @classmethod
    async def has_access_to(cls, current_user: models.User, target_user: models.User, key: PrivacyRuleKeyType) -> bool:
        if current_user == target_user:
            return True
        if await models.Peer.filter(owner=target_user, user=current_user, type=PeerType.USER, blocked=True).exists():
            return False

        rules = {rule.value: rule for rule in await cls.filter(user=target_user, key=key)}
        if PrivacyRuleValueType.ALLOW_ALL in rules and PrivacyRuleValueType.DISALLOW_USERS not in rules:
            return True
        if PrivacyRuleValueType.DISALLOW_ALL in rules and PrivacyRuleValueType.ALLOW_USERS not in rules:
            return False

        if PrivacyRuleValueType.ALLOW_ALL in rules and PrivacyRuleValueType.DISALLOW_USERS in rules:
            return not await rules[PrivacyRuleValueType.DISALLOW_USERS].users.filter(id=current_user.id).exists()
        if PrivacyRuleValueType.DISALLOW_ALL in rules and PrivacyRuleValueType.ALLOW_USERS in rules:
            return await rules[PrivacyRuleValueType.DISALLOW_USERS].users.filter(id=current_user.id).exists()

        # handle PrivacyRuleValueType.ALLOW_CONTACTS and PrivacyRuleValueType.DISALLOW_CONTACTS

        return True
