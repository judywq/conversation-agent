FROM node:20-bullseye-slim

WORKDIR /app/vue_frontend

COPY ./vue_frontend/package.json ./package.json
COPY ./vue_frontend/package-lock.json ./package-lock.json
COPY ./.envs/.local/.env.development ./.env.development

COPY ./compose/local/vite/entrypoint /entrypoint
RUN sed -i 's/\r//' /entrypoint
RUN chmod +x /entrypoint

RUN npm ci && npm cache clean --force

ENV PATH ./node_modules/.bin/:$PATH

ENTRYPOINT ["/entrypoint"]
