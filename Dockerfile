FROM ubuntu:22.04

# 设置非交互式安装
ENV DEBIAN_FRONTEND=noninteractive

# 更新软件源并安装基本工具
RUN apt-get update && \
    apt-get install -y \
    vim \
    net-tools \
    iproute2 \
    iputils-ping \
    openssh-server \
    sudo \
    curl \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 配置 SSH
RUN mkdir /var/run/sshd && \
    echo 'root:root' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' /etc/pam.d/sshd


RUN apt-get update && \ 
    apt-get install -y \
    cmake \
    build-essential \
    python3-pip \
    libboost-dev \
    libopencv-dev \
    libyaml-cpp-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*


# 暴露 SSH 端口
EXPOSE 22

# 设置工作目录
WORKDIR /root

# 复制工作区文件到镜像中
COPY . /root/dobot_quad_sdk/

# 安装 DDS 中间件和 Python 包
WORKDIR /root/dobot_quad_sdk/dist
RUN dpkg -i dds-middleware-with-thirdparty*.deb && \
    pip install dds_middleware_python-*.whl

# 设置环境变量并安装 cyclonedds
ENV CYCLONEDDS_HOME="/usr/local/"
RUN pip install cyclonedds

# install opencv
RUN pip install opencv-python

# install grpc related
RUN apt-get update && \
    apt-get install -y \
    libgrpc++-dev \
    protobuf-compiler-grpc \
    libprotobuf-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install grpcio grpcio-tools

# 切换回工作目录
WORKDIR /root

# 默认启动 bash
CMD ["/bin/bash"]
