#!/usr/bin/python
# -*- coding: utf-8  -*-
import unittest

import requests

import pywikibot

import mock
from importer.DiMuHarvester import DiMuHarvester as harvester


class DiMuHarvesterTestBase(unittest.TestCase):

    def setUp(self):
        # silence output
        output_patcher = mock.patch(
            'importer.DiMuHarvester.pywikibot.output')
        self.mock_output = output_patcher.start()
        self.addCleanup(output_patcher.stop)

        logfile_patcher = mock.patch(
            'importer.DiMuHarvester.common.LogFile')
        self.mock_logfile = logfile_patcher.start()
        self.mock_logfile.return_value = self.mock_logfile
        self.addCleanup(logfile_patcher.stop)

        self.harvester = harvester({})


class TestGetSearchRecordFromUrl(DiMuHarvesterTestBase):

    def setUp(self):
        super(TestGetSearchRecordFromUrl, self).setUp()
        get_json_patcher = mock.patch(
            'importer.DiMuHarvester.get_json_from_url')
        self.mock_get_json = get_json_patcher.start()
        self.addCleanup(get_json_patcher.stop)
        self.mock_get_json.return_value = {'response': 'a response'}

        self.base_url = 'http://api.dimu.org/api/solr/select'

    def test_get_search_record_from_url_defaults(self):
        self.assertEqual(
            self.harvester.get_search_record_from_url(123),
            'a response'
        )
        self.mock_get_json.assert_called_once_with(
            self.base_url,
            {'q': 123, 'rows': 100, 'wt': 'json',
             'api.key': None, 'start': 0})

    def test_get_search_record_from_url_load_api_key(self):
        self.harvester.settings['api_key'] = 'the key'
        self.assertEqual(
            self.harvester.get_search_record_from_url(123),
            'a response'
        )
        self.mock_get_json.assert_called_once_with(
            self.base_url,
            {'q': 123, 'rows': 100, 'wt': 'json',
             'api.key': 'the key', 'start': 0})

    def test_get_search_record_from_url_start(self):
        self.assertEqual(
            self.harvester.get_search_record_from_url(123, start=125),
            'a response'
        )
        self.mock_get_json.assert_called_once_with(
            self.base_url,
            {'q': 123, 'rows': 100, 'wt': 'json',
             'api.key': None, 'start': 125})

    def test_get_search_record_from_url_glam(self):
        self.harvester.settings['glam_code'] = 'GLAM'
        self.assertEqual(
            self.harvester.get_search_record_from_url(123),
            'a response'
        )
        self.mock_get_json.assert_called_once_with(
            self.base_url,
            {'q': 123, 'rows': 100, 'wt': 'json',
             'api.key': None, 'start': 0, 'fq': ['identifier.owner:GLAM']})

    def test_get_search_record_from_url_folder(self):
        self.assertEqual(
            self.harvester.get_search_record_from_url(123, only_folder=True),
            'a response'
        )
        self.mock_get_json.assert_called_once_with(
            self.base_url,
            {'q': 123, 'rows': 100, 'wt': 'json',
             'api.key': None, 'start': 0, 'fq': ['artifact.type:Folder']})

    def test_get_search_record_from_url_glam_and_folder(self):
        self.harvester.settings['glam_code'] = 'GLAM'
        self.assertEqual(
            self.harvester.get_search_record_from_url(123, only_folder=True),
            'a response'
        )
        self.mock_get_json.assert_called_once_with(
            self.base_url,
            {'q': 123, 'rows': 100, 'wt': 'json',
             'api.key': None, 'start': 0,
             'fq': ['identifier.owner:GLAM', 'artifact.type:Folder']})

    def test_get_search_record_from_url_error(self):
        self.mock_get_json.side_effect = requests.HTTPError(
            'AN ERROR',
            response=mock.Mock(url='URL', status_code=400))
        expected_error = 'Error when trying to look up URL: AN ERROR'

        with self.assertRaises(pywikibot.Error) as cm:
            self.harvester.get_search_record_from_url(123)
        self.mock_logfile.write.assert_called_once_with(expected_error)
        self.assertEqual(
            str(cm.exception),
            expected_error
        )

    def test_get_search_record_from_url_404_error(self):
        self.mock_get_json.side_effect = requests.HTTPError(
            'AN ERROR',
            response=mock.Mock(url='URL', status_code=404))
        expected_error = 'Api key not accepted by DiMu API'

        with self.assertRaises(pywikibot.Error) as cm:
            self.harvester.get_search_record_from_url(123)
        self.mock_logfile.write.assert_called_once_with(expected_error)
        self.assertEqual(
            str(cm.exception),
            expected_error
        )


class TestMergePlace(unittest.TestCase):

    def test_merge_place_ok(self):
        """Ensure same values and different keys can be merged."""
        first_place = {
            'country': 'Sverige',
            'county': '20',
            'parish': '123',
            'role': 'depicted_place'
        }
        second_place = {
            'country': 'Sverige',
            'county': '20',
            'muni': '4321',
            'role': 'depicted_place'
        }
        expected = {
            'country': 'Sverige',
            'county': '20',
            'parish': '123',
            'muni': '4321',
            'role': 'depicted_place'
        }

        self.assertEqual(
            harvester.merge_place(first_place, second_place),
            expected
        )

    def test_merge_place_fail(self):
        """Ensure same key different value fails."""
        first_place = {
            'country': 'Sverige',
            'county': '20',
            'muni': '1234',
            'role': 'depicted_place'
        }
        second_place = {
            'country': 'Sverige',
            'county': '20',
            'muni': '4321',
            'role': 'depicted_place'
        }

        with self.assertRaises(pywikibot.Error) as cm:
            harvester.merge_place(first_place, second_place)
        self.assertEqual(
            str(cm.exception),
            'failed merge'
        )

    def test_merge_place_other_ok(self):
        """Ensure same values and different keys in other can be merged."""
        first_place = {
            'country': 'Sverige',
            'county': '20',
            'other': {
                'ort': 'foobar',
                'port': 'foo'
            },
            'role': 'depicted_place'
        }
        second_place = {
            'country': 'Sverige',
            'county': '20',
            'other': {
                'ort': 'foobar',
                'street': 'bar'
            },
            'role': 'depicted_place'
        }
        expected = {
            'country': 'Sverige',
            'county': '20',
            'other': {
                'ort': 'foobar',
                'port': 'foo',
                'street': 'bar'
            },
            'role': 'depicted_place'
        }

        self.assertEqual(
            harvester.merge_place(first_place, second_place),
            expected
        )

    def test_merge_place_other_fail(self):
        """Ensure same key different values in other fails."""
        first_place = {
            'country': 'Sverige',
            'county': '20',
            'other': {
                'ort': 'foobar',
                'port': 'bar'
            },
            'role': 'depicted_place'
        }
        second_place = {
            'country': 'Sverige',
            'county': '20',
            'other': {
                'ort': 'foobar',
                'port': 'foo'
            },
            'role': 'depicted_place'
        }

        with self.assertRaises(pywikibot.Error) as cm:
            harvester.merge_place(first_place, second_place)
        self.assertEqual(
            str(cm.exception),
            'failed merge other'
        )
