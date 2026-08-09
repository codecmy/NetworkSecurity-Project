from networksecurity.components.data_ingestion import DataIngestion
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.entity.config_entity import DataIngestionConfig
from networksecurity.entity.config_entity import TrainingPipelineConfig,DataValidationConfig,DataTransformationConfig
from networksecurity.components.data_validation import DataValidation
from networksecurity.components.data_transformation import DataTransformation
from networksecurity.entity.config_entity import ModelTrainerConfig
from networksecurity.components.model_trainer import ModelTrainer
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

        logging.info("Data Tranfomation Started in the main.py file")
        data_transormation_config=DataTransformationConfig(trainingpipelineconfig)
        data_transfomation=DataTransformation(data_trandformation_config=data_transormation_config,data_validation_artifact=data_validation_artifact)
        data_transformation_artifact=data_transfomation.initiate_data_transformation()
        print(data_transformation_artifact)
        logging.info("Data Transformation Successfully ended from main.py file")

        logging.info("Model Training Strated in main.py")
        model_training_config=ModelTrainerConfig(trainingpipelineconfig)
        model_trainer=ModelTrainer(model_training_config,data_transformation_artifact)
        model_trainer_artifact=model_trainer.initiate_model_trainer()
        logging.info("Model Training Ended Successfully exited main.py")
    except Exception as e:
        raise NetworkSecurityException(e,sys)