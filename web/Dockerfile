FROM node:20-slim AS base
WORKDIR /app
ENV NODE_ENV=development

FROM base AS deps
COPY package.json ./
RUN npm install

FROM deps AS dev
COPY . .
EXPOSE 9010
CMD ["npx", "quasar", "dev", "-p", "9010", "--host"]

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:alpine AS production
COPY --from=build /app/dist/pwa /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
