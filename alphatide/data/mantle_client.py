"""Mantle network data access via JSON-RPC.

TODO: block polling, DEX swap log decoding, transfer/bridge event streams.
"""

from web3 import Web3

from alphatide.core.config import settings


def get_web3() -> Web3:
    return Web3(Web3.HTTPProvider(settings.mantle_rpc_url))
