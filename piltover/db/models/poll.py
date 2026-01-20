from __future__ import annotations

from datetime import datetime
from time import time

from pytz import UTC
from tortoise import Model, fields
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.tl import Poll as TLPoll, TextWithEntities
from piltover.tl.base import PollResults as PollResultsBase
from piltover.tl.to_format import PollResultsToFormat, PollAnswerVotersToFormat


class Poll(Model):
    id: int = fields.BigIntField(pk=True)
    closed: bool = fields.BooleanField(default=False)
    quiz: bool = fields.BooleanField(default=False)
    public_voters: bool = fields.BooleanField(default=False)
    multiple_choices: bool = fields.BooleanField(default=False)
    question: str = fields.CharField(max_length=255)
    # TODO: solution entities
    solution: str | None = fields.CharField(max_length=200, null=True, default=None)
    ends_at: datetime | None = fields.DatetimeField(null=True, default=None)
    version: int = fields.IntField(default=0)
    pollanswers: fields.ReverseRelation[models.PollAnswer]

    CACHE_TTL = 60 * 5

    @property
    def is_closed_fr(self) -> bool:
        return self.closed or (self.ends_at is not None and datetime.now(UTC) > self.ends_at)

    def to_tl(self) -> TLPoll:
        if not self.pollanswers._fetched:
            raise RuntimeError("Poll answers must be prefetched")

        return TLPoll(
            id=self.id,
            closed=self.is_closed_fr,
            public_voters=self.public_voters,
            multiple_choice=self.multiple_choices,
            quiz=self.quiz,
            question=TextWithEntities(text=self.question, entities=[]),
            answers=[
                answer.to_tl()
                for answer in self.pollanswers
            ],
            close_date=int(self.ends_at.timestamp()) if self.ends_at else None,
        )

    def _cache_key(self) -> str:
        return f"poll-results:{self.id}:f:{self.version}:{int(time() // self.CACHE_TTL)}"

    async def to_tl_results(self) -> PollResultsBase:
        if not self.pollanswers._fetched:
            raise RuntimeError("Poll answers must be prefetched")

        cache_key = self._cache_key()
        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        answer_ids = [answer.id for answer in self.pollanswers]
        voter_counts = {
            answer_id: voters
            for answer_id, voters in await models.PollVote.filter(
                answer__id__in=answer_ids
            ).group_by("answer__id").annotate(voters=Count("id")).values_list("answer__id", "voters")
        }

        results = PollResultsToFormat(
            id=self.id,
            results=[
                PollAnswerVotersToFormat(
                    id=answer.id,
                    poll_id=self.id,
                    correct=self.quiz and answer.correct,
                    option=answer.option,
                    voters=voter_counts.get(answer.id, 0),
                )
                for answer in self.pollanswers
            ],
            total_voters=await models.User.filter(pollvotes__answer__poll=self).distinct().count(),
            solution=self.solution if self.quiz else None,
        )

        await Cache.obj.set(cache_key, results)
        return results

    @classmethod
    async def to_tl_results_bulk(cls, polls: list[Poll]) -> list[PollResultsBase]:
        cached = {}
        for cached_poll in await Cache.obj.multi_get([poll._cache_key() for poll in polls]):
            if cached_poll:
                cached[cached_poll.id] = cached_poll

        answer_ids = [answer.id for poll in polls for answer in poll.pollanswers if poll.id not in cached]
        if answer_ids:
            voter_counts = {
                (poll_id, answer_id): voters
                for poll_id, answer_id, voters in await models.PollVote.filter(
                    answer__id__in=answer_ids
                ).group_by("answer__id").annotate(voters=Count("id")).values_list(
                    "answer__poll__id", "answer__id", "voters"
                )
            }
        else:
            voter_counts = {}

        poll_ids = [poll.id for poll in polls if poll.id not in cached]
        if poll_ids:
            total_counts = {
                poll_id: total_voters
                for poll_id, total_voters in await models.User.filter(
                    pollvotes__answer__poll__id__in=poll_ids,
                ).group_by(
                    "pollvotes__answer__poll__id",
                ).annotate(
                    voters=Count("id", distinct=True),
                ).values_list("pollvotes__answer__poll__id", "total_voters")
            }
        else:
            total_counts = {}

        tl = []
        to_cache = []

        for poll in polls:
            if poll.id in cached:
                tl.append(cached[poll.id])
                continue

            tl.append(PollResultsToFormat(
                id=poll.id,
                results=[
                    PollAnswerVotersToFormat(
                        id=answer.id,
                        poll_id=poll.id,
                        correct=poll.quiz and answer.correct,
                        option=answer.option,
                        voters=voter_counts.get((poll.id, answer.id), 0),
                    )
                    for answer in poll.pollanswers
                ],
                total_voters=total_counts.get(poll.id, 0),
                solution=poll.solution if poll.quiz else None,
            ))
            to_cache.append((poll._cache_key(), tl[-1]))

        await Cache.obj.multi_set(to_cache)
        return tl
