import sys 
import os
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import KNNImputer

from networksecurity.constants.training_pipeline import TARGET_COLUMN
from networksecurity.constants.training_pipeline import DATA_TRANSFORMATIONAL_IMPUTER_PARAMS

from networksecurity.entity.artifact_entity import (
    DataTransformationArtifact,
    DataValidationArtifact
)

from networksecurity.entity.config_entity import DataTransformationConfig
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.utils.main_utils.utils import save_numpy_array_data,save_object

class DataTransformation:
    def __init__(self,data_validation_artifact:DataValidationArtifact,data_trandformation_config:DataTransformationConfig):
        try:
            self.data_validation_artifect:DataValidationArtifact=data_validation_artifact
            self.data_transformation_config:DataTransformationConfig=data_trandformation_config
        except Exception as e:
            raise NetworkSecurityException(e,sys) 



    @staticmethod
    def read_data(file_path)->pd.DataFrame:
        try:
            return pd.read_csv(file_path)
        except Exception as e:
            raise NetworkSecurityException(e,sys)


    def get_data_transformer_object(cls)->Pipeline:
        """
        It initialises KNN imputer and pipeline and keep the KNN impute at first step..

        Input: cls: DataTransformation

        Output:A Pipeline Object 
        """
        logging.info("Entered Data_Tranformation_Object....")
        try:
            knn:KNNImputer=KNNImputer(**DATA_TRANSFORMATIONAL_IMPUTER_PARAMS)
            logging.info(f"Initialise KNNImputer with {DATA_TRANSFORMATIONAL_IMPUTER_PARAMS}")
            processor:Pipeline=Pipeline([("impute",knn)])
            return processor
        except Exception as e:
            raise NetworkSecurityException(e,sys)
        
    def initiate_data_transformation(self)->DataTransformationArtifact:
        logging.info("Data Transformation Initiated....")
        try:
            train_df=DataTransformation.read_data(self.data_validation_artifect.valid_test_file_path)
            test_df=DataTransformation.read_data(self.data_validation_artifect.valid_test_file_path)

            #training data
            input_features_train_df=train_df.drop(columns=[TARGET_COLUMN])
            target_feature_train_df=train_df[TARGET_COLUMN] 
            target_feature_train_df=target_feature_train_df.replace(-1,0)

            #testing data 
            input_features_test_df=test_df.drop(columns=[TARGET_COLUMN])
            target_feature_test_df=test_df[TARGET_COLUMN]
            target_feature_test_df=target_feature_test_df.replace(-1,0)

            preprocessor=self.get_data_transformer_object()
            preprocessor_object=preprocessor.fit(input_features_train_df)
            transformed_input_train_feature=preprocessor_object.transform(input_features_train_df)
            transformed_input_test_feature=preprocessor_object.transform(input_features_test_df)

            train_arr=np.c_[transformed_input_train_feature,np.array(target_feature_train_df)]
            test_arr=np.c_[transformed_input_test_feature,np.array(target_feature_test_df)]

            #Save the array 
            save_numpy_array_data(self.data_transformation_config.transformed_train_file_path,array=train_arr)
            save_numpy_array_data(self.data_transformation_config.transformed_test_file_path,array=test_arr)
            save_object(self.data_transformation_config.transformed_test_file_path,preprocessor_object)


            #prepairing Artifacts
            data_tranformation_artifacts=DataTransformationArtifact(
                transformed_test_file_path=self.data_transformation_config.transformed_test_file_path,
                transformed_train_file_path=self.data_transformation_config.transformed_train_file_path,
                transformed_object_file_path=self.data_transformation_config.transformed_object_file_path
            )
            logging.info("Data Transformation Successfully ended.")
            return data_tranformation_artifacts
        
        except Exception as e:
            raise NetworkSecurityException(e,sys)