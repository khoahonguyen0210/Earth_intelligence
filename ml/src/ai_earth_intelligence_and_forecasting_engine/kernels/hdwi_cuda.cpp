#include <ATen/cuda/CUDAContext.h>
#include <torch/extension.h>

extern "C" cudaError_t launch_hdwi(const float* t2m, const float* d2m,
                                   const float* u10, const float* v10,
                                   const float* surface_pressure,
                                   const float* temperature,
                                   const float* humidity, const float* u,
                                   const float* v, const float* pressure,
                                   float* out, int batch, int columns,
                                   int levels, cudaStream_t stream);

namespace {

void check(const torch::Tensor& tensor, const char* name) {
  TORCH_CHECK(tensor.is_cuda(), name, " must be on a CUDA device");
  TORCH_CHECK(tensor.scalar_type() == torch::kFloat32, name, " must be float32");
  TORCH_CHECK(tensor.is_contiguous(), name, " must be contiguous");
}

torch::Tensor hdwi(torch::Tensor t2m, torch::Tensor d2m, torch::Tensor u10,
                   torch::Tensor v10, torch::Tensor surface_pressure,
                   torch::Tensor temperature, torch::Tensor humidity,
                   torch::Tensor u, torch::Tensor v, torch::Tensor pressure) {
  check(t2m, "t2m");
  check(d2m, "d2m");
  check(u10, "u10");
  check(v10, "v10");
  check(surface_pressure, "surface_pressure");
  check(temperature, "temperature");
  check(humidity, "humidity");
  check(u, "u");
  check(v, "v");
  check(pressure, "pressure");
  TORCH_CHECK(t2m.dim() == 2, "surface fields must be (batch, columns)");
  TORCH_CHECK(temperature.dim() == 3, "level fields must be (batch, levels, columns)");

  const int batch = static_cast<int>(t2m.size(0));
  const int columns = static_cast<int>(t2m.size(1));
  const int levels = static_cast<int>(pressure.size(0));
  auto out = torch::empty_like(t2m);

  const cudaError_t status = launch_hdwi(
      t2m.data_ptr<float>(), d2m.data_ptr<float>(), u10.data_ptr<float>(),
      v10.data_ptr<float>(), surface_pressure.data_ptr<float>(),
      temperature.data_ptr<float>(), humidity.data_ptr<float>(),
      u.data_ptr<float>(), v.data_ptr<float>(), pressure.data_ptr<float>(),
      out.data_ptr<float>(), batch, columns, levels,
      at::cuda::getCurrentCUDAStream());
  TORCH_CHECK(status == cudaSuccess, cudaGetErrorString(status));
  return out;
}

}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, module) {
  module.def("hdwi", &hdwi, "Hot-Dry-Windy Index on CUDA");
}
