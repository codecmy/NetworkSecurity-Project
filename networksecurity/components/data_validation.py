from networksecurity.entity.artifact_entity import DataIngestionArtifacts,DataValidationArtifact
from networksecurity.entity.config_entity import DataValidationConfig
from networksecurity.logging.logger import logging
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.utils.main_utils import read_yaml_file,write_yaml_file
from scipy.stats import ks_2samp
import pandas as pd
import os,sys

from networksecurity.constants.training_pipeline import SCHEMA_FILE_PATH


class DataValidation:
    def __init__(self,data_ingestion_artifact:DataIngestionArtifacts,data_validation_config:DataValidationConfig):
        try:
            self.data_ingestion_artifact=data_ingestion_artifact
            self.data_validation_config=data_validation_config
            self._schema_config=read_yaml_file(SCHEMA_FILE_PATH)
        except Exception as e:
            raise NetworkSecurityException(e,sys)   

    @staticmethod
    def read_data(file_path)->pd.DataFrame:
        try:
            return pd.read_csv(file_path)
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def validate_number_of_columns(self,dataframe:pd.DataFrame):
        try:
            number_of_columns=len(self._schema_config["columns"])
            logging.info(f"Required no of columns:{number_of_columns}")
            logging.info(f"Given number of columns{len(dataframe.columns)}")
            if len(dataframe.columns) != number_of_columns:
                return False
            if len(dataframe.select_dtypes(include="number").columns) != number_of_columns:
                return False
            return True
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def detect_data_drift(self,base_df:pd.DataFrame,current_df:pd.DataFrame,threshold=0.05)->bool:
        try:
            status=True
            report={}
            for column in base_df.columns:
                d1=base_df[column]
                d2=current_df[column]
                is_sample_dist=ks_2samp(d1,d2)
                if threshold<=is_sample_dist.pvalue:
                    is_found=False
                else:
                    is_found=True
                    status=False
                report.update({
                    column:{
                        "p_value":float(is_sample_dist.pvalue),
                        "drift_status":is_found
                    }
                })
            drift_report_file_path=self.data_validation_config.drift_report_file_path
            dir_path=os.path.dirname(drift_report_file_path)
            os.makedirs(dir_path,exist_ok=True)
            write_yaml_file(file_path=drift_report_file_path,content=report)
            return status

        except Exception as e:
            raise NetworkSecurityException(e,sys)
        
    def _save_validated_data(self, dataframe:pd.DataFrame, status:bool, valid_file_path:str, invalid_file_path:str)->str:
        try:
            if status:
                dir_path=os.path.dirname(valid_file_path)
                os.makedirs(dir_path,exist_ok=True)
                dataframe.to_csv(valid_file_path,index=False,header=True)
                return valid_file_path
            else:
                dir_path=os.path.dirname(invalid_file_path)
                os.makedirs(dir_path,exist_ok=True)
                dataframe.to_csv(invalid_file_path,index=False,header=True)
                return invalid_file_path
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def initiate_data_validation(self)->DataValidationArtifact:
        try:
            train_file_path=self.data_ingestion_artifact.train_file_path
            test_file_path=self.data_ingestion_artifact.test_file_path
            #read the data from train and test 
            train_dataframe=DataValidation.read_data(train_file_path)
            test_dataframe=DataValidation.read_data(test_file_path)
            #validate number of columns 
            train_status=self.validate_number_of_columns(dataframe=train_dataframe)
            if not train_status:
                logging.info(f"Train dataframe does not contain all columns.")
            test_status=self.validate_number_of_columns(dataframe=test_dataframe)
            if not test_status:
                logging.info(f"Test dataframe does not contain all columns.")

            #Check datadrift
            drift_status=self.detect_data_drift(base_df=train_dataframe,current_df=test_dataframe)
            logging.info(f"Data drift status: {drift_status}")

            valid_train_file_path=self._save_validated_data(
                dataframe=train_dataframe,
                status=train_status,
                valid_file_path=self.data_validation_config.valid_train_file_path,
                invalid_file_path=self.data_validation_config.invalid_train_file_path
            )
            valid_test_file_path=self._save_validated_data(
                dataframe=test_dataframe,
                status=test_status,
                valid_file_path=self.data_validation_config.valid_test_file_path,
                invalid_file_path=self.data_validation_config.invalid_test_file_path
            )
            invalid_train_file_path=None if train_status else valid_train_file_path
            invalid_test_file_path=None if test_status else valid_test_file_path

            data_validation_artifact=DataValidationArtifact(
                validation_status=(train_status and test_status),
                valid_train_file_path=valid_train_file_path if train_status else None,
                valid_test_file_path=valid_test_file_path if test_status else None,
                invalid_train_file_path=invalid_train_file_path,
                invalid_test_file_path=invalid_test_file_path,
                drift_report_file_path=self.data_validation_config.drift_report_file_path,
            )
            logging.info(f"Data Validation artifact: {data_validation_artifact}")
            return data_validation_artifact
        except Exception as e:
            raise NetworkSecurityException(e,sys)
