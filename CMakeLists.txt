# SPDX-FileCopyrightText: Copyright (c) 2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

cmake_minimum_required(VERSION 3.18)
project(pp_infer LANGUAGES CXX)

include(CTest)
option(PP_BUILD_RUNTIME "Build the CUDA/TensorRT ROS inference executable" ON)
option(PP_BUILD_ROS_ADAPTER "Build ROS adapters without requiring GPU inference" ${PP_BUILD_RUNTIME})
option(PP_ENABLE_SANITIZERS "Enable address/undefined behavior sanitizers" OFF)

add_library(pp_core src/postprocess.cpp)
target_compile_features(pp_core PUBLIC cxx_std_17)
target_include_directories(pp_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(pp_core PRIVATE -Wall -Wextra -Wpedantic)
endif()
if(PP_ENABLE_SANITIZERS)
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    message(FATAL_ERROR "PP_ENABLE_SANITIZERS requires GCC or Clang")
  endif()
  target_compile_options(pp_core PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(pp_core PUBLIC -fsanitize=address,undefined)
endif()

if(BUILD_TESTING)
  add_executable(test_postprocess tests/core/test_postprocess.cpp)
  target_link_libraries(test_postprocess PRIVATE pp_core)
  add_test(NAME postprocess COMMAND test_postprocess)
  add_executable(test_output_contract tests/runtime/test_output_contract.cpp)
  target_link_libraries(test_output_contract PRIVATE pp_core)
  add_test(NAME output_contract COMMAND test_output_contract)
endif()

if(PP_BUILD_RUNTIME OR PP_BUILD_ROS_ADAPTER)
  # Ubuntu's pcl_conversions exports PCL/VTK, whose MPI target requires C.
  # Keep this toolchain discovery out of the standalone CPU-only path.
  enable_language(C)
  find_package(ament_cmake REQUIRED)
  find_package(rclcpp REQUIRED)
  find_package(rcl_interfaces REQUIRED)
  find_package(std_msgs REQUIRED)
  find_package(sensor_msgs REQUIRED)
  find_package(geometry_msgs REQUIRED)
  find_package(vision_msgs REQUIRED)
  find_package(pcl_conversions REQUIRED)
  find_package(PCL REQUIRED COMPONENTS common)
  add_library(pp_ros_adapter src/pointcloud_adapter.cpp)
  target_link_libraries(pp_ros_adapter PUBLIC pp_core ${PCL_LIBRARIES})
  target_include_directories(pp_ros_adapter SYSTEM PUBLIC ${PCL_INCLUDE_DIRS})
  ament_target_dependencies(pp_ros_adapter PUBLIC rclcpp rcl_interfaces std_msgs
    sensor_msgs geometry_msgs vision_msgs pcl_conversions)
  if(BUILD_TESTING)
    add_executable(test_ros_adapter tests/ros/test_ros_adapter.cpp)
    target_link_libraries(test_ros_adapter PRIVATE pp_ros_adapter)
    add_test(NAME ros_adapter_data COMMAND test_ros_adapter --data-only)
    # Keep distribution-provided ROS middleware/allocators outside instrumented
    # data checks. Local node parameter behavior is tested in the normal build.
    if(NOT PP_ENABLE_SANITIZERS)
      add_test(NAME ros_adapter_parameters COMMAND test_ros_adapter --parameters-only)
    endif()
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/ros-logs")
    if(NOT PP_ENABLE_SANITIZERS)
      set_tests_properties(ros_adapter_parameters PROPERTIES
        ENVIRONMENT "ROS_LOG_DIR=${CMAKE_CURRENT_BINARY_DIR}/ros-logs;ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST")
    endif()
  endif()
endif()

if(PP_BUILD_RUNTIME)
  find_package(CUDAToolkit REQUIRED)
  set(TENSORRT_ROOT "$ENV{TENSORRT_ROOT}" CACHE PATH "Root of the selected TensorRT installation")
  find_path(TENSORRT_INCLUDE_DIR NvInfer.h HINTS ${TENSORRT_ROOT}
    PATH_SUFFIXES include include/${CMAKE_LIBRARY_ARCHITECTURE})
  foreach(component nvinfer nvinfer_plugin)
    find_library(TENSORRT_${component}_LIBRARY NAMES ${component}
      HINTS ${TENSORRT_ROOT} PATH_SUFFIXES lib lib64 lib/${CMAKE_LIBRARY_ARCHITECTURE})
    if(NOT TENSORRT_${component}_LIBRARY)
      message(FATAL_ERROR "Missing TensorRT ${component}; set TENSORRT_ROOT or use -DPP_BUILD_RUNTIME=OFF")
    endif()
    add_library(TensorRT::${component} UNKNOWN IMPORTED)
    set_target_properties(TensorRT::${component} PROPERTIES
      IMPORTED_LOCATION "${TENSORRT_${component}_LIBRARY}"
      INTERFACE_INCLUDE_DIRECTORIES "${TENSORRT_INCLUDE_DIR}")
  endforeach()
  if(NOT TENSORRT_INCLUDE_DIR)
    message(FATAL_ERROR "Missing NvInfer.h; set TENSORRT_ROOT or use -DPP_BUILD_RUNTIME=OFF")
  endif()
  # Prepared for TensorRT 10; target SDK/engine execution remains a W01/W04 gate.
  # SDK packages may define the major version through another macro. Ask the
  # preprocessor rather than parsing a numeric literal from the header.
  include(CheckCXXSourceCompiles)
  set(saved_required_includes "${CMAKE_REQUIRED_INCLUDES}")
  set(CMAKE_REQUIRED_INCLUDES "${TENSORRT_INCLUDE_DIR}")
  unset(PP_TENSORRT10_HEADERS CACHE)
  check_cxx_source_compiles("#include <NvInferVersion.h>
    #if NV_TENSORRT_MAJOR != 10
    #error TensorRT 10 required
    #endif
    int main() { return 0; }" PP_TENSORRT10_HEADERS)
  set(CMAKE_REQUIRED_INCLUDES "${saved_required_includes}")
  if(NOT PP_TENSORRT10_HEADERS)
    message(FATAL_ERROR "Runtime targets TensorRT 10. Select the matching SDK or disable PP_BUILD_RUNTIME.")
  endif()
  add_library(pp_runtime src/pointpillar.cpp)
  add_executable(pp_device_info src/device_info.cpp)
  target_include_directories(pp_device_info PRIVATE include)
  target_link_libraries(pp_device_info PRIVATE CUDA::cudart)
  target_link_libraries(pp_runtime PUBLIC pp_core CUDA::cudart TensorRT::nvinfer
    TensorRT::nvinfer_plugin)
  if(BUILD_TESTING)
    add_executable(runtime_smoke tests/runtime/runtime_smoke.cpp)
    target_link_libraries(runtime_smoke PRIVATE pp_runtime)
  endif()
  add_executable(pp_infer src/pp_inference_node.cpp)
  target_link_libraries(pp_infer PRIVATE pp_runtime pp_ros_adapter ${PCL_LIBRARIES})
  target_include_directories(pp_infer SYSTEM PRIVATE ${PCL_INCLUDE_DIRS})
  ament_target_dependencies(pp_infer PUBLIC rclcpp std_msgs sensor_msgs geometry_msgs
    vision_msgs pcl_conversions)
  install(TARGETS pp_infer pp_device_info DESTINATION lib/${PROJECT_NAME})
  install(TARGETS pp_core pp_runtime ARCHIVE DESTINATION lib LIBRARY DESTINATION lib)
  install(DIRECTORY include/ DESTINATION include)
  install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})
endif()

if(PP_BUILD_RUNTIME OR PP_BUILD_ROS_ADAPTER)
  ament_package()
endif()
