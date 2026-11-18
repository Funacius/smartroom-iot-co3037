// Arduino-ESP32 2.0.17 / ESP-IDF 4.4 callback signatures, pinned in PlatformIO.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <DHT20.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Preferences.h>
#include "protocol.h"
#if __has_include("config.local.h")
#include "config.local.h"
#else
#include "config.example.h"
#endif

QueueHandle_t radioQueue;
WebServer web(80);
DHT20 dht;
Preferences preferences;
uint32_t bootId, sequenceNo = 0, lastSample = 0, lastCommandId = 0, lastCommandMs = 0;
bool fan = false;
Packet latest;
bool haveLatest = false;
uint32_t latestMs = 0;
String serialLine;

void outputFan(bool value) {
    fan = value;
    digitalWrite(FAN_PIN, FAN_ACTIVE_HIGH ? value : !value);
}

void onRadio(const uint8_t* mac, const uint8_t* bytes, int length) {
    if (memcmp(mac, PEER_MAC, 6) || length != sizeof(Packet)) return;
    Packet p;
    memcpy(&p, bytes, sizeof(p));
    if (validHeader(p)) xQueueSend(radioQueue, &p, 0);
    // No Serial, flash writes, JSON or web processing in the Wi-Fi callback.
}

void sendRadio(const Packet& p) {
    esp_now_send(PEER_MAC, reinterpret_cast<const uint8_t*>(&p), sizeof(p));
}

void serialPacket(const Packet& p) {
    StaticJsonDocument<320> json;
    if (p.type == TELEMETRY) {
        json["type"] = "telemetry";
        json["device"] = ROOM_DEVICE;
        json["boot"] = p.boot;
        json["seq"] = p.seq;
        json["temperature"] = p.temperature;
        json["humidity"] = p.humidity;
        json["fan"] = bool(p.fan);
    } else {
        json["type"] = "ack";
        json["id"] = p.commandId;
        json["value"] = bool(p.fan);
    }
    serializeJson(json, Serial);
    Serial.println();
}

bool authorized() {
    if (web.authenticate(LOCAL_USER, LOCAL_PASSWORD)) return true;
    web.requestAuthentication();
    return false;
}

void beginWeb() {
    web.on("/", HTTP_GET, []() {
        if (!authorized()) return;
        web.send(200, "text/html; charset=utf-8", R"HTML(
<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>SmartRoom Bridge</title><style>body{font:18px sans-serif;max-width:620px;margin:60px auto;padding:20px;background:#edf3ee;color:#184436}button{padding:12px;margin:8px}pre{white-space:pre-wrap}</style>
<h1>SmartRoom · ESP32-S3</h1><p>Web server chạy trực tiếp trên bridge (T07).</p><pre id="data">Đang nhận dữ liệu…</pre>
<button onclick="setFan(true)">Bật quạt</button><button onclick="setFan(false)">Tắt quạt</button><p id="result"></p>
<script>async function refresh(){const r=await fetch('/api/state');document.getElementById('data').textContent=JSON.stringify(await r.json(),null,2)}
async function setFan(value){const r=await fetch('/api/fan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value})});document.getElementById('result').textContent=await r.text()}
setInterval(refresh,2000);refresh()</script></html>)HTML");
    });
    web.on("/api/state", HTTP_GET, []() {
        if (!authorized()) return;
        StaticJsonDocument<256> json;
        json["connected"] = haveLatest && millis() - latestMs < 15000;
        if (haveLatest) {
            json["temperature"] = latest.temperature;
            json["humidity"] = latest.humidity;
            json["fan"] = bool(latest.fan);
            json["age_ms"] = millis() - latestMs;
        }
        String data;
        serializeJson(json, data);
        web.send(200, "application/json", data);
    });
    // Local web commands go through the PC's same id/ACK/timeout path.
    web.on("/api/fan", HTTP_POST, []() {
        if (!authorized()) return;
        StaticJsonDocument<128> json;
        if (deserializeJson(json, web.arg("plain")) || !json["value"].is<bool>()) {
            web.send(400, "text/plain", "Expected boolean value"); return;
        }
        StaticJsonDocument<128> request;
        request["type"] = "local_command";
        request["value"] = json["value"].as<bool>();
        serializeJson(request, Serial); Serial.println();
        web.send(202, "text/plain; charset=utf-8", "Đã gửi yêu cầu tới PC gateway; xem trạng thái quạt để xác nhận. PC phải đang chạy.");
    });
    web.begin();
}

void setup() {
    Serial.begin(115200);
    delay(800);
    bootId = esp_random();
    pinMode(FAN_PIN, OUTPUT);
    outputFan(false);
    radioQueue = xQueueCreate(12, sizeof(Packet));
    if (!radioQueue) abort();
    WiFi.mode(ROLE_SENSOR ? WIFI_STA : WIFI_AP_STA);
    if (!ROLE_SENSOR) WiFi.softAP(LOCAL_AP_SSID, LOCAL_AP_PASSWORD, RADIO_CHANNEL);
    esp_wifi_set_channel(RADIO_CHANNEL, WIFI_SECOND_CHAN_NONE);
    Serial.printf("# STA MAC=%s role=%s channel=%d\n", WiFi.macAddress().c_str(), ROLE_SENSOR ? "sensor" : "bridge", RADIO_CHANNEL);
    if (esp_now_init() != ESP_OK) abort();
    esp_now_set_pmk(RADIO_KEY);
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, PEER_MAC, 6);
    memcpy(peer.lmk, RADIO_KEY, 16);
    peer.channel = RADIO_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = true;
    if (esp_now_add_peer(&peer) != ESP_OK) abort();
    esp_now_register_recv_cb(onRadio);
    if (ROLE_SENSOR) {
        preferences.begin("smartroom", false);
        lastCommandId = preferences.getUInt("last_id", 0);
        Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
        dht.begin();
    } else beginWeb();
}

void loop() {
    Packet p;
    while (xQueueReceive(radioQueue, &p, 0) == pdTRUE) {
        if (ROLE_SENSOR && p.type == COMMAND && p.commandId >= lastCommandId) {
            if (p.commandId > lastCommandId) {
                lastCommandId = p.commandId;
                preferences.putUInt("last_id", lastCommandId);
                outputFan(p.fan);
                lastCommandMs = millis();
            }
            // Duplicate ids ACK the ACTUAL current output; never reapply old commands.
            p.type = ACK; p.fan = fan; sendRadio(p);
        } else if (!ROLE_SENSOR && p.type == TELEMETRY && isfinite(p.temperature) && isfinite(p.humidity)) {
            latest = p; haveLatest = true; latestMs = millis(); serialPacket(p);
        } else if (!ROLE_SENSOR && p.type == ACK) serialPacket(p);
    }
    if (ROLE_SENSOR) {
        // A bounded manual lease returns to the safe output when control disappears.
        if (fan && millis() - lastCommandMs > FAN_LEASE_MS) outputFan(false);
        if (millis() - lastSample >= SAMPLE_MS) {
            lastSample = millis();
            int status = dht.read();
            if (status == DHT20_OK) {
                Packet reading; reading.boot = bootId; reading.seq = ++sequenceNo;
                reading.temperature = dht.getTemperature(); reading.humidity = dht.getHumidity(); reading.fan = fan;
                sendRadio(reading);
            } else {
                outputFan(false);
                Serial.printf("# DHT20 error=%d; no fabricated telemetry\n", status);
            }
        }
    } else {
        web.handleClient();
        while (Serial.available()) {
            char ch = Serial.read();
            if (ch == '\n') {
                StaticJsonDocument<192> json;
                if (!deserializeJson(json, serialLine) && json["type"] == "command" &&
                    json["id"].is<uint32_t>() && json["value"].is<bool>()) {
                    Packet command; command.type = COMMAND; command.commandId = json["id"];
                    command.fan = json["value"].as<bool>(); sendRadio(command);
                }
                serialLine = "";
            } else if (serialLine.length() < 256) serialLine += ch;
            else serialLine = "";
        }
    }
    delay(1);
}
