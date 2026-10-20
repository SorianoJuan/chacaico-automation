// HTCC-AB01/ASR6501, node 2. Private settings are generated locally.
#include "node_config.h"
#if CHACAICO_NODE_ID != 2
#error "This sketch must be configured for node 2"
#endif
// Bench measurements only: disconnect the external valve driver before using >200 ms.
#define CHACAICO_MAX_PULSE_MS 3000
#include <ChacaicoNode.h>
