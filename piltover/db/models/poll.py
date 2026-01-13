from __future__ import annotations

from datetime import datetime

from pytz import UTC
from tortoise import Model, fields
from tortoise.functions import Count

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

    async def to_tl_results(self, user: models.User) -> PollResults:
        if not self.pollanswers._fetched:
            raise RuntimeError("Poll answers must be prefetched")

        user_voted_answers = set(await models.PollVote.filter(answer__poll=self, user=user).values_list("answer__id"))
        # TODO: create PollResults with min, results, total_voters, min and cache it
        #if not user_votes:
        #    return PollResults(min=True, ...)

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

        return PollResults(
            results=answers,
            total_voters=await models.User.filter(pollvotes__answer__poll=self).distinct().count(),
            solution=self.solution if self.quiz and incorrect else None,
        )
