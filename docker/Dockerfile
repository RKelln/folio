# Dockerfile for folio

FROM python:3.12-slim

WORKDIR /app

RUN pip install pipx && pipx install folio

COPY folio.yaml /app/

ENTRYPOINT ["folio"]
