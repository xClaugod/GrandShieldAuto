from pyspark.sql import SparkSession,DataFrameWriter
from pyspark.sql import functions as F
from pyspark.sql.functions import from_json, col, lit, struct
from pyspark.sql.types import StructType, StringType, DoubleType, TimestampType
import math
import redis
from datetime import datetime
import numpy as np
from sklearn.linear_model import LinearRegression
import os
from dotenv import load_dotenv
from twilio.rest import Client


#account_sid = os.getenv("TWILIO_ACCOUNT_SID")
account_sid = "AC49e2913e6ae4821df43d14c353c5d24f"
print("queto è accont_sid",account_sid)
auth_token = "93b0730201fc1128700f50f418f2bda5"
client = Client(account_sid, auth_token)



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
    schema = StructType().add("latitude", DoubleType()).add("longitude", DoubleType()).add("timestamp", TimestampType())
    
    # Leggere i dati da Redis in un DataFrame separato
    redis_df = spark.read \
        .format("org.apache.spark.sql.redis") \
        .option("table", "*") \
        .schema(schema) \
        .load()
    
    index = redis_df.count()
    
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
                "timestamp": timestamp
            })
            es_df = spark.createDataFrame([
                        {
                            "timestamp": timestamp,
                            "location": {
                                "lat": latitude,
                                "lon": longitude
                            }
                        }
                    ])

            # Invia il DataFrame a Elasticsearch con geo_point mapping
            es_df.write.format("org.elasticsearch.spark.sql")\
                .option("es.resource", "location-data")\
                .option("es.mapping.id", "timestamp") \
                .mode("append")\
                .save()

        return
    
    stolen = False
    all_keys = redis_client.keys("*")
    for key in all_keys: 
        if key.decode('utf-8').startswith("stolen:"):
            stolen = True

    called = False
    all_keys = redis_client.keys("*")
    for key in all_keys: 
        if key.decode('utf-8').startswith("called:"):
            called = True

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
                distance = haversine(first_latitude, first_longitude, latitude, longitude)
                print(f"Distanza: {distance} metri")
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

                if distance > 30 or stolen == True:
                    if not called :
                        call = client.calls.create(
                        url="http://demo.twilio.com/docs/voice.xml",
                        to="+393401413938",
                        from_="+12178639786"
                        )

                        print("call info:",call)
                                            
                        unique_key = "called"
                        redis_client.hset(unique_key, mapping={
                            "called": "True",
                        })

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



                    es_df = spark.createDataFrame([
                                    {
                                        "timestamp": str(last_timestamp.timestamp()),
                                        "location": {
                                            "lat": latitude,
                                            "lon": longitude
                                        }
                                    }
                                ])

                    # Aggiungi un campo geo_point
                    es_df = es_df.withColumn("location", struct(
                        col("latitude").alias("lat"), 
                        col("longitude").alias("lon")
                    ))

                    # Invia il DataFrame a Elasticsearch con geo_point mapping
                    es_df.write.format("org.elasticsearch.spark.sql")\
                        .option("es.resource", "location-data")\
                        .option("es.mapping.id", "timestamp") \
                        .option("es.mapping.include", "timestamp,location") \
                        .mode("append")\
                        .save()

                    es_df = spark.createDataFrame([
                        {
                            "speed": speed,
                            "direction": direction
                        }
                    ])

                    # Invia il DataFrame a Elasticsearch
                    es_df.write.format("org.elasticsearch.spark.sql")\
                        .option("es.resource", "location-data-stats")\
                        .mode("append")\
                        .save()

                    
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
    .config("es.nodes", "elasticsearch") \
    .config("es.port", "9200") \
    .config("es.index.auto.create", "true") \
    .config("es.net.ssl", "false") \
    .config("es.nodes.wan.only", "true") \
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
