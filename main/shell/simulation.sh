#!/bin/bash

latitude=41.66704
longitude=-72.66648
timestamp=$(date +%s)

# Definire gli incrementi corrispondenti a 20 metri nelle direzioni cardinali
lat_increment=0.000180
lon_increment=0.000260

while true; do
    # Generare un numero casuale tra 1 e 4 per determinare la direzione
    direction=$((1 + RANDOM % 4))

    case $direction in
        1)
            # Nord
            latitude=$(echo "$latitude + $lat_increment" | bc)
            ;;
        2)
            # Sud
            latitude=$(echo "$latitude - $lat_increment" | bc)
            ;;
        3)
            # Est
            longitude=$(echo "$longitude + $lon_increment" | bc)
            ;;
        4)
            # Ovest
            longitude=$(echo "$longitude - $lon_increment" | bc)
            ;;
    esac

    timestamp=$(date +%s)

    # Costruzione del JSON
    json="{\"latitude\":\"$latitude\",\"longitude\":\"$longitude\",\"timestamp\":\"$timestamp\"}"

    # Esecuzione del curl
    curl -X POST -H "Content-Type: application/json" -d "$json" http://localhost:9884

    echo $json

    sleep 15
done
