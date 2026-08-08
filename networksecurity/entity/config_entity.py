from datetime import datetime
import os
from networksecurity.constants import training_pipeline
import sys
from networksecurity.exception.exception import NetworkSecurityException
print(training_pipeline.DATA_INGESTION_COLLECTION_NAME)


class TrainingPipelineConfig:
    def __init__(self,timestamp=datetime.now().strftime("%m_%d_%Y_%H_%M_%S")):
        self.pipeline_name = training_pipeline.PIPELINE_NAME
        self.ARTIFACT_DIR = os.path.join(training_pipeline.ARTIFACT_DIR, timestamp)
        self.DATA_INGESTION_FEATURE_STORE_DIR=training_pipeline.DATA_INGESTION_FEATURE_STORE_DIR
        self.DATA_INGESTION_INGESTED_DIR=training_pipeline.DATA_INGESTION_INGESTED_DIR
        self.timestamp:str = timestamp
        self.data_validation_dir_name=training_pipeline.DATA_VALIDATION_DIR_NAME
        self.data_validation_valid_dir=training_pipeline.DATA_VALIDATION_VALID_DIR
        self.data_validation_invalid_dir=training_pipeline.DATA_VALIDATION_INVALID_DIR
        self.data_validation_drift_report=training_pipeline.DATA_VALIDATION_DRIFT_REPORT
        self.data_validation_drift_report_file_name=training_pipeline.DATA_VALIDATION_DRIFT_REPORT_FILE_NAME

class DataIngestionConfig:
    def __init__(self, training_pipeline_config:TrainingPipelineConfig):
        try:
            self.database_name = training_pipeline.DATA_INGESTION_DATABASE_NAME
            self.collection_name = training_pipeline.DATA_INGESTION_COLLECTION_NAME
            self.file_name = training_pipeline.FILE_NAME
            self.feature_store_file_path = os.path.join(training_pipeline_config.ARTIFACT_DIR, training_pipeline_config.DATA_INGESTION_FEATURE_STORE_DIR)
            self.ingested_dir = os.path.join(training_pipeline_config.ARTIFACT_DIR, training_pipeline_config.DATA_INGESTION_INGESTED_DIR)
            self.training_file_path = os.path.join(self.ingested_dir, training_pipeline.TRAIN_FILE_NAME)
            self.testing_file_path = os.path.join(self.ingested_dir, training_pipeline.TEST_FILE_NAME)
            self.train_test_split_ratio = training_pipeline.DATA_INGESTION_TRAIN_TEST_SPLIT_RATIO
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e

class DataValidationConfig:
    def __init__(self,training_pipeline_config:TrainingPipelineConfig):
        self.data_validation_dir=os.path.join(training_pipeline_config.ARTIFACT_DIR,training_pipeline_config.data_validation_dir_name)
        self.valid_data_dir = os.path.join(self.data_validation_dir,training_pipeline_config.data_validation_valid_dir)
        self.invalid_data_dir=os.path.join(self.data_validation_dir,training_pipeline_config.data_validation_invalid_dir)
        self.valid_train_file_path=os.path.join(self.valid_data_dir,training_pipeline.TRAIN_FILE_NAME)
        self.valid_test_file_path=os.path.join(self.valid_data_dir,training_pipeline.TEST_FILE_NAME)
        self.invalid_train_file_path=os.path.join(self.invalid_data_dir,training_pipeline.TRAIN_FILE_NAME)
        self.invalid_test_file_path=os.path.join(self.invalid_data_dir,training_pipeline.TEST_FILE_NAME)
        self.drift_report_file_path=os.path.join(
            self.data_validation_dir,
            training_pipeline_config.data_validation_drift_report,
            training_pipeline_config.data_validation_drift_report_file_name
        )