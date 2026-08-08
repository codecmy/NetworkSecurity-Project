import os
from dotenv import load_dotenv
import sys
import json

load_dotenv()
MONGO_DB_URL = os.getenv("MONGODB_URL")
import certifi
ca=certifi.where()

import pandas as pd
import numpy as np
import pymongo
from networksecurity.exception.exception import NetworkSecurityException

from networksecurity.logging.logger import logging

class NetworkDataExtract:
    def __init__(self):
        try:
            pass
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e

    def cv_to_json_converter(self, file_path):
        try:
            data=pd.read_csv(file_path)
            data.reset_index(drop=True, inplace=True)
            data_json=list(json.loads(data.T.to_json()).values())
            return data_json

        except Exception as e:
            raise NetworkSecurityException(e, sys) from e
    def insert_data_to_mongo(self, data, database_name, collection_name):
        try:
            client=pymongo.MongoClient(MONGO_DB_URL, tlsCAFile=ca)
            db=client[database_name]
            collection=db[collection_name]
            if isinstance(data, list):
                collection.insert_many(data)
            else:
                collection.insert_one(data)
        except Exception as e:
            raise NetworkSecurityException(e, sys) from e




if __name__=="__main__":
    try:
        FILE_PATH=r"Network_Data\phisingData.csv"
        DATABASE_NAME="NetworkSecurity"
        Collection="NetworkData"
        network_obj=NetworkDataExtract()
        records=network_obj.cv_to_json_converter(FILE_PATH)
        print(records)
        network_obj.insert_data_to_mongo(records, DATABASE_NAME, Collection)
        print("Data inserted successfully into MongoDB.")
    except Exception as e:
        raise NetworkSecurityException(e, sys) from e            