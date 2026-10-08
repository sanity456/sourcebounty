"""Windows compatibility for gltest's stdin message injection.

The upstream loader uses a named temporary file and unlinks it while fd 0 is
still attached to the file. Windows correctly rejects that operation. A pipe
has the same stdin semantics and no pathname to clean up.
"""

import os

from gltest.direct import loader


def _inject_message_to_pipe(vm):
    from genlayer.py import calldata
    from genlayer.py.types import Address

    sender_addr = Address(vm.sender) if isinstance(vm.sender, bytes) else vm.sender
    contract_addr = Address(vm._contract_address) if isinstance(vm._contract_address, bytes) else vm._contract_address
    origin_addr = Address(vm.origin) if isinstance(vm.origin, bytes) else vm.origin
    message_data = {
        "contract_address": contract_addr,
        "sender_address": sender_addr,
        "origin_address": origin_addr,
        "stack": [],
        "value": vm._value,
        "datetime": vm._datetime,
        "is_init": False,
        "chain_id": vm._chain_id,
        "entry_kind": 0,
        "entry_data": b"",
        "entry_stage_data": None,
    }
    encoded = calldata.encode(message_data)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, encoded)
    os.close(write_fd)
    vm._original_stdin_fd = os.dup(0)
    os.dup2(read_fd, 0)
    os.close(read_fd)


loader._inject_message_to_fd0 = _inject_message_to_pipe
