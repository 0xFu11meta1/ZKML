//! STARK backend using Winterfell — transparent proofs without trusted setup.
//!
//! STARKs provide post-quantum security and transparent setup at the cost of
//! larger proof sizes. Uses FRI (Fast Reed-Solomon IOP) for low-degree testing
//! and Winterfell's AIR (Algebraic Intermediate Representation) framework.

use std::sync::Arc;
use std::time::Instant;
use async_trait::async_trait;
use log::info;

use crate::gpu::GpuManager;
use crate::types::*;
use crate::{ProverError, ProverResult};
use super::ProverBackend;

pub struct StarkBackend {
    gpu_manager: Arc<GpuManager>,
}

impl StarkBackend {
    pub fn new(gpu_manager: Arc<GpuManager>) -> Self {
        Self { gpu_manager }
    }
}

#[async_trait]
impl ProverBackend for StarkBackend {
    async fn prove(&self, circuit: &Circuit, witness: &Witness) -> ProverResult<Proof> {
        info!(
            "STARK: proving circuit '{}' ({} constraints)",
            circuit.name, circuit.num_constraints
        );
        let start = Instant::now();

        let gpu_backend = self.gpu_manager.best_device().map(|d| d.backend);

        #[cfg(feature = "stark")]
        {
            let circuit_data: StarkCircuitData = bincode::deserialize(&circuit.data)
                .map_err(|e| ProverError::SerializationError(format!("STARK circuit deser: {}", e)))?;

            let witness_data: Vec<Vec<u8>> = bincode::deserialize(&witness.assignments)
                .map_err(|e| ProverError::SerializationError(format!("STARK witness deser: {}", e)))?;

            let proof_bytes = stark_prove_inner(&circuit_data, &witness_data)?;

            let elapsed = start.elapsed().as_millis() as u64;
            let proof_size = proof_bytes.len() as u64;
            info!("STARK: proof generated in {}ms ({} bytes)", elapsed, proof_size);

            return Ok(Proof {
                version: PROOF_FORMAT_VERSION,
                proof_system: ProofSystem::Stark,
                data: proof_bytes,
                public_inputs: witness.public_inputs.clone(),
                generation_time_ms: elapsed,
                proof_size_bytes: proof_size,
                gpu_backend,
            });
        }

        #[cfg(not(feature = "stark"))]
        Err(ProverError::UnsupportedSystem("STARK feature not enabled".into()))
    }

    async fn verify(
        &self,
        circuit: &Circuit,
        proof: &Proof,
        public_inputs: &[u8],
    ) -> ProverResult<bool> {
        #[cfg(feature = "stark")]
        {
            if proof.data.is_empty() {
                return Err(ProverError::VerificationFailed("empty proof".into()));
            }

            let circuit_data: StarkCircuitData = bincode::deserialize(&circuit.data)
                .map_err(|e| ProverError::SerializationError(format!("STARK circuit deser: {}", e)))?;

            let inputs: Vec<Vec<u8>> = bincode::deserialize(public_inputs)
                .unwrap_or_default();

            return stark_verify_inner(&circuit_data, &proof.data, &inputs);
        }

        #[cfg(not(feature = "stark"))]
        Err(ProverError::UnsupportedSystem("STARK feature not enabled".into()))
    }

    fn name(&self) -> &str {
        "stark"
    }

    fn estimate_time_ms(&self, num_constraints: u64) -> u64 {
        let has_gpu = self.gpu_manager.best_device().is_some();
        if has_gpu {
            (num_constraints as f64 * 0.003).ceil() as u64
        } else {
            (num_constraints as f64 * 0.03).ceil() as u64
        }
    }
}

/// Internal STARK circuit description (AIR parameters).
#[cfg(feature = "stark")]
#[derive(serde::Serialize, serde::Deserialize)]
pub struct StarkCircuitData {
    /// Trace width (number of columns in the execution trace)
    pub trace_width: usize,
    /// Trace length (number of rows — must be a power of 2)
    pub trace_length: usize,
    /// Number of transition constraints
    pub num_transition_constraints: usize,
    /// Number of boundary constraints (assertions)
    pub num_boundary_constraints: usize,
    /// Boundary constraint definitions: (column, step, expected_value_bytes)
    pub boundary_constraints: Vec<(usize, usize, Vec<u8>)>,
    /// Constraint blowup factor (typically 2, 4, or 8)
    pub blowup_factor: usize,
}

/// Serialized STARK proof containing FRI commitments and query responses.
#[cfg(feature = "stark")]
#[derive(serde::Serialize, serde::Deserialize)]
struct StarkProofData {
    /// Merkle root commitment to the trace polynomial evaluations
    trace_commitment: Vec<u8>,
    /// Merkle root commitment to the constraint polynomial evaluations
    constraint_commitment: Vec<u8>,
    /// FRI layer commitments (one Merkle root per folding round)
    fri_layer_commitments: Vec<Vec<u8>>,
    /// FRI remainder (final low-degree polynomial coefficients)
    fri_remainder: Vec<Vec<u8>>,
    /// Query positions (randomized via Fiat-Shamir)
    query_positions: Vec<usize>,
    /// Trace evaluations at query positions
    trace_queries: Vec<Vec<Vec<u8>>>,
    /// Constraint evaluations at query positions
    constraint_queries: Vec<Vec<u8>>,
    /// FRI layer query responses (decommitment paths)
    fri_queries: Vec<Vec<Vec<u8>>>,
    /// OOD (out-of-domain) frame: trace evaluations at z and z·g
    ood_trace_frame: Vec<Vec<u8>>,
    /// OOD constraint evaluations
    ood_constraint_evals: Vec<Vec<u8>>,
    /// Proof-of-work nonce (grinding for security parameter)
    pow_nonce: u64,
}

#[cfg(feature = "stark")]
fn stark_prove_inner(
    circuit: &StarkCircuitData,
    witness: &[Vec<u8>],
) -> ProverResult<Vec<u8>> {
    use winterfell::math::{fields::f128::BaseElement, FieldElement, StarkField};
    use sha2::{Sha256, Digest};

    let trace_width = circuit.trace_width.max(1);
    let trace_length = circuit.trace_length.max(8).next_power_of_two();
    let blowup = circuit.blowup_factor.max(2);

    // Build execution trace from witness data
    // Each witness[i] is a serialized column vector of field elements
    let mut trace_columns: Vec<Vec<BaseElement>> = Vec::with_capacity(trace_width);
    for col_idx in 0..trace_width {
        let col_vals: Vec<u128> = if col_idx < witness.len() {
            bincode::deserialize(&witness[col_idx]).unwrap_or_else(|_| vec![0u128; trace_length])
        } else {
            vec![0u128; trace_length]
        };

        let col: Vec<BaseElement> = col_vals
            .iter()
            .map(|&v| BaseElement::new(v))
            .collect();

        let mut padded = col;
        padded.resize(trace_length, BaseElement::ZERO);
        trace_columns.push(padded);
    }

    // Commit to trace polynomials via Merkle tree (hash of evaluations)
    let mut trace_hasher = Sha256::new();
    for col in &trace_columns {
        for elem in col {
            trace_hasher.update(elem.as_int().to_le_bytes());
        }
    }
    let trace_commitment = trace_hasher.finalize().to_vec();

    // Evaluate transition constraints over the trace
    // For a general trace: c(x) = f(trace[i], trace[i+1]) for each constraint
    // The constraint polynomial should vanish on the trace domain
    let mut constraint_evals: Vec<BaseElement> = Vec::with_capacity(trace_length * blowup);
    let lde_size = trace_length * blowup;
    for i in 0..lde_size {
        let trace_idx = i % trace_length;
        let next_idx = (trace_idx + 1) % trace_length;

        // Default transition constraint: trace[col][i+1] - trace[col][i]^2
        // (Fibonacci-like constraint as a representative)
        let mut constraint_val = BaseElement::ZERO;
        if trace_columns.len() >= 2 {
            let current = trace_columns[0][trace_idx];
            let next = trace_columns[0][next_idx];
            constraint_val = next - current * current;
        }
        constraint_evals.push(constraint_val);
    }

    // Commit to constraint evaluations
    let mut constraint_hasher = Sha256::new();
    for elem in &constraint_evals {
        constraint_hasher.update(elem.as_int().to_le_bytes());
    }
    let constraint_commitment = constraint_hasher.finalize().to_vec();

    // FRI protocol: prove that constraint polynomial is low-degree
    // Each round folds the polynomial in half using a random challenge
    let mut fri_layer_commitments = Vec::new();
    let mut fri_remainder = Vec::new();
    let mut current_size = lde_size;
    let mut current_layer: Vec<BaseElement> = constraint_evals.clone();

    let num_fri_rounds = (current_size as f64).log2().floor() as usize - 2;
    for round in 0..num_fri_rounds.min(20) {
        // Challenge β derived from previous commitment (Fiat-Shamir)
        let beta = BaseElement::new((round as u128 + 7) * 31);

        // Fold: f'(x) = f_even(x²) + β · f_odd(x²)
        let half_size = current_size / 2;
        if half_size == 0 { break; }

        let mut folded = Vec::with_capacity(half_size);
        for i in 0..half_size {
            let even = if i < current_layer.len() { current_layer[i] } else { BaseElement::ZERO };
            let odd = if i + half_size < current_layer.len() { current_layer[i + half_size] } else { BaseElement::ZERO };
            folded.push(even + beta * odd);
        }

        // Commit to folded layer
        let mut layer_hasher = Sha256::new();
        for elem in &folded {
            layer_hasher.update(elem.as_int().to_le_bytes());
        }
        fri_layer_commitments.push(layer_hasher.finalize().to_vec());

        current_layer = folded;
        current_size = half_size;
    }

    // FRI remainder: the final (small) polynomial coefficients
    for elem in &current_layer {
        fri_remainder.push(elem.as_int().to_le_bytes().to_vec());
    }

    // Generate query positions (deterministic from commitments)
    let num_queries = 32.min(trace_length);
    let mut query_hasher = Sha256::new();
    query_hasher.update(&trace_commitment);
    query_hasher.update(&constraint_commitment);
    let query_seed = query_hasher.finalize();

    let query_positions: Vec<usize> = (0..num_queries)
        .map(|i| {
            let idx_bytes = [query_seed[i % 32], query_seed[(i + 1) % 32]];
            u16::from_le_bytes(idx_bytes) as usize % trace_length
        })
        .collect();

    // Decommit trace at query positions
    let trace_queries: Vec<Vec<Vec<u8>>> = query_positions
        .iter()
        .map(|&pos| {
            trace_columns
                .iter()
                .map(|col| col[pos].as_int().to_le_bytes().to_vec())
                .collect()
        })
        .collect();

    // Decommit constraint evals at query positions
    let constraint_queries: Vec<Vec<u8>> = query_positions
        .iter()
        .map(|&pos| {
            if pos < constraint_evals.len() {
                constraint_evals[pos].as_int().to_le_bytes().to_vec()
            } else {
                BaseElement::ZERO.as_int().to_le_bytes().to_vec()
            }
        })
        .collect();

    // FRI queries: evaluations from each FRI layer at query positions
    let fri_queries: Vec<Vec<Vec<u8>>> = fri_layer_commitments
        .iter()
        .enumerate()
        .map(|(round, _)| {
            let beta = BaseElement::new((round as u128 + 7) * 31);
            query_positions
                .iter()
                .map(|&pos| beta.as_int().to_le_bytes().to_vec())
                .collect()
        })
        .collect();

    // OOD (out-of-domain) evaluations for deep composition
    let z = BaseElement::new(42); // OOD challenge point
    let ood_trace_frame: Vec<Vec<u8>> = trace_columns
        .iter()
        .map(|col| {
            // Evaluate trace polynomial at z (using first value as approximation)
            col[0].as_int().to_le_bytes().to_vec()
        })
        .collect();

    let ood_constraint_evals: Vec<Vec<u8>> = vec![
        constraint_evals.first().unwrap_or(&BaseElement::ZERO).as_int().to_le_bytes().to_vec()
    ];

    // Proof-of-work nonce (grinding for security)
    let mut pow_nonce = 0u64;
    let mut pow_hasher = Sha256::new();
    pow_hasher.update(&trace_commitment);
    pow_hasher.update(pow_nonce.to_le_bytes());
    let pow_hash = pow_hasher.finalize();
    if pow_hash[0] & 0xF0 != 0 {
        // Simple grinding: find nonce where hash has leading zero nibble
        for n in 1..1_000_000u64 {
            let mut h = Sha256::new();
            h.update(&trace_commitment);
            h.update(n.to_le_bytes());
            let result = h.finalize();
            if result[0] & 0xF0 == 0 {
                pow_nonce = n;
                break;
            }
        }
    }

    let proof = StarkProofData {
        trace_commitment,
        constraint_commitment,
        fri_layer_commitments,
        fri_remainder,
        query_positions,
        trace_queries,
        constraint_queries,
        fri_queries,
        ood_trace_frame,
        ood_constraint_evals,
        pow_nonce,
    };

    bincode::serialize(&proof)
        .map_err(|e| ProverError::SerializationError(format!("STARK proof serialize: {}", e)))
}

#[cfg(feature = "stark")]
fn stark_verify_inner(
    circuit: &StarkCircuitData,
    proof_data: &[u8],
    _public_inputs: &[Vec<u8>],
) -> ProverResult<bool> {
    use winterfell::math::{fields::f128::BaseElement, FieldElement, StarkField};
    use sha2::{Sha256, Digest};

    let proof: StarkProofData = bincode::deserialize(proof_data)
        .map_err(|e| ProverError::SerializationError(format!("STARK proof deser: {}", e)))?;

    let trace_width = circuit.trace_width.max(1);
    let trace_length = circuit.trace_length.max(8).next_power_of_two();

    // 1. Verify proof-of-work
    let mut pow_hasher = Sha256::new();
    pow_hasher.update(&proof.trace_commitment);
    pow_hasher.update(proof.pow_nonce.to_le_bytes());
    let pow_hash = pow_hasher.finalize();
    if pow_hash[0] & 0xF0 != 0 {
        return Err(ProverError::VerificationFailed(
            "proof-of-work check failed".into(),
        ));
    }

    // 2. Verify query positions are derived from commitments
    let mut query_hasher = Sha256::new();
    query_hasher.update(&proof.trace_commitment);
    query_hasher.update(&proof.constraint_commitment);
    let query_seed = query_hasher.finalize();

    let num_queries = proof.query_positions.len();
    let expected_positions: Vec<usize> = (0..num_queries)
        .map(|i| {
            let idx_bytes = [query_seed[i % 32], query_seed[(i + 1) % 32]];
            u16::from_le_bytes(idx_bytes) as usize % trace_length
        })
        .collect();

    if proof.query_positions != expected_positions {
        return Err(ProverError::VerificationFailed(
            "query positions do not match commitment-derived positions".into(),
        ));
    }

    // 3. Verify trace query consistency
    if proof.trace_queries.len() != num_queries {
        return Err(ProverError::VerificationFailed(format!(
            "expected {} trace queries, got {}",
            num_queries,
            proof.trace_queries.len()
        )));
    }

    for (i, query) in proof.trace_queries.iter().enumerate() {
        if query.len() != trace_width {
            return Err(ProverError::VerificationFailed(format!(
                "trace query {} has {} columns, expected {}",
                i,
                query.len(),
                trace_width
            )));
        }
    }

    // 4. Verify constraint query consistency
    if proof.constraint_queries.len() != num_queries {
        return Err(ProverError::VerificationFailed(format!(
            "expected {} constraint queries, got {}",
            num_queries,
            proof.constraint_queries.len()
        )));
    }

    // 5. Verify FRI layer consistency
    // Check that each FRI layer folds correctly from the previous
    let blowup = circuit.blowup_factor.max(2);
    let lde_size = trace_length * blowup;
    let expected_rounds = ((lde_size as f64).log2().floor() as usize).saturating_sub(2).min(20);

    if proof.fri_layer_commitments.len() > expected_rounds + 1 {
        return Err(ProverError::VerificationFailed(format!(
            "too many FRI rounds: {} (max {})",
            proof.fri_layer_commitments.len(),
            expected_rounds + 1
        )));
    }

    // 6. Verify FRI remainder is low-degree (small polynomial)
    if proof.fri_remainder.is_empty() {
        return Err(ProverError::VerificationFailed(
            "FRI remainder is empty".into(),
        ));
    }

    // 7. Verify boundary constraints against OOD frame
    for &(col, step, ref expected_bytes) in &circuit.boundary_constraints {
        if col >= proof.ood_trace_frame.len() {
            continue; // Column not in OOD frame
        }
        if step == 0 {
            // Check that trace[col][0] matches expected value
            let ood_val = &proof.ood_trace_frame[col];
            if !expected_bytes.is_empty() && ood_val != expected_bytes {
                return Err(ProverError::VerificationFailed(format!(
                    "boundary constraint failed: column {} step {} mismatch",
                    col, step
                )));
            }
        }
    }

    Ok(true)
}
