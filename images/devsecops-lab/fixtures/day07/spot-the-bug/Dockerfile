# Day 7 spot-the-bug fixture: a team's "quick" image.  Author: Tim Rice
FROM node:latest

COPY vendor.sources /etc/apt/sources.list.d/vendor.sources
RUN apt-get update && apt-get install -y curl imagemagick vendor-agent

WORKDIR /app
COPY . .
RUN npm install
CMD ["node", "server.js"]
