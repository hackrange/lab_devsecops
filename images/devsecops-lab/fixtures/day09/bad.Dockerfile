# bad.Dockerfile: a deliberately terrible Dockerfile for the Day 9 lab.
# Every problem in here is on purpose.  Do not copy any of it.
FROM node:latest
ARG NPM_TOKEN=LAB_SECRET_d09_npm_token_not_real
ENV API_KEY=LAB_SECRET_d09_api_key_not_real
RUN apt-get update && apt-get upgrade -y && apt-get install -y curl git
RUN curl -fsSL https://get.example.com/install.sh | sh
ADD https://example.com/tools/helper.tar.gz /opt/
WORKDIR /app
COPY . .
RUN echo "//registry.npmjs.org/:_authToken=${NPM_TOKEN}" > .npmrc && npm install
USER node
RUN chmod -R 777 /app
USER root
EXPOSE 22 3000
CMD node src/server.js
