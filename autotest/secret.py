"""Admin 비밀번호 보관: Windows 자격 증명 관리자(이 PC의 이 사용자 계정으로 암호화). 파일에는 남기지 않는다.

확인·삭제: 제어판 → 자격 증명 관리자 → Windows 자격 증명 → 'PalletizOS-Smoke-Admin'
명령줄: python -m autotest.secret set | show | delete
"""
import ctypes
import ctypes.wintypes as wt
import sys

TARGET = "PalletizOS-Smoke-Admin"
CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE = 1, 2
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wt.DWORD),
                ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
                ("UserName", wt.LPWSTR)]


def save(password, user="Admin", target=TARGET, comment="PalletizOS 스모크 자동화 Admin 로그인"):
    blob = password.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIAL(Type=CRED_TYPE_GENERIC, TargetName=target, Comment=comment,
                   CredentialBlobSize=len(blob), CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                   Persist=CRED_PERSIST_LOCAL_MACHINE, UserName=user)
    if not advapi32.CredWriteW(ctypes.byref(c), 0):
        raise OSError(ctypes.get_last_error(), "CredWrite 실패")


def read(target=TARGET):
    """(사용자 이름, 비밀 값) 또는 None."""
    p = ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        return c.UserName, bytes(c.CredentialBlob[:c.CredentialBlobSize]).decode("utf-16-le")
    finally:
        advapi32.CredFree(p)


def load(target=TARGET):
    r = read(target)
    return r[1] if r else None


def delete(target=TARGET):
    return bool(advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0))


if __name__ == "__main__":
    import getpass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "set":
        save(getpass.getpass("저장할 Admin 비밀번호: "))
        print("저장했습니다:", TARGET)
    elif cmd == "delete":
        print("삭제했습니다" if delete() else "저장된 값이 없습니다")
    else:
        print("저장됨" if load() else "저장된 값 없음", "-", TARGET)
