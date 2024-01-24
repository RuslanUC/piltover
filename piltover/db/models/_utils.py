import tortoise
from tortoise.expressions import Q


class Model(tortoise.Model):
    async def update(self, **kwargs) -> None:
        await self.update_from_dict(kwargs)
        await self.save()


def user_auth_q_temp(key_id: int) -> Q:
    """
    Returns tortoise-orm Q object for UserAuthorization model which will work both for perm keys and temp keys.
    """
    return Q(key__id=str(key_id)) | Q(key__tempauthkeys__id=str(key_id))
