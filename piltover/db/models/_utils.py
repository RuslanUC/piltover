import tortoise
from tortoise.expressions import Q


class Model(tortoise.Model):
    async def update(self, **kwargs) -> None:
        await self.update_from_dict(kwargs)
        await self.save()
