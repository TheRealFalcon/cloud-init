"""Integration tests for CLI functionality

These would be for behavior manually invoked by user from the command line
"""
import json
import yaml

import pytest

from tests.integration_tests.instances import IntegrationInstance


NETWORK_DATA = """\
network:
  version: 1
  config:
    - type: physical
      name: eth0
"""


RENDER_CONFIG = """\
##template: jinja
#cloud-config
runcmd:
  - echo '{{v1.local_hostname}}' > /var/tmp/runcmd_output
"""


VALID_USER_DATA = """\
#cloud-config
runcmd:
  - echo 'hi' > /var/tmp/test
"""


@pytest.mark.user_data(VALID_USER_DATA)
class TestCliUtilities:
    """Basic check of CLI utilities"""
    def test_schema_valid_userdata(self, class_client: IntegrationInstance):
        """Test `cloud-init devel schema` with valid userdata.

        PR #575
        """
        client = class_client
        result = client.execute('cloud-init devel schema --system')
        assert result.ok
        assert 'Valid cloud-config: system userdata' == result.stdout.strip()

    def test_collect_logs(self, class_client: IntegrationInstance):
        """Test `cloud-init collect-logs`"""
        client = class_client
        collect_run = client.execute(
            'cloud-init collect-logs -u -t ./cloud-init.tar.gz 2>&1')
        assert collect_run.ok
        assert 'Wrote' in collect_run
        assert collect_run.count('\n') == 0

        untar_run = client.execute('tar xvf cloud-init.tar.gz')
        assert untar_run.ok
        # Not exhaustive, but files we'd expect to be in any successful run
        expected_files = [
            '/version',
            '/cloud-init.log',
            '/cloud-init-output.log',
            '/run/cloud-init/result.json',
            '/run/cloud-init/status.json',
            '/run/cloud-init/instance-data.json',
            '/run/cloud-init/instance-data-sensitive.json'
        ]
        for f in expected_files:
            assert f in untar_run

    def test_status(self, class_client: IntegrationInstance):
        """Test `cloud-init status`"""
        client = class_client
        status = client.execute('cloud-init status')
        assert status.ok
        assert 'status: done' == status

        status_long = client.execute('cloud-init status --long')
        assert status_long.ok
        assert 'status: done' in status_long
        assert 'time:' in status_long
        assert 'detail:' in status_long

    def test_query(self, class_client: IntegrationInstance):
        """Test `cloud-init query`"""
        client = class_client
        query_all_run = client.execute('cloud-init query -a')
        assert query_all_run.ok
        query_all = json.loads(query_all_run)
        expected_keys = [
            'cloud_name',
            'ds',
            'instance_id',
            'merged_cfg',
            'platform',
            'sys_info',
            'userdata',
            'v1'
        ]
        for key in expected_keys:
            assert key in query_all

        query_list_run = client.execute('cloud-init query -l')
        assert query_list_run.ok
        for key in query_list_run:
            assert key in query_list_run

        query_format_run = client.execute(
            'cloud-init query -f "{{v1.local_hostname}}"')
        assert query_format_run.ok
        assert client.execute('hostname') == query_format_run

    def test_render_config(self, class_client: IntegrationInstance):
        """Test `cloud-init devel render`"""
        client = class_client
        client.write_to_file('/tmp/cloud-config.yml', RENDER_CONFIG)
        render = client.execute(
            'cloud-init devel render /tmp/cloud-config.yml')
        assert "- echo '{}' > /var/tmp/runcmd_output".format(
            client.execute('hostname')) in render

    def test_net_convert(self, class_client: IntegrationInstance):
        """Test `cloud-init net-convert`.

        Unit tests should cover most of this functionality, so ensure
        we can do some basic transformations.
        """
        client = class_client
        client.write_to_file('/tmp/net1.yaml', NETWORK_DATA)
        common_start = (
            'cloud-init devel net-convert -p /tmp/net1.yaml -k yaml -d /tmp ')

        # ENI on debian
        assert client.execute(common_start + '-D debian -O eni').ok
        eni_out = client.read_from_file(
            '/tmp/etc/network/interfaces.d/50-cloud-init')
        assert 'iface eth0 inet manual' in eni_out

        # Netplan on ubuntu
        assert client.execute(common_start + '-D ubuntu -O netplan').ok
        netplan_out = client.read_from_file(
            '/tmp/etc/netplan/50-cloud-init.yaml')
        netplan_conf = yaml.safe_load(netplan_out)
        assert netplan_conf['network']['version'] == 2
        assert netplan_conf['network']['ethernets']['eth0'] == {}

        # Sysconfig on RHEL
        assert client.execute(common_start + '-D rhel -O sysconfig').ok
        sysconfig_network = client.read_from_file('/tmp/etc/sysconfig/network')
        assert 'NETWORKING=yes' in sysconfig_network

        sysconfig_script = client.read_from_file(
            '/tmp/etc/sysconfig/network-scripts/ifcfg-eth0')
        assert 'DEVICE=eth0' in sysconfig_script
        assert 'ONBOOT=yes' in sysconfig_script
        assert 'TYPE=Ethernet' in sysconfig_script

        # Networkd on photon
        assert client.execute(common_start + '-D photon -O networkd').ok
        networkd_out = client.read_from_file(
            '/tmp/etc/systemd/network/10-cloud-init-eth0.network')
        assert '[Match]\nName=eth0' in networkd_out
        assert '[Network]\nDHCP=no' in networkd_out


INVALID_USER_DATA = """\
runcmd:
  - echo 'hi' > /var/tmp/test
"""


@pytest.mark.user_data(INVALID_USER_DATA)
def test_schema_invalid_userdata(client: IntegrationInstance):
    """Test `cloud-init devel schema` with invalid userdata.

    PR #575
    """
    result = client.execute('cloud-init devel schema --system')
    assert not result.ok
    assert 'Cloud config schema errors' in result.stderr
    assert 'needs to begin with "#cloud-config"' in result.stderr
