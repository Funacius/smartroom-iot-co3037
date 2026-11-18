#pragma once
// Copy to config.local.h. GPIO numbers below are proposed RAW ESP32 GPIOs,
// not Arduino Dx labels. Confirm on the actual YoloUNO board revision.
#define I2C_SDA_PIN 11
#define I2C_SCL_PIN 12
#define FAN_PIN 6
#define FAN_ACTIVE_HIGH 1
#define RADIO_CHANNEL 1
#define SAMPLE_MS 2000
#define FAN_LEASE_MS 30000
#define ROOM_DEVICE "room-node-01"
// Each board's PEER_MAC must be the OTHER board's Wi-Fi STA MAC printed at boot.
static const uint8_t PEER_MAC[6] = {0x02, 0, 0, 0, 0, 1};
// Set a different 16-byte random key on BOTH boards before a real demo.
static const uint8_t RADIO_KEY[16] = {'R','E','P','L','A','C','E','_','T','H','I','S','_','K','E','Y'};
#define LOCAL_AP_SSID "SmartRoom-Bridge"
#define LOCAL_AP_PASSWORD "ChangeMe2353"
#define LOCAL_USER "admin"
#define LOCAL_PASSWORD "ChangeMe2353"
