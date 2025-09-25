from __future__ import annotations

import hashlib
import secrets
from io import BytesIO
from time import time
from typing import TYPE_CHECKING, cast

import tgcrypto
from loguru import logger

from piltover.auth_data import GenAuthData
from piltover.db.models import TempAuthKey, AuthKey
from piltover.exceptions import Disconnection
from piltover.tl import MsgsAck, ReqPqMulti, ReqPq, ReqDHParams, SetClientDHParams, ResPQ, PQInnerData, PQInnerDataDc, \
    PQInnerDataTemp, PQInnerDataTempDc, ServerDHInnerData, ServerDHParamsOk, ClientDHInnerData, DhGenOk, Int256, Long, \
    Int128, TLObject
from piltover.utils import generate_large_prime, gen_safe_prime
from piltover.utils.rsa_utils import rsa_decrypt, rsa_pad_inverse

if TYPE_CHECKING:
    from piltover.gateway import Client


async def req_pq(client: Client, req_pq_multi: ReqPqMulti | ReqPq) -> None:
    p = generate_large_prime(31)
    q = generate_large_prime(31)

    if p > q:
        p, q = q, p

    client.auth_data = GenAuthData()
    client.auth_data.p, client.auth_data.q = p, q

    if p == -1 or q == -1 or q == p:
        raise Disconnection(404)

    pq = client.auth_data.p * client.auth_data.q

    client.auth_data.server_nonce = Int128.read_bytes(secrets.token_bytes(128 // 8))

    await client.send_unencrypted(ResPQ(
        nonce=req_pq_multi.nonce,
        server_nonce=client.auth_data.server_nonce,
        pq=pq.to_bytes(64 // 8, "big"),
        server_public_key_fingerprints=[client.server.fingerprint_signed]
    ))


async def req_dh_params_handler(client: Client, req_dh_params: ReqDHParams):
    if not isinstance(client.auth_data, GenAuthData):
        raise Disconnection(404)

    auth_data = client.auth_data

    if len(req_dh_params.p) != 4 or len(req_dh_params.q) != 4:
        raise Disconnection(404)
    client_p = int.from_bytes(req_dh_params.p, "big", signed=False)
    client_q = int.from_bytes(req_dh_params.q, "big", signed=False)
    if client_p != auth_data.p or client_q != auth_data.q:
        raise Disconnection(404)

    if auth_data.server_nonce != req_dh_params.server_nonce:
        raise Disconnection(404)

    encrypted_data: bytes = req_dh_params.encrypted_data
    if len(encrypted_data) != 256:
        raise Disconnection(404)

    old = False
    key_aes_encrypted = rsa_decrypt(encrypted_data, client.server.public_key, client.server.private_key)
    try:
        key_aes_encrypted = rsa_pad_inverse(key_aes_encrypted)
    except RuntimeError as e:
        logger.debug(f"rsa_pad_inverse raised error: {e}. Using old pre-RSA_PAD encryption.")
        old = True
    key_aes_encrypted = key_aes_encrypted.lstrip(b"\0")

    # TODO: assert key_aes_encrypted < public.n, "key_aes_encrypted greater than RSA modulus, aborting..."

    if old:
        p_q_inner_data = TLObject.read(BytesIO(key_aes_encrypted[20:]))

        digest = key_aes_encrypted[:20]
        if hashlib.sha1(p_q_inner_data.write()).digest() != digest:
            logger.debug("sha1 of data doesn't match")
            raise Disconnection(404)
    else:
        p_q_inner_data = TLObject.read(BytesIO(key_aes_encrypted))

    logger.debug(f"p_q_inner_data: {p_q_inner_data}")

    if not isinstance(p_q_inner_data, (PQInnerData, PQInnerDataDc, PQInnerDataTemp, PQInnerDataTempDc)):
        logger.debug(f"Expected p_q_inner_data_*, got instead {type(p_q_inner_data)}")
        raise Disconnection(404)

    if auth_data.server_nonce != p_q_inner_data.server_nonce:
        raise Disconnection(404)

    auth_data.is_temp = isinstance(p_q_inner_data, (PQInnerDataTemp, PQInnerDataTempDc))
    auth_data.expires_in = max(cast(PQInnerDataTempDc, p_q_inner_data).expires_in, 86400) \
        if auth_data.is_temp else 0

    new_nonce = Int256.write(p_q_inner_data.new_nonce)
    auth_data.new_nonce = new_nonce
    # TODO: set server salt to server_nonce

    logger.info("Generating safe prime...")
    dh_prime, g = gen_safe_prime(2048)

    logger.info("Prime successfully generated")

    auth_data.a = int.from_bytes(secrets.token_bytes(256), "big")
    g_a = pow(g, auth_data.a, dh_prime)

    if g <= 1 or g >= dh_prime - 1 \
            or g_a <= 1 or g_a >= dh_prime - 1 \
            or g_a <= 2 ** (2048 - 64) or g_a >= dh_prime - 2 ** (2048 - 64):
        raise Disconnection(404)

    answer = ServerDHInnerData(
        nonce=p_q_inner_data.nonce,
        server_nonce=auth_data.server_nonce,
        g=g,
        dh_prime=dh_prime.to_bytes(2048 // 8, "big", signed=False),
        g_a=g_a.to_bytes(256, "big"),
        server_time=int(time()),
    ).write()

    auth_data.server_nonce_bytes = server_nonce_bytes = Int128.write(auth_data.server_nonce)

    answer_with_hash = hashlib.sha1(answer).digest() + answer
    answer_with_hash += secrets.token_bytes(-len(answer_with_hash) % 16)
    auth_data.tmp_aes_key = (
            hashlib.sha1(new_nonce + server_nonce_bytes).digest()
            + hashlib.sha1(server_nonce_bytes + new_nonce).digest()[:12]
    )
    auth_data.tmp_aes_iv = (
            hashlib.sha1(server_nonce_bytes + new_nonce).digest()[12:]
            + hashlib.sha1(new_nonce + new_nonce).digest()
            + new_nonce[:4]
    )
    encrypted_answer = tgcrypto.ige256_encrypt(
        answer_with_hash,
        auth_data.tmp_aes_key,
        auth_data.tmp_aes_iv,
    )

    await client.send_unencrypted(ServerDHParamsOk(
        nonce=p_q_inner_data.nonce,
        server_nonce=auth_data.server_nonce,
        encrypted_answer=encrypted_answer,
    ))


async def set_client_dh_params(client: Client, set_client_DH_params: SetClientDHParams):
    auth_data = client.auth_data

    if not isinstance(auth_data, GenAuthData) \
            or auth_data.tmp_aes_key is None \
            or auth_data.server_nonce != set_client_DH_params.server_nonce:
        raise Disconnection(404)

    decrypted_params = tgcrypto.ige256_decrypt(
        set_client_DH_params.encrypted_data,
        auth_data.tmp_aes_key,
        auth_data.tmp_aes_iv,
    )
    client_DH_inner_data = ClientDHInnerData.read(BytesIO(decrypted_params[20:]))
    if hashlib.sha1(client_DH_inner_data.write()).digest() != decrypted_params[:20]:
        logger.debug("sha1 hash mismatch for client_DH_inner_data")
        raise Disconnection(404)

    if auth_data.server_nonce != client_DH_inner_data.server_nonce:
        raise Disconnection(404)

    dh_prime, _ = gen_safe_prime(2048)

    auth_data.auth_key = auth_key = pow(
        int.from_bytes(client_DH_inner_data.g_b, "big"),
        auth_data.a,
        dh_prime,
    ).to_bytes(256, "big")

    auth_key_digest = hashlib.sha1(auth_key).digest()
    auth_key_hash = auth_key_digest[-8:]
    auth_key_aux_hash = auth_key_digest[:8]

    await client.send_unencrypted(DhGenOk(
        nonce=client_DH_inner_data.nonce,
        server_nonce=auth_data.server_nonce,
        new_nonce_hash1=Int128.read_bytes(
            hashlib.sha1(auth_data.new_nonce + bytes([1]) + auth_key_aux_hash).digest()[-16:]
        )
    ))

    auth_data.auth_key_id = Long.read_bytes(auth_key_hash)

    auth_key_id = auth_data.auth_key_id
    auth_key = auth_data.auth_key
    expires_in = auth_data.expires_in
    if expires_in:
        await TempAuthKey.create(id=str(auth_key_id), auth_key=auth_key, expires_at=int(time() + expires_in))
    else:
        await AuthKey.create(id=str(auth_key_id), auth_key=auth_key)

    logger.info("Auth key generation successfully completed!")


async def msgs_ack(_1: Client, _2: MsgsAck):
    return


KEYGEN_HANDLERS = {
    ReqPqMulti.tlid(): req_pq,
    ReqPq.tlid(): req_pq,
    ReqDHParams.tlid(): req_dh_params_handler,
    SetClientDHParams.tlid(): set_client_dh_params,
    MsgsAck.tlid(): msgs_ack,
}
