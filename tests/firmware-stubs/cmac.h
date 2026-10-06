// Test stub for GPIO/timing only; AES-CMAC is tested separately in Python.
#pragma once
struct AES_CMAC_CTX {};
inline void AES_CMAC_Init(AES_CMAC_CTX*){}
inline void AES_CMAC_SetKey(AES_CMAC_CTX*,const uint8_t*){}
inline void AES_CMAC_Update(AES_CMAC_CTX*,const uint8_t*,unsigned){}
inline void AES_CMAC_Final(uint8_t* result,AES_CMAC_CTX*){memset(result,0xA5,16);}
