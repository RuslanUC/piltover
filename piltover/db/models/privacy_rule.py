from __future__ import annotations

from typing import Iterable

from tortoise import fields, Model
from tortoise.expressions import Subquery, Q
from tortoise.query_utils import Prefetch

from piltover.context import request_ctx
from piltover.db import models
from piltover.db.enums import PrivacyRuleKeyType
from piltover.db.models import Contact
from piltover.tl import PrivacyValueAllowContacts, PrivacyValueAllowAll, PrivacyValueAllowUsers, \
    PrivacyValueDisallowAll, PrivacyValueDisallowUsers, InputPrivacyValueAllowContacts, InputPrivacyValueAllowAll, \
    InputPrivacyValueAllowUsers, InputPrivacyValueDisallowUsers, InputUserSelf, InputUser, InputPeerUser
from piltover.tl.base import InputPrivacyRule, PrivacyRule as TLPrivacyRule


def _inputusers_to_uids(
        user: models.User, input_users: list[InputUserSelf | InputUser], existing_set: set[int] | None = None
) -> set[int]:
    auth_id = request_ctx.get().auth_id
    result = existing_set if existing_set is not None else set()

    for input_user in input_users:
        if not isinstance(input_user, (InputUser, InputPeerUser)):
            continue
        if input_user.user_id == user.id:
            continue
        if models.User.check_access_hash(user.id, auth_id, input_user.user_id, input_user.access_hash):
            result.add(input_user.user_id)

    return result


class PrivacyRule(Model):
    id: int = fields.BigIntField(pk=True)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
    key: PrivacyRuleKeyType = fields.IntEnumField(PrivacyRuleKeyType)
    allow_all: bool = fields.BooleanField()
    allow_contacts: bool = fields.BooleanField()

    exceptions: fields.ReverseRelation[models.PrivacyRuleException]

    user_id: int

    class Meta:
        unique_together = (
            ("user", "key"),
        )

    @classmethod
    async def update_from_tl(
            cls, user: models.User, rule_key: PrivacyRuleKeyType, rules: list[InputPrivacyRule],
    ) -> PrivacyRule:
        allow_all = False
        allow_contacts = False
        allow_users = set()
        disallow_users = set()

        for rule in rules:
            # Telegram completely ignores InputPrivacyValueDisallowAll/InputPrivacyValueDisallowContacts
            #  after encountering InputPrivacyValueAllowAll/InputPrivacyValueAllowContacts for some unknown to reason,
            #  so doing same thing here.
            if isinstance(rule, InputPrivacyValueAllowAll):
                allow_all = True
            elif isinstance(rule, InputPrivacyValueAllowContacts):
                allow_contacts = True
            elif isinstance(rule, InputPrivacyValueAllowUsers):
                _inputusers_to_uids(user, rule.users, allow_users)
            elif isinstance(rule, InputPrivacyValueDisallowUsers):
                _inputusers_to_uids(user, rule.users, disallow_users)

        all_users = {*allow_users, *disallow_users}

        rule, created = await cls.update_or_create(user=user, key=rule_key, defaults={
            "allow_all": allow_all,
            "allow_contacts": allow_contacts,
        })

        if all_users:
            await models.PrivacyRuleException.filter(id__in=Subquery(
                models.PrivacyRuleException.filter(rule=rule, user__id__not_in=all_users).values_list("id", flat=True)
            )).delete()

            existing = {}
            if not created:
                existing = {
                    exc.user_id: exc
                    for exc in await models.PrivacyRuleException.filter(rule=rule)
                }

            to_update = []
            to_create = []
            for user in await models.User.filter(id__in=all_users):
                allow = user.id in allow_users
                if user.id in existing:
                    exc = existing[user.id]
                    if exc.allow != allow:
                        exc.allow = allow
                        to_update.append(exc)
                else:
                    to_create.append(models.PrivacyRuleException(
                        rule=rule,
                        user=user,
                        allow=user.id in allow_users,
                    ))

            if to_create:
                await models.PrivacyRuleException.bulk_create(to_create)
            if to_update:
                await models.PrivacyRuleException.bulk_update(to_update, fields=["allow"])
        else:
            await models.PrivacyRuleException.filter(rule=rule).delete()

        return rule

    def to_tl_rules(self) -> list[TLPrivacyRule]:
        rules = []

        if self.allow_all:
            rules.append(PrivacyValueAllowAll())
        elif self.allow_contacts:
            rules.append(PrivacyValueDisallowAll())
            rules.append(PrivacyValueAllowContacts())
        else:
            rules.append(PrivacyValueDisallowAll())

        if not self.exceptions._fetched:
            raise RuntimeError("Privacy rule exceptions must be prefetched")

        allow_users = []
        disallow_users = []

        for exc in self.exceptions:
            if exc.user is not None:
                if exc.allow:
                    allow_users.append(exc.user_id)
                else:
                    disallow_users.append(exc.user_id)

        if allow_users:
            rules.append(PrivacyValueAllowUsers(users=allow_users))
        if disallow_users:
            rules.append(PrivacyValueDisallowUsers(users=disallow_users))

        return rules

    @classmethod
    async def has_access_to(
            cls, current_user: models.User | int, target_user: models.User | int, key: PrivacyRuleKeyType,
    ) -> bool:
        current_id = current_user.id if isinstance(current_user, models.User) else current_user
        target_id = target_user.id if isinstance(target_user, models.User) else target_user

        if current_id == target_id:
            return True

        # TODO: check if target_user blocked current_user

        rule = await cls.get_or_none(
            user__id=target_id, key=key,
        ).prefetch_related(Prefetch(
            "exceptions", queryset=models.PrivacyRuleException.filter(user__id=current_id),
        )).annotate(
            is_contact=Subquery(Contact.filter(
                owner_id=target_id,
                target_id=current_id,
            ).exists()),
        )

        if rule is None:
            return False

        if rule.exceptions.related_objects:
            return rule.exceptions.related_objects[0].allow

        if rule.allow_all:
            return True
        elif rule.allow_contacts and rule.is_contact:
            return True

        return False

    @classmethod
    async def has_access_to_bulk(
            cls, users: Iterable[models.User | int], user: models.User, keys: list[PrivacyRuleKeyType],
            contacts: set[int] | None = None,
    ) -> dict[int, dict[PrivacyRuleKeyType, bool]]:
        if not keys:
            return {}

        user_ids = {
            (target.id if isinstance(target, models.User) else target)
            for target in users
        }
        results = {
            user_id: {}
            for user_id in user_ids
        }

        if user.id in user_ids:
            user_ids.remove(user.id)
            results[user.id] = {
                key: True for key in keys
            }

        for target_user in users:
            if isinstance(target_user, models.User) and target_user.bot:
                user_ids.discard(target_user.id)
                results[target_user.id] = {
                    key: True for key in keys
                }

        if not user_ids:
            return results

        key_query = Q()
        for key in keys:
            key_query |= Q(key=key)

        if contacts is None:
            contacts = {
                contact.owner_id
                for contact in await models.Contact.filter(owner__id__in=user_ids, target__id=user.id)
            }

        rules = await cls.filter(
            key_query, user__id__in=user_ids,
        ).prefetch_related(Prefetch(
            "exceptions", queryset=models.PrivacyRuleException.filter(user__id=user.id),
        ))

        leftover = {
            (user_id, key)
            for user_id in user_ids
            for key in keys
        }

        for rule in rules:
            leftover.discard((rule.user_id, rule.key))

            if rule.exceptions.related_objects:
                results[rule.user_id][rule.key] = rule.exceptions.related_objects[0].allow
                continue

            if rule.allow_all or rule.allow_contacts and rule.user_id in contacts:
                results[rule.user_id][rule.key] = True
                continue

            results[rule.user_id][rule.key] = False

        for user_id, key in leftover:
            results[user_id][key] = False

        return results
