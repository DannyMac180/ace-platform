# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Build args for environment configuration
ARG VITE_API_URL=https://aceagent.io
ARG VITE_DOCS_URL=https://docs.aceagent.io/docs
ARG VITE_SENTRY_DSN=
ARG VITE_SENTRY_RELEASE=
ARG VITE_SENTRY_ENVIRONMENT=production
ARG VITE_SENTRY_TRACES_SAMPLE_RATE=0.05

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Set environment variables for build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_DOCS_URL=$VITE_DOCS_URL
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
ENV VITE_SENTRY_RELEASE=$VITE_SENTRY_RELEASE
ENV VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT
ENV VITE_SENTRY_TRACES_SAMPLE_RATE=$VITE_SENTRY_TRACES_SAMPLE_RATE

# Build the app
RUN npm run build

# Production stage - serve with nginx
FROM nginx:alpine

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config template for SPA routing
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Default CSP API URL (overridden by env var at runtime)
ENV CSP_API_URL=https://aceagent.io

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
