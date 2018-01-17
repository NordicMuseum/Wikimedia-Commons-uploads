## About This Repository
This repository contains the python3 scripts used by the Nordic Museum to upload images
to Wikimedia Commons. It is based on [lokal-profil/upload-batches](https://github.com/lokal-profil/upload-batches).

This is a work in progress during the fall of 2017 and winter of 2018. For more details, contact
[Aron Ambrosiani](https://github.com/Ambrosiani).

### Additional Reading:
* [blog post (in Swedish)](http://nyamedier.blogg.nordiskamuseet.se/2017/12/att-flytta-bilder-fran-digitalt-museum-till-wikimedia-commons/) about how to copy images from Digitalt museum to Wikimedia Commons using this repository
* [Documentation of the Digitalt Museum API](https://github.com/NordicMuseum/DiMu-API-documentation)

## Requirements

To run it you will have to install [`BatchUploadTools`](https://github.com/lokal-profil/BatchUploadTools)
and [`pywikibot`](https://github.com/wikimedia/pywikibot-core) using:
`pip install -r requirements.txt`

*Note*: You might have to add the `--process-dependency-links` flag to the above
command if you are running a different version of pywikibot from the required one.

## User Account

The script must be run from an account which has the `upload_by_url` user right.
On Wikimedia Commons this is limited to users with one of the `image-reviewer`,
`bot`, `gwtoolset` or `sysop` flags. [Apply for `bot` rights](https://commons.wikimedia.org/wiki/Commons:Bots/Requests).

## Settings

The `settings.json` file should contain the following settings:

* **api_key**: your [Digitalt museum API key](https://dok.digitaltmuseum.org/sv/api) (as provided by [KulturIT](mailto:support@kulturit.no)).
* **glam_code**: institution code in Digitalt Museum. [List of institution codes for Swedish museums](http://api.dimu.org/api/owners?country=se&api.key=demo)
* **log_file**: path to desired log file
* **output_file**: path to desired output file (default: false)
* **verbose**: bool on whether verbose output is desired
* **cutoff**: integer stating how many results to process (remove to process everything in folder)
* **folder_id**: unique id (12 digits) or uuid (8-4-4-4-12 hexadecimal digits) of the Digitalt Museum folder used

## Usage

### The basic workflow is the following:
1. Create settings.json (see above)
2. Create user-config.py with the bot username
3. Create user-password.py with the bot username & password. [Generate a bot password](https://commons.wikimedia.org/wiki/Special:BotPasswords).

### The following commands are run from the root folder of your installation:
4. Run `python importer/DiMuHarvester.py` to scrape info from the DiMu API. [Example output](https://github.com/NordicMuseum/Wikimedia-Commons-uploads/blob/master/examples/dimu_harvest_data.json)
5. Run `python importer/DiMuMappingUpdater.py` to generate mapping files for Wikimedia Commons
6. Run `python importer/make_NordicMuseum_info.py -in_file:dimu_harvest_data.json -base_name:nm_output -update_mappings:True` to prepare the batch file. [Example output](https://github.com/NordicMuseum/Wikimedia-Commons-uploads/blob/master/examples/nm_output.json)
7. Run `python importer/uploader.py -in_path:nm_output.json -type:URL` to perform the actual batch upload. `-cutoff:X` limits the number of files uploaded to `X` (this will override settings)
