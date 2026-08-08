from networksecurity.components.data_ingestion import DataIngestion
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.entity.config_entity import DataIngestionConfig
from networksecurity.entity.config_entity import TrainingPipelineConfig,DataValidationConfig
from networksecurity.components.data_validation import DataValidation
import sys
if __name__ == "__main__":
    try:
        logging.info("Enter the try block")
        trainingpipelineconfig=TrainingPipelineConfig()
        dataingestionconfig=DataIngestionConfig(trainingpipelineconfig)
        data_ingestion=DataIngestion(dataingestionconfig)
        logging.info("Initiated data ingestion")
        dataingestionartifact=data_ingestion.initiate_data_ingestion()
        print(dataingestionartifact)
        logging.info("Data Ingestion Completed")
        logging.info("Data Validation Started")
        datavalidationconfig=DataValidationConfig(training_pipeline_config=trainingpipelineconfig)
        data_validation=DataValidation(data_ingestion_artifact=dataingestionartifact,data_validation_config=datavalidationconfig)
        data_validation_artifact=data_validation.initiate_data_validation()
        logging.info("Data Validation Successfully completed")
        print(data_validation_artifact)

    except Exception as e:
        raise NetworkSecurityException(e,sys)