FROM python:3.11-bookworm AS deps

WORKDIR /piltover

RUN apt update && apt install curl
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

ENV UV_NO_DEV=1
RUN uv sync --locked

FROM python:3.11-bookworm AS tl

WORKDIR /piltover

COPY piltover piltover
COPY tools tools

RUN python tools/tl_gen.py

FROM python:3.11-bookworm

WORKDIR /piltover

RUN apt update && apt install dumb-init && apt clean

COPY . .
COPY --from=deps /piltover/.venv /piltover/.venv
COPY --from=tl /piltover/piltover/tl /piltover/piltover/tl

ENV PATH="/piltover/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
