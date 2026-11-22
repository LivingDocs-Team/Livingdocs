FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml .
RUN log="$(mktemp)" \
    && for delay in 5 15 final; do \
      if mvn -q -B -U dependency:go-offline >"$log" 2>&1; then \
        cat "$log"; rm -f "$log"; break; \
      else \
        status=$?; cat "$log"; \
        if [ "$delay" = final ] || ! grep -Eq 'from/to central \(https://repo\.maven\.apache\.org/maven2/?\).*status code: 429([, ]|$)' "$log"; then \
          exit "$status"; \
        fi; \
        echo "Maven Central HTTP 429, retrying in ${delay}s"; sleep "$delay"; \
      fi; \
    done
COPY src ./src
RUN mvn -q -B package -DskipTests

FROM eclipse-temurin:21-jre
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/target/github-integration-service-*.jar app.jar
EXPOSE 8082
ENTRYPOINT ["java", "-jar", "app.jar"]
