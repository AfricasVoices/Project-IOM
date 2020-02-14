import argparse
import json

from core_data_modules.cleaners import PhoneCleaner, Codes
from core_data_modules.logging import Logger
from core_data_modules.traced_data.io import TracedDataJsonIO
from dateutil.parser import isoparse
from id_infrastructure.firestore_uuid_table import FirestoreUuidTable
from rapid_pro_tools.rapid_pro_client import RapidProClient
from storage.google_cloud import google_cloud_utils

from src.lib import PipelineConfiguration
from src.lib.pipeline_configuration import RapidProSource

log = Logger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO")  # TODO

    parser.add_argument("user", help="User launching this program")
    parser.add_argument("google_cloud_credentials_file_path", metavar="google-cloud-credentials-file-path",
                        help="Path to a Google Cloud service account credentials file to use to access the "
                             "credentials bucket")
    parser.add_argument("pipeline_configuration_file_path", metavar="pipeline-configuration-file",
                        help="Path to the pipeline configuration json file")

    parser.add_argument("messages_json_input_path", metavar="messages-json-input-path",
                        help="Path to a JSONL file to read the TracedData of the messages data from")
    
    args = parser.parse_args()
    user = args.user
    google_cloud_credentials_file_path = args.google_cloud_credentials_file_path
    pipeline_configuration_file_path = args.pipeline_configuration_file_path
    messages_json_input_path = args.messages_json_input_path

    log.info("Loading Pipeline Configuration File...")
    with open(pipeline_configuration_file_path) as f:
        pipeline_configuration = PipelineConfiguration.from_configuration_file(f)
    Logger.set_project_name(pipeline_configuration.pipeline_name)
    log.debug(f"Pipeline name is {pipeline_configuration.pipeline_name}")

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

    # Download all the sent messages from Rapid Pro for the duration of this project
    raw_sent_messages = []
    for raw_data_source in pipeline_configuration.raw_data_sources:
        if type(raw_data_source) != RapidProSource:
            log.info("Skipped a raw data source that wasn't Rapid Pro")
            continue

        rapid_pro_token = google_cloud_utils.download_blob_to_string(
            google_cloud_credentials_file_path, raw_data_source.token_file_url).strip()
        rapid_pro = RapidProClient(raw_data_source.domain, rapid_pro_token)

        project_messages = rapid_pro.get_raw_messages(
            created_after_inclusive=pipeline_configuration.project_start_date,
            created_before_exclusive=pipeline_configuration.project_end_date
        )
        log.info(f"Downloaded {len(project_messages)} messages for the project")

        raw_sent_messages.extend([msg for msg in project_messages
                                  if msg.direction == "out" and msg.urn.startswith("tel:")])
    log.info(f"{len(raw_sent_messages)} of the downloaded messages were outbound")
    
    sent_message_counts = dict()  # of message text -> number of times that message was sent during the project
    for msg in raw_sent_messages:
        if msg.text not in sent_message_counts:
            sent_message_counts[msg.text] = 0
        sent_message_counts[msg.text] += 1
    log.info(f"{len(sent_message_counts)} unique texts were sent out during this project")

    # Create a list of de-identified outbound message objects containing the information we care about
    phone_numbers = {PhoneCleaner.normalise_phone(msg.urn.split(":")[1]) for msg in raw_sent_messages}
    phone_to_uuid_lut = phone_number_uuid_table.data_to_uuid_batch(phone_numbers)
    sent_messages = []
    for msg in raw_sent_messages:
        if msg.sent_on is None:
            log.warning(f"Found a message with a sent_on date of None, ignoring. Text was: {msg.text}")
            continue

        sent_messages.append({
            "uid": phone_to_uuid_lut[PhoneCleaner.normalise_phone(msg.urn.split(":")[1])],
            "text": msg.text,
            "sent_on": msg.sent_on.isoformat(),
            "direction": "out"
        })

    # Load the labelled project messages data
    log.info(f"Loading messages from {messages_json_input_path}...")
    with open(messages_json_input_path) as f:
        traced_messages = TracedDataJsonIO.import_jsonl_to_traced_data_iterable(f)
    log.info(f"Loaded {len(traced_messages)} labelled message objects")

    received_messages = []
    for msg in traced_messages:
        if msg["consent_withdrawn"] == Codes.TRUE:
            continue
        
        for coding_plan in PipelineConfiguration.RQA_CODING_PLANS:
            labels = []
            for cc in coding_plan.coding_configurations:
                codes = [cc.code_scheme.get_code_with_code_id(label["CodeID"]) for label in msg[cc.coded_field]]
                if len(codes) > 1 or codes[0].control_code != Codes.TRUE_MISSING:
                    received_messages.append({
                        "uid": msg["uid"],
                        "text": msg[coding_plan.raw_field],
                        "sent_on": msg["sent_on"],
                        "direction": "in",
                        "labels": msg[cc.coded_field]
                    })

    # Join the in- and out-bound messages
    messages_by_individual = dict()  # of uuid -> message object
    for msg in sent_messages + received_messages:
        uid = msg["uid"]
        if uid not in messages_by_individual:
            messages_by_individual[uid] = []
        messages_by_individual[uid].append(msg)

    # for msg in sent_messages:
    #     uid = msg["uid"]
    #     if uid not in messages_by_individual:
    #         messages_by_individual[uid] = []
    #     messages_by_individual[uid].append(("out", msg))

    # Within each group, sort the messages in the order that they were sent
    for messages in messages_by_individual.values():
        messages.sort(key=lambda msg: isoparse(msg["sent_on"]))

    # for ind in messages_by_individual.values():
    #     for msg in ind:
    #         print(msg)

    with open("test.json", "w") as f:
        json.dump(messages_by_individual, f)
