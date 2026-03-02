#!/bin/bash
# 重新编译 proto 和 C++ 服务端

set -e

echo "=== 重新生成 Protobuf 文件 ==="
# Python
python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. cam_service.proto

# C++
protoc --cpp_out=. --grpc_out=. --plugin=protoc-gen-grpc=`which grpc_cpp_plugin` cam_service.proto
cp cam_service.pb.* cpp_server/
cp cam_service.grpc.pb.* cpp_server/

echo "=== 重新编译 mock_cam ==="
cd mock_cam
rm -rf build
mkdir build
cd build
cmake ..
make
cd ../..

echo "=== 重新编译 cpp_server ==="
cd cpp_server
rm -rf build
mkdir build
cd build
cmake ..
make
cd ../..

echo "=== 完成 ==="
echo "请运行以下命令启动服务端："
echo "  cd cpp_server/build && ./cam_server"
