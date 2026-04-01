FROM python:3.12

RUN python -m pip install --upgrade pip uv

COPY . /src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system /src[agent,tracing]

CMD ["python"]
