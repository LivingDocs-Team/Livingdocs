# syntax=docker/dockerfile:1.7
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app

ENV MAVEN_OPTS="-Dmaven.wagon.http.retryHandler.count=5 \
 -Dmaven.wagon.http.retryHandler.requestSentEnabled=true \
 -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
 -Dhttp.keepAlive=false"

COPY settings.xml /root/.m2/settings.xml
 COPY pom.xml .
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B dependency:resolve dependency:resolve-plugins \
    || (sleep 10 && mvn -B dependency:resolve dependency:resolve-plugins)

COPY src ./src
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B package -DskipTests

FROM eclipse-temurin:21-jre
# phần runtime giữ nguyên