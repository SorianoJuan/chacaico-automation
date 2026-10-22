#pragma once
#include "Arduino.h"
#include <array>
#define MODEM_LORA 1
#define CY_SFLASH_USERBASE 0x0ffff400UL
inline std::array<uint8_t,768> flashMemory;
inline int flashWrites=0, flashCut=-1;
inline bool flashReadFail=false;
inline int FLASH_read_at(uint32_t address,uint8_t *out,uint32_t size) {
    if(flashReadFail)return -1;
    assert(address>=CY_SFLASH_USERBASE && address+size<=CY_SFLASH_USERBASE+768);
    memcpy(out,flashMemory.data()+address-CY_SFLASH_USERBASE,size);return 0;
}
inline int FLASH_update(uint32_t address,const void *in,uint32_t size) {
    assert(address>=CY_SFLASH_USERBASE && address+size<CY_SFLASH_USERBASE+768);
    ++flashWrites;
    const uint32_t count=flashCut<0?size:std::min(uint32_t(flashCut),size);
    memcpy(flashMemory.data()+address-CY_SFLASH_USERBASE,in,count);
    return 0; // Reproduce the official core's silent write-failure behavior.
}
struct TimerEvent_t {void (*callback)()=nullptr;uint32_t value=0,at=0;bool active=false;};
inline TimerEvent_t* timer=nullptr;
inline void TimerInit(TimerEvent_t *t,void(*fn)()){t->callback=fn;timer=t;}
inline void TimerSetValue(TimerEvent_t*t,uint32_t ms){t->value=ms;}
inline void TimerStart(TimerEvent_t*t){t->at=millis()+t->value;t->active=true;}
inline int lowPowerCalls=0;
inline void lowPowerHandler(){
    ++lowPowerCalls;++clockMs;
    if(timer && timer->active && int32_t(millis()-timer->at)>=0){
        timer->active=false;timer->callback();
    }
}
struct RadioEvents_t {
    void(*TxDone)()=nullptr;void(*TxTimeout)()=nullptr;
    void(*RxDone)(uint8_t*,uint16_t,int16_t,int8_t)=nullptr;void(*RxError)()=nullptr;
};
struct RecordedPacket {uint32_t at;std::vector<uint8_t> payload;};
struct TestRadio {
    enum State { STANDBY,RX,TX,SLEEP } state=STANDBY;
    RadioEvents_t* callbacks=nullptr;
    uint32_t txDoneAt=0;
    int txPower=0;
    std::vector<RecordedPacket> sent;
    void Init(RadioEvents_t*e){callbacks=e;}
    void Standby(){state=STANDBY;}
    void Sleep(){assert(!gpio[1]&&!gpio[2]);state=SLEEP;}
    void Rx(int){state=RX;}
    void IrqProcess(){
        if(state==TX && int32_t(millis()-txDoneAt)>=0){
            state=STANDBY;callbacks->TxDone();
        }
    }
    void SetChannel(uint32_t){}
    void SetPublicNetwork(bool){}
    template<class...Args>void SetTxConfig(int,int power,Args...){txPower=power;}
    template<class...Args>void SetRxConfig(Args...){}
    void Send(uint8_t*p,uint8_t len){
        assert(!gpio[1]&&!gpio[2]);assert(state!=TX);
        sent.push_back({millis(),std::vector<uint8_t>(p,p+len)});
        state=TX;txDoneAt=millis()+98;
    }
};
inline TestRadio Radio;
