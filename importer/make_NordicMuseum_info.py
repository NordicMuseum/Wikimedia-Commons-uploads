#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
Construct image information templates and categories for Nordic Museum data.

These templates may be Artwork/Photograph/Information depending on the image
type.

Transforms the partially processed data from nm_massload into a
BatchUploadTools compliant json file.
"""
import os.path
from collections import OrderedDict

import pywikibot

import batchupload.common as common
import batchupload.helpers as helpers
from batchupload.make_info import MakeBaseInfo
import importer.DiMuMappingUpdater as mapping_updater


DIR_PATH = os.path.dirname(os.path.realpath(__file__))
MAPPINGS_DIR = 'mappings'
BATCH_CAT = 'Images from Nordiska museet'  # stem for maintenance categories (We use "Images from Nordiska museet" for both content and maintenance today, consider splitting these)
BATCH_DATE = '2017-10'  # branch for this particular batch upload
LOGFILE = 'nm_processing_october.log'


class NMInfo(MakeBaseInfo):
    """Construct descriptions + filenames for a Nordic Museum batch upload."""

    def __init__(self, **options):
        """Initialise a make_info object."""
        batch_date = options.get('batch_label') or BATCH_DATE
        batch_cat = options.get('base_meta_cat') or BATCH_CAT
        super(NMInfo, self).__init__(batch_cat, batch_date, **options)

        # black-listed values
        self.bad_namn = (u'okänd fotograf', u'okänd konstnär')
        self.bad_date = (u'odaterad', )

        #self.commons = pywikibot.Site('commons', 'commons')
        #self.wikidata = pywikibot.Site('wikidata', 'wikidata')
        #self.category_cache = {}  # cache for category_exists()
        #self.k_nav_list = {}
        #self.photographer_cache = {}
        self.log = common.LogFile('', LOGFILE)

    def load_data(self, in_file):
        """
        Load the provided data (output from nm_massload).

        Return this as a dict with an entry per file which can be used for
        further processing.

        :param in_file: the path to the metadata file
        :return: dict
        """
        return common.open_and_read_file(in_file, as_json=True)

    def load_mappings(self, update_mappings):
        """
        Update mapping files, load these and package appropriately.

        :param update_mappings: whether to first download the latest mappings
        """
        self.mappings = mapping_updater.load_mappings(update_mappings)

    def process_data(self, raw_data):
        """
        Take the loaded data and construct a NMItem for each.

        Populates self.data.

        :param raw_data: output from load_data()
        """
        d = {}
        for key, value in raw_data.items():
            item = NMItem(value, self)
            if item.problem:
                text = '{0} -- image was skipped because of: {1}'.format(
                    item.ID, '\n'.join(item.problem))
                pywikibot.output(text)
                self.log.write(text)
            else:
                d[key] = item

        self.data = d

    def generate_filename(self, item):
        """
        Given an item (dict) generate an appropriate filename.

        The filename has the shape: descr - Collection - id
        and does not include filetype

        :param item: the metadata for the media file in question
        :return: str
        """
        return helpers.format_filename(
            item.get_title_description(), 'Nordiska museet', item.idno)

    def make_info_template(self, item):
        """
        Given an item of any type return the filled out template.

        @param item: the metadata for the media file in question
        @return: str
        """
        if item.type == "Photograph":
            if item.is_photo:
                self.make_photograph_template(item)
            else:
                self.make_artwork_info(item)
        else:
            # haven't figured out Thing yet
            raise NotImplementedError

    def get_object_location(self, item):
        """
        Append object location if appropriate.

        :param item: the metadata for the media file in question
        :return: str
        """
        if item.latitude and item.longitude:
            return '\n{{Object location dec|%s|%s}}' % (
                item.latitude, item.longitude)
        return ''

    def make_photograph_template(self, item):
        """
        Create the Photograph template for a single NM entry.

        :param item: the metadata for the media file in question
        :return: str
        """
        template_name = 'Photograph'
        template_data = OrderedDict()
        template_data['photographer'] = item.get_creator()
        template_data['title'] = item.get_title()
        template_data['description'] = item.get_description()
        template_data['original description'] = item.get_original_description()
        template_data['depicted people'] = item.get_depicted_object(
            typ='person')
        template_data['depicted place'] = item.get_depicted_place()
        template_data['date'] = item.get_creation_date()
        template_data['medium'] = item.get_materials()
        template_data['institution'] = '{{Institution:Nordiska museet}}'
        template_data['accession number'] = item.get_id_link()
        template_data['source'] = item.get_source()
        template_data['permission'] = item.get_license_text()
        template_data['other_versions'] = item.get_other_versions()

        txt = helpers.output_block_template(template_name, template_data, 0)
        txt += self.get_object_location(item)

        return txt

    def make_artwork_info(self, item):
        """
        Create the Artwork template for a single NM entry.

        :param item: the metadata for the media file in question
        :return: str
        """
        template_name = 'Artwork'
        template_data = OrderedDict()
        template_data['artist'] = item.get_creator()
        template_data['title'] = item.get_title()
        template_data['date'] = item.get_creation_date()
        template_data['description'] = item.get_description(with_depicted=True)
        template_data['other_fields_2'] = item.get_original_description()
        template_data['medium'] = item.get_materials()
        template_data['dimensions'] = ''
        template_data['institution'] = '{{Institution:Nordiska museet}}'
        template_data['location'] = ''
        template_data['references'] = ''
        template_data['object history'] = ''
        template_data['credit line'] = ''
        template_data['inscriptions'] = ''
        template_data['notes'] = ''
        template_data['accession number'] = item.get_id_link()
        template_data['source'] = item.get_source()
        template_data['permission'] = item.get_license_text()
        template_data['other_versions'] = item.get_other_versions()

        txt = helpers.output_block_template(template_name, template_data, 0)
        txt += self.get_object_location(item)

        return txt

    # @todo: ensure that these work with uploade_by_url
    # can also try the CORS enabled fdms01.dimu.org server
    def get_original_filename(self, item):
        """
        Generate the url where the original files can be found.

        Uses media_id instead of filename as the latter is not guaranteed to
        exist or be mapped to the right image.
        """
        server = 'http://dms01.dimu.org'
        return '{server}/image/{id}?dimension=max&filename={id}.jpg'.format(
            server=server, id=item.media_id)

    # @todo: check need
    def get_creator(self, creator):
        """
        given a creator (or creators) return the creator template,
        linked entry or plain name
        """
        raise NotImplementedError

    def generate_content_cats(self, item):
        """
        Extract any mapped keyword categories or depicted categories.

        @param item: the item to analyse
        """
        raise NotImplementedError

    def generate_meta_cats(self, item, content_cats):
        """
        Produce maintanance categories related to a media file.

        @param item: the metadata for the media file in question
        @param content_cats: any content categories for the file
        @return: list of categories (without "Category:" prefix)
        """
        raise NotImplementedError

    # @todo update
    @classmethod
    def main(cls, *args):
        """Command line entry-point."""
        usage = (
            'Usage:'
            '\tpython make_info.py -in_file:PATH -dir:PATH\n'
            '\t-in_file:PATH path to metadata file\n'
            '\t-dir:PATH specifies the path to the directory containing a '
            'user_config.py file (optional)\n'
            '\t-update_mappings:BOOL if mappings should first be updated '
            'against online sources (defaults to True)\n'
            '\tExample:\n'
            '\tpython make_NordicMuseum_info.py -in_file:nm_data.json '
            '-base_name:nm_output -update_mappings:True -dir:NM\n'
        )
        info = super(NMInfo, cls).main(usage=usage, *args)
        if info:
            pywikibot.output(info.log.close_and_confirm())


class NMItem(object):
    """Store metadata and methods for a single media file."""

    def __init__(self, initial_data, nm_info):
        """
        Create a NMItem item from a dict where each key is an attribute.

        :param initial_data: dict of data to set up item with
        :param nm_info: the NMInfo instance
        """
        # ensure all required variables are present
        required_entries = ('latitude', 'longitude', 'is_photo', 'photographer')
        for entry in required_entries:
            if entry not in initial_data:
                initial_data[entry] = None

        for key, value in initial_data.items():
            setattr(self, key, value)

        self.wd = {}  # store for relevant Wikidata identifiers
        self.content_cats = set()  # content relevant categories without prefix
        self.meta_cats = set()  # meta/maintenance proto categories
        self.nm_info = nm_info  # the NMInfo instance creating this NMItem
        self.log = nm_info.log
        self.commons = nm_info.commons

    def get_title_description(self):
        """Construct an appropriate description for a filename."""
        raise NotImplementedError

    # @todo: adapt for depicted person, other keywords
    def get_original_description(self):
        """
        Given an item get an appropriate original description
        """
        original_desc = self.description
        if self.subjects:
            original_desc += '<br />{label}: {words}'.format(
                label=helpers.bolden('Ämnesord'),
                words='; '.join(self.subjects))

        return '{{Nordiska museet description|1=%s}}' % original_desc

    def get_id_link(self):
        """Create the id link template."""
        nm_id = ''
        for glam, idno in self.glam_id:
            if glam == 'S-NM':
                nm_id = idno
        if nm_id:
            series, _, idno = nm_id.partition('.')
            return '{{Nordiska museet link|{series}|{id}}}'.format(
                series=series, id=idno)
        return ''

    def get_source(self):
        """Produce a linked source statement."""
        template = '{{Nordiska museet cooperation project}}'
        txt = ''
        if self.photographer:
            txt += '{} / '.format(self.photographer)
        txt += 'Nordiska museet'
        return '[{url} {link_text}]\n{template}'.format(
            url=self.get_dimu_url(), link_text=txt, template=template)

    def get_dimu_url(self):
        """Create the url for the item on DigitaltMuseum."""
        return 'https://digitaltmuseum.se/{id}/?slide={order}'.format(
            id=self.dimu_id, order=self.slider_order)

    def get_description(self, with_depicted=True):
        """
        Given an item get an appropriate description

        :param with_depicted: whether to also include depicted data
        """
        raise NotImplementedError
        #Use get_depicted_place
        #handle view over
        #get_depicted_object(item, typ='person')


if __name__ == "__main__":
    NMInfo.main()
