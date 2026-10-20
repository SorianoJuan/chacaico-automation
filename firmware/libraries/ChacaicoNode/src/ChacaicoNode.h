#pragma once
#include "LoRaWan_APP.h"
#include "Arduino.h"
#include "ChacaicoStorage.h"

namespace Chacaico {
static ConfigStore config;
static RadioEvents_t events;
static TimerEvent_t wakeTimer;
static volatile bool wakeRequested=false;
static bool sleeping=false, transmitting=false, replyPending=false, incoming=false;
static bool pulsing=false, led=false, blinkLed=false, restoringLed=false, endRequested=false;
static uint8_t valve=UNKNOWN, requestedValve=UNKNOWN, blinkTransitions=0;
static uint8_t rx[FRAME_SIZE], lastRequest[BODY_SIZE], reply[FRAME_SIZE], lastReply[FRAME_SIZE];
static uint32_t wake=0, lastSequence=0, pulseEnd=0, replyAt=0, blinkAt=0;
static uint32_t idleUntil=0, hardUntil=0, announceAt=0, rng=1, txStarted=0;
static bool haveSequence=false, announcement=false, sleepAfterTx=false;
static const int POFF=GPIO1, PON=GPIO2;
static const uint32_t LISTEN_MS=3000, MAX_AWAKE_MS=10000, REPLY_GUARD_MS=150;
static bool due(uint32_t at) { return int32_t(millis()-at)>=0; }
static uint32_t jitter(uint32_t max) {
    rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng%(max+1);
}
static void receive() { Radio.Rx(0); }
static void onWake() { wakeRequested=true; }
static void extendWindow() { idleUntil=millis()+LISTEN_MS; }
static void startWindow() {
    if (wake==0xffffffff) { config.healthy=false;return; }
    ++wake;endRequested=false;sleepAfterTx=false;
    idleUntil=millis()+LISTEN_MS;hardUntil=millis()+MAX_AWAKE_MS;
    announcement=true;replyPending=true;replyAt=millis()+jitter(800)+100;
    receive();
}
static void makeResponse(uint8_t kind,uint8_t op,uint8_t status,uint32_t sequence) {
    memset(reply,0,sizeof(reply));reply[0]='C';reply[1]='L';reply[2]=2;reply[3]=kind;
    write16(reply+4,CHACAICO_NODE_ID);write32(reply+6,config.boot);
    write32(reply+10,wake);write32(reply+14,sequence);
    reply[18]=op;reply[19]=status;write32(reply+20,config.revision);
    write16(reply+24,config.sleep);write16(reply+26,config.pulse);
    reply[28]=valve;reply[29]=led?1:0;authenticate(reply,reply+BODY_SIZE);
}
static void queueResponse(uint8_t status=OK) {
    announcement=false;makeResponse(RESPONSE,lastRequest[18],status,lastSequence);
    memcpy(lastReply,reply,FRAME_SIZE);replyAt=millis()+REPLY_GUARD_MS;replyPending=true;
    extendWindow();
}
static void onTxDone() {
    transmitting=false;
    if (announcement) {
        idleUntil=millis()+LISTEN_MS;hardUntil=millis()+MAX_AWAKE_MS;
        announceAt=millis()+30000+jitter(2000);announcement=false;
    }
    if(sleepAfterTx) endRequested=true;
    receive();
}
static void onTxTimeout() {
    transmitting=false;sleepAfterTx=false;announcement=false;
    Radio.Standby();receive();extendWindow();
    Serial.println("TX timeout");
}
static void onRxError() { if(!sleeping && !transmitting && !pulsing) receive(); }
static void onRxDone(uint8_t *payload,uint16_t size,int16_t,int8_t) {
    // Validate/copy only; flash writes and actuation run from loop, never IRQ context.
    if(sleeping || incoming || pulsing || transmitting || size!=FRAME_SIZE
        || payload[0]!='C' || payload[1]!='L' || payload[2]!=2 || payload[3]!=REQUEST
        || read16(payload+4)!=CHACAICO_NODE_ID || read32(payload+6)!=config.boot
        || read32(payload+10)!=wake || !read32(payload+14) || payload[18]>END
        || payload[19]!=0 || payload[28]>1 || payload[29]>1 || !authentic(payload)) return;
    Radio.Standby();memcpy(rx,payload,FRAME_SIZE);incoming=true;
}
static void processRequest() {
    incoming=false;
    const uint32_t seq=read32(rx+14);
    if(haveSequence && seq<=lastSequence) {
        if(seq==lastSequence && !memcmp(rx,lastRequest,BODY_SIZE)) {
            memcpy(reply,lastReply,FRAME_SIZE);replyPending=true;announcement=false;
            replyAt=millis()+REPLY_GUARD_MS;extendWindow();
            sleepAfterTx=lastRequest[18]==END && reply[19]==OK && config.sleep;
        } else receive();
        return;
    }
    haveSequence=true;lastSequence=seq;memcpy(lastRequest,rx,BODY_SIZE);
    announcement=false;replyPending=false;sleepAfterTx=false;endRequested=false;
    Serial.printf("CMD node=%u boot=%lu wake=%lu seq=%lu op=%u\r\n",CHACAICO_NODE_ID,
        (unsigned long)config.boot,(unsigned long)wake,(unsigned long)seq,rx[18]);
    if(!config.healthy) { queueResponse(STORE_FAILED);return; }
    // Budget the maximum pulse, flash and response before accepting new work.
    if(config.sleep && int32_t(hardUntil-millis())<1000 && rx[18]!=END) {
        queueResponse(BUSY);return;
    }
    if(rx[18]!=SET_CONFIG && (read32(rx+20) || read16(rx+24) || read16(rx+26))) {
        queueResponse(INVALID);return;
    }
    if(rx[18]==SET_CONFIG) {
        const bool wasContinuous=config.sleep==0;
        const Status result=config.apply(read32(rx+20),read16(rx+24),read16(rx+26));
        if(result==OK && wasContinuous && config.sleep) hardUntil=millis()+MAX_AWAKE_MS;
        Serial.printf("CONFIG node=%u revision=%lu sleep=%u pulse=%u result=%u\r\n",
            CHACAICO_NODE_ID,(unsigned long)config.revision,config.sleep,config.pulse,result);
        queueResponse(result);return;
    }
    if(rx[18]==SET_VALVE && valve!=rx[28]) {
        requestedValve=rx[28];
        digitalWrite(POFF,LOW);digitalWrite(PON,LOW);
        digitalWrite(requestedValve?PON:POFF,HIGH);
        pulseEnd=millis()+config.pulse;pulsing=true;return;
    }
    if(rx[18]==SET_LED) {
        led=rx[29]!=0;
        if(!blinkTransitions && !restoringLed) turnOnRGB(led?0x001000:0,0);
    }
    if(rx[18]==END) sleepAfterTx=config.sleep!=0;
    queueResponse();
}
static void sleepNow() {
    digitalWrite(PON,LOW);digitalWrite(POFF,LOW);
    Radio.Sleep();sleeping=true;endRequested=false;sleepAfterTx=false;
    // A requested diagnostic LED stays visible; it still consumes power.
    TimerSetValue(&wakeTimer,uint32_t(config.sleep)*1000+jitter(250));
    TimerStart(&wakeTimer);
    Serial.printf("SLEEP node=%u seconds=%u revision=%lu\r\n",CHACAICO_NODE_ID,
        config.sleep,(unsigned long)config.revision);
    Serial.flush();
}
static void nodeSetup() {
    digitalWrite(POFF,LOW);digitalWrite(PON,LOW);pinMode(POFF,OUTPUT);pinMode(PON,OUTPUT);
    Serial.begin(115200);turnOnRGB(0,0);
    config.begin();
    rng=read32(KEY)^CHACAICO_NODE_ID^config.boot*2654435761UL;
    if(!rng) rng=1;
    events.TxDone=onTxDone;events.TxTimeout=onTxTimeout;
    events.RxDone=onRxDone;events.RxError=onRxError;
    Radio.Init(&events);Radio.SetChannel(CHACAICO_FREQUENCY);
    Radio.SetTxConfig(MODEM_LORA,0,0,0,7,1,8,false,true,0,0,false,3000);
    Radio.SetRxConfig(MODEM_LORA,0,7,1,0,8,0,false,0,true,0,0,false,true);
    Radio.SetPublicNetwork(false);TimerInit(&wakeTimer,onWake);
    Serial.printf("CHACAICO valve-0.4.0 node=%u boot=%lu revision=%lu sleep=%u pulse=%u store=%u\r\n",
        CHACAICO_NODE_ID,(unsigned long)config.boot,(unsigned long)config.revision,
        config.sleep,config.pulse,config.healthy);
    startWindow();
}
static void nodeLoop() {
    if(sleeping) {
        if(!wakeRequested) { lowPowerHandler();return; }
        wakeRequested=false;sleeping=false;startWindow();
    }
    Radio.IrqProcess();
    if(incoming && config.sleep && due(hardUntil) && !pulsing && !replyPending && !transmitting)
        incoming=false;
    if(incoming) processRequest();
    if(pulsing && due(pulseEnd)) {
        digitalWrite(PON,LOW);digitalWrite(POFF,LOW);pulsing=false;valve=requestedValve;
        blinkLed=!led;turnOnRGB(blinkLed?0x001000:0,0);
        blinkTransitions=valve?1:3;if(led)++blinkTransitions;
        restoringLed=false;blinkAt=millis()+200;
        Serial.printf("VALVE node=%u seq=%lu state=%u GPIO1=LOW GPIO2=LOW\r\n",
            CHACAICO_NODE_ID,(unsigned long)lastSequence,valve);
        queueResponse();
    }
    if(blinkTransitions && due(blinkAt)) {
        blinkLed=!blinkLed;turnOnRGB(blinkLed?0x001000:0,0);
        --blinkTransitions;blinkAt=millis()+200;
        if(!blinkTransitions)restoringLed=true;
    }
    if(restoringLed && due(blinkAt)) { turnOnRGB(led?0x001000:0,0);restoringLed=false; }
    if(transmitting && uint32_t(millis()-txStarted)>3500) onTxTimeout();
    if(replyPending && !transmitting && due(replyAt)) {
        if(announcement) makeResponse(READY,GET_STATE,config.healthy?OK:STORE_FAILED,0);
        replyPending=false;transmitting=true;txStarted=millis();Radio.Send(reply,FRAME_SIZE);
    }
    const bool idle=!incoming && !pulsing && !transmitting && !replyPending
        && !blinkTransitions && !restoringLed;
    if(idle && config.healthy && config.sleep && (endRequested || due(idleUntil) || due(hardUntil))) {
        sleepNow();return;
    }
    if(idle && (!config.sleep || !config.healthy) && due(announceAt)) {
        announcement=true;replyPending=true;replyAt=millis()+jitter(250);
    }
    delay(1);
}
}
void setup() { Chacaico::nodeSetup(); }
void loop() { Chacaico::nodeLoop(); }
