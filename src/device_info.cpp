#include <cuda_runtime.h>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include "pp_infer/cuda_resources.hpp"

// Uses CUDA's visible-device mapping, the same mapping as trtexec and the node.
int main() {
  try {
    int count{}, driver{}, runtime{};
    pp_infer::cuda_check(cudaGetDeviceCount(&count), "enumerate GPUs (check driver/container GPU access)");
    if (!count) throw std::runtime_error("No visible NVIDIA CUDA GPU");
    pp_infer::cuda_check(cudaSetDevice(0), "select first visible GPU");
    cudaDeviceProp gpu{};
    pp_infer::cuda_check(cudaGetDeviceProperties(&gpu, 0), "inspect selected GPU");
    if (gpu.major * 10 + gpu.minor < 75)
      throw std::runtime_error("TensorRT 10.16 requires compute capability 7.5 or newer; use a separate legacy stack for this GPU");
    pp_infer::cuda_check(cudaDriverGetVersion(&driver), "inspect CUDA driver");
    pp_infer::cuda_check(cudaRuntimeGetVersion(&runtime), "inspect CUDA runtime");
    std::cout << "GPU=" << gpu.name << "\nCC=" << gpu.major << '.' << gpu.minor << "\nUUID=";
    for (unsigned char byte : gpu.uuid.bytes)
      std::cout << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(byte);
    std::cout << std::dec << "\nCUDA_DRIVER=" << driver << "\nCUDA_RUNTIME=" << runtime << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "GPU startup check failed: " << error.what() << '\n';
    return 1;
  }
}
