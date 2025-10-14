from __future__ import annotations

from datetime import datetime

from pytz import UTC
from tortoise import Model, fields

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

    async def to_tl(self) -> TLPoll:
        answer: models.PollAnswer

        return TLPoll(
            id=self.id,
            closed=self.is_closed_fr,
            public_voters=self.public_voters,
            multiple_choice=self.multiple_choices,
            quiz=self.quiz,
            question=TextWithEntities(text=self.question, entities=[]),
            answers=[
                answer.to_tl()
                async for answer in self.pollanswers.all()
            ],
            close_date=int(self.ends_at.timestamp()) if self.ends_at else None,
        )

    async def to_tl_results(self, user: models.User) -> PollResults:
        user_votes = await models.PollVote.filter(answer__poll=self, user=user).select_related("answer")
        # TODO: create PollResults with min, results, total_voters, min and cache it
        #if not user_votes:
        #    return PollResults(min=True)

        chosen = set(vote.answer.option for vote in user_votes)

        answers = []
        answer: models.PollAnswer
        async for answer in self.pollanswers.all():
            answers.append(PollAnswerVoters(
                chosen=answer.option in chosen,
                correct=self.quiz and answer.correct,
                option=answer.option,
                voters=await models.PollVote.filter(answer=answer).count(),
            ))

        return PollResults(
            results=answers,
            total_voters=await models.User.filter(pollvotes__answer__poll=self).distinct().count(),
            solution=self.solution if self.quiz and not user_votes[0].answer.correct else None,
        )
