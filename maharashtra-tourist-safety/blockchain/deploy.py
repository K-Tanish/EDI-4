"""
deploy.py — Deploy TouristSafety.sol to a running Ganache instance and save
the contract address + ABI to deployed.json.

Usage:
    python deploy.py [--ganache-url http://127.0.0.1:8545]
"""

import argparse
import json
from pathlib import Path

from web3 import Web3

BASE_DIR = Path(__file__).parent
COMPILED_PATH = BASE_DIR / "compiled.json"
DEPLOYED_PATH = BASE_DIR / "deployed.json"

DEFAULT_GANACHE_URL = "http://127.0.0.1:8545"


def deploy(ganache_url: str = DEFAULT_GANACHE_URL) -> dict:
    """
    Deploy TouristSafety contract to Ganache.

    Reads compiled.json (run compile.py first), deploys using the first
    Ganache account, and writes deployed.json with address + ABI.

    Returns:
        dict with keys 'address' and 'abi'.
    """
    if not COMPILED_PATH.exists():
        raise FileNotFoundError(
            f"compiled.json not found at {COMPILED_PATH}. Run compile.py first."
        )

    compiled = json.loads(COMPILED_PATH.read_text())
    abi = compiled["abi"]
    bytecode = compiled["bytecode"]

    w3 = Web3(Web3.HTTPProvider(ganache_url))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to Ganache at {ganache_url}")

    deployer = w3.eth.accounts[0]
    w3.eth.default_account = deployer

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = Contract.constructor().transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    address = receipt["contractAddress"]
    result = {"address": address, "abi": abi}
    DEPLOYED_PATH.write_text(json.dumps(result, indent=2))

    print(f"Contract deployed at {address}")
    print(f"Deployment info saved → {DEPLOYED_PATH}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy TouristSafety to Ganache")
    parser.add_argument(
        "--ganache-url",
        default=DEFAULT_GANACHE_URL,
        help="Ganache RPC URL (default: http://127.0.0.1:8545)",
    )
    args = parser.parse_args()
    deploy(args.ganache_url)
