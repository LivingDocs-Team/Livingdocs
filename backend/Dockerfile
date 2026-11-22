# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /app

COPY pom.xml .
COPY src ./src
RUN --mount=type=cache,id=livingdocs-maven,target=/root/.m2/repository,sharing=locked <<'MAVEN_BUILD'
set -eu
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
for delay in 5 10 20 final; do
    if mvn -B -ntp -U -Dstyle.color=never -DskipTests package >"$log" 2>&1; then
        cat "$log"
        exit 0
    else
        status=$?
    fi
    cat "$log"
    if [ "$delay" = final ] || ! grep -Eq 'from/to central \(https://repo\.maven\.apache\.org/maven2/?\).*status code: 429([, ]|$)' "$log"; then
        exit "$status"
    fi
    echo "Maven Central HTTP 429, retrying in $delay seconds"
    sleep "$delay"
done
MAVEN_BUILD

FROM eclipse-temurin:21-jre

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /app/target/*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
