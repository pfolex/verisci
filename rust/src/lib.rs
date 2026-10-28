//! `verisci`: Universal Scientific & Formal Verification Cartridges.
//!
//! Provides deterministic, zero-hallucination formal verification traits and
//! high-speed evaluation primitives across 4 scientific & engineering domains:
//! - `logic`: Propositional/first-order proof steps & SAT truth-table checks
//! - `silicon`: Combinational & sequential digital logic gate netlist equivalence
//! - `systems`: Distributed systems concurrency & safety invariant model checking
//! - `matter`: Molecular graph valence, stoichiometry, and energetic stability verification

use std::collections::HashMap;

/// Outcome of a single formal verification step or full trajectory evaluation.
#[derive(Debug, Clone, PartialEq)]
pub struct VerificationResult {
    pub verified: bool,
    pub score: f64,
    pub passed_invariants: Vec<String>,
    pub failed_invariants: Vec<String>,
    pub diagnostics: HashMap<String, f64>,
}

/// Core trait implemented by all verifiable scientific domain cartridges.
pub trait Verifier {
    type Task;
    type Submission;

    fn domain_name(&self) -> &'static str;
    fn verify(&self, task: &Self::Task, submission: &Self::Submission) -> VerificationResult;
}

/// Fast Boolean truth-table evaluator for digital logic & SAT verification.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LogicGateOp {
    And,
    Or,
    Xor,
    Nand,
    Nor,
    Not,
    Mux,
}

impl LogicGateOp {
    #[inline]
    pub fn eval(self, inputs: &[bool]) -> bool {
        match self {
            LogicGateOp::And => inputs.iter().copied().all(|b| b),
            LogicGateOp::Or => inputs.iter().copied().any(|b| b),
            LogicGateOp::Xor => inputs.iter().copied().fold(false, |acc, b| acc ^ b),
            LogicGateOp::Nand => !inputs.iter().copied().all(|b| b),
            LogicGateOp::Nor => !inputs.iter().copied().any(|b| b),
            LogicGateOp::Not => !inputs.first().copied().unwrap_or(false),
            LogicGateOp::Mux => {
                // sel, a, b -> if sel { b } else { a }
                let sel = inputs.first().copied().unwrap_or(false);
                let a = inputs.get(1).copied().unwrap_or(false);
                let b = inputs.get(2).copied().unwrap_or(false);
                if sel { b } else { a }
            }
        }
    }
}

/// Standard covalent valence limits for computational chemistry cartridges.
pub fn standard_valence(element: &str) -> Option<u8> {
    match element {
        "H" | "F" | "Cl" | "Br" | "I" => Some(1),
        "O" | "S" => Some(2),
        "N" | "P" => Some(3),
        "C" | "Si" => Some(4),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gate_ops() {
        assert!(LogicGateOp::And.eval(&[true, true]));
        assert!(!LogicGateOp::And.eval(&[true, false]));
        assert!(LogicGateOp::Xor.eval(&[true, false]));
        assert!(!LogicGateOp::Xor.eval(&[true, true]));
        assert!(LogicGateOp::Mux.eval(&[true, false, true]));
    }

    #[test]
    fn test_valence() {
        assert_eq!(standard_valence("C"), Some(4));
        assert_eq!(standard_valence("O"), Some(2));
        assert_eq!(standard_valence("N"), Some(3));
        assert_eq!(standard_valence("H"), Some(1));
    }
}
