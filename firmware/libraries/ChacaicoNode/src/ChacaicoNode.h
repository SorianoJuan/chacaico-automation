#pragma once
// HTCC-AB01 / PCB V1.2 / ASR6501: authenticated bench valve control.
#include "LoRaWan_APP.h"
#include "Arduino.h"
extern "C" {
#include "cmac.h"
}

static const uint8_t KEY[16] = CHACAICO_KEY;
static const uint8_t FRAME_SIZE = 20, HEADER_SIZE = 12;
enum Operation : uint8_t { GET_LED = 0, SET_LED = 1, SET_VALVE = 2, GET_VALVE = 3 };
static const uint8_t VALVE_UNKNOWN = 2;
static const int POFF = GPIO1, PON = GPIO2;
static const uint32_t VALVE_PULSE_MS = 50;
static RadioEvents_t events;
static uint8_t reply[FRAME_SIZE], lastRequest[HEADER_SIZE];
static uint8_t valve = VALVE_UNKNOWN, requestedValve = VALVE_UNKNOWN;
// led is the requested steady state; valve indication never changes it.
static bool led = false, blinkLed = false, restoringLed = false;
static bool replyPending = false, transmitting = false, pulsing = false;
static uint32_t lastSequence = 0, replyAt = 0, pulseEnd = 0;
static bool haveSequence = false;
static uint8_t blinkTransitions = 0;
static uint32_t blinkAt = 0;
static const uint32_t LED_BLINK_MS = 200;

static void authenticate(const uint8_t *data, uint8_t *tag) {
    AES_CMAC_CTX ctx;
    uint8_t digest[16];
    AES_CMAC_Init(&ctx);
    AES_CMAC_SetKey(&ctx, KEY);
    AES_CMAC_Update(&ctx, data, HEADER_SIZE);
    AES_CMAC_Final(digest, &ctx);
    memcpy(tag, digest, 8);
}

static void prepareReply() {
    memcpy(reply, lastRequest, HEADER_SIZE);
    reply[3] = 1;
    reply[11] = lastRequest[10] <= SET_LED ? (led ? 1 : 0) : valve;
    authenticate(reply, reply + HEADER_SIZE);
    replyAt = millis() + 25;
    replyPending = true;
}

static void onTxDone() {
    transmitting = false;
    Radio.Rx(0);
}

static void onTxTimeout() {
    Serial.println("TX timeout");
    Radio.Standby();
    transmitting = false;
    Radio.Rx(0);
}

static void onRxError() { Radio.Rx(0); }

static void onRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr) {
    if (pulsing || transmitting) return;
    if (size != FRAME_SIZE || payload[0] != 'C' || payload[1] != 'L' ||
        payload[2] != 1 || payload[3] != 0 ||
        (uint16_t(payload[4]) | uint16_t(payload[5]) << 8) != CHACAICO_NODE_ID ||
        payload[10] > GET_VALVE || payload[11] > 1 ||
        ((payload[10] == GET_LED || payload[10] == GET_VALVE) && payload[11] != 0)) return;
    uint8_t tag[8], difference = 0;
    authenticate(payload, tag);
    for (uint8_t i = 0; i < 8; ++i) difference |= tag[i] ^ payload[HEADER_SIZE + i];
    if (difference) return;
    uint32_t seq = uint32_t(payload[6]) | uint32_t(payload[7]) << 8 |
                   uint32_t(payload[8]) << 16 | uint32_t(payload[9]) << 24;
    // Bench deduplication is RAM-only. A duplicate resends its cached ACK;
    // it never repeats the valve pulse. Field use needs persistent recovery.
    if (haveSequence && int32_t(seq - lastSequence) < 0) return;
    if (haveSequence && seq == lastSequence) {
        if (memcmp(payload, lastRequest, HEADER_SIZE) != 0) return;
        Radio.Standby();
        replyAt = millis() + 25;
        replyPending = true;
        return;
    }
    Radio.Standby();
    memcpy(lastRequest, payload, HEADER_SIZE);
    lastSequence = seq;
    haveSequence = true;
    Serial.printf("CMD node=%u seq=%lu op=%u value=%u RSSI=%d SNR=%d\r\n",
                  CHACAICO_NODE_ID, (unsigned long)seq, payload[10], payload[11], rssi, snr);
    if (payload[10] == SET_VALVE) {
        requestedValve = payload[11];
        digitalWrite(POFF, LOW);
        digitalWrite(PON, LOW);
        digitalWrite(requestedValve ? PON : POFF, HIGH);
        pulseEnd = millis() + VALVE_PULSE_MS;
        pulsing = true;
        return; // ACK only after the selected GPIO has returned LOW.
    }
    if (payload[10] == SET_LED) {
        led = payload[11] != 0;
        if (!blinkTransitions && !restoringLed) turnOnRGB(led ? 0x001000 : 0, 0);
    }
    prepareReply();
}

void setup() {
    digitalWrite(POFF, LOW);
    digitalWrite(PON, LOW);
    pinMode(POFF, OUTPUT);
    pinMode(PON, OUTPUT);
    Serial.begin(115200);
    turnOnRGB(0, 0);
    events.TxDone = onTxDone;
    events.TxTimeout = onTxTimeout;
    events.RxDone = onRxDone;
    events.RxError = onRxError;
    Radio.Init(&events);
    Radio.SetChannel(CHACAICO_FREQUENCY);
    Radio.SetTxConfig(MODEM_LORA, 0, 0, 0, 7, 1, 8, false, true, 0, 0, false, 3000);
    Radio.SetRxConfig(MODEM_LORA, 0, 7, 1, 0, 8, 0, false, 0, true, 0, 0, false, true);
    Radio.SetPublicNetwork(false);
    Serial.printf("CHACAICO valve-0.3.0 node=%u ASR6501 frequency=%lu GPIO1=OFF GPIO2=ON pulse=50ms state=unknown\r\n",
                  CHACAICO_NODE_ID, (unsigned long)CHACAICO_FREQUENCY);
    Radio.Rx(0);
}

void loop() {
    Radio.IrqProcess();
    if (pulsing && int32_t(millis() - pulseEnd) >= 0) {
        digitalWrite(PON, LOW);
        digitalWrite(POFF, LOW);
        pulsing = false;
        valve = requestedValve;
        // One green flash for OPEN, two for CLOSE, then restore steady LED state.
        // When already on, begin with an off interval so flashes remain visible.
        blinkLed = !led;
        turnOnRGB(blinkLed ? 0x001000 : 0, 0);
        blinkTransitions = valve ? 1 : 3;
        if (led) ++blinkTransitions;
        restoringLed = false;
        blinkAt = millis() + LED_BLINK_MS;
        Serial.printf("VALVE seq=%lu state=%s GPIO1=LOW GPIO2=LOW\r\n",
                      (unsigned long)lastSequence, valve ? "open" : "closed");
        prepareReply();
    }
    if (blinkTransitions && int32_t(millis() - blinkAt) >= 0) {
        blinkLed = !blinkLed;
        turnOnRGB(blinkLed ? 0x001000 : 0, 0);
        --blinkTransitions;
        blinkAt = millis() + LED_BLINK_MS;
        if (!blinkTransitions) restoringLed = true;
    }
    if (restoringLed && int32_t(millis() - blinkAt) >= 0) {
        turnOnRGB(led ? 0x001000 : 0, 0);
        restoringLed = false;
    }
    if (replyPending && !transmitting && int32_t(millis() - replyAt) >= 0) {
        replyPending = false;
        transmitting = true;
        Radio.Send(reply, FRAME_SIZE);
    }
    delay(1);
}
