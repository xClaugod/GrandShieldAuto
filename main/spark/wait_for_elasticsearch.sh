#!/bin/bash
set -e

host="$1"
shift
cmd="$@"

until curl -fsSL "$host/_cluster/health"; do
  >&2 echo "Elasticsearch is unavailable - sleeping"
  sleep 5
done

>&2 echo "Elasticsearch is up - executing command"
exec $cmd
