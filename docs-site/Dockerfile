# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Build args for environment-specific URLs
ARG APP_URL=https://app.aceagent.io
ARG API_URL=https://aceagent.io

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Set environment variables for build
ENV APP_URL=$APP_URL
ENV API_URL=$API_URL

# Build the static site
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 8080 (Fly.io default)
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
