from typing import TypedDict


class UrlMetadataDict(TypedDict, total=False):
    title: str
    description: str
    image: str
    site_name: str


class WebpageMetaTarget:
    def __init__(self) -> None:
        self._in_head = False
        self._in_title = False
        self._should_stop = False

        self._title_parts: list[str] = []
        self._og_title: str | None = None
        self._og_description: str | None = None
        self._og_image: str | None = None
        self._og_site_name: str | None = None
        self._twitter_title: str | None = None
        self._twitter_description: str | None = None
        self._twitter_image: str | None = None

    def should_stop(self) -> bool:
        return self._should_stop

    def get_parsed_meta(self) -> UrlMetadataDict:
        result: UrlMetadataDict = {}
        if self._og_title is not None:
            result["title"] = self._og_title
        elif self._twitter_title is not None:
            result["title"] = self._twitter_title
        elif self._title_parts:
            result["title"] = "".join(self._title_parts)

        if self._og_description is not None:
            result["description"] = self._og_description
        elif self._twitter_description is not None:
            result["description"] = self._twitter_description

        if self._og_image is not None:
            result["image"] = self._og_image
        elif self._twitter_image is not None:
            result["image"] = self._twitter_image

        if self._og_site_name is not None:
            result["site_name"] = self._og_site_name

        return result

    def start(self, tag: str, attrib: dict) -> None:
        if self._should_stop:
            return
        if self._in_title:
            self._should_stop = True
            return
        if tag == "head":
            if self._in_head:
                self._should_stop = True
                return
            self._in_head = True
        if self._in_head and tag == "meta":
            meta_name = attrib.get("property")
            meta_value = attrib.get("content")
            if not meta_name or not meta_value:
                return
            if meta_name == "og:title":
                self._og_title = meta_value
            elif meta_name == "og:description":
                self._og_description = meta_value
            elif meta_name == "og:image":
                self._og_image = meta_value
            elif meta_name == "og:site_name":
                self._og_site_name = meta_value
            elif meta_name == "twitter:title":
                self._twitter_title = meta_value
            elif meta_name == "twitter:description":
                self._twitter_description = meta_value
            elif meta_name == "twitter:image":
                self._twitter_image = meta_value
        elif self._in_head and tag == "title":
            self._in_title = True
            self._in_head = False

    def end(self, tag: str) -> None:
        if tag == "head":
            self._in_head = False
            self._should_stop = True
        elif tag == "title":
            self._in_head = True
            self._in_title = False

    def data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def close(self):
        self._should_stop = True
