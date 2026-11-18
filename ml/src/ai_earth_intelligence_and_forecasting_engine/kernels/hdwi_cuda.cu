#include <cuda_runtime.h>
#include <math.h>

namespace {

constexpr float kLayerDepth = 50.0f;
constexpr float kKappa = 0.2857f;
constexpr float kEpsilon = 0.622f;
constexpr float kMagnusA = 6.1094f;
constexpr float kMagnusB = 17.625f;
constexpr float kMagnusC = 243.04f;
constexpr float kKelvin = 273.15f;
constexpr int kThreads = 256;
constexpr int kLevelsPerLoad = 4;

__device__ __forceinline__ float saturation(float kelvin) {
  const float celsius = kelvin - kKelvin;
  return kMagnusA * expf(kMagnusB * celsius / (kMagnusC + celsius));
}

__global__ void hdwi_kernel(const float* __restrict__ t2m,
                            const float* __restrict__ d2m,
                            const float* __restrict__ u10,
                            const float* __restrict__ v10,
                            const float* __restrict__ surface_pressure,
                            const float* __restrict__ temperature,
                            const float* __restrict__ humidity,
                            const float* __restrict__ u,
                            const float* __restrict__ v,
                            const float* __restrict__ pressure,
                            float* __restrict__ out, int columns, int levels) {
  extern __shared__ float level_pressure[];
  for (int k = threadIdx.x; k < levels; k += blockDim.x) {
    level_pressure[k] = pressure[k];
  }
  __syncthreads();

  const int column = blockIdx.x * blockDim.x + threadIdx.x;
  if (column >= columns) {
    return;
  }
  const long long batch = blockIdx.y;
  const long long cell = batch * columns + column;

  const float surface = surface_pressure[cell] / 100.0f;
  const float top = surface - kLayerDepth;
  float wind_max = sqrtf(u10[cell] * u10[cell] + v10[cell] * v10[cell]);
  const float deficit = saturation(t2m[cell]) - saturation(d2m[cell]);
  bool bad = isnan(surface) || isnan(wind_max) || isnan(deficit);
  float deficit_max = fmaxf(deficit, 0.0f);

  for (int k = 0; k < levels && !bad; ++k) {
    const float p = level_pressure[k];
    if (p > surface) {
      continue;
    }
    const long long index = (batch * levels + k) * columns + column;
    const float speed = sqrtf(u[index] * u[index] + v[index] * v[index]);
    const float q = humidity[index];
    const float lowered = temperature[index] * powf(surface / p, kKappa);
    const float vapor = q * surface / (kEpsilon + (1.0f - kEpsilon) * q);
    const float level_deficit = saturation(lowered) - vapor;
    bad = isnan(speed) || isnan(level_deficit);
    wind_max = fmaxf(wind_max, speed);
    deficit_max = fmaxf(deficit_max, fmaxf(level_deficit, 0.0f));
    if (p < top) {
      break;
    }
  }

  out[cell] = bad ? nanf("") : wind_max * deficit_max;
}

__global__ void hdwi_ranged_kernel(const float* __restrict__ t2m,
                                   const float* __restrict__ d2m,
                                   const float* __restrict__ u10,
                                   const float* __restrict__ v10,
                                   const float* __restrict__ surface_pressure,
                                   const float* __restrict__ temperature,
                                   const float* __restrict__ humidity,
                                   const float* __restrict__ u,
                                   const float* __restrict__ v,
                                   const float* __restrict__ pressure,
                                   float* __restrict__ out, int columns,
                                   int levels) {
  extern __shared__ float level_pressure[];
  for (int k = threadIdx.x; k < levels; k += blockDim.x) {
    level_pressure[k] = pressure[k];
  }
  __syncthreads();

  const int column = blockIdx.x * blockDim.x + threadIdx.x;
  if (column >= columns) {
    return;
  }
  const long long batch = blockIdx.y;
  const long long cell = batch * columns + column;

  const float surface = surface_pressure[cell] / 100.0f;
  const float top = surface - kLayerDepth;
  float wind_max = sqrtf(u10[cell] * u10[cell] + v10[cell] * v10[cell]);
  const float deficit = saturation(t2m[cell]) - saturation(d2m[cell]);
  bool bad = isnan(surface) || isnan(wind_max) || isnan(deficit);
  float deficit_max = fmaxf(deficit, 0.0f);

  int first = levels;
  int last = levels - 1;
  for (int k = 0; k < levels; ++k) {
    const float p = level_pressure[k];
    if (first == levels && p <= surface) {
      first = k;
    }
    if (first < levels && p < top) {
      last = k;
      break;
    }
  }
  if (bad) {
    first = levels;
  }

  const long long base = batch * levels * columns + column;
  for (int start = first; start <= last; start += kLevelsPerLoad) {
    float uk[kLevelsPerLoad];
    float vk[kLevelsPerLoad];
    float q[kLevelsPerLoad];
    float t[kLevelsPerLoad];
#pragma unroll
    for (int j = 0; j < kLevelsPerLoad; ++j) {
      if (start + j <= last) {
        const long long index =
            base + static_cast<long long>(start + j) * columns;
        uk[j] = u[index];
        vk[j] = v[index];
        q[j] = humidity[index];
        t[j] = temperature[index];
      }
    }
#pragma unroll
    for (int j = 0; j < kLevelsPerLoad; ++j) {
      if (start + j <= last) {
        const float p = level_pressure[start + j];
        const float speed = sqrtf(uk[j] * uk[j] + vk[j] * vk[j]);
        const float lowered = t[j] * powf(surface / p, kKappa);
        const float vapor =
            q[j] * surface / (kEpsilon + (1.0f - kEpsilon) * q[j]);
        const float level_deficit = saturation(lowered) - vapor;
        bad = bad || isnan(speed) || isnan(level_deficit);
        wind_max = fmaxf(wind_max, speed);
        deficit_max = fmaxf(deficit_max, fmaxf(level_deficit, 0.0f));
      }
    }
  }

  out[cell] = bad ? nanf("") : wind_max * deficit_max;
}

}

extern "C" cudaError_t launch_hdwi_ranged(
    const float* t2m, const float* d2m, const float* u10, const float* v10,
    const float* surface_pressure, const float* temperature,
    const float* humidity, const float* u, const float* v,
    const float* pressure, float* out, int batch, int columns, int levels,
    cudaStream_t stream) {
  const dim3 grid((columns + kThreads - 1) / kThreads, batch);
  const size_t shared = static_cast<size_t>(levels) * sizeof(float);
  hdwi_ranged_kernel<<<grid, kThreads, shared, stream>>>(
      t2m, d2m, u10, v10, surface_pressure, temperature, humidity, u, v,
      pressure, out, columns, levels);
  return cudaGetLastError();
}

extern "C" cudaError_t launch_hdwi(const float* t2m, const float* d2m,
                                   const float* u10, const float* v10,
                                   const float* surface_pressure,
                                   const float* temperature,
                                   const float* humidity, const float* u,
                                   const float* v, const float* pressure,
                                   float* out, int batch, int columns,
                                   int levels, cudaStream_t stream) {
  const dim3 grid((columns + kThreads - 1) / kThreads, batch);
  const size_t shared = static_cast<size_t>(levels) * sizeof(float);
  hdwi_kernel<<<grid, kThreads, shared, stream>>>(
      t2m, d2m, u10, v10, surface_pressure, temperature, humidity, u, v,
      pressure, out, columns, levels);
  return cudaGetLastError();
}
