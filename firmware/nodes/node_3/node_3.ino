// HTCC-AB01/ASR6501, node 3. Private settings are generated locally.
#include "node_config.h"
#if CHACAICO_NODE_ID != 3
#error "This sketch must be configured for node 3"
#endif
// Standard valve profile: 50 ms default, configurable up to 200 ms.
#define CHACAICO_MAX_PULSE_MS 200
#include <ChacaicoNode.h>
