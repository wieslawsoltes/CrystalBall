# Dependencies are unconditional: ESP-IDF expands these before CONFIG_* exists.
idf_component_register(
  SRCS "core.c" "display.c" "audio.c" "halo.c" "diagnostics_core.c"
  INCLUDE_DIRS "."
  REQUIRES esp_driver_gpio esp_driver_spi esp_driver_i2s esp_driver_rmt
           esp_timer esp_psram esp_http_client esp_wifi esp_netif nvs_flash json lwip)
# idf_component_register returns from the early dependency-expansion pass.
if(CONFIG_ORB_FACTORY_DIAGNOSTICS)
  target_sources(${COMPONENT_LIB} PRIVATE "factory_main.c" "diagnostics.c")
else()
  if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/gateway_ca.pem")
    message(FATAL_ERROR "Missing gateway_ca.pem. Export your trusted gateway CA. Never disable TLS verification.")
  endif()
  target_sources(${COMPONENT_LIB} PRIVATE "app_main.c" "network.c" "config.c")
  target_add_binary_data(${COMPONENT_LIB} "gateway_ca.pem" TEXT)
endif()
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Wformat=2)
