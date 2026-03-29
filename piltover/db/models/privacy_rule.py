from __future__ import annotations

from typing import Iterable

from tortoise import fields, Model
from tortoise.expressions import Subquery, Q, F
from tortoise.query_utils import Prefetch
from tortoise.transactions import in_transaction

from piltover.cache import Cache
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
    id: int = fields.BigIntField(primary_key=True)
    user: models.User = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
    key: PrivacyRuleKeyType = fields.IntEnumField(PrivacyRuleKeyType, description="")
    allow_all: bool = fields.BooleanField()
    allow_contacts: bool = fields.BooleanField()
    version: int = fields.BigIntField(default=0)

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

        async with in_transaction():
            rule, created = await cls.update_or_create(user=user, key=rule_key, defaults={
                "allow_all": allow_all,
                "allow_contacts": allow_contacts,
            })

            if all_users:
                await models.PrivacyRuleException.filter(id__in=Subquery(
                    models.PrivacyRuleException.filter(
                        rule=rule, user_id__not_in=all_users,
                    ).values_list("id", flat=True)
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

            await cls.filter(id=rule.id).update(version=F("version") + 1)
            await rule.refresh_from_db(["version"])

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
    def cache_key(cls, this_user: int, rule_user: int, key: PrivacyRuleKeyType, version: int) -> str:
        return f"privacy-rule:{rule_user}:{key.value}:{version}:{this_user}"

    @classmethod
    async def has_access_to(
            cls, current_user: models.User | int, target_user: models.User | int, key: PrivacyRuleKeyType,
    ) -> bool:
        current_id = current_user.id if isinstance(current_user, models.User) else current_user
        target_id = target_user.id if isinstance(target_user, models.User) else target_user

        if current_id == target_id:
            return True

        rule_simple = await cls.get_or_none(user_id=target_id, key=key).only("id", "version")
        if rule_simple is None:
            return False

        cache_key = cls.cache_key(current_id, target_id, key, rule_simple.version)
        cached = await Cache.obj.get(cache_key)
        if cached is not None:
            return cached

        # TODO: check if target_user blocked current_user

        rule = await cls.get_or_none(
            id=rule_simple.id,
        ).prefetch_related(Prefetch(
            "exceptions", queryset=models.PrivacyRuleException.filter(user_id=current_id),
        )).annotate(
            is_contact=Subquery(Contact.filter(
                owner_id=target_id,
                target_id=current_id,
            ).exists()),
        )

        result = False

        if rule is None:
            ...
        elif rule.exceptions.related_objects:
            result = rule.exceptions.related_objects[0].allow
        elif rule.allow_all or (rule.allow_contacts and rule.is_contact):
            result = True

        await Cache.obj.set(cache_key, result)

        return result

    @classmethod
    async def has_access_to_bulk(
            cls, users: Iterable[models.User | int], user: models.User | int, keys: list[PrivacyRuleKeyType],
            contacts: set[int] | None = None,
    ) -> dict[int, dict[PrivacyRuleKeyType, bool]]:
        if not keys:
            return {}

        this_user_id = user.id if isinstance(user, models.User) else user

        user_ids = {
            (target.id if isinstance(target, models.User) else target)
            for target in users
        }
        results = {
            user_id: {}
            for user_id in user_ids
        }

        if this_user_id in user_ids:
            user_ids.remove(this_user_id)
            results[this_user_id] = {
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

        rules_simple = await cls.filter(key_query, user_id__in=user_ids).only("id", "version", "user_id", "key")
        cache_keys = [cls.cache_key(this_user_id, rule.user_id, rule.key, rule.version) for rule in rules_simple]
        if cache_keys:
            cached_all = await Cache.obj.multi_get(cache_keys)
        else:
            cached_all = []

        not_cached_ids = []

        leftover = {
            (user_id, key)
            for user_id in user_ids
            for key in keys
        }

        for rule, allowed in zip(rules_simple, cached_all):
            if allowed is None:
                not_cached_ids.append(rule.id)
            else:
                results[rule.user_id][rule.key] = allowed
                leftover.discard((rule.user_id, rule.key))

        if not_cached_ids and contacts is None:
            contacts = {
                contact.owner_id
                for contact in await models.Contact.filter(owner_id__in=user_ids, target_id=this_user_id)
            }

        if not_cached_ids:
            rules = await cls.filter(
                id__in=not_cached_ids,
            ).prefetch_related(Prefetch(
                "exceptions", queryset=models.PrivacyRuleException.filter(user_id=this_user_id),
            ))
        else:
            rules = []

        to_cache = []

        for rule in rules:
            leftover.discard((rule.user_id, rule.key))

            cache_key = cls.cache_key(this_user_id, rule.user_id, rule.key, rule.version)

            if rule.exceptions.related_objects:
                allow = rule.exceptions.related_objects[0].allow
                results[rule.user_id][rule.key] = allow
                to_cache.append((cache_key, allow))
                continue

            if rule.allow_all or rule.allow_contacts and rule.user_id in contacts:
                results[rule.user_id][rule.key] = True
                to_cache.append((cache_key, True))
                continue

            results[rule.user_id][rule.key] = False
            to_cache.append((cache_key, False))

        for user_id, key in leftover:
            results[user_id][key] = False

        if to_cache:
            await Cache.obj.multi_set(to_cache)

        return results
