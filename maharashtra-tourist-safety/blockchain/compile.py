"""
compile.py — Compile TouristSafety.sol using py-solc-x and write ABI + bytecode
to compiled.json.

Usage:
    python compile.py
"""

import json
import os
from pathlib import Path

from solcx import compile_standard, install_solc

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONTRACT_PATH = BASE_DIR / "contracts" / "TouristSafety.sol"
OUTPUT_PATH = BASE_DIR / "compiled.json"

SOLC_VERSION = "0.8.20"


def compile_contract() -> dict:
    """Compile TouristSafety.sol and return the compiled output dict."""
    install_solc(SOLC_VERSION, show_progress=False)

    source = CONTRACT_PATH.read_text()

    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {
                "TouristSafety.sol": {"content": source},
            },
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "evm.bytecode"],
                    }
                }
            },
        },
        solc_version=SOLC_VERSION,
    )

    contract_data = compiled["contracts"]["TouristSafety.sol"]["TouristSafety"]
    result = {
        "abi": contract_data["abi"],
        "bytecode": contract_data["evm"]["bytecode"]["object"],
    }

    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"Compiled successfully → {OUTPUT_PATH}")
    return result


if __name__ == "__main__":
    compile_contract()
