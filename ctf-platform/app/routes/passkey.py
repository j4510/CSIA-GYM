"""
WebAuthn Passkey routes — registration and authentication.
Uses pure Python (no external webauthn library) with the Web Authentication API.
Implements a simplified FIDO2/WebAuthn flow:
  - Registration: generate challenge -> browser creates credential -> server verifies & stores
  - Authentication: generate challenge -> browser signs -> server verifies signature
"""

import os
import json
import base64
import hashlib
import struct
import cbor2
from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user, login_user
from app import db, csrf
from app.models import User, UserPasskey

passkey_bp = Blueprint('passkey', __name__)

RP_ID = os.environ.get('PASSKEY_RP_ID', 'localhost')
RP_NAME = 'CSIA GYM'
ORIGIN = os.environ.get('PASSKEY_ORIGIN', 'http://localhost:5050')


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _b64url_decode(s: str) -> bytes:
    s = s.replace('-', '+').replace('_', '/')
    pad = 4 - len(s) % 4
    if pad != 4:
        s += '=' * pad
    return base64.b64decode(s)


def _random_challenge() -> str:
    return _b64url_encode(os.urandom(32))


# ── Registration ──────────────────────────────────────────────────────────────

@passkey_bp.route('/passkey/verify-for-add/begin', methods=['POST'])
@login_required
@csrf.exempt
def verify_for_add_begin():
    """
    When a user already has passkeys and wants to add a new one,
    they must first authenticate with an existing passkey.
    This begins that authentication challenge.
    """
    if not current_user.passkeys:
        # No existing passkeys — no verification needed, mark directly
        session['passkey_add_verified'] = True
        return jsonify(ok=True, skip=True)

    challenge = _random_challenge()
    session['passkey_verify_add_challenge'] = challenge
    allow = [{'type': 'public-key', 'id': pk.credential_id} for pk in current_user.passkeys]
    return jsonify(ok=True, skip=False, challenge=challenge, rpId=RP_ID,
                   allowCredentials=allow, userVerification='required', timeout=60000)


@passkey_bp.route('/passkey/verify-for-add/complete', methods=['POST'])
@login_required
@csrf.exempt
def verify_for_add_complete():
    """Verify the existing passkey signature before allowing a new passkey to be added."""
    data = request.get_json(silent=True) or {}
    challenge = session.pop('passkey_verify_add_challenge', None)
    if not challenge:
        return jsonify(ok=False, error='No challenge in session'), 400

    try:
        credential_id = data['id']
        pk_record = UserPasskey.query.filter_by(
            credential_id=credential_id, user_id=current_user.id
        ).first()
        if not pk_record:
            return jsonify(ok=False, error='Unknown credential'), 400

        client_data = json.loads(_b64url_decode(data['clientDataJSON']))
        assert client_data['type'] == 'webauthn.get'
        assert client_data['challenge'] == challenge
        assert client_data['origin'] == ORIGIN

        auth_data = _b64url_decode(data['authenticatorData'])
        assert auth_data[:32] == hashlib.sha256(RP_ID.encode()).digest()
        assert auth_data[32] & 0x01  # UP flag
        sign_count = struct.unpack('>I', auth_data[33:37])[0]

        cose_key = cbor2.loads(_b64url_decode(pk_record.public_key))
        if 3 not in cose_key:
            return jsonify(ok=False, error='Missing algorithm'), 400
        alg = cose_key[3]
        client_data_hash = hashlib.sha256(_b64url_decode(data['clientDataJSON'])).digest()
        verification_data = auth_data + client_data_hash
        signature = _b64url_decode(data['signature'])

        if alg == -7:
            from cryptography.hazmat.primitives.asymmetric.ec import (
                EllipticCurvePublicNumbers, SECP256R1, ECDSA)
            from cryptography.hazmat.primitives.hashes import SHA256
            from cryptography.hazmat.backends import default_backend
            x = int.from_bytes(cose_key[-2], 'big')
            y = int.from_bytes(cose_key[-3], 'big')
            pub = EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key(default_backend())
            pub.verify(signature, verification_data, ECDSA(SHA256()))
        elif alg == -257:
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
            from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
            from cryptography.hazmat.primitives.hashes import SHA256
            from cryptography.hazmat.backends import default_backend
            n = int.from_bytes(cose_key[-1], 'big')
            e = int.from_bytes(cose_key[-2], 'big')
            pub = RSAPublicNumbers(e, n).public_key(default_backend())
            pub.verify(signature, verification_data, PKCS1v15(), SHA256())
        else:
            return jsonify(ok=False, error='Unsupported algorithm'), 400

        if sign_count != 0 and sign_count <= pk_record.sign_count:
            return jsonify(ok=False, error='Replay detected'), 400
        pk_record.sign_count = sign_count
        db.session.commit()

        session['passkey_add_verified'] = True
        return jsonify(ok=True)
    except (KeyError, ValueError, AssertionError):
        db.session.rollback()
        return jsonify(ok=False, error='Verification failed'), 400


@passkey_bp.route('/passkey/register/begin', methods=['POST'])
@login_required
@csrf.exempt
def register_begin():
    # If user already has passkeys, they must verify with one first
    if current_user.passkeys and not session.pop('passkey_add_verified', False):
        return jsonify(ok=False, error='Must verify existing passkey first'), 403
    challenge = _random_challenge()
    session['passkey_reg_challenge'] = challenge
    return jsonify({
        'rp': {'id': RP_ID, 'name': RP_NAME},
        'user': {
            'id': _b64url_encode(str(current_user.id).encode()),
            'name': current_user.username,
            'displayName': current_user.username,
        },
        'challenge': challenge,
        'pubKeyCredParams': [
            {'type': 'public-key', 'alg': -7},   # ES256
            {'type': 'public-key', 'alg': -257},  # RS256
        ],
        'timeout': 60000,
        'attestation': 'none',
        'authenticatorSelection': {
            'residentKey': 'preferred',
            'userVerification': 'preferred',
        },
        'excludeCredentials': [
            {'type': 'public-key', 'id': pk.credential_id}
            for pk in current_user.passkeys
        ],
    })


@passkey_bp.route('/passkey/register/complete', methods=['POST'])
@login_required
@csrf.exempt
def register_complete():
    data = request.get_json(silent=True) or {}
    challenge = session.pop('passkey_reg_challenge', None)
    if not challenge:
        return jsonify(ok=False, error='No challenge in session'), 400

    try:
        client_data = json.loads(_b64url_decode(data['clientDataJSON']))
        assert client_data['type'] == 'webauthn.create'
        assert client_data['challenge'] == challenge
        assert client_data['origin'] == ORIGIN

        att_obj = cbor2.loads(_b64url_decode(data['attestationObject']))
        auth_data = att_obj['authData']

        # Parse authData: rpIdHash(32) + flags(1) + signCount(4) + aaguid(16) + credIdLen(2) + credId + coseKey
        rp_id_hash = auth_data[:32]
        assert rp_id_hash == hashlib.sha256(RP_ID.encode()).digest()
        flags = auth_data[32]
        assert flags & 0x01  # UP flag
        sign_count = struct.unpack('>I', auth_data[33:37])[0]
        # aaguid at 37, credIdLen at 53
        cred_id_len = struct.unpack('>H', auth_data[53:55])[0]
        cred_id_bytes = auth_data[55:55 + cred_id_len]
        cose_key_bytes = auth_data[55 + cred_id_len:]

        credential_id = _b64url_encode(cred_id_bytes)
        public_key_b64 = _b64url_encode(cose_key_bytes)
        device_name = (data['deviceName'] if 'deviceName' in data else 'Passkey Device')[:100]

        pk = UserPasskey(
            user_id=current_user.id,
            credential_id=credential_id,
            public_key=public_key_b64,
            sign_count=sign_count,
            device_name=device_name,
        )
        current_user.passkey_enabled = True
        db.session.add(pk)
        # amazonq-ignore-next-line
        db.session.commit()
        return jsonify(ok=True)
    except (KeyError, ValueError, AssertionError) as e:
        db.session.rollback()
        return jsonify(ok=False, error='Registration verification failed'), 400

@passkey_bp.route('/passkey/auth/begin', methods=['POST'])
@csrf.exempt
def auth_begin():
    if current_user.is_authenticated:
        return jsonify(ok=False, error='Already authenticated'), 400
    challenge = _random_challenge()
    session['passkey_auth_challenge'] = challenge

    # Collect all known credential IDs (for allowCredentials)
    json_body = request.get_json(silent=True) or {}
    username = json_body['username'] if 'username' in json_body else ''
    allow = []
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            allow = [{'type': 'public-key', 'id': pk.credential_id} for pk in user.passkeys]

    return jsonify({
        'challenge': challenge,
        'timeout': 60000,
        'rpId': RP_ID,
        'allowCredentials': allow,
        'userVerification': 'preferred',
    })


@passkey_bp.route('/passkey/auth/complete', methods=['POST'])
@csrf.exempt
def auth_complete():
    if current_user.is_authenticated:
        return jsonify(ok=False, error='Already authenticated'), 400
    data = request.get_json(silent=True) or {}
    challenge = session.pop('passkey_auth_challenge', None)
    if not challenge:
        return jsonify(ok=False, error='No challenge'), 400

    try:
        credential_id = data['id']
        pk_record = UserPasskey.query.filter_by(credential_id=credential_id).first()
        if not pk_record:
            return jsonify(ok=False, error='Unknown credential'), 400

        client_data = json.loads(_b64url_decode(data['clientDataJSON']))
        assert client_data['type'] == 'webauthn.get'
        assert client_data['challenge'] == challenge
        assert client_data['origin'] == ORIGIN

        auth_data = _b64url_decode(data['authenticatorData'])
        rp_id_hash = auth_data[:32]
        assert rp_id_hash == hashlib.sha256(RP_ID.encode()).digest()
        flags = auth_data[32]
        assert flags & 0x01  # UP flag
        sign_count = struct.unpack('>I', auth_data[33:37])[0]

        # Verify signature using stored COSE public key
        cose_key = cbor2.loads(_b64url_decode(pk_record.public_key))
        if 3 not in cose_key:
            return jsonify(ok=False, error='Missing algorithm in credential'), 400
        alg = cose_key[3]

        client_data_hash = hashlib.sha256(_b64url_decode(data['clientDataJSON'])).digest()
        verification_data = auth_data + client_data_hash
        signature = _b64url_decode(data['signature'])

        if alg == -7:  # ES256
            from cryptography.hazmat.primitives.asymmetric.ec import (
                EllipticCurvePublicNumbers, SECP256R1, ECDSA
            )
            from cryptography.hazmat.primitives.hashes import SHA256
            from cryptography.hazmat.backends import default_backend
            x = int.from_bytes(cose_key[-2], 'big')
            y = int.from_bytes(cose_key[-3], 'big')
            pub = EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key(default_backend())
            pub.verify(signature, verification_data, ECDSA(SHA256()))
        elif alg == -257:  # RS256
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
            from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
            from cryptography.hazmat.primitives.hashes import SHA256
            from cryptography.hazmat.backends import default_backend
            n = int.from_bytes(cose_key[-1], 'big')
            e = int.from_bytes(cose_key[-2], 'big')
            pub = RSAPublicNumbers(e, n).public_key(default_backend())
            pub.verify(signature, verification_data, PKCS1v15(), SHA256())
        else:
            return jsonify(ok=False, error='Unsupported algorithm'), 400

        # Enforce sign count — reject replayed authenticator responses
        if sign_count != 0 and sign_count <= pk_record.sign_count:
            return jsonify(ok=False, error='Authenticator sign count invalid (possible replay)'), 400

        # Update sign count
        pk_record.sign_count = sign_count
        db.session.commit()

        user = pk_record.user
        # amazonq-ignore-next-line
        if user.is_banned:
            return jsonify(ok=False, error='Account banned'), 403
        login_user(user, remember=True)
        return jsonify(ok=True)
    except (KeyError, ValueError, AssertionError):
        db.session.rollback()
        return jsonify(ok=False, error='Authentication verification failed'), 400


@passkey_bp.route('/passkey/remove', methods=['POST'])
@login_required
@csrf.exempt
def remove_passkey():
    body = request.get_json(silent=True, force=True) or {}
    pk_id = body['id'] if 'id' in body else ''
    if not pk_id:
        return jsonify(ok=False, error='Missing id'), 400
    pk = UserPasskey.query.filter_by(id=pk_id, user_id=current_user.id).first_or_404()
    db.session.delete(pk)
    db.session.flush()
    if not UserPasskey.query.filter_by(user_id=current_user.id).first():
        current_user.passkey_enabled = False
    db.session.commit()
    return jsonify(ok=True)
