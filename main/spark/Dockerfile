# Utilizza un'immagine base con Spark pre-installato
FROM apache/spark:latest

# Passa all'utente root per installare pacchetti aggiuntivi
USER root

# Aggiorna pip e installa le librerie Python necessarie
RUN pip3 install --upgrade pip && \
    pip3 install pyspark && \
    pip3 install redis && \
    pip3 install scikit-learn && \
    pip3 install twilio && \
    pip3 install python-dotenv && \
    pip3 install elasticsearch

# Installa gli strumenti di linea di comando di Redis
RUN apt-get update && apt-get install -y redis-tools

# Aggiungi il percorso di Spark al PATH
ENV PATH="${PATH}:/opt/apache/spark/bin"

# Copia il codice dell'applicazione e il file .env nell'immagine
COPY ./script.py /opt/spark_app/script.py
COPY .env /opt/spark_app/.env

# Copia lo script wait-for-elasticsearch.sh nel container
COPY ./wait_for_elasticsearch.sh /wait-for-elasticsearch.sh

# Rendi eseguibile lo script wait-for-elasticsearch.sh
RUN chmod +x /wait-for-elasticsearch.sh

# Imposta la directory di lavoro
WORKDIR /opt/spark_app

# Avvia l'applicazione utilizzando lo script di attesa
CMD ["/wait-for-elasticsearch.sh", "http://elasticsearch:9200", "spark-submit", "--packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.3.0,com.redislabs:spark-redis_2.12:3.0.0,org.elasticsearch:elasticsearch-spark-30_2.12:8.2.0", "--master", "local[*]", "script.py"]
