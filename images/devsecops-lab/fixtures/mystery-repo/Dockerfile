FROM node:20 AS web
WORKDIR /web
COPY web/ .
RUN npm install && npm run build

FROM python:3.12
WORKDIR /srv
COPY api/ ./api
COPY --from=web /web/dist ./static
RUN pip install ./api
ENV DATABASE_URL=postgresql://pawn:pawn123@db:5432/pawn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--app-dir", "api"]
