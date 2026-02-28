#include "mock_cam.h"
#include <cstdlib>
#include <cmath>
#include <fstream>
#include <vector>
#include <algorithm>

// OpenCASCADE headers
#include <STEPControl_Reader.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Wire.hxx>
#include <TopExp_Explorer.hxx>
#include <BRep_Tool.hxx>
#include <BRepTools.hxx>
#include <BRepOffsetAPI_MakeOffset.hxx>
#include <BRepAdaptor_CompCurve.hxx>
#include <GCPnts_UniformAbscissa.hxx>
#include <GeomAdaptor_Surface.hxx>
#include <GeomAbs_JoinType.hxx>
#include <GProp_GProps.hxx>
#include <BRepGProp.hxx>
#include <gp_Pnt.hxx>

extern "C" void GenerateMockToolpath(
    double x_min, double x_max,
    double y_min, double y_max,
    double z_max,
    double** out_points,
    int* out_count
) {
    const int rows = 10;
    const int cols = 10;
    const int total_points = rows * cols;
    
    double* points = (double*)malloc(total_points * 3 * sizeof(double));
    
    double x_step = (x_max - x_min) / (cols - 1);
    double y_step = (y_max - y_min) / (rows - 1);
    
    int idx = 0;
    for (int i = 0; i < rows; ++i) {
        double y = y_min + i * y_step;
        
        if (i % 2 == 0) {
            for (int j = 0; j < cols; ++j) {
                points[idx++] = x_min + j * x_step;
                points[idx++] = y;
                points[idx++] = z_max;
            }
        } else {
            for (int j = cols - 1; j >= 0; --j) {
                points[idx++] = x_min + j * x_step;
                points[idx++] = y;
                points[idx++] = z_max;
            }
        }
    }
    
    *out_points = points;
    *out_count = total_points;
}

extern "C" void FreeMockToolpath(double* points) {
    free(points);
}

extern "C" void GenerateSurfaceToolpath(
    const char* step_data,
    int step_data_size,
    double step_u,
    double step_v,
    int toolpath_mode,
    int num_paths,
    int start_direction,
    int face_index,
    double** out_points,
    int* out_count
) {
    const char* temp_file = "/tmp/temp_step_input.step";
    std::ofstream ofs(temp_file, std::ios::binary);
    ofs.write(step_data, step_data_size);
    ofs.close();
    
    STEPControl_Reader reader;
    
    if (reader.ReadFile(temp_file) != IFSelect_RetDone) {
        *out_points = nullptr;
        *out_count = 0;
        return;
    }
    
    reader.TransferRoots();
    TopoDS_Shape shape = reader.OneShape();
    
    TopoDS_Face target_face;
    
    // 如果指定了face_index，使用指定的面；否则选择最大面
    if (face_index >= 0) {
        int current_index = 0;
        for (TopExp_Explorer exp(shape, TopAbs_FACE); exp.More(); exp.Next()) {
            if (current_index == face_index) {
                target_face = TopoDS::Face(exp.Current());
                break;
            }
            current_index++;
        }
    } else {
        // 自动选择最大面
        double max_area = 0.0;
        for (TopExp_Explorer exp(shape, TopAbs_FACE); exp.More(); exp.Next()) {
            TopoDS_Face face = TopoDS::Face(exp.Current());
            GProp_GProps props;
            BRepGProp::SurfaceProperties(face, props);
            double area = props.Mass();
            
            if (area > max_area) {
                max_area = area;
                target_face = face;
            }
        }
    }
    
    if (target_face.IsNull()) {
        *out_points = nullptr;
        *out_count = 0;
        return;
    }
    
    if (toolpath_mode == 1) {
        // 环切模式：在参数空间进行2D offset
        Handle(Geom_Surface) surface = BRep_Tool::Surface(target_face);
        
        if (surface.IsNull()) {
            *out_points = nullptr;
            *out_count = 0;
            return;
        }
        
        Standard_Real u_min, u_max, v_min, v_max;
        BRepTools::UVBounds(target_face, u_min, u_max, v_min, v_max);
        
        double u_range = u_max - u_min;
        double v_range = v_max - v_min;
        
        // 分别计算U和V方向的收缩步长
        double shrink_step_u = u_range / (2.0 * (num_paths + 1));
        double shrink_step_v = v_range / (2.0 * (num_paths + 1));
        
        // 采样密度：按参数空间单位长度的采样数
        const double density = 20.0;
        
        std::vector<double> all_points;
        
        for (int layer = 0; layer < num_paths; ++layer) {
            double shrink_u = layer * shrink_step_u;
            double shrink_v = layer * shrink_step_v;
            
            double u0 = u_min + shrink_u;
            double u1 = u_max - shrink_u;
            double v0 = v_min + shrink_v;
            double v1 = v_max - shrink_v;
            
            if (u1 <= u0 || v1 <= v0) break;
            
            double du = u1 - u0;
            double dv = v1 - v0;
            
            // 每条边按自身参数长度独立计算采样数
            int nu = std::max(2, (int)(du * density));
            int nv = std::max(2, (int)(dv * density));
            
            // 底边 (v=v0, u: u0->u1)
            for (int i = 0; i < nu; ++i) {
                double u = u0 + du * i / nu;
                gp_Pnt pnt;
                surface->D0(u, v0, pnt);
                all_points.push_back(pnt.X());
                all_points.push_back(pnt.Y());
                all_points.push_back(pnt.Z());
            }
            
            // 右边 (u=u1, v: v0->v1)
            for (int i = 0; i < nv; ++i) {
                double v = v0 + dv * i / nv;
                gp_Pnt pnt;
                surface->D0(u1, v, pnt);
                all_points.push_back(pnt.X());
                all_points.push_back(pnt.Y());
                all_points.push_back(pnt.Z());
            }
            
            // 顶边 (v=v1, u: u1->u0)
            for (int i = 0; i < nu; ++i) {
                double u = u1 - du * i / nu;
                gp_Pnt pnt;
                surface->D0(u, v1, pnt);
                all_points.push_back(pnt.X());
                all_points.push_back(pnt.Y());
                all_points.push_back(pnt.Z());
            }
            
            // 左边 (u=u0, v: v1->v0)
            for (int i = 0; i < nv; ++i) {
                double v = v1 - dv * i / nv;
                gp_Pnt pnt;
                surface->D0(u0, v, pnt);
                all_points.push_back(pnt.X());
                all_points.push_back(pnt.Y());
                all_points.push_back(pnt.Z());
            }
            
            // 闭合：重复起点
            gp_Pnt pnt0;
            surface->D0(u0, v0, pnt0);
            all_points.push_back(pnt0.X());
            all_points.push_back(pnt0.Y());
            all_points.push_back(pnt0.Z());
        }
        
        if (all_points.empty()) {
            *out_points = nullptr;
            *out_count = 0;
            return;
        }
        
        int total_points = all_points.size() / 3;
        double* points = (double*)malloc(all_points.size() * sizeof(double));
        std::copy(all_points.begin(), all_points.end(), points);
        
        *out_points = points;
        *out_count = total_points;
        
    } else {
        // 行切模式
        Handle(Geom_Surface) surface = BRep_Tool::Surface(target_face);
        
        if (surface.IsNull()) {
            *out_points = nullptr;
            *out_count = 0;
            return;
        }
        
        Standard_Real u_min, u_max, v_min, v_max;
        BRepTools::UVBounds(target_face, u_min, u_max, v_min, v_max);
        
        int u_steps = (int)((u_max - u_min) / step_u) + 1;
        int v_steps = (int)((v_max - v_min) / step_v) + 1;
        int total_points = u_steps * v_steps;
        
        double* points = (double*)malloc(total_points * 3 * sizeof(double));
        
        int idx = 0;
        
        if (start_direction == 0) {
            // U向扫描：外层U，内层V
            for (int j = 0; j < u_steps; ++j) {
                double u = std::min(u_min + j * step_u, u_max);
                
                if (j % 2 == 0) {
                    for (int i = 0; i < v_steps; ++i) {
                        double v = std::min(v_min + i * step_v, v_max);
                        
                        gp_Pnt pnt;
                        surface->D0(u, v, pnt);
                        points[idx++] = pnt.X();
                        points[idx++] = pnt.Y();
                        points[idx++] = pnt.Z();
                    }
                } else {
                    for (int i = v_steps - 1; i >= 0; --i) {
                        double v = std::min(v_min + i * step_v, v_max);
                        
                        gp_Pnt pnt;
                        surface->D0(u, v, pnt);
                        points[idx++] = pnt.X();
                        points[idx++] = pnt.Y();
                        points[idx++] = pnt.Z();
                    }
                }
            }
        } else {
            // V向扫描：外层V，内层U
            for (int i = 0; i < v_steps; ++i) {
                double v = std::min(v_min + i * step_v, v_max);
                
                if (i % 2 == 0) {
                    for (int j = 0; j < u_steps; ++j) {
                        double u = std::min(u_min + j * step_u, u_max);
                        
                        gp_Pnt pnt;
                        surface->D0(u, v, pnt);
                        points[idx++] = pnt.X();
                        points[idx++] = pnt.Y();
                        points[idx++] = pnt.Z();
                    }
                } else {
                    for (int j = u_steps - 1; j >= 0; --j) {
                        double u = std::min(u_min + j * step_u, u_max);
                        
                        gp_Pnt pnt;
                        surface->D0(u, v, pnt);
                        points[idx++] = pnt.X();
                        points[idx++] = pnt.Y();
                        points[idx++] = pnt.Z();
                    }
                }
            }
        }
        
        *out_points = points;
        *out_count = total_points;
    }
}
