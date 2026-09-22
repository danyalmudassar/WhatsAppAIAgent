FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S dashboard && adduser -S dashboard -G dashboard
COPY --from=build --chown=dashboard:dashboard /app/.next/standalone ./
USER dashboard
EXPOSE 3000
CMD ["node","server.js"]
