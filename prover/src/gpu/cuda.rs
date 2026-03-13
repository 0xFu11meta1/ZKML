//! CUDA GPU backend using ICICLE for elliptic curve MSM acceleration.

use super::GpuDevice;
use crate::types::GpuBackendType;
use log::{debug, warn};

/// Detect NVIDIA CUDA devices.
pub fn detect_devices() -> Option<Vec<GpuDevice>> {
    #[cfg(feature = "cuda")]
    {
        use icicle_cuda_runtime::device::Device as IcicleDevice;
        use icicle_cuda_runtime::memory;

        match icicle_cuda_runtime::device::get_device_count() {
            Ok(count) if count > 0 => {
                let mut devices = Vec::with_capacity(count as usize);
                for i in 0..count {
                    if let Ok(()) = icicle_cuda_runtime::device::set_device(i) {
                        let (free, total) = memory::get_mem_info().unwrap_or((0, 0));
                        devices.push(GpuDevice {
                            name: format!("CUDA Device {}", i),
                            backend: GpuBackendType::Cuda,
                            device_index: i as u32,
                            vram_total: total as u64,
                            vram_available: free as u64,
                            compute_units: 0, // Queried at benchmark time
                            compute_version: String::new(),
                            benchmark_score: 0.0,
                        });
                    }
                }
                if devices.is_empty() {
                    return None;
                }
                return Some(devices);
            }
            _ => return None,
        }
    }

    #[cfg(not(feature = "cuda"))]
    {
        // Fallback: check nvidia-smi availability
        match std::process::Command::new("nvidia-smi")
            .arg("--query-gpu=name,memory.total,memory.free,compute_cap")
            .arg("--format=csv,noheader,nounits")
            .output()
        {
            Ok(output) if output.status.success() => {
                let stdout = String::from_utf8_lossy(&output.stdout);
                let devices: Vec<GpuDevice> = stdout
                    .lines()
                    .enumerate()
                    .filter_map(|(idx, line)| {
                        let parts: Vec<&str> = line.split(", ").collect();
                        if parts.len() >= 4 {
                            Some(GpuDevice {
                                name: parts[0].trim().to_string(),
                                backend: GpuBackendType::Cuda,
                                device_index: idx as u32,
                                vram_total: parts[1].trim().parse::<u64>().unwrap_or(0) * 1024 * 1024,
                                vram_available: parts[2].trim().parse::<u64>().unwrap_or(0) * 1024 * 1024,
                                compute_units: 0,
                                compute_version: parts[3].trim().to_string(),
                                benchmark_score: 0.0,
                            })
                        } else {
                            None
                        }
                    })
                    .collect();
                if devices.is_empty() {
                    None
                } else {
                    Some(devices)
                }
            }
            _ => {
                debug!("nvidia-smi not found — no CUDA devices");
                None
            }
        }
    }
}

/// Run MSM (Multi-Scalar Multiplication) on CUDA via ICICLE.
/// This is the core GPU-accelerated operation for ZK proof generation.
/// Computes: result = Σ scalars[i] · points[i] (elliptic curve multi-scalar multiplication)
#[cfg(feature = "cuda")]
pub fn cuda_msm(
    scalars: &[u8],
    points: &[u8],
    result: &mut [u8],
    device_index: u32,
) -> Result<(), String> {
    use icicle_bn254::curve::{CurveCfg, G1Projective, ScalarField};
    use icicle_core::msm;

    icicle_cuda_runtime::device::set_device(device_index as i32)
        .map_err(|e| format!("Failed to set CUDA device {}: {:?}", device_index, e))?;

    // Validate input sizes
    let scalar_size = std::mem::size_of::<ScalarField>();
    let point_size = std::mem::size_of::<G1Projective>();

    if scalars.is_empty() || points.is_empty() {
        return Err("empty scalars or points".to_string());
    }

    if scalars.len() % scalar_size != 0 {
        return Err(format!(
            "scalars buffer size {} not aligned to scalar size {}",
            scalars.len(),
            scalar_size
        ));
    }

    let num_scalars = scalars.len() / scalar_size;
    let num_points = points.len() / point_size;

    if num_scalars != num_points {
        return Err(format!(
            "mismatched counts: {} scalars vs {} points",
            num_scalars, num_points
        ));
    }

    if result.len() < std::mem::size_of::<G1Projective>() {
        return Err(format!(
            "result buffer too small: {} bytes (need {})",
            result.len(),
            std::mem::size_of::<G1Projective>()
        ));
    }

    // Reinterpret buffers as typed slices
    let scalars_typed: &[ScalarField] = unsafe {
        std::slice::from_raw_parts(scalars.as_ptr() as *const ScalarField, num_scalars)
    };

    let points_typed: &[G1Projective] = unsafe {
        std::slice::from_raw_parts(points.as_ptr() as *const G1Projective, num_points)
    };

    // Configure MSM
    let cfg = msm::MSMConfig::default();

    // Run MSM on GPU
    let mut msm_result = vec![G1Projective::default(); 1];
    msm::msm(scalars_typed, points_typed, &cfg, &mut msm_result)
        .map_err(|e| format!("CUDA MSM failed: {:?}", e))?;

    // Copy result back
    let result_bytes: &[u8] = unsafe {
        std::slice::from_raw_parts(
            &msm_result[0] as *const G1Projective as *const u8,
            std::mem::size_of::<G1Projective>(),
        )
    };

    let copy_len = result.len().min(result_bytes.len());
    result[..copy_len].copy_from_slice(&result_bytes[..copy_len]);

    Ok(())
}

/// Run NTT (Number Theoretic Transform) on CUDA via ICICLE.
/// Used for polynomial evaluation/interpolation in PLONK and STARKs.
/// When `inverse` is true, performs inverse NTT (interpolation).
#[cfg(feature = "cuda")]
pub fn cuda_ntt(
    coefficients: &[u8],
    result: &mut [u8],
    device_index: u32,
    inverse: bool,
) -> Result<(), String> {
    use icicle_bn254::curve::ScalarField;
    use icicle_core::ntt;

    icicle_cuda_runtime::device::set_device(device_index as i32)
        .map_err(|e| format!("Failed to set CUDA device {}: {:?}", device_index, e))?;

    let element_size = std::mem::size_of::<ScalarField>();

    if coefficients.is_empty() {
        return Err("empty coefficients buffer".to_string());
    }

    if coefficients.len() % element_size != 0 {
        return Err(format!(
            "coefficients buffer size {} not aligned to element size {}",
            coefficients.len(),
            element_size
        ));
    }

    let n = coefficients.len() / element_size;
    if !n.is_power_of_two() {
        return Err(format!("NTT size {} must be a power of two", n));
    }

    if result.len() < coefficients.len() {
        return Err(format!(
            "result buffer too small: {} bytes (need {})",
            result.len(),
            coefficients.len()
        ));
    }

    // Reinterpret as typed slice
    let input: &[ScalarField] = unsafe {
        std::slice::from_raw_parts(coefficients.as_ptr() as *const ScalarField, n)
    };

    // Initialize NTT domain with the root of unity for this size
    ntt::initialize_domain(
        ntt::get_root_of_unity::<ScalarField>(n as u64),
        &ntt::NTTInitDomainConfig::default(),
    )
    .map_err(|e| format!("NTT domain init failed: {:?}", e))?;

    // Configure NTT direction
    let direction = if inverse {
        ntt::NTTDir::kInverse
    } else {
        ntt::NTTDir::kForward
    };

    let cfg = ntt::NTTConfig::<ScalarField>::default();
    let mut output = vec![ScalarField::default(); n];

    ntt::ntt(input, direction, &cfg, &mut output)
        .map_err(|e| format!("CUDA NTT failed: {:?}", e))?;

    // Copy result back to byte buffer
    let output_bytes: &[u8] = unsafe {
        std::slice::from_raw_parts(output.as_ptr() as *const u8, n * element_size)
    };

    let copy_len = result.len().min(output_bytes.len());
    result[..copy_len].copy_from_slice(&output_bytes[..copy_len]);

    Ok(())
}

/// Benchmark a CUDA device by running a small MSM and measuring throughput.
/// Returns a score ≥ 0.0 where higher is better.
#[cfg(feature = "cuda")]
pub fn benchmark_device(device_index: u32) -> f64 {
    use icicle_bn254::curve::{G1Projective, ScalarField};
    use icicle_core::msm;
    use std::time::Instant;

    if icicle_cuda_runtime::device::set_device(device_index as i32).is_err() {
        return 0.0;
    }

    // Small benchmark: MSM over 1024 random points
    let n = 1024usize;
    let scalars = vec![0u8; n * std::mem::size_of::<ScalarField>()];
    let points = vec![0u8; n * std::mem::size_of::<G1Projective>()];

    let scalars_typed: &[ScalarField] =
        unsafe { std::slice::from_raw_parts(scalars.as_ptr() as *const ScalarField, n) };
    let points_typed: &[G1Projective] =
        unsafe { std::slice::from_raw_parts(points.as_ptr() as *const G1Projective, n) };

    let cfg = msm::MSMConfig::default();
    let mut msm_result = vec![G1Projective::default(); 1];

    let start = Instant::now();
    let iterations = 10;
    let mut successes = 0;
    for _ in 0..iterations {
        if msm::msm(scalars_typed, points_typed, &cfg, &mut msm_result).is_ok() {
            successes += 1;
        }
    }
    let elapsed = start.elapsed().as_secs_f64();

    if successes == 0 {
        return 0.0;
    }

    // Score: operations per second  
    (successes as f64) / elapsed
}
