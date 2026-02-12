"""Certificate store helpers via CryptoAPI (crypt32.dll)."""
import ctypes
import logging
from ctypes import wintypes
from typing import Optional

logger = logging.getLogger(__name__)

# --- crypt32.dll function signatures ---
_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)

_crypt32.CertOpenStore.restype = ctypes.c_void_p
_crypt32.CertOpenStore.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, ctypes.c_wchar_p,
]

_crypt32.CertFindCertificateInStore.restype = ctypes.c_void_p
_crypt32.CertFindCertificateInStore.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
    wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
]

_crypt32.CertGetNameStringW.restype = wintypes.DWORD
_crypt32.CertGetNameStringW.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
    ctypes.c_void_p, ctypes.c_wchar_p, wintypes.DWORD,
]

_crypt32.CertFreeCertificateContext.restype = wintypes.BOOL
_crypt32.CertFreeCertificateContext.argtypes = [ctypes.c_void_p]

_crypt32.CertCloseStore.restype = wintypes.BOOL
_crypt32.CertCloseStore.argtypes = [ctypes.c_void_p, wintypes.DWORD]


class _CRYPT_DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


# Constants
_CERT_STORE_PROV_SYSTEM_W = 10
_CERT_SYSTEM_STORE_LOCAL_MACHINE = 0x00020000
_CERT_STORE_READONLY_FLAG = 0x00008000
_CERT_FIND_SHA1_HASH = 0x10000
_X509_ASN_ENCODING = 0x00000001
_PKCS_7_ASN_ENCODING = 0x00010000
_CERT_NAME_SIMPLE_DISPLAY_TYPE = 4


def get_cert_subject_cn(thumbprint_hex: str, store_name: str = "MY") -> Optional[str]:
    """Look up a certificate by SHA1 thumbprint and return its Subject CN.

    Opens the LocalMachine certificate store in read-only mode (works without admin).
    Returns None if the certificate is not found or on any error.
    """
    store = None
    cert_ctx = None
    try:
        store = _crypt32.CertOpenStore(
            _CERT_STORE_PROV_SYSTEM_W, 0, None,
            _CERT_SYSTEM_STORE_LOCAL_MACHINE | _CERT_STORE_READONLY_FLAG,
            store_name,
        )
        if not store:
            return None

        hash_bytes = bytes.fromhex(thumbprint_hex)
        hash_buf = (ctypes.c_byte * len(hash_bytes))(*hash_bytes)
        blob = _CRYPT_DATA_BLOB(len(hash_bytes), hash_buf)

        cert_ctx = _crypt32.CertFindCertificateInStore(
            store,
            _X509_ASN_ENCODING | _PKCS_7_ASN_ENCODING,
            0, _CERT_FIND_SHA1_HASH,
            ctypes.byref(blob), None,
        )
        if not cert_ctx:
            return None

        name_buf = ctypes.create_unicode_buffer(256)
        chars = _crypt32.CertGetNameStringW(
            cert_ctx, _CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, name_buf, 256,
        )
        return name_buf.value if chars > 1 else None

    except Exception as e:
        logger.debug("Failed to read cert subject for %s: %s", thumbprint_hex, e)
        return None
    finally:
        if cert_ctx:
            _crypt32.CertFreeCertificateContext(cert_ctx)
        if store:
            _crypt32.CertCloseStore(store, 0)
