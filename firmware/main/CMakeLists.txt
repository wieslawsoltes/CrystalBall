if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/gateway_ca.pem")
  message(FATAL_ERROR "Missing gateway_ca.pem. Export your Caddy/local CA root and copy here. Never disable TLS validation.")
endif()
idf_component_register(
  SRCS "app_main.c" "core.c" "display.c" "audio.c" "halo.c" "network.c" "config.c"
  INCLUDE_DIRS "."
  REQUIRES esp_driver_gpio esp_driver_spi esp_driver_i2s esp_driver_rmt esp_http_client esp_wifi esp_netif nvs_flash esp_timer esp_psram json lwip
  EMBED_TXTFILES "gateway_ca.pem")
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Wformat=2)
