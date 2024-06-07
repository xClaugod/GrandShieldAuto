#!/bin/bash

latitude=41.66704
longitude=-72.66648
timestamp=$(date +%s)

while true; do
    # Incremento di 10 metri verso sud
    latitude=$(echo "$latitude + 0.000090" | bc)
    timestamp=$(date +%s)

    # Costruzione del JSON
    json="{\"latitude\":\"$latitude\",\"longitude\":\"$longitude\",\"timestamp\":\"$timestamp\"}"

    # Esecuzione del curl
    curl -X POST -H "Content-Type: application/json" -d "$json" http://localhost:9884
    
    echo $json

    sleep 15
done
