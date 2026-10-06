#pragma once
#include "Arduino.h"
#define MODEM_LORA 1
struct RadioEvents_t {
 void (*TxDone)()=nullptr; void (*TxTimeout)()=nullptr;
 void (*RxDone)(uint8_t*,uint16_t,int16_t,int8_t)=nullptr;
 void (*RxError)()=nullptr;
};
struct TestRadio {
 RadioEvents_t* callbacks=nullptr;
 std::vector<std::vector<uint8_t>> sent;
 void Init(RadioEvents_t* events){callbacks=events;}
 void Standby(){} void Rx(int){} void IrqProcess(){} void SetChannel(uint32_t){} void SetPublicNetwork(bool){}
 template<class... Args> void SetTxConfig(Args...){}
 template<class... Args> void SetRxConfig(Args...){}
 void Send(uint8_t* p,uint8_t len){assert(gpio[1]==LOW && gpio[2]==LOW);sent.emplace_back(p,p+len);callbacks->TxDone();}
};
inline TestRadio Radio;
