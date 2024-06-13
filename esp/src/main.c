#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <sys/time.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "esp_http_client.h"
#include "driver/uart.h"

#define WIFI_SSID "Samsung Galaxy A50"
#define WIFI_PASS "PasswordProgetto"
#define LED_GPIO GPIO_NUM_2
static const int RX_BUF_SIZE = 1024;

static EventGroupHandle_t s_wifi_event_group;
static const int WIFI_CONNECTED_BIT = BIT0;
#define UART_NUM UART_NUM_1
#define BUF_SIZE (1024)
#define GPS_TX_PIN (GPIO_NUM_43) // Modifica in base alla tua configurazione
#define GPS_RX_PIN (GPIO_NUM_44) // Modifica in base alla tua configurazione


static const char *TAG = "wifi_station";

static void event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        esp_wifi_connect();
        xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        ESP_LOGI(TAG, "got ip:%s", ip4addr_ntoa(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        gpio_set_level(LED_GPIO, 1); // Accendi il LED
    }
}

void wifi_init_sta(void) {
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &event_handler,
                                                        NULL,
                                                        &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &event_handler,
                                                        NULL,
                                                        &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(ESP_IF_WIFI_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "wifi_init_sta finished.");
}



static void send_post_request(double latitude, double longitude) {
    char local_response_buffer[512] = {0};

    esp_http_client_config_t config = {
        .url = "http://157.230.21.212:9884",
        .method = HTTP_METHOD_POST,
        .buffer_size = sizeof(local_response_buffer),
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);

    time_t now;
    time(&now);

    char post_data[128];
    snprintf(post_data, sizeof(post_data), "{\"latitude\":\"%.6f\",\"longitude\":\"%.6f\",\"timestamp\":\"%lld\"}", latitude, longitude, now);

    esp_http_client_set_post_field(client, post_data, strlen(post_data));
    esp_http_client_set_header(client, "Content-Type", "application/json");

    esp_err_t err = esp_http_client_perform(client);

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "HTTP POST Status = %d, content_length = %lld",
                 esp_http_client_get_status_code(client),
                 esp_http_client_get_content_length(client));
    } else {
        ESP_LOGE(TAG, "HTTP POST request failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
}

bool parse_nmea_sentence(const char* sentence, double* latitude, double* longitude) {
    if (strncmp(sentence, "$GPGGA", 6) == 0) {
        // Esempio di frase: $GPGGA,123456.00,4124.8963,N,08151.6838,W,1,08,0.9,545.4,M,46.9,M,,*47
        char temp[128];
        strcpy(temp, sentence); // Copia la frase NMEA in una stringa temporanea
        char* token = strtok(temp, ",");
        int field_num = 0;
        double lat = 0, lon = 0;
        char lat_dir = 'N', lon_dir = 'E';

        while (token != NULL) {
            field_num++;
            switch (field_num) {
                case 3: lat = atof(token); break;
                case 4: lat_dir = token[0]; break;
                case 5: lon = atof(token); break;
                case 6: lon_dir = token[0]; break;
                default: break;
            }
            token = strtok(NULL, ",");
        }

        if (lat != 0 && lon != 0) {
            // Converti in formato decimale
            int lat_deg = (int)(lat / 100);
            double lat_min = lat - lat_deg * 100;
            *latitude = lat_deg + lat_min / 60.0;
            if (lat_dir == 'S') *latitude = -(*latitude);

            int lon_deg = (int)(lon / 100);
            double lon_min = lon - lon_deg * 100;
            *longitude = lon_deg + lon_min / 60.0;
            if (lon_dir == 'W') *longitude = -(*longitude);

            return true;
        }
    }
    return false;
}


void send_post_task(void *pvParameter) {
    uint8_t data[RX_BUF_SIZE];
    char nmea_sentence[128];
    int sentence_index = 0;

    while (1) {
        int len = uart_read_bytes(UART_NUM, data, RX_BUF_SIZE, 100 / portTICK_PERIOD_MS);
        if (len > 0) {
            for (int i = 0; i < len; i++) {
                char c = (char)data[i];
                if (c == '\r' || c == '\n') { // Considera sia \r che \n come fine della frase
                    if (sentence_index > 0) {
                        nmea_sentence[sentence_index] = '\0';
                        double latitude = 0, longitude = 0;
                        if (parse_nmea_sentence(nmea_sentence, &latitude, &longitude)) {
                            send_post_request(latitude, longitude);
                        }
                        sentence_index = 0;
                    }
                } else {
                    if (sentence_index < sizeof(nmea_sentence) - 1) {
                        nmea_sentence[sentence_index++] = c;
                    } else {
                        // Gestisci l'overflow del buffer
                        sentence_index = 0;
                    }
                }
            }
        }
        vTaskDelay(1000 / portTICK_PERIOD_MS); // Riduci la frequenza di lettura per evitare delay inutili
    }
}


void gps_init(void) {
    const uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE
    };

    uart_param_config(UART_NUM, &uart_config);
    uart_set_pin(UART_NUM, GPS_TX_PIN, GPS_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    uart_driver_install(UART_NUM, BUF_SIZE, 0, 0, NULL, 0);
}






void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);

    wifi_init_sta();
    gps_init();

    xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);

    xTaskCreate(&send_post_task, "send_post_task", 4096, NULL, 5, NULL);
}


