FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /app

COPY pom.xml .
RUN mkdir -p /root/.m2 && printf '<settings><mirrors><mirror><id>gcs-maven-central</id><url>https://maven-central.storage-download.googleapis.com/maven2</url><mirrorOf>central</mirrorOf></mirror></mirrors></settings>' > /root/.m2/settings.xml \
    && mvn -B -Daether.connector.basic.threads=2 -DskipTests dependency:go-offline
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
