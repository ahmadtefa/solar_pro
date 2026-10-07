# syntax=docker/dockerfile:1
# Builds the Flutter Web bundle and serves it through Nginx with the API proxy.
FROM ghcr.io/cirruslabs/flutter:stable AS build

WORKDIR /app
COPY frontend/pubspec.yaml frontend/pubspec.lock* ./
RUN flutter pub get
COPY frontend/ ./
RUN flutter build web --release --dart-define=API_BASE_URL=${API_BASE_URL:-/api/v1}

FROM nginx:1.27-alpine AS runtime
COPY infrastructure/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build/web /usr/share/nginx/html
EXPOSE 80
