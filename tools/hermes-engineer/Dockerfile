ARG HERMES_BASE
FROM ${HERMES_BASE}

LABEL org.openhtpc.purpose="isolated-hermes-engineering"

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libinih-dev \
        libsdl2-dev \
        libsdl2-image-dev \
        libsdl2-ttf-dev \
        meson \
        ninja-build \
        pkg-config \
        python3-pytest
