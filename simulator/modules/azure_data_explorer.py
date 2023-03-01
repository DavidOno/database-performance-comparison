from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from azure.kusto.data.helpers import dataframe_from_result_table
from azure.kusto.data import DataFormat
from azure.kusto.ingest import QueuedIngestClient, IngestionProperties, FileDescriptor, BlobDescriptor, ReportLevel, \
    ReportMethod

import pandas as pd

from .config import config

KUSTO_URI = "https://kvc7rq22b9ye5d4a4fgyas.northeurope.kusto.windows.net"
KUSTO_INGEST_URI = "https://ingest-kvc7rq22b9ye5d4a4fgyas.northeurope.kusto.windows.net"
KUSTO_DATABASE = "ConnTest"

DESTINATION_TABLE = "PopulationDataNew"
DESTINATION_TABLE_COLUMN_MAPPING = "PopulationDataNew_CSV_Mapping"



def test():
    kcsb_ingest = KustoConnectionStringBuilder.with_interactive_login(KUSTO_INGEST_URI)
    kcsb_data = KustoConnectionStringBuilder.with_interactive_login(KUSTO_URI)

    kusto_client = KustoClient(kcsb_data)
    create_table_command = f".create table {DESTINATION_TABLE} (State: string, Population: int)"
    kusto_client.execute_mgmt(KUSTO_DATABASE, create_table_command)

    create_mapping_command = """.create table PopulationDataNew ingestion csv mapping 'PopulationDataNew_CSV_Mapping' '[{"Name":"State","datatype":"string","Ordinal":0}, {"Name":"Population","datatype":"int","Ordinal":1}]'"""
    kusto_client.execute_mgmt(KUSTO_DATABASE, create_mapping_command)

    ingestion_client = QueuedIngestClient(kcsb_ingest)
    ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=DESTINATION_TABLE, data_format=DataFormat.CSV,
                                          ignore_first_record=True)
    mapping = {'State': ['Texas', 'New York', 'Arizona'], 'Population': [300, 400, 500]}
    dataframe = pd.DataFrame(data=mapping)
    ingestion_client.ingest_from_dataframe(dataframe, ingestion_props)
    print('Done queuing up ingestion with Azure Data Explorer')


def _ingestion_client():
    kcsb_ingest = KustoConnectionStringBuilder.with_interactive_login(KUSTO_INGEST_URI)
    return QueuedIngestClient(kcsb_ingest)


def init():
    kcsb_data = KustoConnectionStringBuilder.with_interactive_login(KUSTO_URI)
    kusto_client = KustoClient(kcsb_data)

    if config["use_multiple_tables"]:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    if config["clean_database"]:
        for table_name in ["events0", "events1", "events2", "events3", "events"]:
            delete_table_command = f".drop table {table_name}"
            kusto_client.execute_mgmt(KUSTO_DATABASE, delete_table_command)

    for table_name in table_names:
        create_table_command = f".create table {table_name} (timestamp: long, device_id: string, sequence_number: long, temperature: real)"
        kusto_client.execute_mgmt(KUSTO_DATABASE, create_table_command)

        create_mapping_command = f""".create table {table_name} ingestion csv mapping '{table_name}_CSV_Mapping' '[{"Name":"timestamp","datatype":"long","Ordinal":0}, {"Name":"device_id","datatype":"string","Ordinal":1}, {"Name":"sequence_number","datatype":"long","Ordinal":2}, {"Name":"temperature","datatype":"real","Ordinal":3}]'"""
        kusto_client.execute_mgmt(KUSTO_DATABASE, create_mapping_command)


def prefill_events(events):
    _insert_events(events, True, 1_000)


def insert_events(events):
    batch_mode = config.get("batch_mode", False)
    batch_size = config.get("batch_size", 1_000)
    _insert_events(events, batch_mode, batch_size)


def _batch_insert(events, batch_size, table_names):
    count = 0
    timestamps = []
    device_ids = []
    sequence_numbers = []
    temperatures = []
    for idx, event in enumerate(events):
        table = table_names[idx % len(table_names)]
        timestamps.append(event.timestamp)
        device_ids.append(event.device_id)
        sequence_numbers.append(event.sequence_number)
        temperatures.append(event.temperature)
        count += 1
        if count >= batch_size:
            _ingest(table, timestamps, device_ids, sequence_numbers, temperatures)
    if count > 0:
        _ingest(table, timestamps, device_ids, sequence_numbers, temperatures)

def _ingest(table, timestamps, device_ids, sequence_numbers, temperatures):
    ingestion_client = _ingestion_client()
    ingestion_data = {'timestamp': timestamps, 'device_id': device_ids, 'sequence_number': sequence_numbers,
                      'temperature': temperatures}
    dataframe = pd.DataFrame(data=ingestion_data)
    ingestion_props = IngestionProperties(database=KUSTO_DATABASE, table=table, data_format=DataFormat.CSV,
                                          ignore_first_record=True)
    ingestion_client.ingest_from_dataframe(dataframe, ingestion_props)


def _stream_insert(events, table_names):
    pass


def _insert_events(events, batch_mode, batch_size):
    print("Connecting to database", flush=True)
    use_multiple_tables = config["use_multiple_tables"]
    if use_multiple_tables:
        table_names = ["events0", "events1", "events2", "events3"]
    else:
        table_names = ["events"]

    print("Inserting events", flush=True)
    if batch_mode:
        _batch_insert(events, batch_size, table_names)
    else:
        _stream_insert(events, table_names)


def queries():
    db = _db()
