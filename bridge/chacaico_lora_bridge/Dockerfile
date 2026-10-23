FROM homeassistant/aarch64-addon-ssh:10.5.0
LABEL io.hass.version="0.5.2" io.hass.type="app" io.hass.arch="aarch64"
RUN apk add --no-cache python3 py3-libgpiod py3-cryptography py3-pip \
    && apk add --no-cache --virtual .spi-build gcc musl-dev python3-dev \
    && python3 -m venv --system-site-packages /opt/lora \
    && /opt/lora/bin/pip install --no-cache-dir 'spidev==3.8' 'paho-mqtt==2.1.0' \
    && apk del .spi-build
COPY bridge.py engine.py protocol.py radio.py /app/
ENTRYPOINT ["/opt/lora/bin/python", "-u", "/app/bridge.py"]
CMD []
