""" Test basic puppet operations """
from configparser import ConfigParser

import pytest
from tests.integration_tests.instances import IntegrationInstance


_USERDATA = """\
#cloud-config
puppet:
  install: true
  install_type: {install_type}
  cleanup: true
  conf:
    main:
      foo: bar
    agent:
      spam: eggs
    server:
      gork: bork
    user:
      quux: quuux
"""
PACKAGES_USERDATA = _USERDATA.format(install_type='packages')
AIO_USERDATA = _USERDATA.format(install_type='aio')


def common_verify(puppet_conf_contents, log):
    parser = ConfigParser()
    parser.read_string(puppet_conf_contents)
    assert parser.get('main', 'foo') == 'bar'
    assert parser.get('agent', 'spam') == 'eggs'
    assert parser.get('server', 'gork') == 'bork'
    assert parser.get('user', 'quux') == 'quuux'

    assert 'WARN' not in log
    assert 'Traceback' not in log


@pytest.mark.user_data(PACKAGES_USERDATA)
def test_puppet_packages(client: IntegrationInstance):
    assert client.execute('which puppet') == '/usr/bin/puppet'
    assert '/usr/bin/ruby /usr/bin/puppet agent' in client.execute(
        'ps aux | grep puppet')

    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'Attempting to install puppet latest from packages' in log
    common_verify(
        client.read_from_file('/etc/puppet/puppet.conf'),
        log
    )


@pytest.mark.adhoc  # Can't be regularly reaching out to puppet install script
@pytest.mark.user_data(AIO_USERDATA)
def test_puppet_aio(client: IntegrationInstance):
    assert client.execute('test -f /opt/puppetlabs/bin/puppet').ok
    expected_run = ('/opt/puppetlabs/puppet/bin/ruby '
                    '/opt/puppetlabs/puppet/bin/puppet')
    assert expected_run in client.execute('ps aux | grep puppet')
    assert '' == client.execute('ls /var/tmp/cloud-init')

    log = client.read_from_file('/var/log/cloud-init.log')
    assert 'Attempting to install puppet latest from aio' in log
    common_verify(
        client.read_from_file('/etc/puppetlabs/puppet/puppet.conf'),
        log
    )
