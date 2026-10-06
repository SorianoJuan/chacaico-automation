#pragma once
#include <cassert>
#include <cstdint>
#include <cstring>
#include <utility>
#include <vector>
#define LOW 0
#define HIGH 1
#define OUTPUT 1
#define GPIO1 1
#define GPIO2 2
inline uint32_t clockMs=0;
inline int gpio[3]={0,0,0};
inline std::vector<std::pair<int,uint32_t>> highEdges;
inline std::vector<std::pair<uint32_t,uint32_t>> rgbEdges;
inline uint32_t millis(){return clockMs;}
inline void delay(uint32_t t){clockMs+=t;}
inline void pinMode(int,int){}
inline void digitalWrite(int pin,int value){
    gpio[pin]=value;
    assert(!(gpio[1] && gpio[2]));
    if(value) highEdges.push_back({pin,clockMs});
}
inline void turnOnRGB(uint32_t color,int){rgbEdges.push_back({color,clockMs});}
struct TestSerial {void begin(int){} void println(const char*){} template<class... Args> void printf(const char*,Args...){} };
inline TestSerial Serial;
