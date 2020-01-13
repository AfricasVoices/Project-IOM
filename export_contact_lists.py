import argparse
import csv
import json

from core_data_modules.cleaners import Codes
from core_data_modules.logging import Logger
from core_data_modules.traced_data import TracedData
from core_data_modules.traced_data.io import TracedDataJsonIO
from core_data_modules.util import PhoneNumberUuidTable
from id_infrastructure.firestore_uuid_table import FirestoreUuidTable
from storage.google_cloud import google_cloud_utils

from src.lib import PipelineConfiguration
from src.lib.code_schemes import CodeSchemes

Logger.set_project_name("IOM")
log = Logger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generates lists of phone numbers of previous CSAP respondents who  "
                                                 "were labelled as living in ")

    parser.add_argument("google_cloud_credentials_file_path", metavar="google-cloud-credentials-file-path",
                        help="Path to a Google Cloud service account credentials file to use to access the "
                             "credentials bucket")
    parser.add_argument("pipeline_configuration_file_path", metavar="pipeline-configuration-file",
                        help="Path to the pipeline configuration json file")
    parser.add_argument("traced_data_paths", metavar="traced-data-paths", nargs="+",
                        help="Paths to the traced data files (either messages or individuals) to extract phone "
                             "numbers from")

    args = parser.parse_args()

    google_cloud_credentials_file_path = args.google_cloud_credentials_file_path
    pipeline_configuration_file_path = args.pipeline_configuration_file_path
    traced_data_paths = args.traced_data_paths

    iom_locations = {"cabudwaaq", "gaalkacyo", "dhuusamarreeb"}

    log.info("Loading Pipeline Configuration File...")
    with open(pipeline_configuration_file_path) as f:
        pipeline_configuration = PipelineConfiguration.from_configuration_file(f)

    log.info("Downloading Firestore UUID Table credentials...")
    firestore_uuid_table_credentials = json.loads(google_cloud_utils.download_blob_to_string(
        google_cloud_credentials_file_path,
        pipeline_configuration.phone_number_uuid_table.firebase_credentials_file_url
    ))

    phone_number_uuid_table = FirestoreUuidTable(
        pipeline_configuration.phone_number_uuid_table.table_name,
        firestore_uuid_table_credentials,
        "avf-phone-uuid-"
    )
    log.info("Initialised the Firestore UUID table")

    # Load the traced data
    uuids = set()
    for path in traced_data_paths:
        log.info(f"Loading previous traced data from file '{path}'...")
        with open(path) as f:
            data = TracedDataJsonIO.import_jsonl_to_traced_data_iterable(f)
        log.info(f"Loaded {len(data)} traced data objects")

        # Search the TracedData for contacts from relevant locations
        log.info(f"Searching for participants from the IOM target locations ({iom_locations})")
        file_uuids = set()
        for td in data:
            if td["district_coded"] == Codes.STOP:
                continue

            if CodeSchemes.SOMALIA_DISTRICT.get_code_with_code_id(td["district_coded"]["CodeID"]).string_value in iom_locations:
                file_uuids.add(td["uid"])
        uuids.update(file_uuids)
        log.info(f"Found {len(file_uuids)} contacts in the IOM target locations (running total: {len(uuids)})")

    # Convert the uuids to phone numbers
    log.info(f"Converting {len(uuids)} uuids to phone numbers...")
    uuid_phone_number_lut = phone_number_uuid_table.uuid_to_data_batch(uuids)
    phone_numbers = {f"+{uuid_phone_number_lut[uuid]}" for uuid in uuids}

    # Export CSVs
    csv_path = 'test.csv'
    log.warning(f"Exporting {len(phone_numbers)} phone numbers to {csv_path}...")
    with open(csv_path, "w") as f:
        writer = csv.DictWriter(f, fieldnames=["URN:Tel", "Name"], lineterminator="\n")
        writer.writeheader()

        for n in phone_numbers:
            writer.writerow({
                "URN:Tel": n
            })
        log.info(f"Wrote {len(phone_numbers)} contacts to {csv_path}")