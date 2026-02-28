#ifndef MOCK_CAM_H
#define MOCK_CAM_H

#ifdef _WIN32
    #ifdef MOCK_CAM_EXPORTS
        #define MOCK_CAM_API __declspec(dllexport)
    #else
        #define MOCK_CAM_API __declspec(dllimport)
    #endif
#else
    #define MOCK_CAM_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

MOCK_CAM_API void GenerateMockToolpath(
    double x_min, double x_max, 
    double y_min, double y_max, 
    double z_max,
    double** out_points, 
    int* out_count
);

MOCK_CAM_API void GenerateSurfaceToolpath(
    const char* step_data,
    int step_data_size,
    double step_u,
    double step_v,
    int toolpath_mode,
    int num_paths,
    int start_direction,
    double** out_points,
    int* out_count
);

MOCK_CAM_API void FreeMockToolpath(double* points);

#ifdef __cplusplus
}
#endif

#endif
