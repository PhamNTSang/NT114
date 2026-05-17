FROM node:20.20.2-alpine AS builder

WORKDIR /usr/src/app

RUN apk add --no-cache python3 make g++

COPY package*.json ./
RUN npm ci --omit=dev

FROM node:20.20.2-alpine

WORKDIR /usr/src/app

RUN apk add --no-cache libstdc++

COPY --from=builder --chown=node:node /usr/src/app/node_modules ./node_modules
COPY --chown=node:node . .

USER node
EXPOSE 7000
ENTRYPOINT ["node", "server.js"]
