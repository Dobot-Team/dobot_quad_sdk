#!/bin/bash

DOBOT_IP="192.168.5.2"
INTERFACE=$(ip route get $DOBOT_IP 2>/dev/null | grep -oP 'dev \K\S+')

if [ -z "$INTERFACE" ]; then
    echo "❌ Unable to detect network interface connected to board"
    exit 1
fi

echo "✓ Detected network interface: $INTERFACE"

cat > /tmp/cyclonedds_auto.xml << XMLEOF
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="https://cdds.io/config https://raw.githubusercontent.com/eclipse-cyclonedds/cyclonedds/master/etc/cyclonedds.xsd">
    <Domain Id="0">
        <General>
            <Interfaces>
                <NetworkInterface name="$INTERFACE" priority="default" multicast="true" />
            </Interfaces>
            <AllowMulticast>spdp</AllowMulticast>
            <MaxMessageSize>65500B</MaxMessageSize>
            <DontRoute>true</DontRoute>
        </General>
        <Discovery>
            <EnableTopicDiscoveryEndpoints>true</EnableTopicDiscoveryEndpoints>
        </Discovery>
        <Internal>
            <Watermarks>
                <WhcHigh>500kB</WhcHigh>
            </Watermarks>
        </Internal>
    </Domain>
</CycloneDDS>
XMLEOF

export CYCLONEDDS_URI="/tmp/cyclonedds_auto.xml"
echo "✓ Configured CYCLONEDDS_URI=/tmp/cyclonedds_auto.xml"
