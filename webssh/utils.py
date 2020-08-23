

def byte2str(bstr, encoding='utf-8'):
    if isinstance(bstr, bytes):
        return bstr.decode(encoding=encoding)
    return bstr


def str2byte(str, encoding='utf-8'):
    if isinstance(str, str):
        return str.encode(encoding)
    return str
