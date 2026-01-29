#!/bin/bash
# compile_grpc.sh - Regenerate gRPC Python code (after setup.sh)

set -e

# Check if dependencies are installed
if ! python3 -c "import grpc_tools" 2>/dev/null; then
    echo "Dependencies not installed. Run ./setup.sh first"
    exit 1
fi

echo "Generating gRPC Python code..."
python3 -m grpc_tools.protoc \
    -I./ \
    --python_out=./proto \
    --grpc_python_out=./proto \
    grpc_service.proto

echo "✓ Done! Generated files are in ./proto/"