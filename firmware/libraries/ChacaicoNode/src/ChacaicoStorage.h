#pragma once
#include "ChacaicoProtocol.h"

namespace Chacaico {
// Three separate ASR6501 user-flash rows. Row 3 is reserved by the manufacturer.
// Each write touches only an inactive row and is read back before becoming current.
struct ConfigStore {
    uint32_t generation=0, boot=0, revision=1;
    uint16_t sleep=0, pulse=50, listen=3000, awake=10000;
    uint8_t power=0;
    int slot=-1;
    bool healthy=false;
    static uint32_t checksum(const uint8_t *p, size_t n) {
        uint32_t crc=0xffffffff;
        for (size_t i=0;i<n;++i) {
            crc^=p[i];
            for(uint8_t j=0;j<8;++j) crc=(crc>>1)^((crc&1)?0xedb88320:0);
        }
        return ~crc;
    }
    bool readSlot(int i,uint8_t *record) {
        return FLASH_read_at(CY_SFLASH_USERBASE+256*i,record,40)==0;
    }
    bool valid(const uint8_t *r) {
        const bool legacy=read16(r+6)==1;
        return !memcmp(r,"CCF2",4) && read16(r+4)==CHACAICO_NODE_ID
            && (legacy || read16(r+6)==2) && read32(r+8)>0 && read32(r+12)>0
            && read32(r+16)>0
            && validConfig(read16(r+20),read16(r+22),legacy?0:r[24],
                           legacy?3000:read16(r+25),legacy?10000:read16(r+27))
            && (legacy ? read32(r+28)==checksum(r,28) : read32(r+36)==checksum(r,36));
    }
    bool persist(uint32_t nextBoot,uint32_t rev,uint16_t sec,uint16_t ms,
                 uint8_t dbm=0,uint16_t listenMs=3000,uint16_t awakeMs=10000) {
        if (generation==0xffffffff || !nextBoot || !rev || !validConfig(sec,ms,dbm,listenMs,awakeMs)) return false;
        uint8_t record[40]={0}, check[40];
        memcpy(record,"CCF2",4);write16(record+4,CHACAICO_NODE_ID);write16(record+6,2);
        write32(record+8,generation+1);write32(record+12,nextBoot);write32(record+16,rev);
        write16(record+20,sec);write16(record+22,ms);record[24]=dbm;
        write16(record+25,listenMs);write16(record+27,awakeMs);
        write32(record+36,checksum(record,36));
        const int next=(slot+1)%3;
        if (FLASH_update(CY_SFLASH_USERBASE+256*next,record,sizeof(record))!=0
            || !readSlot(next,check) || memcmp(record,check,sizeof(record))) return false;
        ++generation;boot=nextBoot;revision=rev;sleep=sec;pulse=ms;
        power=dbm;listen=listenMs;awake=awakeMs;slot=next;
        return true;
    }
    void begin() {
        uint8_t record[40]; bool damaged=false, readFailed=false;
        for(int i=0;i<3;++i) {
            if (!readSlot(i,record)) { readFailed=true;continue; }
            if (!memcmp(record,"CCF2",4) && !valid(record)) damaged=true;
            if (valid(record) && read32(record+8)>generation) {
                generation=read32(record+8);boot=read32(record+12);revision=read32(record+16);
                sleep=read16(record+20);pulse=read16(record+22);slot=i;
                const bool legacy=read16(record+6)==1;
                power=legacy?0:record[24];listen=legacy?3000:read16(record+25);
                awake=legacy?10000:read16(record+27);
            }
        }
        // Never reuse an authenticated boot session if persistence cannot be proven.
        healthy=!readFailed && !(slot<0 && damaged) && boot!=0xffffffff
            && persist(boot+1,revision,sleep,pulse,power,listen,awake);
    }
    Status apply(uint32_t rev,uint16_t sec,uint16_t ms,uint8_t dbm=0,uint16_t listenMs=3000,uint16_t awakeMs=10000) {
        if (!healthy) return STORE_FAILED;
        if (!validConfig(sec,ms,dbm,listenMs,awakeMs)) return INVALID;
        if (rev==revision)
            return sec==sleep && ms==pulse && dbm==power && listenMs==listen && awakeMs==awake ? OK : CONFLICT;
        if (revision==0xffffffff || rev!=revision+1) return CONFLICT;
        return persist(boot,rev,sec,ms,dbm,listenMs,awakeMs) ? OK : STORE_FAILED;
    }
};
}
