# Copyright (c) 2018 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ddt
import mock

from neutronclient.common import exceptions as n_exc

from kuryr_kubernetes.controller.drivers import base as drivers
from kuryr_kubernetes.controller.drivers import vif_pool
from kuryr_kubernetes.controller.handlers import namespace
from kuryr_kubernetes import exceptions as k_exc
from kuryr_kubernetes.tests import base as test_base


@ddt.ddt
class TestNamespaceHandler(test_base.TestCase):

    def setUp(self):
        super(TestNamespaceHandler, self).setUp()

        self._project_id = mock.sentinel.project_id
        self._subnets = mock.sentinel.subnets

        self._namespace_version = mock.sentinel.namespace_version
        self._namespace_link = mock.sentinel.namespace_link

        self._namespace_name = 'ns-test'
        self._namespace = {
            'metadata': {'name': self._namespace_name,
                         'resourceVersion': self._namespace_version,
                         'selfLink': self._namespace_link},
            'status': {'phase': 'Active'}
        }

        self._handler = mock.MagicMock(spec=namespace.NamespaceHandler)

        self._handler._drv_project = mock.Mock(
            spec=drivers.NamespaceProjectDriver)
        self._handler._drv_subnets = mock.Mock(spec=drivers.PodSubnetsDriver)
        self._handler._drv_vif_pool = mock.MagicMock(
            spec=vif_pool.MultiVIFPool)

        self._get_project = self._handler._drv_project.get_project
        self._get_subnets = self._handler._drv_subnets.get_subnets

        self._create_namespace_network = (
            self._handler._drv_subnets.create_namespace_network)
        self._delete_namespace_subnet = (
            self._handler._drv_subnets.delete_namespace_subnet)
        self._get_net_crd = self._handler._get_net_crd
        self._set_net_crd = self._handler._set_net_crd
        self._get_net_id_from_net_crd = (
            self._handler._get_net_id_from_net_crd)
        self._rollback_network_resources = (
            self._handler._drv_subnets.rollback_network_resources)
        self._delete_network_pools = (
            self._handler._drv_vif_pool.delete_network_pools)

        self._get_project.return_value = self._project_id
        self._get_subnets.return_value = self._subnets

    def _get_crd(self):
        crd = {
            'kind': 'KuryrNet',
            'spec': {
                'routerId': mock.sentinel.router_id,
                'netId': mock.sentinel.net_id,
                'subnetId': mock.sentinel.subnet_id,
            }
        }
        return crd

    @mock.patch.object(drivers.VIFPoolDriver, 'get_instance')
    @mock.patch.object(drivers.PodSubnetsDriver, 'get_instance')
    @mock.patch.object(drivers.NamespaceProjectDriver, 'get_instance')
    def test_init(self, m_get_project_driver, m_get_subnets_driver,
                  m_get_vif_pool_driver):
        project_driver = mock.sentinel.project_driver
        subnets_driver = mock.sentinel.subnets_driver
        vif_pool_driver = mock.Mock(spec=vif_pool.MultiVIFPool)

        m_get_project_driver.return_value = project_driver
        m_get_subnets_driver.return_value = subnets_driver
        m_get_vif_pool_driver.return_value = vif_pool_driver

        handler = namespace.NamespaceHandler()

        self.assertEqual(project_driver, handler._drv_project)
        self.assertEqual(subnets_driver, handler._drv_subnets)
        self.assertEqual(vif_pool_driver, handler._drv_vif_pool)

    def test_on_present(self):
        net_crd = self._get_crd()

        self._get_net_crd.return_value = None
        self._create_namespace_network.return_value = net_crd

        namespace.NamespaceHandler.on_present(self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._create_namespace_network.assert_called_once_with(
            self._namespace_name, self._project_id)
        self._set_net_crd.assert_called_once_with(self._namespace, net_crd)
        self._rollback_network_resources.assert_not_called()

    def test_on_present_existing(self):
        net_crd = self._get_crd()

        self._get_net_crd.return_value = net_crd

        namespace.NamespaceHandler.on_present(self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._create_namespace_network.assert_not_called()
        self._set_net_crd.assert_not_called()
        self._rollback_network_resources.assert_not_called()

    @ddt.data((n_exc.NeutronClientException), (k_exc.K8sClientException))
    def test_on_present_create_exception(self, m_create_net):
        self._get_net_crd.return_value = None
        self._create_namespace_network.side_effect = m_create_net

        self.assertRaises(m_create_net, namespace.NamespaceHandler.on_present,
                          self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._create_namespace_network.assert_called_once_with(
            self._namespace_name, self._project_id)
        self._set_net_crd.assert_not_called()
        self._rollback_network_resources.assert_not_called()

    def test_on_present_set_crd_exception(self):
        net_crd = self._get_crd()

        self._get_net_crd.return_value = None
        self._create_namespace_network.return_value = net_crd
        self._set_net_crd.side_effect = k_exc.K8sClientException

        namespace.NamespaceHandler.on_present(self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._create_namespace_network.assert_called_once_with(
            self._namespace_name, self._project_id)
        self._set_net_crd.assert_called_once_with(self._namespace, net_crd)
        self._rollback_network_resources.assert_called_once()

    def test_on_present_rollback_exception(self):
        net_crd = self._get_crd()

        self._get_net_crd.return_value = None
        self._create_namespace_network.return_value = net_crd
        self._set_net_crd.side_effect = k_exc.K8sClientException
        self._rollback_network_resources.side_effect = (
            n_exc.NeutronClientException)

        self.assertRaises(n_exc.NeutronClientException,
                          namespace.NamespaceHandler.on_present,
                          self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._create_namespace_network.assert_called_once_with(
            self._namespace_name, self._project_id)
        self._set_net_crd.assert_called_once_with(self._namespace, net_crd)
        self._rollback_network_resources.assert_called_once()

    def test_on_deleted(self):
        net_crd = self._get_crd()
        net_id = mock.sentinel.net_id

        self._get_net_crd.return_value = net_crd
        self._get_net_id_from_net_crd.return_value = net_id

        namespace.NamespaceHandler.on_deleted(self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._get_net_id_from_net_crd.assert_called_once_with(net_crd)
        self._delete_network_pools.assert_called_once_with(net_id)
        self._delete_namespace_subnet.assert_called_once_with(net_crd)

    def test_on_deleted_missing_crd_annotation(self):
        self._get_net_crd.return_value = None

        namespace.NamespaceHandler.on_deleted(self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._get_net_id_from_net_crd.assert_not_called()
        self._delete_network_pools.assert_not_called()
        self._delete_namespace_subnet.assert_not_called()

    def test_on_deleted_k8s_exception(self):
        net_crd = self._get_crd()

        self._get_net_crd.return_value = net_crd
        self._get_net_id_from_net_crd.side_effect = k_exc.K8sClientException

        self.assertRaises(k_exc.K8sClientException,
                          namespace.NamespaceHandler.on_deleted,
                          self._handler, self._namespace)

        self._get_net_crd.assert_called_once_with(self._namespace)
        self._get_net_id_from_net_crd.assert_called_once_with(net_crd)
        self._delete_network_pools.assert_not_called()
        self._delete_namespace_subnet.assert_not_called()
