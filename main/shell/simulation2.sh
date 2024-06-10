#!/bin/bash

latitude=40.741895
longitude=-73.989308
timestamp=$(date +%s)

while true; do
    # Incremento di 10 metri verso nord
    latitude=$(echo "$latitude + 0.000090" | bc)
    timestamp=$(date +%s)

    # Costruzione del JSON
    json="{\"latitude\":\"$latitude\",\"longitude\":\"$longitude\",\"timestamp\":\"$timestamp\"}"

    # Esecuzione del curl
    curl -X POST -H "Content-Type: application/json" -d "$json" http://localhost:9884
    
    echo $json

    sleep 15
done