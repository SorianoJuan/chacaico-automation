#pragma once
#include "Arduino.h"
#define MODEM_LORA 1
struct RadioEvents_t {
    void (*TxDone)() = nullptr;
    void (*TxTimeout)() = nullptr;
    void (*RxDone)(uint8_t*, uint16_t, int16_t, int8_t) = nullptr;
    void (*RxError)() = nullptr;
};
struct RecordedPacket { uint32_t at; std::vector<uint8_t> payload; };
struct TestRadio {
    enum State { STANDBY, RX, TX } state = STANDBY;
    RadioEvents_t* callbacks = nullptr;
    uint32_t txDoneAt = 0;
    std::vector<RecordedPacket> sent;
    void Init(RadioEvents_t* events) { callbacks = events; }
    void Standby() { state = STANDBY; }
    void Rx(int) { state = RX; }
    void IrqProcess() {
        if (state == TX && int32_t(millis() - txDoneAt) >= 0) {
            state = STANDBY;
            callbacks->TxDone();
        }
    }
    void SetChannel(uint32_t) {}
    void SetPublicNetwork(bool) {}
    template<class... Args> void SetTxConfig(Args...) {}
    template<class... Args> void SetRxConfig(Args...) {}
    void Send(uint8_t* p, uint8_t len) {
        assert(gpio[GPIO1] == LOW && gpio[GPIO2] == LOW);
        assert(state != TX);
        sent.push_back({millis(), std::vector<uint8_t>(p, p + len)});
        state = TX;
        txDoneAt = millis() + 57; // Rounded 56.576ms airtime; asynchronous.
    }
};
inline TestRadio Radio;
