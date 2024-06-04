from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import from_json, col, lit
from pyspark.sql.types import StructType, StringType, DoubleType, TimestampType
import math
import redis
from datetime import datetime
import numpy as np
from sklearn.linear_model import LinearRegression

# Funzione per calcolare la distanza tra due punti GPS usando la formula dell'haversine
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # raggio della Terra in metri
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

# Funzione per calcolare la direzione basata su regressione lineare
def calculate_direction(history):
    if len(history) < 2:
        return None  # Non è possibile calcolare la direzione con meno di 2 punti
    
    timestamps = np.array([record[2].timestamp() for record in history]).reshape(-1, 1)
    latitudes = np.array([record[0] for record in history])
    longitudes = np.array([record[1] for record in history])

    lat_reg = LinearRegression().fit(timestamps, latitudes)
    lon_reg = LinearRegression().fit(timestamps, longitudes)

    lat_slope = lat_reg.coef_[0]
    lon_slope = lon_reg.coef_[0]

    angle = math.atan2(lon_slope, lat_slope)
    degree = math.degrees(angle)

    if degree >= -22.5 and degree < 22.5:
        return 'north'
    elif degree >= 22.5 and degree < 67.5:
        return 'northeast'
    elif degree >= 67.5 and degree < 112.5:
        return 'east'
    elif degree >= 112.5 and degree < 157.5:
        return 'southeast'
    elif degree >= 157.5 or degree < -157.5:
        return 'south'
    elif degree >= -157.5 and degree < -112.5:
        return 'southwest'
    elif degree >= -112.5 and degree < -67.5:
        return 'west'
    elif degree >= -67.5 and degree < -22.5:
        return 'northwest'

# Calcolare la distanza e segnalarla se supera i 30 metri
def process_new_data(input_df, epoch_id):
    print("sono dentro process_new_data", input_df)
    schema = StructType().add("latitude", DoubleType()).add("longitude", DoubleType()).add("timestamp", TimestampType())
    
    # Leggere i dati da Redis in un DataFrame separato
    redis_df = spark.read \
        .format("org.apache.spark.sql.redis") \
        .option("table", "*") \
        .schema(schema) \
        .load()
    
    index = redis_df.count()
    print("L'indice è:", index)
    
    if index == 0:
        if not input_df.isEmpty():
            info = input_df.select("latitude", "longitude", "timestamp").first()
            latitude = info["latitude"]
            longitude = info["longitude"]
            timestamp = info["timestamp"]
            print(f"Nessuna coordinata iniziale trovata in Redis, dunque salvataggio della coordinata su Redis: {latitude}, {longitude}, {timestamp}")
            # Creare una chiave unica per ogni coppia di coordinate
            unique_key = f"{latitude}:{longitude}"
            # Salvare la coordinata su Redis
            redis_client.hset(f"{index}:{unique_key}", mapping={
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": str(timestamp)
            })

        return
    
    # Estrarre l'indice dalla chiave
    all_keys = redis_client.keys("*")
    matching_hashes = []
    for key in all_keys:
        # Controlla se la chiave inizia con il prefisso desiderato
        if key.decode('utf-8').startswith("0:"):
            # Recupera tutti i campi e valori dell'hash
            hash_values = redis_client.hgetall(key)
            
            # Converti i valori da byte a stringa
            decoded_values = {k.decode('utf-8'): v.decode('utf-8') for k, v in hash_values.items()}
            matching_hashes.append((key.decode('utf-8'), decoded_values))
    
    if matching_hashes:
        history = []
        for record in matching_hashes:
            print("Prova1->",float(record[1]['timestamp']))
            print("Prova2->",datetime.fromtimestamp(float(record[1]['timestamp'])))
            history.append((
                float(record[1]['latitude']),
                float(record[1]['longitude']),
                datetime.fromtimestamp(float(record[1]['timestamp']))
            ))

    rows = input_df.select("latitude", "longitude", "timestamp").collect()

    if rows:
        for row in rows:
            latitude = row['latitude']
            longitude = row['longitude']
            last_timestamp = row['timestamp']

            if history:
                first_latitude, first_longitude, first_timestamp = history[0]
                print(f"allora sto vedendo questa cosa,{first_latitude}, {first_longitude}, {latitude}, {longitude}")
                distance = haversine(first_latitude, first_longitude, latitude, longitude)
                date_time_obj = datetime.strptime( str(history[0][2]), '%Y-%m-%d %H:%M:%S')
                first_time = date_time_obj
                last_timestamp = datetime.fromtimestamp(float(last_timestamp))
                time_diff = (last_timestamp - first_time).total_seconds()
                speed = distance / time_diff if time_diff > 0 else 0
                print(f"Velocità: {speed} m/s")

                history.append((latitude, longitude, last_timestamp))

                # Predizione della direzione
                direction = calculate_direction(history)
                print(f"Direzione: {direction}")

                if distance > 30:
                    print(f"Salvataggio della coordinata su Redis: {latitude}, {longitude}")
                    
                    unique_key = f"{latitude}:{longitude}"
                    
                    redis_client.hset(f"{index}:{unique_key}", mapping={
                        "latitude": latitude,
                        "longitude": longitude,
                        "timestamp": str(last_timestamp.timestamp())
                    })

                    unique_key = "stolen"
                    
                    redis_client.hset(unique_key, mapping={
                        "stolen": "True",
                    })
                    index += 1
            else:
                print(f"Nessuna history trovata, salvataggio della coordinata iniziale su Redis: {latitude}, {longitude}, {last_timestamp}")
                unique_key = f"{latitude}:{longitude}"
                redis_client.hset(f"{index}:{unique_key}", mapping={
                    "latitude": latitude,
                    "longitude": longitude,
                    "timestamp": str(last_timestamp.timestamp())
                })
                history.append((latitude, longitude, timestamp))
    else:
        print("Nessuna coordinata trovata nel batch")

# Creare una sessione Spark con le configurazioni per Redis
spark = SparkSession.builder \
    .appName("KafkaSparkStreaming") \
    .config("spark.redis.host", "redis-host") \
    .config("spark.redis.port", "6379") \
    .getOrCreate()

# Configurazione del client Redis in Python
redis_client = redis.StrictRedis(host='redis-host', port=6379, db=0)

df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "locations") \
    .load()

# Schema dei dati
schema = StructType() \
    .add("latitude", StringType()) \
    .add("longitude", StringType()) \
    .add("timestamp", StringType())

# Trasformare i dati
df = df.selectExpr("CAST(value AS STRING) as json") \
    .select(from_json(col("json"), schema).alias("data")) \
    .select("data.*") \
    .withColumn("value", F.concat(col("latitude"), lit(","), col("longitude"), lit(","), col("timestamp"))) 
   # .withColumn("timestamp", col("timestamp").cast(TimestampType()))

# Converti le coordinate in DoubleType per il calcolo della distanza
df = df.withColumn("latitude", col("latitude").cast(DoubleType())) \
       .withColumn("longitude", col("longitude").cast(DoubleType())) \
        .withColumn("timestamp" , col("timestamp"))

df.writeStream \
    .foreachBatch(process_new_data) \
    .start()

spark.streams.awaitAnyTermination()
