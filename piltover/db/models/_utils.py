import tortoise


class Model(tortoise.Model):
    async def update(self, **kwargs) -> None:
        await self.update_from_dict(kwargs)
        await self.save()
