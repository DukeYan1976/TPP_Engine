#include <grpcpp/grpcpp.h>
#include <grpcpp/server_builder.h>
#include "../cam_service.grpc.pb.h"
#include "../mock_cam/mock_cam.h"
#include <iostream>
#include <thread>

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::Status;
using cam::CamCalculationService;
using cam::CalculationRequest;
using cam::CalculationResponse;
using cam::SurfaceCalculationRequest;

class CamServiceImpl final : public CamCalculationService::Service {
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
        int out_count = 0;
        
        const std::string& step_data = request->step_data();
        int mode = request->toolpath_mode();
        int num_paths = request->num_paths();
        int start_direction = request->start_direction();  // 0=U向, 1=V向
        
        GenerateSurfaceToolpath(
            step_data.data(),
            step_data.size(),
            request->step_u(),
            request->step_v(),
            mode,
            num_paths,
            start_direction,
            &out_points, &out_count
        );
        
        if (out_points == nullptr || out_count == 0) {
            return Status(grpc::StatusCode::INVALID_ARGUMENT, "Failed to parse STEP file or no faces found");
        }
        
        size_t size = out_count * 3 * sizeof(double);
        response->set_raw_vertices(reinterpret_cast<const char*>(out_points), size);
        response->set_point_count(out_count);
        
        FreeMockToolpath(out_points);
        
        const char* mode_name = (mode == 1) ? "contour" : "raster";
        const char* dir_name = (start_direction == 0) ? "U" : "V";
        std::cout << "[SurfaceToolpath] mode=" << mode_name
                  << " dir=" << dir_name
                  << " num_paths=" << num_paths
                  << " step_u=" << request->step_u()
                  << " step_v=" << request->step_v()
                  << " step_data=" << step_data.size() << "B"
                  << " | " << out_count << " pts, " << size << " bytes" << std::endl;
        
        return Status::OK;
    }
};

int main() {
    std::string server_address("0.0.0.0:50051");
    CamServiceImpl service;
    
    ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    
    std::unique_ptr<Server> server(builder.BuildAndStart());
    std::cout << "Server listening on " << server_address << std::endl;
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
