// Runner stages the unchanged real sketch with PUBLIC test keys only.
#include "chacaico_node.ino"
#include "test_expected_ack.h"
#include <iostream>

void advance(uint32_t at) {
    while (clockMs < at) loop();
}
void receive(uint32_t seq, uint8_t op, uint8_t value, uint16_t node=CHACAICO_NODE_ID) {
    uint8_t packet[20] = {'C','L',1,0,uint8_t(node),uint8_t(node>>8),0,0,0,0,op,value};
    for (int i=0; i<4; ++i) packet[6+i] = seq >> (8*i);
    authenticate(packet, packet+12);
    // Fake the completed radio receive event only when the radio is listening.
    if (Radio.state == TestRadio::RX) Radio.callbacks->RxDone(packet,20,-55,9);
}
int main() {
    setup();
    assert(highEdges.empty() && valve == VALVE_UNKNOWN && Radio.state == TestRadio::RX);
    advance(10);
    receive(1,SET_LED,1);
    assert(led && highEdges.empty());
    advance(35);
    assert(Radio.sent.empty());
    advance(37);
    assert(Radio.sent.size() == 1 && transmitting && Radio.state == TestRadio::TX);
    assert(Radio.sent[0].payload == std::vector<uint8_t>(EXPECTED_ACK,EXPECTED_ACK+20));
    // While TX is in progress no other request can enter the radio.
    receive(2,SET_VALVE,1);
    assert(highEdges.empty());
    advance(100);
    assert(!transmitting && Radio.state == TestRadio::RX);
    advance(200);
    receive(2,SET_VALVE,1);
    assert(gpio[PON] == HIGH && gpio[POFF] == LOW && pulsing);
    advance(249);
    assert(gpio[PON] == HIGH);
    advance(252);
    assert(gpio[PON] == LOW && gpio[POFF] == LOW && valve == 1);
    assert(highEdges.size() == 1);
    advance(277);
    assert(Radio.sent.back().payload[10] == SET_VALVE);
    assert(Radio.sent.back().at >= 275 && Radio.sent.back().at <= 277);
    advance(400);
    assert(!transmitting && Radio.state == TestRadio::RX);
    // Base drops ACKs and retries the exact same request after one second.
    for (uint32_t at : {1200u,2200u}) {
        advance(at);
        receive(2,SET_VALVE,1);
        advance(at+100);
        assert(highEdges.size() == 1);
        assert(!transmitting && Radio.state == TestRadio::RX);
    }
    // A new HA click becomes a NEW sequence and repeats the same GPIO pulse.
    advance(3200);
    receive(3,SET_VALVE,1);
    advance(3400);
    assert(highEdges.size() == 2 && valve == 1);
    // A command for another node leaves continuous RX active, then ours works.
    receive(4,SET_LED,0,CHACAICO_NODE_ID == 1 ? 2 : 1);
    assert(led && Radio.state == TestRadio::RX);
    receive(4,SET_LED,0);
    advance(3500);
    assert(!led && !transmitting && Radio.state == TestRadio::RX);
    assert(gpio[PON] == LOW && gpio[POFF] == LOW);
    // Registered timeout callback puts the simulated radio back into RX.
    transmitting = true;
    Radio.state = TestRadio::TX;
    Radio.callbacks->TxTimeout();
    assert(!transmitting && Radio.state == TestRadio::RX);
    std::cout << "PASS node=" << CHACAICO_NODE_ID
              << ": first LED/valve accepted; real AES-CMAC agrees with Python; async TX returns to RX;"
              << " 50ms GPIO; identical retries produce one pulse; new sequence repeats pulse\n";
}
