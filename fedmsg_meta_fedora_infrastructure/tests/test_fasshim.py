# -*- coding: utf-8 -*-
#
# This file is part of the fedmsg_meta_fedora_infrastructure package.
# Copyright (C) 2017, Red Hat, Inc.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
from __future__ import absolute_import, unicode_literals

import unittest

import mock

from fedmsg_meta_fedora_infrastructure import fasshim


class SearchFasTests(unittest.TestCase):
    pass


class Nick2FasTests(unittest.TestCase):
    pass


class Email2FasTests(unittest.TestCase):

    @mock.patch('fedmsg_meta_fedora_infrastructure.fasshim._search_fas')
    def test_fedoraproject_short_circuit(self, mock_search_fas):
        """Assert emails ending with fedoraproject.org skip the FAS query."""
        fasname = fasshim.email2fas('jcline@fedoraproject.org')
        self.assertEqual('jcline', fasname)
        self.assertEqual(0, mock_search_fas.call_count)

    def test_searching_fas(self):
        pass
