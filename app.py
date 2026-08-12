import sys
import os
from typing import List

import certifi
ca=certifi.where()

from dotenv import load_dotenv
load_dotenv()
mongo_db_url=os.getenv("MONGODB_URL")
print(mongo_db_url)

from pydantic import BaseModel, Field

import pymongo
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from networksecurity.pipeline.training_pipeline import TrainigPipeline
from networksecurity.utils.ml_utils.model.estimator import NetworkModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI,File,UploadFile,Request,Depends
from uvicorn import run as app_run

from fastapi.responses import Response
from starlette.responses import RedirectResponse
import pandas as pd

from networksecurity.utils.main_utils.utils import load_object, read_yaml_file

from networksecurity.utils.feature_extraction.scorer import get_scorer
from networksecurity.utils.feature_extraction.extractor import (
    FEATURE_NAMES,
    PhishingFeatureExtractor,
)
from networksecurity.database import feedback_repository
from networksecurity.utils.feature_extraction.api_security import (
    require_api_key,
    enforce_rate_limit,
)

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


class UrlPredictRequest(BaseModel):
    url: str = Field(..., min_length=3, description="Full URL to score, e.g. https://example.com/login")

class UrlPredictBatchRequest(BaseModel):
    urls: List[str] = Field(..., min_length=1, max_length=100, description="List of URLs to score")


class FeedbackRequest(BaseModel):
    url: str = Field(..., min_length=1)
    verdict: str = Field("", description="Risk level shown to the user: low/medium/high")
    label: str = Field("", description="Model label, e.g. phishing/legitimate")
    phishing_probability: float | None = Field(None)
    feedback: str = Field(..., description="correct or wrong")
    reason: str = Field("", description="User-selected reason when feedback is wrong")


@app.get("/",tags=["authentication"])
async def index():
    logging.info("GET / -> redirecting to /docs")
    return RedirectResponse(url='/docs')

@app.get("/health", tags=["health"])
def health_route():
    logging.info("GET /health -> ok")
    return {"status": "ok", "service": "network-security"}

@app.get("/train")
def train_route():
    logging.info("Training started")
    try:
        train_pipeline=TrainigPipeline()
        train_pipeline.run_pipeline()
        logging.info("Training completed successfully")
        return Response("Trainig is Successful")
    except Exception as e:
        logging.error("Training failed: %s", e, exc_info=True)
        raise NetworkSecurityException(e,sys)

@app.post("/predict_url", tags=["url-prediction"])
def predict_url_route(payload: UrlPredictRequest, request: Request, _=Depends(require_api_key)):
    logging.info("POST /predict_url url=%s", payload.url)
    enforce_rate_limit(request)
    result = get_scorer().score(payload.url)
    logging.info("Score for %s -> risk=%s label=%s prob=%s tier=%s",
                 payload.url, result["risk"], result["label"], result["phishing_probability"], result["tier"])
    return result

@app.post("/predict_urls", tags=["url-prediction"])
def predict_urls_route(payload: UrlPredictBatchRequest, request: Request, _=Depends(require_api_key)):
    logging.info("POST /predict_urls count=%d", len(payload.urls))
    enforce_rate_limit(request)
    results = get_scorer().score_many(payload.urls)
    logging.info("Scored %d urls", len(results))
    return {"results": results}


@app.post("/feedback", tags=["url-prediction"])
def feedback_route(payload: FeedbackRequest, request: Request, _=Depends(require_api_key)):
    """Record user feedback on a verdict. Stored in the dedicated feedback DB
    (NetworkSecurityFeedback) for future retraining; falls back to a CSV."""
    logging.info("POST /feedback url=%s feedback=%s verdict=%s", payload.url, payload.feedback, payload.verdict)
    enforce_rate_limit(request)
    import csv
    import datetime

    features = _extract_features_best_effort(payload.url)
    doc = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "url": payload.url,
        "verdict": payload.verdict,
        "label": payload.label,
        "phishing_probability": payload.phishing_probability,
        "feedback": payload.feedback,
        "reason": payload.reason,
        "features": features,
    }

    try:
        doc_id = feedback_repository.save_feedback(doc)
        logging.info("Feedback saved to mongo id=%s", doc_id)
        return {"ok": True, "recorded": doc["timestamp"], "source": "mongo", "id": doc_id}
    except Exception as e:
        logging.warning("Mongo feedback save failed (%s) - falling back to CSV", e)
        # MongoDB unreachable — keep collecting locally so no feedback is lost.
        os.makedirs("real_data", exist_ok=True)
        path = os.path.join("real_data", "feedback.csv")
        write_header = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(doc.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(doc)
        logging.info("Feedback saved to CSV path=%s", path)
        return {"ok": True, "recorded": doc["timestamp"], "source": "csv"}


_feedback_extractor = None


def _extract_features_best_effort(url: str):
    """Extract features so feedback rows are directly trainable later.
    Best-effort: any failure yields an empty dict rather than failing the request."""
    global _feedback_extractor
    try:
        if _feedback_extractor is None:
            _feedback_extractor = PhishingFeatureExtractor(
                request_timeout=6.0, resolve_timeout=4.0, use_whois=False
            )
        return _feedback_extractor.extract(url)
    except Exception:
        return {}

@app.post("/predict")
def predict_route(request:Request,file:UploadFile=File(...)):
    logging.info("POST /predict file=%s", file.filename)
    try:
        df=pd.read_csv(file.file)
        logging.info("Uploaded CSV loaded rows=%d cols=%d", len(df), len(df.columns))

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
        logging.info("Prediction done rows=%d saved to prediction_output/output.csv", len(df))
        table_html=df.to_html(classes='table table-striped')
        return templates.TemplateResponse(request=request,name="table.html",context={"table":table_html})
    except Exception as e:
        logging.error("POST /predict failed: %s", e, exc_info=True)
        raise NetworkSecurityException(e,sys)


if __name__ == "__main__":
    logging.info("Starting FastAPI server on host=0.0.0.0 port=8000")
    app_run(app=app,host="0.0.0.0",port=8000)