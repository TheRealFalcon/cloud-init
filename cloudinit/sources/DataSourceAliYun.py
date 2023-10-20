# This file is part of cloud-init. See LICENSE file for license information.

from typing import List

from cloudinit import dmi, sources
from cloudinit.sources import DataSourceEc2 as EC2
from cloudinit.sources import DataSourceHostname

ALIYUN_PRODUCT = "Alibaba Cloud ECS"


class DataSourceAliYun(EC2.DataSourceEc2):

    dsname = "AliYun"
    metadata_urls = ["http://100.100.100.200"]

    # The minimum supported metadata_version from the ec2 metadata apis
    min_metadata_version = "2016-01-01"
    extended_metadata_versions: List[str] = []

    # Aliyun metadata server security enhanced mode overwrite
    @property
    def imdsv2_token_put_header(self):
        return "X-aliyun-ecs-metadata-token"

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        hostname = self.metadata.get("hostname")
        is_default = False
        if hostname is None:
            hostname = "localhost.localdomain"
            is_default = True
        return DataSourceHostname(hostname, is_default)

    def get_public_ssh_keys(self):
        return parse_public_keys(self.metadata.get("public-keys", {}))

    def _get_cloud_name(self):
        if _is_aliyun():
            return EC2.CloudNames.ALIYUN
        else:
            return EC2.CloudNames.NO_EC2_METADATA


def _is_aliyun():
    return dmi.read_dmi_data("system-product-name") == ALIYUN_PRODUCT


def parse_public_keys(public_keys):
    keys = []
    for _key_id, key_body in public_keys.items():
        if isinstance(key_body, str):
            keys.append(key_body.strip())
        elif isinstance(key_body, list):
            keys.extend(key_body)
        elif isinstance(key_body, dict):
            key = key_body.get("openssh-key", [])
            if isinstance(key, str):
                keys.append(key.strip())
            elif isinstance(key, list):
                keys.extend(key)
    return keys


# Used to match classes to dependencies
datasources = [
    (DataSourceAliYun, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
