from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, lit, split
from pyspark.sql.types import StructType, StringType, DoubleType
import math
from pyspark.sql import functions as F
import redis

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

# Calcolare la distanza e segnalarla se supera i 30 metri
def process_new_data(input_df, epoch_id):
    print("sono dengtro peroces_",input_df)
    schema = StructType().add("latitude", DoubleType()).add("longitude", DoubleType())
    
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
            info = input_df.select("latitude", "longitude").first()
            latitude = info["latitude"]
            longitude = info["longitude"]
            print(f"Nessuna coordinata iniziale trovata in Redis, dunque salvataggio della coordinata su Redis: {latitude}, {longitude}")
            # Creare una chiave unica per ogni coppia di coordinate
            unique_key = f"{latitude}:{longitude}"
            # Salvare la coordinata su Redis
            redis_client.hset(f"{index}:{unique_key}", mapping={
            "latitude": latitude,
            "longitude": longitude
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
    
    if matching_hashes[0] :
        first_record = matching_hashes[0]    
        first_latitude = first_record[1]['latitude']
        first_longitude = first_record[1]['longitude']
        
        print("La prima latitudine è:", first_latitude)
        print("La prima longitudine è:", first_longitude)

        if key.decode('utf-8').startswith("stolen:"):
        # Recupera tutti i campi e valori dell'hash
            hash_values = redis_client.hgetall(key)
            
            # Converti i valori da byte a stringa
            decoded_values = {k.decode('utf-8'): v.decode('utf-8') for k, v in hash_values.items()}
            matching_hashes.append((key.decode('utf-8'), decoded_values))

    stolen = False

    if matching_hashes[0] :
        stolen = True
    rows = input_df.select("latitude", "longitude").collect()

    
    if rows:
        for row in rows:
            latitude = row['latitude']
            longitude = row['longitude']
            print(f"Pre haversine: {first_latitude},{first_longitude} vs {latitude},{longitude}")
            distance = haversine(float(first_latitude), float(first_longitude), float(latitude), float(longitude))
            print(f"La coppia {first_latitude},{first_longitude} con la coppia {latitude},{longitude} distano: {distance}")
            
            if distance > 30 or stolen == True:
                print(f"Salvataggio della coordinata su Redis: {latitude}, {longitude}")
                
                # Creare una chiave unica per ogni coppia di coordinate
                unique_key = f"{latitude}:{longitude}"
                
                # Salvare la coordinata su Redis
                
                redis_client.hset(f"{index}:{unique_key}", mapping={
                    "latitude": latitude,
                    "longitude": longitude
                })

                unique_key = "stolen"
                
                # Salvare la coordinata su Redis
                
                redis_client.hset(unique_key, mapping={
                    "stolen": "True",
                })
                index += 1
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
    .add("longitude", StringType())

# Trasformare i dati
df = df.selectExpr("CAST(value AS STRING) as json") \
    .select(from_json(col("json"), schema).alias("data")) \
    .select("data.*") \
    .withColumn("value", F.concat(col("latitude"), lit(","), col("longitude"))) \

# Converti le coordinate in DoubleType per il calcolo della distanza
df = df.withColumn("latitude", col("latitude").cast(DoubleType())) \
       .withColumn("longitude", col("longitude").cast(DoubleType()))

df.writeStream \
    .foreachBatch(process_new_data) \
    .start()

spark.streams.awaitAnyTermination()
