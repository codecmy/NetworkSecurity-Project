import os
import sys

from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
 
from networksecurity.components.data_ingestion import DataIngestion
from networksecurity.components.data_validation import DataValidation
from networksecurity.components.data_transformation import DataTransformation
from networksecurity.components.model_trainer import ModelTrainer

from networksecurity.entity.config_entity import(
    TrainingPipelineConfig,
    DataIngestionConfig,
    DataValidationConfig,
    DataTransformationConfig,
    ModelTrainerConfig,
)

from networksecurity.entity.artifact_entity import (
    DataIngestionArtifacts,
    DataValidationArtifact,
    DataTransformationArtifact,
    ModelTrainerArtifact,
)

import sys

class TrainigPipeline:
    def __init__(self):
        self.training_pipeline_config=TrainingPipelineConfig()

    def start_data_ingestion(self):
        try:
            self.data_ingestion_config=DataIngestionConfig(training_pipeline_config=self.training_pipeline_config)
            logging.info("Start Data Ingestion")
            data_ingestion=DataIngestion(data_ingestion_config=self.data_ingestion_config)
            data_ingestion_artifact=data_ingestion.initiate_data_ingestion()
            logging.info(f"Data Ingestion Completed!")
            return data_ingestion_artifact
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def start_data_validation(self,data_ingestion_artifact:DataIngestionArtifacts):
        try:
            logging.info("Data Validation Started")
            datavalidationconfig=DataValidationConfig(training_pipeline_config=self.training_pipeline_config)
            data_validation=DataValidation(data_ingestion_artifact=data_ingestion_artifact,data_validation_config=datavalidationconfig)
            data_validation_artifact=data_validation.initiate_data_validation()
            logging.info("Data Validation Successfully completed")
            return data_validation_artifact
        except Exception as e:
            raise NetworkSecurityException(e,sys)
    def start_data_transformation(self,data_validation_artifact:DataValidationArtifact):
        try:
            logging.info("Data Tranfomation Started in the main.py file")
            data_transormation_config=DataTransformationConfig(self.training_pipeline_config)
            data_transfomation=DataTransformation(data_trandformation_config=data_transormation_config,data_validation_artifact=data_validation_artifact)
            data_transformation_artifact=data_transfomation.initiate_data_transformation()
            print(data_transformation_artifact)
            logging.info("Data Transformation Successfully ended from main.py file")
            return data_transformation_artifact
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def start_model_trainer(self,data_transformation_artifact:DataTransformationArtifact)->ModelTrainerArtifact:
        try:
            self.model_trainer_config:ModelTrainerConfig=ModelTrainerConfig(training_pipeline_config=self.training_pipeline_config)
            model_trainer=ModelTrainer(
                data_transformation_artifact=data_transformation_artifact,
                model_trainer_config=self.model_trainer_config,
            )
            model_trainer_artifact=model_trainer.initiate_model_trainer()
            return model_trainer_artifact

        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def run_pipeline(self):
        try:
            data_ingestion_artifact=self.start_data_ingestion()
            data_validation_artifact=self.start_data_validation(data_ingestion_artifact=data_ingestion_artifact)
            data_transformation_artifact=self.start_data_transformation(data_validation_artifact=data_validation_artifact)
            model_trainer_artifact=self.start_model_trainer(data_transformation_artifact=data_transformation_artifact)
        except Exception as e:
            raise NetworkSecurityException(e,sys)

     
        