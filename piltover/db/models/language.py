from tortoise import Model, fields

from piltover.tl import LangPackLanguage


class Language(Model):
    id: int = fields.BigIntField(pk=True)
    name: str = fields.CharField(max_length=64)
    native_name: str = fields.CharField(max_length=64)
    platform: str = fields.CharField(max_length=16)
    lang_code: str = fields.CharField(max_length=8)
    base_lang_code: str | None = fields.CharField(max_length=8, null=True, default=None)
    plural_lang_code: str = fields.CharField(max_length=8)
    strings_count: int = fields.IntField()
    translated_count: int = fields.IntField()
    official: bool = fields.BooleanField(default=False)
    rtl: bool = fields.BooleanField(default=False)
    beta: bool = fields.BooleanField(default=False)
    version: int = fields.IntField()

    class Meta:
        unique_together = (
            ("platform", "lang_code"),
        )

    def to_tl(self) -> LangPackLanguage:
        return LangPackLanguage(
            official=self.official,
            rtl=self.rtl,
            beta=self.beta,
            name=self.name,
            native_name=self.native_name,
            lang_code=self.lang_code,
            base_lang_code=self.base_lang_code,
            plural_code=self.plural_lang_code,
            strings_count=self.strings_count,
            translated_count=self.translated_count,
            translations_url="http://127.0.0.1",
        )
