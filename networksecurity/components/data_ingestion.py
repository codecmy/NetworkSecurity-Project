from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging

from networksecurity.entity.config_entity import DataIngestionConfig
from networksecurity.entity.artifact_entity import DataIngestionArtifacts
import os
import sys
import pymongo
from sklearn.model_selection import train_test_split
from typing import List

from dotenv import load_dotenv
import certifi
import pandas as pd
import numpy as np
load_dotenv()

MONGO_DB_URL = os.getenv("MONGODB_URL")
ca = certifi.where()

class DataIngestion:
    def __init__(self,data_ingestion_config:DataIngestionConfig):
        try:
            self.data_ingestion_config=data_ingestion_config
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e
    def export_collection_as_dataframe(self, collection_name:str, database_name:str)->pd.DataFrame:
        try:
            database_name=self.data_ingestion_config.database_name
            collection_name=self.data_ingestion_config.collection_name
            self.mongo_client=pymongo.MongoClient(MONGO_DB_URL, tlsCAFile=ca)
            collection=self.mongo_client[database_name][collection_name]

            df=pd.DataFrame(list(collection.find()))
            if "_id" in df.columns.to_list():
                df=df.drop("_id", axis=1)
            df.replace("na",np.nan, inplace=True)    
            return df
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e 

    def export_data_to_feature_store(self, data:pd.DataFrame)->str:
        try:
            feature_store_file_path=self.data_ingestion_config.feature_store_file_path
            os.makedirs(feature_store_file_path, exist_ok=True)
            file_path=os.path.join(feature_store_file_path, self.data_ingestion_config.file_name)
            data.to_csv(file_path, index=False, header=True)
            return file_path 
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e

    def split_data_as_train_test_split(self, dataframe:pd.DataFrame)->None:
        try:
            train_set, test_set=train_test_split(dataframe, test_size=self.data_ingestion_config.train_test_split_ratio, random_state=42)
            train_file_path=self.data_ingestion_config.training_file_path
            logging.info(f"Perform train test split on the data")
            dir_path=os.path.dirname(self.data_ingestion_config.training_file_path)
            os.makedirs(dir_path, exist_ok=True)
            logging.info(f"Exporting training data to file: [{train_file_path}]")
            train_set.to_csv(train_file_path, index=False, header=True)
            test_set.to_csv(self.data_ingestion_config.testing_file_path,index=False,header=True)
            logging.info("Exported train test split")
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e

        
    def initiate_data_ingestion(self):
        try:
            dataframe=self.export_collection_as_dataframe(
                collection_name=self.data_ingestion_config.collection_name,
                database_name=self.data_ingestion_config.database_name
            )
            self.export_data_to_feature_store(data=dataframe)
            self.split_data_as_train_test_split(dataframe=dataframe)
            data_ingestion_artifact=DataIngestionArtifacts(self.data_ingestion_config.training_file_path,self.data_ingestion_config.testing_file_path)
            return data_ingestion_artifact
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e    