#include "node_under_test.ino"
#include "test_expected_ack.h"
#include <iostream>
using namespace Chacaico;

static void advance(uint32_t ms) {
    uint32_t until=millis()+ms;
    while(int32_t(until-millis())>0)loop();
}
static std::vector<uint8_t> request(uint8_t op,uint32_t seq,uint8_t value=0,
                                  uint32_t rev=0,uint16_t sleep=0,uint16_t pulse=0,uint8_t power=0,uint16_t listen=3000,uint16_t awake=10000) {
    std::vector<uint8_t> p(FRAME_SIZE,0);
    p[0]='C';p[1]='L';p[2]=3;p[3]=REQUEST;write16(p.data()+4,CHACAICO_NODE_ID);
    write32(p.data()+6,config.boot);write32(p.data()+10,wake);write32(p.data()+14,seq);
    p[18]=op;write32(p.data()+20,rev);write16(p.data()+24,sleep);write16(p.data()+26,pulse);
    if(op==SET_LED)p[29]=value;
    if(op==SET_VALVE)p[28]=value;
    p[30]=power;write16(p.data()+31,listen);write16(p.data()+33,awake);
    authenticate(p.data(),p.data()+BODY_SIZE);return p;
}
static void deliver(std::vector<uint8_t> p) {
    assert(Radio.state==TestRadio::RX);
    events.RxDone(p.data(),p.size(),-50,12);loop();
}
static void storageTests() {
    for(int cut=0;cut<=40;++cut) {
        flashMemory.fill(255);flashCut=-1;ConfigStore a;a.begin();
        assert(a.healthy && a.boot==1);
        assert(a.apply(2,5,75)==OK);
        int before=flashWrites;
        assert(a.apply(2,5,75)==OK && flashWrites==before);
        assert(a.apply(2,6,75)==CONFLICT && flashWrites==before);
        assert(a.apply(3,3601,75)==INVALID && flashWrites==before);
        flashCut=cut;const Status result=a.apply(3,9,100);
        assert(result==(cut==40?OK:STORE_FAILED));
        flashCut=-1;ConfigStore reboot;reboot.begin();
        assert(reboot.healthy && reboot.boot==2);
        assert(reboot.sleep==(cut==40?9:5));
        assert(reboot.pulse==(cut==40?100:75));
    }
    flashMemory.fill(255);flashCut=-1;ConfigStore good;good.begin();
    auto saved=flashMemory;flashReadFail=true;ConfigStore unreadable;unreadable.begin();
    assert(!unreadable.healthy && flashMemory==saved);flashReadFail=false;
    flashMemory[36]^=1;ConfigStore damaged;damaged.begin();assert(!damaged.healthy);
    flashMemory.fill(255);flashCut=0;ConfigStore failed;failed.begin();assert(!failed.healthy);
    // Upgrade a legacy record without losing its boot counter or user settings.
    flashCut=-1;flashMemory.fill(255);
    uint8_t old[32]={0};memcpy(old,"CCF2",4);write16(old+4,CHACAICO_NODE_ID);write16(old+6,1);
    write32(old+8,41);write32(old+12,25);write32(old+16,7);write16(old+20,30);write16(old+22,75);
    write32(old+28,ConfigStore::checksum(old,28));memcpy(flashMemory.data(),old,32);
    ConfigStore migrated;migrated.begin();
    assert(migrated.healthy && migrated.boot==26 && migrated.generation==42);
    assert(migrated.revision==7 && migrated.sleep==30 && migrated.pulse==75);
    assert(migrated.power==0 && migrated.listen==3000 && migrated.awake==10000);
    flashMemory.fill(255);flashWrites=0;
}
int main() {
    storageTests();
    setup();advance(1200);
    assert(config.healthy && config.boot==1 && config.sleep==0 && config.pulse==50);
    assert(highEdges.empty() && Radio.state==TestRadio::RX);
    auto ledOn=request(SET_LED,1,1);deliver(ledOn);advance(500);
    assert(led && highEdges.empty());
    assert(Radio.sent.back().payload==std::vector<uint8_t>(EXPECTED_ACK,EXPECTED_ACK+FRAME_SIZE));
    auto foreign=request(SET_VALVE,2,1);
    write16(foreign.data()+4,CHACAICO_NODE_ID==1?2:1);authenticate(foreign.data(),foreign.data()+BODY_SIZE);
    deliver(foreign);advance(300);assert(highEdges.empty());
    auto valid=request(SET_VALVE,2,1);
    for(unsigned bit=0;bit<FRAME_SIZE*8;++bit) {
        auto bad=valid;bad[bit/8]^=1<<(bit%8);deliver(bad);
    }
    assert(highEdges.empty());
    deliver(valid);
    auto start=highEdges.back().second;
    while(uint32_t(millis()-start)<50)loop();
    loop();assert(!gpio[GPIO1]&&!gpio[GPIO2]);assert(millis()-start<=52);
    advance(1300);assert(valve==1 && led && highEdges.size()==1);
    deliver(valid);advance(500);assert(highEdges.size()==1); // Lost ACK retry.
    deliver(request(SET_VALVE,3,1));advance(500);assert(highEdges.size()==1); // Same desired state.
    deliver(request(SET_LED,4,0));advance(500);assert(!led);
    rgbEdges.clear();deliver(request(SET_VALVE,5,0));advance(1400);
    assert(highEdges.size()==2 && highEdges.back().first==GPIO1 && valve==0 && !led);
    int green=0;for(auto edge:rgbEdges)if(edge.first)++green;assert(green==2);
    auto oldFrame=request(SET_LED,6,1);
    write32(oldFrame.data()+6,config.boot+1);authenticate(oldFrame.data(),oldFrame.data()+BODY_SIZE);
    deliver(oldFrame);advance(300);assert(!led);
    deliver(request(SET_CONFIG,6,0,2,0,200));advance(500);
    assert(config.revision==2 && config.pulse==200 && highEdges.size()==2);
    const int writes=flashWrites;
    deliver(request(SET_CONFIG,7,0,2,0,200));advance(500);assert(flashWrites==writes);
    deliver(request(SET_CONFIG,8,0,3,0,MAX_PULSE+1));advance(500);
    assert(config.revision==2 && reply[19]==INVALID);
    deliver(request(SET_VALVE,9,1));start=highEdges.back().second;
    while(uint32_t(millis()-start)<199)loop();
    assert(gpio[GPIO2]);
    advance(3);assert(!gpio[GPIO2] && millis()-start<=203);advance(1000);
    deliver(request(SET_CONFIG,10,0,3,5,50));advance(500);
    assert(config.sleep==5 && config.pulse==50);
    auto previousWake=request(SET_LED,11,1);
    deliver(request(END,11));advance(500);
    assert(sleeping && Radio.state==TestRadio::SLEEP && !gpio[1]&&!gpio[2]);
    const uint32_t oldWake=wake;advance(6200);
    assert(wake==oldWake+1 && !sleeping && Radio.state==TestRadio::RX);
    deliver(previousWake);advance(100);assert(!led); // Old wake/session ignored.
    deliver(request(SET_LED,12,1));advance(500);assert(led);
    deliver(request(SET_CONFIG,13,0,4,0,50));advance(500);
    assert(config.sleep==0);advance(11000);assert(!sleeping && Radio.state==TestRadio::RX);
    // A lost TX IRQ cannot leave the radio permanently stuck in transmitting.
    deliver(request(GET_CONFIG,14));advance(160);assert(transmitting);
    Radio.txDoneAt=millis()+6000;advance(3600);assert(!transmitting && Radio.state==TestRadio::RX);
    deliver(request(SET_CONFIG,15,0,5,5,50));advance(500);
    // No base: the initial/extended wait expires, then the RTC wakes the node.
    advance(2800);assert(sleeping);
    assert(lowPowerCalls>0);
    // Fresh ConfigStore emulates reboot and reads the persisted active settings.
    ConfigStore reboot;reboot.begin();
    assert(reboot.healthy && reboot.boot==2 && reboot.revision==5 && reboot.sleep==5);
    advance(6200);
    uint32_t seq=16;
    const uint32_t hard=hardUntil;
    while(!sleeping && int32_t(hard+600-millis())>0) {
        if(Radio.state==TestRadio::RX && !incoming && !replyPending && !transmitting)
            deliver(request(GET_CONFIG,seq++));
        advance(300);
    }
    assert(sleeping); // Even valid traffic cannot hold the node awake indefinitely.
    advance(6200);
    deliver(request(SET_CONFIG,seq++,0,6,0,50));advance(500);
    assert(config.sleep==0);
    clockMs=0xfffffff0UL;
    idleUntil=millis()+config.listen;hardUntil=millis()+config.awake;announceAt=millis()+30000;
    deliver(request(SET_VALVE,seq++,0));start=highEdges.back().second;
    advance(55);
    assert(!gpio[1]&&!gpio[2] && uint32_t(millis()-start)<=57);
    advance(1500);assert(valve==0 && !sleeping);
    {
        assert(MAX_PULSE==3000);
        deliver(request(SET_CONFIG,seq++,0,config.revision+1,30,3000));advance(500);
        assert(config.pulse==3000 && config.sleep==30);
        for(uint8_t desired : {1,0}) {
            const auto count=highEdges.size();
            const auto packets=Radio.sent.size();
            auto command=request(SET_VALVE,seq++,desired);
            deliver(command);start=highEdges.back().second;
            assert(highEdges.back().first==(desired?GPIO2:GPIO1));
            // A duplicate during the pulse must not restart or extend it.
            events.RxDone(command.data(),command.size(),-50,12);loop();
            while(uint32_t(millis()-start)<2999)loop();
            assert(pulsing && gpio[desired?GPIO2:GPIO1] && !gpio[desired?GPIO1:GPIO2]);
            assert(Radio.sent.size()==packets); // Never acknowledge before GPIO LOW.
            advance(3);
            assert(!gpio[GPIO1]&&!gpio[GPIO2] && millis()-start<=3003);
            advance(1200);assert(valve==desired && highEdges.size()==count+1);
            assert(Radio.sent.back().at-start>=3000 && Radio.sent.back().payload[19]==OK);
            deliver(command);advance(500);assert(highEdges.size()==count+1);
            deliver(request(END,seq++));advance(500);assert(sleeping);
            advance(31500);assert(!sleeping && Radio.state==TestRadio::RX);
        }
        const auto count=highEdges.size();
        hardUntil=millis()+3500;
        deliver(request(SET_VALVE,seq++,1));advance(500);
        assert(reply[19]==BUSY && highEdges.size()==count && !gpio[1]&&!gpio[2]);
        ConfigStore persisted;persisted.begin();
        assert(persisted.healthy && persisted.pulse==3000 && persisted.sleep==30);
        deliver(request(SET_CONFIG,seq++,0,config.revision+1,0,50));advance(500);
        assert(config.pulse==50 && config.sleep==0 && highEdges.size()==count);
        ConfigStore restored;restored.begin();
        assert(restored.healthy && restored.pulse==50 && restored.sleep==0);
    }
    // Power must be tried bidirectionally before persistence; lost trial replies roll back.
    const auto edgesBefore=highEdges.size();
    const int writesBefore=flashWrites;
    auto trial=request(SET_CONFIG,seq++,0,config.revision+1,7,50,14,2500,12000);
    deliver(trial);advance(500);
    assert(powerTrial && config.power==0 && Radio.txPower==14 && reply[19]==TRIAL && reply[38]==1);
    assert(config.sleep==0 && flashWrites==writesBefore);
    advance(8500);assert(!powerTrial && config.power==0 && Radio.txPower==0 && flashWrites==writesBefore);
    deliver(trial);advance(500);assert(!powerTrial && reply[19]==CONFLICT);
    deliver(request(SET_CONFIG,seq++,0,config.revision+1,7,50,14,2500,12000));advance(500);
    assert(powerTrial);
    flashCut=0;
    deliver(request(COMMIT_CONFIG,seq++,0,config.revision+1,7,50,14,2500,12000));advance(500);
    assert(!powerTrial && config.power==0 && Radio.txPower==0 && reply[19]==STORE_FAILED);
    flashCut=-1;
    deliver(request(SET_CONFIG,seq++,0,config.revision+1,7,50,14,2500,12000));advance(500);
    assert(powerTrial);
    auto commit=request(COMMIT_CONFIG,seq++,0,config.revision+1,7,50,14,2500,12000);
    deliver(commit);advance(500);
    assert(!powerTrial && config.power==14 && config.sleep==7 && config.listen==2500 && config.awake==12000);
    assert(flashWrites==writesBefore+2 && reply[19]==OK && reply[38]==0);
    assert(int16_t(read16(reply+35))==-50 && int8_t(reply[37])==12);
    deliver(commit);advance(500);assert(flashWrites==writesBefore+2);
    ConfigStore withPower;withPower.begin();
    assert(withPower.healthy && withPower.power==14 && withPower.listen==2500 && withPower.awake==12000);
    deliver(request(SET_CONFIG,seq++,0,config.revision+1,5,50,14,1000,5000));advance(500);
    advance(650);assert(sleeping);
    advance(6200);
    const uint32_t budget=hardUntil;
    while(!sleeping && int32_t(budget+600-millis())>0) {
        if(Radio.state==TestRadio::RX && !incoming && !replyPending && !transmitting)
            deliver(request(GET_CONFIG,seq++));
        advance(300);
    }
    assert(sleeping && highEdges.size()==edgesBefore);
    std::cout<<"PASS node="<<CHACAICO_NODE_ID
             <<" real CMAC; 41 torn-write points; GPIO timing/LED; dedup; sessions; config; sleep; TX timeout\n";
}
