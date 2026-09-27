# leaky.Dockerfile: the recipe behind the Day 9 "layers remember" image.
# It looks careful: it deletes .env and .npmrc before it finishes.
# Build it on your own machine with Docker if you like; in the lab, run
# make-leaky-image.py, which assembles the same layers without a daemon.
FROM node:24-bookworm-slim
ARG NPM_TOKEN=LAB_SECRET_d09_npm_token_not_real
WORKDIR /app
COPY app/ ./
RUN echo "//registry.npmjs.org/:_authToken=${NPM_TOKEN}" > .npmrc && echo installed
RUN rm -f .env .npmrc
CMD ["node", "server.js"]
