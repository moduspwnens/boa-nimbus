import os
import base64
import hashlib

#http://stackoverflow.com/questions/3431825/generating-an-md5-checksum-of-a-file/3431838#3431838
def file_md5_checksum(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def file_sha256_checksum_base64(fname):
    hash_sha256 = hashlib.sha256()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    
    return base64.b64encode(hash_sha256.digest()).decode("utf-8")

#http://code.activestate.com/recipes/576973-getting-the-sha-1-or-md5-hash-of-a-directory/
def directory_sha1_hash(directory):
    import hashlib, os
    SHAhash = hashlib.sha1()
    if not os.path.exists (directory):
        return -1
    
    for root, dirs, files in os.walk(directory):
        for names in files:
            filepath = os.path.join(root,names)
            try:
                f1 = open(filepath, 'rb')
            except:
                # You can't open the file for some reason
                f1.close()
                continue

            while 1:
                # Read file in as little chunks
                buf = f1.read(4096)
                if not buf : break
                SHAhash.update(hashlib.sha1(buf).digest())
            f1.close()
    
    return SHAhash.hexdigest()