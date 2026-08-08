import os
import sys
import numpy as np
import pandas as pd

"""
Common constants for training pipeline
"""
TARGET_COLUMN:str = "Result"
PIPELINE_NAME:str = "NetworkSecurity"
ARTIFACT_DIR:str = "Artifact"
FILE_NAME:str = "NetworkData.csv"

TRAIN_FILE_NAME:str = "train.csv"
TEST_FILE_NAME:str = "test.csv"

SCHEMA_FILE_PATH=os.path.join("data_schema","schema.yaml")

"""
Data Ingestion Related Constants
"""

DATA_INGESTION_COLLECTION_NAME :str = "NetworkData"
DATA_INGESTION_DATABASE_NAME :str = "NetworkSecurity"
DATA_INGESTION_FEATURE_STORE_DIR :str = "feature_store"
DATA_INGESTION_TRAIN_TEST_SPLIT_RATIO :float = 0.2
DATA_INGESTION_INGESTED_DIR:str = "ingested"

"""
Data Validation realted constants with DATA_VALIDATION VAR NAME
"""

DATA_VALIDATION_DIR_NAME:str="data_validation"
DATA_VALIDATION_VALID_DIR:str="validation"
DATA_VALIDATION_INVALID_DIR:str="invalid"
DATA_VALIDATION_DRIFT_REPORT:str="drift_report"
DATA_VALIDATION_DRIFT_REPORT_FILE_NAME:str="report.yml"