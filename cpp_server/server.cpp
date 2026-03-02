#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include "../cam_service.grpc.pb.h"
#include "../mock_cam/mock_cam.h"
#include <iostream>
#include <thread>
#include <unordered_map>
#include <mutex>

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;
using cam::CamCalculationService;
using cam::CalculationRequest;
using cam::CalculationResponse;
using cam::SurfaceCalculationRequest;

class CamServiceImpl final : public CamCalculationService::Service {
private:
    std::unordered_map<std::string, std::string> model_cache_;  // hash -> step_data
    std::mutex cache_mutex_;

public:
    Status CalculateToolpath(ServerContext* context,
                           const CalculationRequest* request,
                           CalculationResponse* response) override {
        double* out_points = nullptr;
        int out_count = 0;
        
        GenerateMockToolpath(
            request->x_min(), request->x_max(),
            request->y_min(), request->y_max(),
            request->z_max(),
            &out_points, &out_count
        );
        
        size_t size = out_count * 3 * sizeof(double);
        response->set_raw_vertices(reinterpret_cast<const char*>(out_points), size);
        response->set_point_count(out_count);
        
        FreeMockToolpath(out_points);
        
        std::cout << "[BoxToolpath] mode=grid"
                  << " x=[" << request->x_min() << "," << request->x_max() << "]"
                  << " y=[" << request->y_min() << "," << request->y_max() << "]"
                  << " z=" << request->z_max()
                  << " | " << out_count << " pts, " << size << " bytes" << std::endl;
        
        return Status::OK;
    }
    
    Status CalculateSurfaceToolpath(ServerContext* context,
                                   const SurfaceCalculationRequest* request,
                                   CalculationResponse* response) override {
        double* out_points = nullptr;
        double* out_normals = nullptr;
        int out_count = 0;
        
        std::string step_data;
        const std::string& model_hash = request->model_hash();
        
        // 缓存逻辑
        if (!model_hash.empty()) {
            std::lock_guard<std::mutex> lock(cache_mutex_);
            auto it = model_cache_.find(model_hash);
            
            if (it != model_cache_.end()) {
                // 缓存命中
                step_data = it->second;
                std::cout << "[Cache HIT] hash=" << model_hash << std::endl;
            } else {
                // 缓存未命中，存储新数据
                step_data = request->step_data();
                if (!step_data.empty()) {
                    model_cache_[model_hash] = step_data;
                    std::cout << "[Cache MISS] hash=" << model_hash << " size=" << step_data.size() << "B" << std::endl;
                } else {
                    return Status(grpc::StatusCode::INVALID_ARGUMENT, "Model hash provided but no step_data");
                }
            }
        } else {
            // 无哈希，直接使用数据
            step_data = request->step_data();
        }
        
        if (step_data.empty()) {
            return Status(grpc::StatusCode::INVALID_ARGUMENT, "No step data provided");
        }
        
        int mode = request->toolpath_mode();
        int num_paths = request->num_paths();
        int start_direction = request->start_direction();
        
        GenerateSurfaceToolpath(
            step_data.data(),
            step_data.size(),
            request->step_u(),
            request->step_v(),
            mode,
            num_paths,
            start_direction,
            request->face_index(),
            &out_points, &out_count, &out_normals
        );
        
        if (out_points == nullptr || out_count == 0) {
            return Status(grpc::StatusCode::INVALID_ARGUMENT, "Failed to parse STEP file or no faces found");
        }
        
        size_t size = out_count * 3 * sizeof(double);
        response->set_raw_vertices(reinterpret_cast<const char*>(out_points), size);
        
        if (out_normals != nullptr) {
            response->set_raw_normals(reinterpret_cast<const char*>(out_normals), size);
        }
        
        response->set_point_count(out_count);
        
        FreeMockToolpath(out_points);
        if (out_normals != nullptr) {
            FreeMockToolpath(out_normals);
        }
        
        const char* mode_name = (mode == 1) ? "contour" : "raster";
        const char* dir_name = (start_direction == 0) ? "U" : "V";
        std::cout << "[SurfaceToolpath] mode=" << mode_name
                  << " dir=" << dir_name
                  << " num_paths=" << num_paths
                  << " | " << out_count << " pts, " << size << " bytes" << std::endl;
        
        return Status::OK;
    }
};

int main() {
    std::string server_address("0.0.0.0:50051");
    CamServiceImpl service;
    
    ServerBuilder builder;
    
    // 设置最大消息大小为100MB
    builder.SetMaxReceiveMessageSize(100 * 1024 * 1024);
    builder.SetMaxSendMessageSize(100 * 1024 * 1024);
    
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    
    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "Server listening on " << server_address << std::endl;
    std::cout << "Max message size: 100 MB" << std::endl;
    std::cout << "Type 'exit' to shutdown server" << std::endl;
    
    std::thread server_thread([&server]() {
        server->Wait();
    });
    
    std::string input;
    while (std::getline(std::cin, input)) {
        if (input == "exit") {
            std::cout << "Shutting down server..." << std::endl;
            server->Shutdown();
            break;
        }
    }
    
    server_thread.join();
    return 0;
}
