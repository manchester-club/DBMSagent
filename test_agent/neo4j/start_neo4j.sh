#!/bin/bash
# Neo4j启动脚本

cd "$(dirname "$0")/neo4j-server"

export NEO4J_HOME=$(pwd)
export NEO4J_CONF=$(pwd)/conf
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

./bin/neo4j "$@"



