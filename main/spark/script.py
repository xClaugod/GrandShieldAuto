from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import from_json, col, lit
from pyspark.sql.types import StructType, StringType, DoubleType, TimestampType
from twilio.rest import Client
from sklearn.linear_model import LinearRegression
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from datetime import datetime
import numpy as np
import math
import redis
import os
import re


load_dotenv()

# URL di Elasticsearch
es_host = "http://157.230.21.212:9200"
es_index_name = "first-location"
es_current_location_index = "current-location"
es_current_stats_index = "current-stats"

# ES Mapping config to handle map data
mapping_location = {
    "mappings": {
        "properties": {
            "timestamp": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"},
            "location": {"type": "geo_point"}
        }
    }
}

# ES Mapping config to handle stats data
mapping_stats = {
    "mappings": {
        "properties": {
            "timestamp": {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"},
            "speed": {"type": "float"},
            "direction": {"type": "keyword"}
        }
    }
}

es = Elasticsearch(es_host)

# Elasticsearch Initialization with mapping
if not es.indices.exists(index=es_index_name):
    es.indices.create(index=es_index_name, body=mapping_location)
if not es.indices.exists(index=es_current_location_index):
    es.indices.create(index=es_current_location_index, body=mapping_location)
if not es.indices.exists(index=es_current_stats_index):
    es.indices.create(index=es_current_stats_index, body=mapping_stats)



# Loading data to use TWILIO
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token)
phone_number = os.getenv("PHONE_NUMBER")
twilio_number = os.getenv("TWILIO_NUMBER")

# Update current index
def update_elastic_data(es, index, data, id):
    es.index(index=index, id=id, body=data)

# Haversine function to evaluate distance between 2 geo point
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

# Function to convert m/ps to km/ph
def mps_to_kmph(mps):
    kmph = mps * 3.6
    return kmph

# Linear regression to predict car direction
def calculate_direction(history):
    if len(history) < 2:
        return None  # Linear Regression need at least 2 point
    
    model = LinearRegression()

    # Taking data saved into "history"
    timestamps = np.array([datetime.strptime(str(record[2]),"%Y-%m-%dT%H:%M:%S.%fZ").timestamp() for record in history]).reshape(-1, 1)
    latitudes = np.array([record[0] for record in history]).reshape(-1, 1)
    longitudes = np.array([record[1] for record in history]).reshape(-1, 1)

    lat_reg = model.fit(timestamps, latitudes)
    lon_reg = model.fit(timestamps, longitudes)

    lat_slope = lat_reg.coef_[0][0] 
    lon_slope = lon_reg.coef_[0][0]  

    angle = math.atan2(lon_slope, lat_slope)
    degree = math.degrees(angle)

    if degree >= -22.5 and degree < 22.5:
        return 'N'
    elif degree >= 22.5 and degree < 67.5:
        return 'NE'
    elif degree >= 67.5 and degree < 112.5:
        return 'E'
    elif degree >= 112.5 and degree < 157.5:
        return 'SE'
    elif degree >= 157.5 or degree < -157.5:
        return 'S'
    elif degree >= -157.5 and degree < -112.5:
        return 'SW'
    elif degree >= -112.5 and degree < -67.5:
        return 'W'
    elif degree >= -67.5 and degree < -22.5:
        return 'NW'

# New position trigger
def process_new_data(input_df, epoch_id):
    if input_df.isEmpty():
        return
    
    # Schema definition for redis data
    schema = StructType().add("latitude", DoubleType()).add("longitude", DoubleType()).add("timestamp", TimestampType())

    index = len(redis_client.keys("*"))

    print(f"countIndex: {index}")
    
    # If there are 0 elements we are evaluating first position
    if index == 0:
        if not input_df.isEmpty():
            info = input_df.select("latitude", "longitude", "timestamp").first()
            latitude = info["latitude"]
            longitude = info["longitude"]
            timestamp = info["timestamp"]
            print(f"ho letto {latitude},{longitude},{timestamp}")
            if latitude is None or longitude is None or timestamp is None: return
            # Creating unique key to save data into redis
            unique_key = f"{latitude}:{longitude}"
            # Data formatting
            formatted_timestamp = datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            print(f"Nessuna coordinata iniziale trovata in Redis, dunque salvataggio della coordinata su Redis: {latitude}, {longitude}, {formatted_timestamp}")
            # Storing into redis
            redis_client.hset(f"{index}:{unique_key}", mapping={
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": str(formatted_timestamp)
            })


            # Formatting map data to Elasticsearch
            es_data = {
                "timestamp" : formatted_timestamp,
                "location" : {
                    "lat" : latitude,
                    "lon" : longitude
                }
            }

            # Sending data to Elasticsearch
            update_elastic_data(es, es_index_name, es_data, 1)
            update_elastic_data(es, es_current_location_index, es_data, 2)

            # Formatting stats data to Elasticsearch
            es_data_stats = {
                "timestamp": formatted_timestamp,
                "speed": 0,
                "direction": "N",
                "stolen": False
            }

            # Sending data to Elasticsearch
            update_elastic_data(es, es_current_stats_index, es_data_stats, 3)

        return

    # Boolean variable which represent car status. It will be true if car is moving (so it's stolen)
    stolen = False

    # Retrieving car status from redis 
    all_keys = redis_client.keys("*")
    for key in all_keys: 
        # if "stolen" row is find
        if key.decode('utf-8').startswith("stolen"): 
            stolen = True 

    # Retrieving row "called" from redis to know if user's phone had beeing called
    called = False
    all_keys = redis_client.keys("*")
    for key in all_keys: 
        if key.decode('utf-8').startswith("called"):
            called = True

    # Taking all coordinates send by car. First one will represent parking location
    all_keys = redis_client.keys("*")
    numeric_keys = sorted([key for key in all_keys if re.match(r"^[0-9]+:", key.decode('utf-8'))], key=lambda x: int(x.decode('utf-8').split(':')[0]))
    matching_hashes = []
    for key in numeric_keys:
        key_str = key.decode('utf-8')
        # Check if key starts with a number (don't look for "stolen" and "called" rows)
        if re.match(r"^[0-9]", key_str):
            # Retrieving data
            hash_values = redis_client.hgetall(key)
            # From byte to string
            decoded_values = {k.decode('utf-8'): v.decode('utf-8') for k, v in hash_values.items()}
            matching_hashes.append((key.decode('utf-8'), decoded_values))

    # Index value will be used to take last known coordinate and evaluate distance,speed matching with processed coordinate
    index = 0

    # All the coordinates will be saved into a "history" vector
    if matching_hashes:
        history = []
        for record in matching_hashes:
            index+=1
            history.append((
                float(record[1]['latitude']),
                float(record[1]['longitude']),
                str(record[1]['timestamp'])
            ))


    # Evaluating and comparison between first,last coordinate and the processed one
    # First coordinate will be used to evaluate if car is moving (distance)
    # Last coordinate will be used to evaluate car speed

    rows = input_df.select("latitude", "longitude", "timestamp").collect()
    if rows:
        for row in rows:

            # Processing data
            latitude = row['latitude']
            longitude = row['longitude']
            unix_timestamp = float(row['timestamp'])

            # First coordinates
            first_latitude, first_longitude, first_timestamp = history[0]
            unix_first_timestamp = datetime.strptime(first_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
            unix_first_timestamp = unix_first_timestamp.timestamp()

            # Distance evaluation
            distance = haversine(first_latitude, first_longitude, latitude, longitude) 

            print(f"Distance: {distance} m")

            # Last saved coordinates
            last_latitude,last_longitude,last_timestamp = history[index-1]
            unix_last_timestamp = datetime.strptime(last_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
            unix_last_timestamp = unix_last_timestamp.timestamp()

            # Speed evaluation
            time_diff = (datetime.fromtimestamp(unix_timestamp) - datetime.fromtimestamp(unix_last_timestamp)).total_seconds()
            speed = distance / time_diff if time_diff > 0 else 0
            speed_kmh = mps_to_kmph(speed)
            print(f"Speed: {speed_kmh} km/h")

            formatted_timestamp = datetime.fromtimestamp(unix_timestamp).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

            # Update history
            history.append((latitude, longitude, formatted_timestamp))

            # Predicting direction
            direction = calculate_direction(history)
            print(f"Direction: {direction}")

             # Storing new coordinate into redis
            print(f"Salvataggio della coordinata su Redis: {latitude}, {longitude}")
            
            unique_key = f"{latitude}:{longitude}"
            
            redis_client.hset(f"{index}:{unique_key}", mapping={
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": str(formatted_timestamp)
            })

            # Sending new coordinate to Elasticsearch
            es_data = {
                    "timestamp" : formatted_timestamp,
                    "location" : {
                        "lat" : latitude,
                        "lon" : longitude
                    }
                }

            update_elastic_data(es, es_current_location_index, es_data, 2)

            # Sending updated speed and direction to Elasticsearch
            es_data_stats = {
                "timestamp": formatted_timestamp,
                "speed": speed_kmh,
                "direction": direction,
                "stolen": stolen
            }
            update_elastic_data(es, es_current_stats_index, es_data_stats, 3)

            index += 1

            # Check to alert user
            if distance > 30 or stolen == True:

                # if call hasn't been taken already
                if not called :
                    # Call user
                    call = client.calls.create(
                    url="http://demo.twilio.com/docs/voice.xml",
                    to= phone_number,
                    from_= twilio_number
                    )

                    print("call info:",call)
                                        
                    # Storing into redis call action
                    unique_key = "called"
                    redis_client.hset(unique_key, mapping={
                        "called": "True",
                    })

               
                # If car was not already stolen, storing steal action into redis
                if not stolen:
                    unique_key = "stolen"
                    
                    redis_client.hset(unique_key, mapping={
                        "stolen": "True",
                    })

    else:
        print("Batch contain no coordinates")


# Spark session with redis config
spark = SparkSession.builder \
    .appName("KafkaSparkStreaming") \
    .getOrCreate()

# Redis client config
redis_client = redis.StrictRedis(host='redis-host', port=6379, db=0)

# Subscribing spark to kafka topic "locations"
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "locations") \
    .load()

# Kafka data schema
schema = StructType() \
    .add("latitude", StringType()) \
    .add("longitude", StringType()) \
    .add("timestamp", StringType())

# Casting data
df = df.selectExpr("CAST(value AS STRING) as json") \
    .select(from_json(col("json"), schema).alias("data")) \
    .select("data.*") \
    .withColumn("value", F.concat(col("latitude"), lit(","), col("longitude"), lit(","), col("timestamp"))) 

df = df.withColumn("latitude", col("latitude").cast(DoubleType())) \
       .withColumn("longitude", col("longitude").cast(DoubleType())) \
       .withColumn("timestamp", col("timestamp"))

# When a new data comes into kafka location topic it will be processed by process_new_data
df.writeStream \
    .foreachBatch(process_new_data) \
    .start()

spark.streams.awaitAnyTermination()