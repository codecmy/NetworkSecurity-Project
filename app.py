import sys
import os

import certifi
ca=certifi.where()

from dotenv import load_dotenv
load_dotenv()
mongo_db_url=os.getenv("MONGODB_URL")
print(mongo_db_url)

import pymongo
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.pipeline.training_pipeline import TrainigPipeline
from networksecurity.utils.ml_utils.model.estimator import NetworkModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI,File,UploadFile,Request
from uvicorn import run as app_run

from fastapi.responses import Response
from starlette.responses import RedirectResponse
import pandas as pd

from networksecurity.utils.main_utils.utils import load_object, read_yaml_file

from networksecurity.constants.training_pipeline import (
    DATA_INGESTION_COLLECTION_NAME,
    DATA_INGESTION_DATABASE_NAME,
    SCHEMA_FILE_PATH,
    TARGET_COLUMN,
)

client=pymongo.MongoClient(mongo_db_url,tlsCAFile=ca)
database=client[DATA_INGESTION_DATABASE_NAME]
collection=client[DATA_INGESTION_DATABASE_NAME][DATA_INGESTION_COLLECTION_NAME]

app=FastAPI()
origin=['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origin,
    allow_methods=['*'],
    allow_headers=['*'],
    allow_credentials=True
)

from fastapi.templating import Jinja2Templates
templates=Jinja2Templates(directory="./templates")


@app.get("/",tags=["authentication"])
async def index():
    return RedirectResponse(url='/docs')

@app.get("/train")
def train_route():
    try:
        train_pipeline=TrainigPipeline()
        train_pipeline.run_pipeline()
        return Response("Trainig is Successful")
    except Exception as e:
        raise NetworkSecurityException(e,sys)

@app.post("/predict")
def predict_route(request:Request,file:UploadFile=File(...)):
    try:
        df=pd.read_csv(file.file)

        schema=read_yaml_file(SCHEMA_FILE_PATH)
        feature_columns=[list(col.keys())[0] for col in schema["columns"] if list(col.keys())[0]!=TARGET_COLUMN]

        if TARGET_COLUMN in df.columns:
            df=df.drop(columns=[TARGET_COLUMN])

        missing_columns=set(feature_columns)-set(df.columns)
        if missing_columns:
            raise Exception(f"Uploaded file is missing columns: {sorted(missing_columns)}")
        df=df[feature_columns]

        preprocessor=load_object("final_model/preprocessor.pkl")
        model=load_object("final_model/model.pkl")
        network_model=NetworkModel(preprocessor=preprocessor,model=model)

        y_pred=network_model.predict(df)
        df['predicted_column']=y_pred
        df.to_csv("prediction_output/output.csv",index=False)
        table_html=df.to_html(classes='table table-striped')
        return templates.TemplateResponse(request=request,name="table.html",context={"table":table_html})
    except Exception as e:
        raise NetworkSecurityException(e,sys)


if __name__ == "__main__":
    app_run(app=app,host="0.0.0.0",port=8000)