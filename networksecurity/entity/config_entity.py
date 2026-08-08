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