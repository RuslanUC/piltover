import asyncio
import socket
from collections import defaultdict
from time import time

from aioudp import open_local_endpoint


async def reflector() -> None:
    server = await open_local_endpoint(port=12345)
    print(f"Running udp reflector on {server.address}")

    clients: dict[bytes, set[tuple[str, int]]] = defaultdict(set)

    while True:
        data, addr = await server.receive()
        peer_tag, data = data[:16], data[16:]

        peer_tag = peer_tag[:-4]
        if addr not in clients[peer_tag]:
            print(f"Got new client for peer tag {peer_tag}: {addr}")

        clients[peer_tag].add(addr)

        print(f"Got data from {peer_tag} ({addr}): {data}")

        if data.startswith(b"\xff" * 12 + b"\xfe" + b"\xff" * 3):
            query_id = data[16:16+8]

            server.send(
                (
                        b""
                        + b"\xff" * 12
                        + (0xc01572c7).to_bytes(4, "little", signed=False)
                        + int(time()).to_bytes(4, "little", signed=False)
                        + query_id
                        + b"\x00" * 12
                        + socket.inet_aton(addr[0])
                        + addr[1].to_bytes(4, "little", signed=False)
                ),
                addr,
            )
            continue

        for other_peer in clients[peer_tag]:
            if other_peer == addr:
                continue
            print("forwarding to other peer")
            server.send(other_peer + data, other_peer)


if __name__ == "__main__":
    asyncio.new_event_loop().run_until_complete(reflector())
