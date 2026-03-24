FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# ── System packages ──────────────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y \
    vim net-tools iproute2 iputils-ping \
    openssh-server sudo curl wget \
    cmake build-essential python3-pip \
    libboost-dev libopencv-dev libyaml-cpp-dev \
    libgrpc++-dev protobuf-compiler-grpc libprotobuf-dev pkg-config \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── SSH ──────────────────────────────────────────────────────────────────────
RUN mkdir /var/run/sshd && \
    echo 'root:root' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' /etc/pam.d/sshd

EXPOSE 22

# ── Upgrade pip / setuptools so pyproject.toml [project] table is recognised ─
RUN pip install --upgrade pip setuptools wheel

# ── Copy workspace ──────────────────────────────────────────────────────
WORKDIR /root
COPY . /root/dobot_quad_sdk/

# ── DDS middleware ──────────────────────────────────────────────────────────
WORKDIR /root/dobot_quad_sdk/dist
RUN dpkg -i dds-middleware-with-thirdparty*.deb && \
    pip install dds_middleware_python-*.whl
ENV CYCLONEDDS_HOME="/usr/local/"

# ── Python packages ─────────────────────────────────────────────────────────
RUN pip install cyclonedds opencv-python

# ── High-level Python SDK (dobot_quad) ──────────────────────────────────────
WORKDIR /root/dobot_quad_sdk/high_level/python
RUN pip install .

# ── High-level C++ build ────────────────────────────────────────────────────
WORKDIR /root/dobot_quad_sdk/high_level/cpp
RUN mkdir -p build && cd build && cmake .. && make -j

# ── Low-level C++ build ─────────────────────────────────────────────────────
WORKDIR /root/dobot_quad_sdk/low_level/cpp
RUN mkdir -p build && cd build && cmake .. && make -j

WORKDIR /root/dobot_quad_sdk
CMD ["/bin/bash"]
