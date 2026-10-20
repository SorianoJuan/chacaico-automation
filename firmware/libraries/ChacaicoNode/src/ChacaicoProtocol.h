#pragma once
#include "Arduino.h"
extern "C" {
#include "cmac.h"
}

#ifndef CHACAICO_MAX_PULSE_MS
#define CHACAICO_MAX_PULSE_MS 200
#endif
static_assert(CHACAICO_MAX_PULSE_MS >= 10 && CHACAICO_MAX_PULSE_MS <= 3000, "Unsupported pulse limit");

namespace Chacaico {
static const uint8_t KEY[16] = CHACAICO_KEY;
static const uint8_t BODY_SIZE = 30, FRAME_SIZE = 38;
enum Kind : uint8_t { REQUEST, RESPONSE, READY };
enum Op : uint8_t { GET_STATE, SET_LED, SET_VALVE, GET_CONFIG, SET_CONFIG, END };
enum Status : uint8_t { OK, INVALID, STORE_FAILED, CONFLICT, BUSY };
static const uint8_t UNKNOWN = 2;
static const uint16_t MAX_SLEEP = 3600, MIN_PULSE = 10, MAX_PULSE = CHACAICO_MAX_PULSE_MS;
static uint16_t read16(const uint8_t *p) { return uint16_t(p[0]) | uint16_t(p[1]) << 8; }
static uint32_t read32(const uint8_t *p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
static void write16(uint8_t *p, uint16_t v) { p[0]=v; p[1]=v>>8; }
static void write32(uint8_t *p, uint32_t v) {
    for (uint8_t i=0;i<4;++i) p[i]=v>>(i*8);
}
static bool validConfig(uint16_t sleep, uint16_t pulse) {
    return sleep<=MAX_SLEEP && pulse>=MIN_PULSE && pulse<=MAX_PULSE;
}
static void authenticate(const uint8_t *p, uint8_t *tag) {
    AES_CMAC_CTX ctx; uint8_t digest[16];
    AES_CMAC_Init(&ctx); AES_CMAC_SetKey(&ctx,KEY);
    AES_CMAC_Update(&ctx,p,BODY_SIZE); AES_CMAC_Final(digest,&ctx);
    memcpy(tag,digest,8);
}
static bool authentic(const uint8_t *p) {
    uint8_t tag[8], difference=0; authenticate(p,tag);
    for (uint8_t i=0;i<8;++i) difference |= tag[i]^p[BODY_SIZE+i];
    return difference==0;
}
}
