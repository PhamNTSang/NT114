FROM eclipse-temurin:21-jdk-noble AS builder

WORKDIR /app

COPY build.gradle settings.gradle gradlew ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew --no-daemon downloadRepos

COPY src ./src
RUN ./gradlew --no-daemon installDist

FROM eclipse-temurin:21-jre-alpine

RUN addgroup -S appgroup && adduser -S -G appgroup appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appgroup /app/build/install/hipstershop/ ./

USER appuser
EXPOSE 9555
ENTRYPOINT ["/app/bin/AdService"]
