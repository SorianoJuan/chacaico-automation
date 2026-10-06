// Executes the real sketch against fake radio/GPIO/clock; never uses hardware.
#include "firmware-stubs/node_config.h"
#include "../firmware/libraries/ChacaicoNode/src/ChacaicoNode.h"
#include <iostream>
void receive(uint32_t seq,uint8_t op,uint8_t value,uint16_t node=CHACAICO_NODE_ID,bool corruptTag=false){
 uint8_t packet[20]={'C','L',1,0,uint8_t(node),uint8_t(node>>8),0,0,0,0,op,value};
 for(int i=0;i<4;i++)packet[6+i]=seq>>(8*i);
 authenticate(packet,packet+12);
 if(corruptTag) packet[19]^=1;
 onRxDone(packet,20,-50,10);
}
void tick(uint32_t at){clockMs=at;loop();}
int main(){
 setup();assert(highEdges.empty());assert(valve==VALVE_UNKNOWN);
 const uint16_t otherNode=CHACAICO_NODE_ID==1 ? 2 : 1;
 auto rgbInitial=rgbEdges.size();
 for(auto op:{SET_LED,SET_VALVE}) {
  receive(1,op,1,otherNode);
  receive(1,op,1,CHACAICO_NODE_ID,true);
 }
 assert(highEdges.empty() && rgbEdges.size()==rgbInitial && !replyPending && !haveSequence);
 receive(1,GET_VALVE,0);assert(highEdges.empty());tick(25);assert(Radio.sent.back()[11]==VALVE_UNKNOWN);
 clockMs=100;receive(2,SET_VALVE,1);assert(gpio[PON]==HIGH && gpio[POFF]==LOW);
 assert(!replyPending);tick(149);assert(gpio[PON]==HIGH);tick(150);
 assert(gpio[PON]==LOW && gpio[POFF]==LOW && valve==1);assert(replyPending);
 tick(175);assert(Radio.sent.back()[10]==SET_VALVE && Radio.sent.back()[11]==1);
 auto before=highEdges.size();receive(2,SET_VALVE,1);tick(201);assert(highEdges.size()==before);
 receive(2,SET_VALVE,0);receive(1,SET_VALVE,0);assert(highEdges.size()==before);
 tick(350);tick(550);assert(!led && blinkTransitions==0 && !restoringLed);
 auto rgbBefore=rgbEdges.size();clockMs=600;receive(3,SET_VALVE,0);
 assert(gpio[POFF]==HIGH && gpio[PON]==LOW);tick(649);assert(gpio[POFF]==HIGH);
 tick(650);assert(gpio[POFF]==LOW && gpio[PON]==LOW && valve==0);
 tick(675);assert(Radio.sent.back()[11]==0);
 tick(850);tick(1050);tick(1250);tick(1450);assert(!led && blinkTransitions==0 && !restoringLed);
 unsigned flashes=0;for(size_t i=rgbBefore;i<rgbEdges.size();i++)if(rgbEdges[i].first)flashes++;
 assert(flashes==2);assert(highEdges.size()==2);
 receive(4,GET_LED,0);tick(1476);assert(highEdges.size()==2);
 assert(Radio.sent.back()[11]==0);
 clockMs=1500;receive(5,SET_LED,1);tick(1525);assert(led && rgbEdges.back().first==0x001000);
 clockMs=1600;receive(6,SET_VALVE,1);tick(1650);assert(led && !blinkLed);
 tick(1675);tick(1850);tick(2050);tick(2250);
 assert(led && !blinkTransitions && !restoringLed && rgbEdges.back().first==0x001000);
 clockMs=2300;receive(7,SET_VALVE,0);tick(2350);tick(2375);
 tick(2550);tick(2750);tick(2950);tick(3150);tick(3350);
 assert(led && rgbEdges.back().first==0x001000);
 // A command during valve indication updates only the steady state.
 clockMs=3400;receive(8,SET_VALVE,1);tick(3450);tick(3475);
 clockMs=3500;receive(9,SET_LED,0);tick(3525);assert(!led && blinkTransitions);
 tick(3650);tick(3850);tick(4050);
 assert(!led && !blinkTransitions && !restoringLed && rgbEdges.back().first==0);
 auto pulses=highEdges.size();auto colors=rgbEdges.size();
 receive(10,SET_LED,1,otherNode);receive(10,SET_VALVE,1,otherNode);
 assert(highEdges.size()==pulses && rgbEdges.size()==colors && !replyPending);
 std::cout<<"PASS: foreign ID/bad tag ignored; startup/query no pulses; OPEN/CLOSE 50 ms; ACK after LOW; duplicates no pulse; valve 1/2 flashes preserve independent LED state\n";
}
