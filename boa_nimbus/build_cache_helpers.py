import os
import json
import uuid
import hashlib
import hashing_helpers

build_cache_hashes_directory = None

def get_hash_of_path(path):
    if os.path.isfile(path):
        return hashing_helpers.file_md5_checksum(path)
    else:
        return hashing_helpers.directory_sha1_hash(path)

def get_previous_build_cache_hash_file_path(build_key, path):
    cache_file = "{}-{}.json".format(
        hashlib.md5(build_key.encode("utf-8")).hexdigest(),
        hashlib.md5(path.encode("utf-8")).hexdigest()
    )
    
    return os.path.join(
        build_cache_hashes_directory,
        cache_file
    )

def get_previous_build_hash_for_path(build_key, path):
    cache_hash_file_path = get_previous_build_cache_hash_file_path(build_key, path)
    
    try:
        previous_build_cache_dict = json.loads(open(cache_hash_file_path).read())
        return previous_build_cache_dict["path"]
    except:
        # Effectively guarantee the hash doesn't match.
        return hashlib.md5(str(uuid.uuid4()).encode("utf-8")).hexdigest()

def has_build_hash_changed_for_path(build_key, path):
    new_hash = get_hash_of_path(path)
    old_hash = get_previous_build_hash_for_path(build_key, path)
    
    return old_hash != new_hash

def write_build_hash_for_path(build_key, path):
    cache_hash_file_path = get_previous_build_cache_hash_file_path(build_key, path)
    
    with open(cache_hash_file_path, "w") as f:
    
        current_path_hash = get_hash_of_path(path)
    
        f.write(json.dumps({
            "path": current_path_hash
        }))