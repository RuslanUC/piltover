from __future__ import annotations

from datetime import datetime
from time import time

from pytz import UTC
from tortoise import Model, fields
from tortoise.functions import Count

from piltover.cache import Cache
from piltover.db import models
from piltover.tl import Poll as TLPoll, PollResults, PollAnswerVoters, TextWithEntities


class Poll(Model):
    id: int = fields.BigIntField(pk=True)
    closed: bool = fields.BooleanField(default=False)
    quiz: bool = fields.BooleanField(default=False)
    public_voters: bool = fields.BooleanField(default=False)
    multiple_choices: bool = fields.BooleanField(default=False)
    question: str = fields.CharField(max_length=255)
    solution: str | None = fields.CharField(max_length=200, null=True, default=None)
    ends_at: datetime | None = fields.DatetimeField(null=True, default=None)
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

    def _cache_key(self, user_id: int | None) -> str:
        # TODO: add some version (for when poll is edited)? idk
        return f"poll-results:{self.id}:{user_id or 0}:{int(time() // self.CACHE_TTL)}"

    # TODO: to_tl_results_bulk

    async def to_tl_results(self, user_id: int) -> PollResults:
        if not self.pollanswers._fetched:
            raise RuntimeError("Poll answers must be prefetched")

        results_min = False
        user_voted_answers = set(
            await models.PollVote.filter(answer__poll=self, user__id=user_id).values_list("answer__id")
        )
        if not user_voted_answers:
            user_id = None
            results_min = True

        cache_key = self._cache_key(user_id)
        if (cached := await Cache.obj.get(cache_key)) is not None:
            return cached

        answers = []
        incorrect = False

        answer_ids = [answer.id for answer in self.pollanswers]
        voter_counts = {
            answer_id: voters
            for answer_id, voters in await models.PollVote.filter(
                answer__id__in=answer_ids
            ).group_by("answer__id").annotate(voters=Count("id")).values_list("answer__id", "voters")
        }

        for answer in self.pollanswers:
            if answer.correct and answer.id not in user_voted_answers:
                incorrect = True
            answers.append(PollAnswerVoters(
                chosen=answer.id in user_voted_answers,
                correct=self.quiz and user_voted_answers and answer.correct,
                option=answer.option,
                voters=voter_counts.get(answer.id, 0),
            ))

        results = PollResults(
            min=results_min,
            results=answers,
            total_voters=await models.User.filter(pollvotes__answer__poll=self).distinct().count(),
            solution=self.solution if self.quiz and incorrect else None,
        )

        await Cache.obj.set(cache_key, results)
        return results
