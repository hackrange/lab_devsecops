# Dockerfile from the same team.  Values are fake lab markers.
FROM node:24-slim
WORKDIR /app
ARG NPM_TOKEN
ENV NPM_TOKEN=${NPM_TOKEN}
COPY . .
RUN echo "//registry.npmjs.org/:_authToken=${NPM_TOKEN}" > .npmrc && npm ci --omit=dev
ENV DB_PASSWORD=LAB_SECRET_DOCKERDBPASS0001
USER node
CMD ["node", "src/index.js"]
