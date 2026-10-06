FROM homeassistant/aarch64-addon-ssh:10.5.0
LABEL io.hass.version="0.1.1" io.hass.type="app" io.hass.arch="aarch64"
RUN apk add --no-cache python3 py3-libgpiod py3-pip \
    && apk add --no-cache --virtual .spi-build gcc musl-dev python3-dev \
    && python3 -m venv --system-site-packages /opt/lora \
    && /opt/lora/bin/pip install --no-cache-dir 'spidev==3.8' \
    && apk del .spi-build
COPY probe-sx1262.py /probe-sx1262.py
COPY run.sh /run-probe.sh
ENTRYPOINT ["/bin/sh", "/run-probe.sh"]
CMD []
