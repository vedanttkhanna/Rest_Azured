from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlparse


def job_id(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}",value):
        raise ValueError("job_id must contain 1-128 letters, digits, underscores or hyphens")
    return value


class Store:
    def __init__(self, root, bucket=None, client=None):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.bucket=bucket
        self._client=client

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client=boto3.client("s3")
        return self._client

    def path(self,key):
        dest=(self.root/key).resolve()
        if not dest.is_relative_to(self.root): raise ValueError("Object key escapes workspace")
        dest.parent.mkdir(parents=True,exist_ok=True)
        return dest

    def put_bytes(self,key,data,content_type):
        self.path(key).write_bytes(data)
        if self.bucket:
            self.client.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType=content_type)
            return f"s3://{self.bucket}/{key}"
        return str(self.path(key))

    def put_json(self,key,data):
        return self.put_bytes(key,json.dumps(data,indent=2,allow_nan=False).encode(),"application/json")

    def publish(self,key,path,content_type):
        return self.put_bytes(key,Path(path).read_bytes(),content_type)

    def get_optional(self,key):
        if self.path(key).exists(): return self.path(key).read_bytes()
        if not self.bucket: return None
        from botocore.exceptions import ClientError
        try: return self.client.get_object(Bucket=self.bucket,Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey","404"): return None
            raise

    def materialize(self,uri):
        if str(uri).startswith("s3://"):
            parts=urlparse(uri)
            if not self.bucket or parts.netloc!=self.bucket:
                raise ValueError("Input S3 URI must belong to the configured jobs bucket")
            key=parts.path.lstrip("/")
            dest=self.path(key)
            self.client.download_file(self.bucket,key,str(dest))
            return dest
        if self.bucket: raise ValueError("Cloud handlers require S3 input URIs")
        path=Path(uri).resolve()
        if not path.is_file(): raise ValueError(f"Input file not found: {path.name}")
        return path
