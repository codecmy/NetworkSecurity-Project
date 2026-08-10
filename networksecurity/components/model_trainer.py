import os
import sys

from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging

from networksecurity.entity.artifact_entity import DataTransformationArtifact,ModelTrainerArtifact
from networksecurity.entity.config_entity import ModelTrainerConfig

from networksecurity.utils.ml_utils.model.estimator import NetworkModel
from networksecurity.utils.main_utils.utils import save_object,load_object
from networksecurity.utils.main_utils.utils import load_numpy_array_data
from networksecurity.utils.ml_utils.metric.classification_metric import get_classification_score
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    AdaBoostClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier
)
from networksecurity.utils.main_utils.utils import evaluate_models
import dagshub
from dotenv import load_dotenv
import mlflow
load_dotenv()
try:
    repo_owner=os.getenv("DAGSHUB_REPO_OWNER")
    repo_name=os.getenv("DAGSHUB_REPO_NAME")
    if repo_owner and repo_name:
        dagshub.init(repo_owner=repo_owner, repo_name=repo_name, mlflow=True)
except Exception as e:
    logging.warning(f"Dagshub init skipped: {e}")


class ModelTrainer:
    def __init__(self,model_trainer_config:ModelTrainerConfig,data_transformation_artifact:DataTransformationArtifact):
        self.model_trainer_config=model_trainer_config
        self.data_transformation_artifact=data_transformation_artifact
    
    def track_mlflow(self,best_model,classificationmetric):
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000"))
        with mlflow.start_run():
            f1_score=classificationmetric.f1_score
            precision_score=classificationmetric.precision_score
            recall_score=classificationmetric.recall_score
            mlflow.log_metric("f1_score",f1_score)
            mlflow.log_metric("precision_score",precision_score)
            mlflow.log_metric("recall_score",recall_score)
            mlflow.sklearn.log_model(best_model,"model")

    def train_model(self,X_train,y_train,X_test,y_test):
        models={
            "RandomForestClassifier":RandomForestClassifier(verbose=1,n_jobs=-1),
            "GradientBoostingClassifier":GradientBoostingClassifier(verbose=1),
            "AdaBoostClassifier":AdaBoostClassifier(),
            "DecisionTreeClassifier":DecisionTreeClassifier(),
            "LogisticRegression":LogisticRegression(verbose=1)
        }
        #Hyper parameter tuning 
        params={
            "DecisionTreeClassifier":{
                "criterion":['gini','entropy','log_loss']
            },
            "RandomForestClassifier":{
                'n_estimators':[16,64,256]
            },
            "GradientBoostingClassifier":{
                'learning_rate':[.1,.05,.01],
                'subsample':[0.6,0.8,0.9],
                'n_estimators':[16,64,256]
            },
            "LogisticRegression":{},
            "AdaBoostClassifier":{
                'learning_rate':[.1,0.01,0.5],
                'n_estimators':[16,64,256]
            }
        }
        model_report, best_estimators=evaluate_models(X_train,y_train,X_test,y_test,models,params)
        best_model_score=max(model_report.values())

        best_model_name=list(model_report.keys())[list(model_report.values()).index(best_model_score)]
        best_model=best_estimators[best_model_name]
        y_train_pred=best_model.predict(X_train)
        classification_train_metric=get_classification_score(y_true=y_train,y_pred=y_train_pred)

        #Track MLFlow
        self.track_mlflow(best_model,classification_train_metric)

        y_test_pred=best_model.predict(X_test)
        classification_test_metric=get_classification_score(y_true=y_test,y_pred=y_test_pred)

        self.track_mlflow(best_model,classification_test_metric)

        preprocessor=load_object(file_path=self.data_transformation_artifact.transformed_object_file_path)
        model_dir_path=os.path.dirname(self.model_trainer_config.model_trainer_dir)
        os.makedirs(model_dir_path,exist_ok=True)
        newtwork_model=NetworkModel(preprocessor,best_model)
        save_object(self.model_trainer_config.trained_model_file_path,obj=newtwork_model)

        save_object("final_model/model.pkl",best_model)

        #Model Trainer Artifact 
        model_train_artifact=ModelTrainerArtifact(
            trained_model_file_path=self.model_trainer_config.trained_model_file_path,
            train_metric_artifact=classification_train_metric,
            test_metric_artifact=classification_test_metric
        )
        logging.info(f"Model Traning Completed and Artifact is {model_train_artifact}")
        return model_train_artifact

    def initiate_model_trainer(self)->ModelTrainerArtifact:
        try:
            train_file_path=self.data_transformation_artifact.transformed_train_file_path
            test_file_path=self.data_transformation_artifact.transformed_test_file_path

            train_arr=load_numpy_array_data(train_file_path)
            test_arr=load_numpy_array_data(test_file_path)

            
            x_train,y_train,x_test,y_test=(
                train_arr[:,:-1],
                train_arr[:,-1],
                test_arr[:,:-1],
                test_arr[:,-1]
            )

            model=self.train_model(x_train,y_train,x_test,y_test)
            return model

        except Exception as e:
            raise NetworkSecurityException(e,sys)

