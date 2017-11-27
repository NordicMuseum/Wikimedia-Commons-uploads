#!/usr/bin/python
# -*- coding: utf-8  -*-
"""
Download and process DiMu data for folder of images and store as json.


usage:
    python importer/DiMuHarvester.py [OPTIONS]

&params;
"""
import requests

import pywikibot

import batchupload.common as common
import batchupload.helpers as helpers

SETTINGS = "settings.json"
LOGFILE = 'dimu_harvest.log'
OUTPUT_FILE = 'dimu_harvest_data.json'

DEFAULT_OPTIONS = {
    'settings_file': SETTINGS,
    'api_key': 'demo',
    'glam_code': None,
    'log_file': LOGFILE,
    'output_file': OUTPUT_FILE,
    'verbose': False,
    'cutoff': None,
    'folder_id': None
}
PARAMETER_HELP = u"""\
Basic DiMuHarvester options (can also be supplied via the settings file):
-settings_file:PATH path to settings file (DEF: {settings_file})
-api_key:STR        key used to access DiMu API (DEF: {api_key})
-glam_code:STR      DiMu code for the institution, e.g. "S-NM" \
(DEF: {glam_code})
-log_file:PATH      path to log file (DEF: {log_file})
-output_file:PATH   path to output file (DEF: {output_file})
-verbose:BOOL       if verbose output is desired (DEF: {verbose})
-cutoff:INT         if run should be terminated after these many hits. \
All are processed if not present (DEF: {cutoff})

Can also handle any pywikibot options. Most importantly:
-simulate           don't write to database
-help               output all available options
"""
docuReplacements = {'&params;': PARAMETER_HELP.format(**DEFAULT_OPTIONS)}

## use person role (in license etc.) to set data['creator']
## consider merging copyright and default_copyright into one tag


class DiMuHarvester(object):
    """A harvester for all images in a DigitaltMuseum folder."""

    def __init__(self, options):
        """Initialise a harvester object for a DigitaltMuseum harvest."""
        self.data = {}  # data container for harvested info
        self.settings = options
        self.log = common.LogFile('', self.settings.get('log_file'))
        self.log.write_w_timestamp('Harvester started...')

    def save_data(self, filename=None):
        """Dump data as json blob."""
        filename = filename or self.settings.get('output_file')
        common.open_and_write_file(filename, self.data, as_json=True)
        pywikibot.output('{0} created'.format(filename))

    def get_search_record_from_url(self, query, only_folder=False, start=None):
        """
        Perform search on DiMu api and return the response.

        :param query: the required search term, e.g. an uuid
        :param only_folder: filter out any non-folders
        :param start: starting value of result pager. Default: 0
        """
        base_url = 'http://api.dimu.org/api/solr/select'
        payload = {
            'wt': 'json',
            'rows': 100,
            'api.key': self.settings.get('api_key'),
            'start': start or 0,
            'q': query
        }
        if self.settings.get('glam_code'):
            payload['fq'] = []
            payload['fq'].append('identifier.owner:{}'.format(
                self.settings.get('glam_code')))
        if only_folder:
            payload['fq'] = payload.get('fq') or []
            payload['fq'].append('artifact.type:Folder')

        try:
            data = get_json_from_url(base_url, payload)
        except requests.HTTPError as e:
            # Note that DiMu might have redirected the url
            error_message = 'Error when trying to look up {0}: {1}'.format(
                e.response.url, e)
            if e.response.status_code == 404:
                # a 404 is returned if the api key is incorrect
                error_message = 'Api-key not accepted by DiMu API!'

            self.log.write(error_message)
            raise pywikibot.Error(error_message)

        return data.get('response')

    def load_collection(self, idno):
        """
        Process the collection/folder with the given id.

        :param idno: either the uuid or uniqueId for the folder
        """
        self.folder_uuid = self.load_collection_object(idno)

        search_data = self.get_search_record_from_url(
            query='artifact.folderUids:{}'.format(self.folder_uuid))
        total_results = search_data.get('numFound')
        start = 0
        self.verbose_output('Found {} results'.format(total_results))

        num_hits = len(search_data.get('docs'))
        cutoff = self.settings.get('cutoff')
        stop = False
        while(not stop and num_hits > 0):
            # allow a run to be interupted after a given number of entries
            if cutoff and (start + num_hits) >= cutoff:
                diff = start + num_hits - cutoff
                search_data['docs'] = search_data.get('docs')[diff:]
                stop = True

            for item in search_data.get('docs'):
                item_type = item.get('artifact.type')
                if item_type == 'Folder':
                    continue
                elif item_type == 'Photograph':
                    # skip items without images
                    if not item.get('artifact.hasPictures'):
                        continue
                    self.process_single_object(item.get('artifact.uuid'))
                else:
                    raise pywikibot.Error(
                        'Unexpected aritfact type: {}'.format(item_type))
            if not stop:
                start += num_hits
                search_data = self.get_search_record_from_url(
                    query=self.folder_uuid, start=start)
                num_hits = len(search_data.get('docs'))

    def load_collection_object(self, idno):
        """
        Fetch the folder object, ensuring a unique hit and returning its uuid.

        :param idno: either the uuid or uniqueId for the folder
        :return: the uuid for the folder
        """
        search_data = self.get_search_record_from_url(
            query=idno, only_folder=True)

        if not search_data['numFound'] == 1:
            raise pywikibot.Error(
                'Found {num} hits for the folder with id "{idno}", '
                'expected a unique hit'.format(
                    num=search_data['numFound'], idno=idno))

        folder = search_data.get('docs')[0]
        self.verbose_output('working on the folder: {}'.format(
            folder.get('artifact.ingress.title')))
        return folder.get('artifact.uuid')

    def process_single_object(self, item_uuid):
        """
        Process the data for a single search hit.

        One hit may contain multiple images. The results are stored in
        self.data as one entry per image.

        :param item_uuid: the uuid of the item
        """
        data = self.load_single_object(item_uuid)

        parsed_data = self.parse_single_object(data)
        all_image_keys = set([
            '{item}_{image}'.format(item=item_uuid, image=image.get('index'))
            for image in data.get('media').get('pictures')])

        for order, image in enumerate(data.get('media').get('pictures')):
            key = '{item}_{image}'.format(
                item=item_uuid, image=image.get('index'))
            other_keys = all_image_keys - set([key])

            image_data = self.make_image_object(
                image, order, parsed_data, other_keys)
            if (image_data.get('copyright') or
                    image_data.get('default_copyright')):
                self.data[key] = image_data
            else:
                self.log.write('{}: had no license info. Skipping.'.format(
                    key))

    def load_single_object(self, uuid):
        """
        Load the data for a single object.

        :param uuid: the uuid for the item
        """
        url = 'http://api.dimu.org/artifact/uuid/{}'.format(uuid)

        try:
            data = get_json_from_url(url)
        except requests.HTTPError as e:
            error_message = '{0}: {1}'.format(e, url)
            self.log.write(error_message)
            return None

        return data

    def parse_single_object(self, raw_data):
        """
        Parse the json for the single object, retaining only necessary values.

        Only handles the data that is the same for any media files linked to
        the object.
        """
        self.active_uuid = raw_data.get('uuid')
        data = {}
        data['dimu_id'] = raw_data.get('dimuCode')
        data['glam_id'] = [(raw_data.get('identifier').get('owner'),
                            raw_data.get('identifier').get('id'))]
        data['type'] = raw_data.get('artifactType')

        data['filename'] = self.parse_alternative_id(
            raw_data.get('alternativeIdentifiers'))

        # copyright can exists on both object and image level
        data['default_copyright'] = self.parse_license_info(
            raw_data.get('licenses'))

        # motif includes keywords, a general description and depicted place.
        self.parse_motif(data, raw_data.get('motif'))

        # event_wrapper contains info about both creator and creation date
        self.parse_event_wrap(data, raw_data.get('eventWrap'))

        # not implemented yet
        data['title'] = self.not_implemented_yet_waring(raw_data, 'titles')  # titles contains titles in multiple languages (NOR as default)  # noqa
        data['coordinate'] = self.not_implemented_yet_waring(
            raw_data, 'coordinates')
        data['tags'] = self.not_implemented_yet_waring(raw_data, 'tags')
        data['inscriptions'] = self.not_implemented_yet_waring(
            raw_data, 'inscriptions')
        data['subjects_2'] = self.not_implemented_yet_waring(  # subjects also exist within motif  # noqa
            raw_data, 'subjects')
        data['names'] = self.not_implemented_yet_waring(raw_data, 'names')
        data['measures'] = self.not_implemented_yet_waring(
            raw_data, 'measures')
        data['classification'] = self.not_implemented_yet_waring(
            raw_data, 'classifications')
        data['technique'] = self.not_implemented_yet_waring(
            raw_data, 'technique')
        data['material'] = self.not_implemented_yet_waring(
            raw_data, 'material')

        return data

    def parse_motif(self, data, motif_data):
        """
        Parse data about motif.

        This field contains (at least) a general description, depicted places
        and subjects (keywords).

        :param data: the object in which to store the parsed components
        :param motif_data: the full data objects about motifs
        """
        known_keys = ('description', 'subjects', 'depictedPlaces',
                      'depictedPersons')

        data['description'] = motif_data.get('description')

        if motif_data.get('subjects'):
            subjects = set()
            for subject in motif_data.get('subjects'):
                if subject.get('nameType') == "subject":
                    subjects.add(subject.get('name'))
                else:
                    self.log.write(
                        '{}: had an unexpected subject name type "{}".'.format(
                            self.active_uuid, subject.get('nameType')))
            data['subjects'] = list(subjects)

        if motif_data.get('depictedPlaces'):
            data['description_place'] = {}
            found_roles = {}
            for place_data in motif_data.get('depictedPlaces'):
                place = self.parse_place(place_data)
                place_role = place.get('role')
                if place_role in found_roles:
                    try:
                        found_roles[place_role] = DiMuHarvester.merge_place(
                            found_roles[place_role], place)
                    except pywikibot.Error:
                        self.log.write(
                            '{}: encountered multiple conflicting places with '
                            'the "{}" role, skipping the later.'.format(
                                self.active_uuid, place_role))
                        continue

                found_roles[place_role] = place

            for role, place in found_roles.items():
                if role == 'depicted_place':
                    data['depicted_place'] = place
                else:
                    data['description_place'][role] = place

        if motif_data.get('depictedPersons'):
            data['depicted_persons'] = [
                self.parse_person(person)
                for person in motif_data.get('depictedPersons')]

        if any(k not in known_keys for k in motif_data.keys()):
            self.log.write(
                '{}: encountered an unexpected motif key in: {}'.format(
                    self.active_uuid, ', '.join(motif_data.keys())))

    @staticmethod
    def merge_place(old_place, new_place):
        """
        Attempt to merge one place into another.

        Skips any keys which are the same, adds any new keys and raises an
        error if the same key is present with different values.
        """
        place = old_place.copy()
        for k, v in new_place.items():
            if k in place:
                if k == 'other':
                    for kk, vv in new_place['other'].items():
                        if kk in place.get('other'):
                            if place.get('other').get(kk) != vv:
                                raise pywikibot.Error('failed merge other')
                        else:
                            place['other'][kk] = vv
                elif place.get(k) != v:
                    raise pywikibot.Error('failed merge')
            else:
                place[k] = v
        return place

    def parse_place(self, place_data):
        """
        Parse the place component of e.g. motif.

        Codes can be mapped via
        http://kulturnav.org/a9d52054-c737-4c04-99fb-4e0b1890c7c3
        """
        structured_types = ('country', 'province', 'county',
                            'municipality', 'parish')
        place = {'other': {}}
        for field in place_data.get('fields'):
            place_type = field.get('placeType')
            if place_type in structured_types:
                if place_type == 'parish':
                    # correct use of parish codes has them zero padded
                    field['code'] = field.get('code').zfill(4)
                place[place_type] = {'label': field.get('value')}
                place[place_type]['code'] = (field.get('code') or
                                             field.get('value'))
            elif place_type:
                self.log.write(
                    '{}: encountered an unknown place_type "{}".'.format(
                        self.active_uuid, place_type))
            else:
                place['other'][field.get('name')] = {
                    'label': field.get('value'),
                    'code':  field.get('value')
                }

        place['role'] = self.map_place_role(place_data.get('role'))

        return place

    def parse_alternative_id(self, alt_id_data):
        """Parse data about alternative identifiers."""
        problem = None
        if alt_id_data:
            # unclear how to handle multiple such or non-filename such
            if len(alt_id_data) > 1:
                problem = (
                    '{}: Found multiple alternative identifiers, '
                    'unsure how to deal with this.'.format(self.active_uuid))
            elif alt_id_data[0].get('type') != 'Filnamn':
                problem = (
                    '{0}: Found an unexpected alternative identifiers type '
                    '("{1}"), unsure how to deal with this.'.format(
                        self.active_uuid, alt_id_data[0].get('type')))

        if problem:
            self.verbose_output(problem)
        else:
            return alt_id_data[0].get('identifier')

    def parse_license_info(self, license_data):
        """Parse data about licensing."""
        problem = None
        if not license_data:
            return
        elif len(license_data) > 1:
            problem = (
                '{}: Found multiple license informations, '
                'unsure how to deal with this.'.format(self.active_uuid))
        else:
            license = {}
            license['code'] = license_data[0].get('code')

            if license_data[0].get('persons'):
                license['persons'] = []
                for person in license_data[0].get('persons'):
                    license['persons'].append(self.parse_person(person))
            return license

        if problem:
            self.verbose_output(problem)

    def parse_person(self, person_data):
        """Parse data about a person, e.g. in licenses."""
        person = {}
        person['name'] = helpers.flip_name(person_data['name'])
        if person_data.get('authority') == 'KULTURNAV':
            person['k_nav'] = person_data.get('uuid')
        person['role'] = self.map_person_role(
            person_data.get('role'))
        person['id'] = person_data.get('id')
        return person

    def map_place_role(self, role):
        """
        Map place roles to standardised values.

        These are mapped to Commons values at a later stage.
        """
        mapped_roles = {
            "21": 'depicted_place',
            "25": 'view_over'
        }
        mapped_value = mapped_roles.get(role.get('code'))
        if mapped_value:
            return mapped_value
        else:
            self.verbose_output(
                'The place role "{0}" ("{1}") is unmapped'.format(
                    role.get('name'), role.get('code')))

    def map_person_role(self, role):
        """
        Map person roles to standardised values.

        These are mapped to Commons values at a later stage.
        """
        #map to false to tell the calling function to discard that entry
        mapped_roles = {
            "11K": 'creator',  # artist
        }
        mapped_value = mapped_roles.get(role.get('code'))
        if mapped_value:
            return mapped_value
        else:
            self.verbose_output(
                'The person role "{0}" ("{1}") is unmapped'.format(
                    role.get('name'), role.get('code')))

    def check_license(self, license_data):
        """
        Map license codes to allowed Commons templates.

        These are mapped to Commons templates at a later stage.
        """
        free_licenses = ('pdm', 'by', 'by-sa')
        unfree_licenses = ('by-nc', 'by-nc-sa', 'by-nd', 'by-nc-nd')
        code = license_data.get('code')

        problem = None
        if license_data.get('system') != 'CC':
            problem = 'Only CC licenses are supported, not "{}"'.format(
                license_data.get('system'))
        else:
            if code in free_licenses:
                return True
            elif code in unfree_licenses:
                problem = 'The CC license "{}" is not allowed'.format(code)
            else:
                problem = 'The CC license "{}" is not mapped'.format(code)

        if problem:
            self.verbose_output(problem)
            return False

    def parse_event_wrap(self, data, event_wrap_data):
        """
        Parse all data in the eventWrap.

        This field may contain:
        * the creation date
        * the creator (if not specified in the license section)
        * further events?

        :param data: the object in which to store the parsed components
        :param event_wrap_data: the full data objects about all events
        """
        creation_types = ('Fotografering', 'Produktion')

        # store producers (might contain creator)
        if event_wrap_data.get('producers'):
            data['producers'] = [
                self.parse_person(producer)
                for producer in event_wrap_data.get('producers')]

        production_data = event_wrap_data.get('production')
        if production_data:
            event_type = production_data.get('eventType')
            if event_type == 'Fotografering':
                data['is_photo'] = True
            elif event_type not in creation_types:
                self.log.write(
                    '{}: had an unexpected event type "{}".'.format(
                        self.active_uuid, event_type))

            data['creation'] = self.parse_event(production_data)

        # store non-creation events but log the types
        data['events'] = []
        for event in event_wrap_data.get('events'):
            event_type = event.get('eventType')
            if event_type not in creation_types:
                self.log.write(
                    '{}: found a new event type "{}".'.format(
                        self.active_uuid, event_type))
                data['events'].append(self.parse_event(event))

    def parse_event(self, event_data):
        """Parse data about and event."""
        data = {
            'type': event_data.get('eventType'),
            'related_persons': [],
            'related_places': [],
            'date': None
        }
        for person in event_data.get('relatedPersons'):
            data['related_persons'].append(self.parse_person(person))
        for place in event_data.get('relatedPlaces'):
            data['related_places'].append(self.parse_place(place))

        from_year = event_data.get('timespan').get('fromYear')
        to_year = event_data.get('timespan').get('toYear')
        if from_year == to_year:
            data['date'] = from_year
        else:
            data['date'] = (from_year, to_year)

        return data

    def make_image_object(self, image_data, order, item_data, other_keys):
        """
        Construct a data object for a single image.

        :param image_data: the unique data for the image
        :param order: the order of the image, used for getting right hit in
            the slider.
        :param item_data: the shared data for all images of this item
        :param other_keys: the keys to other images of the same object
        """
        image = item_data.copy()
        if image_data.get('photographer'):
            image['photographer'] = helpers.flip_name(
                image_data.get('photographer'))
        image['copyright'] = self.parse_license_info(
            image_data.get('licenses'))
        image['media_id'] = image_data.get('identifier')
        image['slider_order'] = order
        image['see_also'] = list(other_keys)
        return image

    def load_uuid_list(self, uuid_list):
        """Process a list of image uuids instead of starting from a folder."""
        for uuid in uuid_list:
            self.process_single_object(uuid)

    def not_implemented_yet_waring(self, raw_data, method):
        """Raise a pywikibot warning that a method has not been implemented."""
        if raw_data.get(method):
            pywikibot.warning(
                '{uuid}: You found an entry which contains data about '
                '"{method}", sadly this has not been implemented yet.'.format(
                    uuid=self.active_uuid, method=method))

    def verbose_output(self, txt, no_log=False):
        """
        Log and output to terminal in verbose mode.

        :param txt: text to output
        :param no_log: if logging should be skipped
        """
        if self.settings.get('verbose'):
            pywikibot.output(txt)
        if not no_log:
            self.log.write(txt)


def handle_args(args, usage):
    """
    Parse and load all of the basic arguments.

    Also passes any needed arguments on to pywikibot and sets any defaults.

    :param args: arguments to be handled
    :return: dict of options
    """
    expected_args = ('api_key', 'glam_code', 'log_file', 'output_file',
                     'settings_file', 'verbose', 'cutoff', 'collection_id')
    options = {}

    for arg in pywikibot.handle_args(args):
        option, sep, value = arg.partition(':')
        if option == '-verbose':
            options['verbose'] = common.interpret_bool(value)
        elif option == '-cutoff':
            options['cutoff'] = int(value)
        elif option.startswith('-') and option[1:] in expected_args:
            options[option[1:]] = common.convert_from_commandline(value)
        else:
            pywikibot.output(usage)
            exit()

    return options


def load_settings(args):
    """
    Load settings from, file, commandline or defaults.

    Any command line values takes precedence over setting file values.
    If neither is present then defaults are used.
    """
    default_options = DEFAULT_OPTIONS.copy()

    options = handle_args(args, PARAMETER_HELP.format(**default_options))

    # settings_file must be handled first
    options['settings_file'] = (options.get('settings_file') or
                                default_options.pop('settings_file'))

    # combine all loaded settings
    settings_options = common.open_and_read_file(
        options.get('settings_file'), as_json=True)
    for key, val in default_options.items():
        options[key] = options.get(key) or settings_options.get(key) or val

    return options


def get_json_from_url(url, payload=None):
    """Download json record from url."""
    response = requests.get(url, params=payload)
    response.raise_for_status()
    return response.json()


def main(*args):
    """Initialise and run the harvester."""
    options = load_settings(args)
    harvester = DiMuHarvester(options)
    harvester.load_collection(options.get('folder_id'))
    harvester.save_data()
    harvester.log.write_w_timestamp('...Harvester finished\n')
    pywikibot.output(harvester.log.close_and_confirm())


if __name__ == '__main__':
    main()
