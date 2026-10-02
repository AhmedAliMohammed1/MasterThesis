#pragma once
#include <cuda_runtime.h>
#include <stdexcept>
#include <string>

namespace pp_infer {
inline void cuda_check(cudaError_t status, const char* operation) {
  if (status != cudaSuccess)
    throw std::runtime_error(std::string(operation) + ": " + cudaGetErrorString(status));
}
class CudaStream {
 public:
  CudaStream() { cuda_check(cudaStreamCreateWithFlags(&value_, cudaStreamNonBlocking), "create stream"); }
  ~CudaStream() { if (value_) { cudaStreamSynchronize(value_); cudaStreamDestroy(value_); } }
  CudaStream(const CudaStream&) = delete;
  CudaStream& operator=(const CudaStream&) = delete;
  cudaStream_t get() const { return value_; }
 private:
  cudaStream_t value_{};
};
class DeviceBuffer {
 public:
  explicit DeviceBuffer(std::size_t bytes) { cuda_check(cudaMalloc(&value_, bytes), "allocate device buffer"); }
  ~DeviceBuffer() { if (value_) cudaFree(value_); }
  DeviceBuffer(const DeviceBuffer&) = delete;
  DeviceBuffer& operator=(const DeviceBuffer&) = delete;
  void* get() const { return value_; }
 private:
  void* value_{};
};
}  // namespace pp_infer
