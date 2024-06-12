#!/bin/bash

# Funzione per calcolare gli incrementi
calculate_increment() {
    local start=$1
    local end=$2
    local duration=$3
    echo "scale=12; ($end - $start) / ($duration / 10)" | bc
}

# Coordinate iniziali e finali
lat_start=37.584232
lon_start=15.142237

lat1=37.586074
lon1=15.141722

lat2=37.586145 
lon2=15.142108

lat3=37.584911 
lon3=15.144518

lat4=37.583895
lon4=15.142448

# Calcolo degli incrementi
lat_increment1=$(calculate_increment $lat_start $lat1 60)
lon_increment1=$(calculate_increment $lon_start $lon1 60)

lat_increment2=$(calculate_increment $lat1 $lat2 20)
lon_increment2=$(calculate_increment $lon1 $lon2 20)

lat_increment3=$(calculate_increment $lat2 $lat3 60)
lon_increment3=$(calculate_increment $lon2 $lon3 60)

lat_increment4=$(calculate_increment $lat3 $lat4 30)
lon_increment4=$(calculate_increment $lon3 $lon4 30)

lat_increment5=$(calculate_increment $lat4 $lat_start 10)
lon_increment5=$(calculate_increment $lon4 $lon_start 10)

# Funzione per inviare i dati
send_data() {
    local lat=$1
    local lon=$2
    local timestamp=$(date +%s)
    local json="{\"latitude\":\"$lat\",\"longitude\":\"$lon\",\"timestamp\":\"$timestamp\"}"
    curl -X POST -H "Content-Type: application/json" -d "$json" http://localhost:9884
    echo $json
}

# Movimento tra le coordinate
move() {
    local lat=$1
    local lon=$2
    local lat_increment=$3
    local lon_increment=$4
    local steps=$5

    for ((i=0; i<steps; i++)); do
        lat=$(echo "$lat + $lat_increment" | bc)
        lon=$(echo "$lon + $lon_increment" | bc)
        send_data $lat $lon
        sleep 10
    done
}

# Eseguire i movimenti
latitude=$lat_start
longitude=$lon_start

for((i=0;i<3;i++)); do
    lat=$(echo "$lat_start" | bc)
    lon=$(echo "$lon_start" | bc)
    send_data $lat_start $lon_start
    sleep 10
done

move $latitude $longitude $lat_increment1 $lon_increment1 6
move $lat1 $lon1 $lat_increment2 $lon_increment2 2
move $lat2 $lon2 $lat_increment3 $lon_increment3 6
move $lat3 $lon3 $lat_increment4 $lon_increment4 3
move $lat4 $lon4 $lat_increment5 $lon_increment5 1
