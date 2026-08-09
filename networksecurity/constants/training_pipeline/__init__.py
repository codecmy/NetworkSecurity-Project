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


SAVED_MODEL_DIR=os.path.join("saved_models")
MODEL_FILE_NAME="model.pkl"


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
PREPROCESSING_OBJECT_FILE_NAME = "preprocessing.pkl"

"""
Data Transformation realted constants 
"""

DATA_TRANSFORMATIONAL_DIR_NAME:str="data_transformation"
DATA_TRANSFORMATIONAL_TRANSFORMED_DATA_DIR:str="transformed"
DATA_TRANSFORMATIONAL_TRANSFORMED_OBJECT_DIR:str="transformed_object"
DATA_TRANSFORMATIONAL_IMPUTER_PARAMS:dict={
    "missing_values":np.nan,
    "n_neighbors":3,
    "weights":"uniform"
}

DATA_TRANSFORMATION_TRAIN_FILE_PATH: str = "train.npy"

DATA_TRANSFORMATION_TEST_FILE_PATH: str = "test.npy"


"""
Model Training realted content start with MODE TRAINER VAR NAME
"""

MODEL_TRAINER_DIR_NAME:str="model_trainer"
MODEL_TRAINER_TRAINED_MODEL_DIR:str="trained_model"
MODEL_TRAINER_TRAINED_MODEL_NAME:str="model.pkl"
MODEL_TRAINER_EXPECTED_SCORE=0.6
MODEL_TRAINER_OVER_FITTING_UNDER_FITTING_THRESHOLD=0.05