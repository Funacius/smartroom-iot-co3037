#pragma once
#include <Arduino.h>

enum PacketType : uint8_t { TELEMETRY = 1, COMMAND = 2, ACK = 3 };
#pragma pack(push, 1)
struct Packet {
    uint16_t magic = 0x5352;
    uint8_t version = 1;
    uint8_t type = TELEMETRY;
    uint32_t boot = 0;
    uint32_t seq = 0;
    uint32_t commandId = 0;
    float temperature = 0;
    float humidity = 0;
    uint8_t fan = 0;
};
#pragma pack(pop)
static_assert(sizeof(Packet) == 25, "Wire format must match on both boards");
inline bool validHeader(const Packet& p) {
    return p.magic == 0x5352 && p.version == 1 && p.fan <= 1;
}
