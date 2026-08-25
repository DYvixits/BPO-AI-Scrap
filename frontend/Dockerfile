# Dev-mode image: runs the Vite dev server with HMR against the API
# container. A production multi-stage build (vite build -> nginx) is a
# Phase 11 deployment concern, not needed for local/dev Docker Compose.
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
