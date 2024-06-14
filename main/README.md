# Grand Shield Auto CAR - MAIN

<p align="center">
<picture>
 <source width="500" height="200" media="(prefers-color-scheme: dark)"  srcset="https://i.postimg.cc/9F6hcmbc/logo.png">
 <img width="500" height="375" alt="Shows logo with black blackground in white theme" src="https://i.postimg.cc/9F6hcmbc/logo.png">
</picture>
</p>
  
## Technologies
- Data source: [ESP32-S3-WROOM-1](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
- Data ingestion: [Fluentd](https://www.fluentd.org/architecture)
- Data streaming: [Kafka](https://www.confluent.io/what-is-apache-kafka "Apache Kafka")
- Data processing: [Spark](https://spark.apache.org/streaming/ "Spark Streaming")
- Data caching: [Redis](https://redis.io)
- Notification: [Twilio](https://www.twilio.com/en-us/company)
- Data indexing: [Elasticsearch](https://www.elastic.co/what-is/elasticsearch "ElasticSearch")
- Data visualisation: [Kibana](https://www.elastic.co/what-is/kibana "Kibana")
  
## Project Structure
<p align="center">
    <img width="1200" height="600" src="https://i.postimg.cc/vB5s1pZp/Screenshot-2024-06-13-at-15-56-00.png">
</p>

## Features
- Realtime car detection 📍
- Phone notification 📲
- Car direction prediction ⬆️

# Installation 🔧
GSA requires 
- [Docker](https://www.docker.com/) 
- 16 GB RAM 😬 or Droplet like [DigitalOcean](https://www.digitalocean.com/products/droplets)

## Before start
Setup you .env file with configurations!
``` sh
$ cd spark
$ touch .env
$ nano .env   
```

.env file has to contain:
- WILIO_ACCOUNT_SID = value
- TWILIO_AUTH_TOKEN = value
- PHONE_NUMBER = value
- TWILIO_NUMBER = value

Replace values with your keys. PHONE_NUMBER refers to your mobile number to call you in case of a theft 

## Launch app

``` sh
$ docker compose up --build   
```

## Stop app
``` sh
$ docker compose down 
```
That's it.
Welcome to GSA!

## Usage

After setup the environment let's jump into the core of GSA. Here is services ip table:

| Container     | URL                                        | Description                                     |
| ------------- | ------------------------------------------ | ----------------------------------------------- |
| Kafka UI      | http://localhost:8080                      | Open kafka UI to monitor Kafka Topics           |
| Elasticsearch | http://localhost:9200                      | Open Elasticsearch to manage indexes            |
| Kibana        | http://localhost:5601                      | Open Kibana to view data and create a dashboard |

I created this visualisation: 
<p align="center">
<picture>
 <source width="500" height="300" media="(prefers-color-scheme: dark)"  srcset="https://i.postimg.cc/Hsm5BYvr/Screenshot-2024-06-13-at-16-32-34.png">
 <img width="500" height="300" alt="Shows logo with black blackground in white theme" src="https://i.postimg.cc/Hsm5BYvr/Screenshot-2024-06-13-at-16-32-34.png">
</picture>
</p>

If you want the same graphs, follow this steps:

- Open [Kibana](localhost:5601);
- Search for "Saved Objects";
- Import from file;
- Choose Kibana/kibanGraphConf.ndjson


## ESP32-Less // DEMO
In case you don't have an ESP32 or similar, you can simulate data using shell scripts. Follow this steps to play demos:

``` sh
$ docker compose up -D
$ cd shell
$ chmod +x simulation.sh
$ ./simulation.sh
```

There are 3 simulation:

- simulation.sh : car moves every 10 second in a random direction.
- simulation2.sh : car moves north every 10 seconds, moving 10 meters.
- simulation3.sh : car moves in a triangle area and then stops. Data is sent every 10 seconds.

# Author 💻 👦
GSA has been developed by Claudio Caudullo, Computer Science student at Department of Mathematics and Computer Science, University of Catania, Italy. 

Email: claudiocaudullo01@gmail.com
