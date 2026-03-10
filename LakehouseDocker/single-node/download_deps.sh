#!/usr/bin/env bash
set -o pipefail

mkdir -p lib opt plugins hadoop-uber

# Flink connectors
curl -fL -o "lib/flink-faker-0.5.3.jar" "https://github.com/knaufk/flink-faker/releases/download/v0.5.3/flink-faker-0.5.3.jar"
curl -fL -o "lib/fluss-flink-1.20-0.9.0-incubating.jar" "https://repo1.maven.org/maven2/org/apache/fluss/fluss-flink-1.20/0.9.0-incubating/fluss-flink-1.20-0.9.0-incubating.jar"
curl -fL -o "lib/paimon-flink-1.20-1.3.1.jar" "https://repo1.maven.org/maven2/org/apache/paimon/paimon-flink-1.20/1.3.1/paimon-flink-1.20-1.3.1.jar"

# Flink s3 plugin
curl -fL -o "plugins/flink-s3-fs-hadoop-1.20.3.jar" "https://repo1.maven.org/maven2/org/apache/flink/flink-s3-fs-hadoop/1.20.3/flink-s3-fs-hadoop-1.20.3.jar"

# Fluss lake plugin
curl -fL -o "lib/fluss-lake-paimon-0.9.0-incubating.jar" "https://repo1.maven.org/maven2/org/apache/fluss/fluss-lake-paimon/0.9.0-incubating/fluss-lake-paimon-0.9.0-incubating.jar"
curl -fL -o "lib/fluss-fs-s3-0.9.0-incubating.jar" "https://repo1.maven.org/maven2/org/apache/fluss/fluss-fs-s3/0.9.0-incubating/fluss-fs-s3-0.9.0-incubating.jar"

# Paimon bundle jar
curl -fL -o "lib/paimon-bundle-1.3.1.jar" "https://repo.maven.apache.org/maven2/org/apache/paimon/paimon-bundle/1.3.1/paimon-bundle-1.3.1.jar"

# Hadoop 2.x uber jar (loaded via HADOOP_CLASSPATH AFTER fluss-fs-s3 to avoid version conflict)
curl -fL -o "hadoop-uber/flink-shaded-hadoop-2-uber-2.8.3-10.0.jar" "https://repo.maven.apache.org/maven2/org/apache/flink/flink-shaded-hadoop-2-uber/2.8.3-10.0/flink-shaded-hadoop-2-uber-2.8.3-10.0.jar"

# AWS S3 support
curl -fL -o "lib/paimon-s3-1.3.1.jar" "https://repo.maven.apache.org/maven2/org/apache/paimon/paimon-s3/1.3.1/paimon-s3-1.3.1.jar"

# Tiering service
curl -fL -o "opt/fluss-flink-tiering-0.9.0-incubating.jar" "https://repo1.maven.org/maven2/org/apache/fluss/fluss-flink-tiering/0.9.0-incubating/fluss-flink-tiering-0.9.0-incubating.jar"
