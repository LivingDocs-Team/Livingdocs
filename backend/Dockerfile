FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /app

COPY pom.xml .
RUN mvn -B -Dmaven.wagon.http.retryHandler.count=5 -Daether.transport.http.retryHandler.count=5 -DskipTests dependency:go-offline

COPY src ./src

RUN mvn -B -Dmaven.wagon.http.retryHandler.count=5 -Daether.transport.http.retryHandler.count=5 -DskipTests package

FROM eclipse-temurin:21-jre

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /app/target/*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
