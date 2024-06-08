from pyspark.sql import SparkSession,DataFrameWriter
from pyspark.sql import functions as F
from pyspark.sql.functions import from_json, col, lit, struct,date_format
from pyspark.sql.types import StructType, StringType, DoubleType, TimestampType
import math
import redis
from datetime import datetime
import numpy as np
from sklearn.linear_model import LinearRegression
import os
from dotenv import load_dotenv
from twilio.rest import Client
import requests
import json
from elasticsearch import Elasticsearch
import time



# Configura l'URL di Elasticsearch
es_host = "http://157.230.21.212:9200"
es_index_name = "location-data"

# Definisci il mapping
mapping = {
    "mappings": {
        "properties": {
            "timestamp": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"},
            "location": {"type": "geo_point"}
        }
    }
}

es = Elasticsearch(es_host)
# Inizializza Elasticsearch con il mapping
if not es.indices.exists(index=es_index_name):
    es.indices.create(index=es_index_name, body=mapping)


load_dotenv()

account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token)
phone_number = os.getenv("PHONE_NUMBER")
twilio_number = os.getenv("TWILIO_NUMBER")



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
    
    model = LinearRegression()

    timestamps = np.array([datetime.strptime(str(record[2]),"%Y-%m-%d %H:%M:%S").timestamp() for record in history]).reshape(-1, 1)
    latitudes = np.array([record[0] for record in history]).reshape(-1, 1)
    longitudes = np.array([record[1] for record in history]).reshape(-1, 1)

    lat_reg = model.fit(timestamps, latitudes)
    lon_reg = model.fit(timestamps, longitudes)

    lat_slope = lat_reg.coef_[0][0]  # Corrected to access the slope value
    lon_slope = lon_reg.coef_[0][0]  # Corrected to access the slope value

    '''
    print(f"prima della predizione{lat_slope},{lon_slope}")

    predict = model.predict([[lat_reg.coef_[0]],[lon_reg.coef_[0]]])

    print(f"predizione:",predict)
    angle = math.atan2(predict[0], predict[1])
    degree = math.degrees(angle)
    if degree >= -22.5 and degree < 22.5:
            print("predict north") 
    elif degree >= 22.5 and degree < 67.5:
        print("predict northeast") 
    elif degree >= 67.5 and degree < 112.5:
        print("predict east") 
    elif degree >= 112.5 and degree < 157.5:
        print("predict southeast") 
    elif degree >= 157.5 or degree < -157.5:
        print("predict south") 
    elif degree >= -157.5 and degree < -112.5:
        print("predict southwest") 
    elif degree >= -112.5 and degree < -67.5:
        print("predict west") 
    elif degree >= -67.5 and degree < -22.5:
        print("predict northwest") 
    '''

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
    if input_df.isEmpty():
        return
    schema = StructType().add("latitude", DoubleType()).add("longitude", DoubleType()).add("timestamp", TimestampType())
    
    # Leggere i dati da Redis in un DataFrame separato
    redis_df = spark.read \
        .format("org.apache.spark.sql.redis") \
        .option("table", "*") \
        .schema(schema) \
        .load()
    
    # Conto gli elementi salvati
    index = redis_df.count()
    
    # Se non ho nulla vorrà dire che sto processando la coordinata della posizione iniziale
    if index == 0:
        if not input_df.isEmpty():
            info = input_df.select("latitude", "longitude", "timestamp").first()
            latitude = info["latitude"]
            longitude = info["longitude"]
            timestamp = info["timestamp"]
            print(f"ho letto {latitude},{longitude},{timestamp}")
            if latitude is None or longitude is None or timestamp is None: return
            # Creare una chiave unica per ogni coppia di coordinate
            unique_key = f"{latitude}:{longitude}"
            formatted_timestamp = datetime.fromtimestamp(int(timestamp))
            print(f"Nessuna coordinata iniziale trovata in Redis, dunque salvataggio della coordinata su Redis: {latitude}, {longitude}, {formatted_timestamp}")
            # Salvare la coordinata su Redis
            redis_client.hset(f"{index}:{unique_key}", mapping={
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": str(formatted_timestamp)
            })
            '''
                        # Creo i dati da mandare ad Elasticsearch
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
            '''

            es_data = {
                "timestamp" : formatted_timestamp.isoformat() + "Z",
                "location" : {
                    "lat" : latitude,
                    "lon" : longitude
                }
            }

            es.index(index=es_index_name, body=es_data, ignore=400)


        return
    
    stolen = False

    # Verifico se la macchina era in movimento cercando stolen su redis
    all_keys = redis_client.keys("*")
    for key in all_keys: 
        if key.decode('utf-8').startswith("stolen"):
            stolen = True

    # Verifico se già ho effettuato la chiamata all'utente cercando called su redis
    called = False
    all_keys = redis_client.keys("*")
    for key in all_keys: 
        if key.decode('utf-8').startswith("called"):
            called = True

    # Estraggo la prima coordinata gps mandata dall'auto (posizione del parcheggio)
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
                str(record[1]['timestamp'])
            ))

# Gestione della coordinata che è arrivata dopo quella iniziale

    rows = input_df.select("latitude", "longitude", "timestamp").collect()
    if rows:
        for row in rows:
            latitude = row['latitude']
            longitude = row['longitude']
            unix_timestamp = float(row['timestamp'])


            print(f"ho letto {latitude},{longitude},{unix_timestamp}")


            # Dati delle coordinate iniziali
            first_latitude, first_longitude, first_timestamp = history[0]

            unix_first_timestamp = datetime.strptime(first_timestamp, "%Y-%m-%d %H:%M:%S")
            unix_first_timestamp = unix_first_timestamp.timestamp()

            print(f"li confronto con {first_latitude},{first_longitude},{unix_first_timestamp}")
            # Misuro la distanza
            distance = haversine(first_latitude, first_longitude, latitude, longitude) 
            print(f"Distanza: {distance} metri")

            # Calcolo la velocità
            time_diff = (datetime.fromtimestamp(unix_timestamp) - datetime.fromtimestamp(unix_first_timestamp)).total_seconds()
            speed = distance / time_diff if time_diff > 0 else 0
            print(f"Velocità: {speed} m/s")

            formatted_timestamp = datetime.fromtimestamp(int(unix_timestamp))

            history.append((latitude, longitude, formatted_timestamp))

            # Predizione della direzione
            direction = calculate_direction(history)
            print(f"Direzione: {direction}")

            #Se la distanza supera i 30 metri o se la macchina risulta già rubata, aggiorno la posizione della mappa
            #ed effettuo la chiamata all'utente nel caso in cui non l'avessi già fatta
            print(f"stolen risulta: {stolen}")
            if distance > 30 or stolen == True:
                if not called :
                    # Chiamata
                    call = client.calls.create(
                    url="http://demo.twilio.com/docs/voice.xml",
                    to= phone_number,
                    from_= twilio_number
                    )

                    print("call info:",call)
                                        
                    # Conservo su redis l'annotazione per aver effettuato la chiamata
                    unique_key = "called"
                    redis_client.hset(unique_key, mapping={
                        "called": "True",
                    })

                # Salvo la nuova posizione su redis
                print(f"Salvataggio della coordinata su Redis: {latitude}, {longitude}")
                
                unique_key = f"{latitude}:{longitude}"
                
                redis_client.hset(f"{index}:{unique_key}", mapping={
                    "latitude": latitude,
                    "longitude": longitude,
                    "timestamp": str(formatted_timestamp)
                })

                # Se non risultava ancora rubata, indico che lo è salvando l'annotazione stolen su redis
                if not stolen:
                    unique_key = "stolen"
                    
                    redis_client.hset(unique_key, mapping={
                        "stolen": "True",
                    })

                # Invio la posizione anche ad Elasticsearch per aggiornare il puntatore sulla mappa gps
                '''
                es_df = spark.createDataFrame([
                                {
                                    "timestamp": formatted_timestamp,
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
                ''' 
                es_data = {
                    "timestamp" : formatted_timestamp.isoformat() + "Z",
                    "location" : {
                        "lat" : latitude,
                        "lon" : longitude
                    }
                }

                es.index(index=es_index_name, body=es_data, ignore=400)

                # Invio ad Elasticsearch anche i dati calcolati in precedenza di velocità e direzione predetta
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
'''
# Converti le coordinate in DoubleType per il calcolo della distanza
df = df.withColumn("latitude", col("latitude").cast(DoubleType())) \
       .withColumn("longitude", col("longitude").cast(DoubleType())) \
       .withColumn("timestamp", col("timestamp").cast("timestamp"))

df = df.withColumn("timestamp", date_format(col("timestamp"), "yyyy-MM-dd'T'HH:mm:ss.SSSZ"))
'''
df = df.withColumn("latitude", col("latitude").cast(DoubleType())) \
       .withColumn("longitude", col("longitude").cast(DoubleType())) \
       .withColumn("timestamp", col("timestamp"))
# Ogni nuovo dato presente su kafka al topic locations viene processato da process_new_data
df.writeStream \
    .foreachBatch(process_new_data) \
    .start()


spark.streams.awaitAnyTermination()