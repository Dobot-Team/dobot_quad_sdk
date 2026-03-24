#!/usr/bin/env python3
"""Custom build hook: generates gRPC Python bindings from grpc_service.proto.

All project metadata lives in pyproject.toml.  This file only provides the
build_py override that runs protoc before packaging.
"""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


ROOT = Path(__file__).resolve().parent
PKG_DIR = ROOT / "dobot_quad"
PROTO_SRC = PKG_DIR / "proto" / "grpc_service.proto"
PROTO_OUT = PKG_DIR / "proto"
GRPC_PY_FILE = PROTO_OUT / "grpc_service_pb2_grpc.py"


def generate_grpc_sources() -> None:
    """Run grpc_tools.protoc and patch the generated import to be relative."""
    try:
        from grpc_tools import protoc
    except ImportError as exc:
        raise RuntimeError(
            "grpcio-tools is required to build the Python SDK. "
            "Please install it and retry."
        ) from exc

    PROTO_OUT.mkdir(parents=True, exist_ok=True)

    result = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{PROTO_OUT}",
            f"--python_out={PROTO_OUT}",
            f"--grpc_python_out={PROTO_OUT}",
            str(PROTO_SRC),
        ]
    )
    if result != 0:
        raise RuntimeError(f"Failed to generate gRPC Python code from {PROTO_SRC}")

    # Patch: absolute import → relative import inside the proto package
    text = GRPC_PY_FILE.read_text()
    old = "import grpc_service_pb2 as grpc__service__pb2"
    new = "from . import grpc_service_pb2 as grpc__service__pb2"
    if old in text:
        GRPC_PY_FILE.write_text(text.replace(old, new, 1))


class BuildPyCommand(build_py):
    """Generate gRPC sources before the standard build_py runs."""

    def run(self):
        generate_grpc_sources()
        super().run()


setup(cmdclass={"build_py": BuildPyCommand})
