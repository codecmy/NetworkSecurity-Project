import yaml
import dill
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
from sklearn.model_selection import GridSearchCV
import os,sys
import pickle
from sklearn.metrics import r2_score
import numpy as np

def read_yaml_file(file_path)->dict:
    try:
        with open(file_path,"rb") as yaml_file:
            return yaml.safe_load(yaml_file)
    except Exception as e:
        raise NetworkSecurityException(e,sys) from e


def write_yaml_file(file_path:str,content:object,replace:bool=False)->dict:
    try:
        if replace:
            if os.path.exists(file_path):
                os.remove(file_path)
        os.makedirs(os.path.dirname(file_path),exist_ok=True)
        with open(file_path,"w") as file:
            yaml.dump(content,file)
    except Exception as e:
        raise NetworkSecurityException(e,sys)

def save_numpy_array_data(file_path:str,array:np.array):
    try:
        dir_path=os.path.dirname(file_path)
        os.makedirs(dir_path,exist_ok=True)
        with open(file_path,"wb") as file:
            np.save(file,array)
    except Exception as e:
        raise NetworkSecurityException(e,sys)

def save_object(file_path:str,obj:object):
    try:
        logging.info("Saving Object process Initialted.")
        os.makedirs(os.path.dirname(file_path),exist_ok=True)
        with open(file_path,"wb") as file:
            pickle.dump(obj,file=file)
        logging.info("Pickle file successfully saved.")
    except Exception as e:
        raise NetworkSecurityException(e,sys)


def load_object(file_path:str):
    try:
        if not os.path.exists(file_path):
            raise Exception("Object Path Not found.")
        with open(file_path,"rb") as file_obj:
            print(file_obj)
            return pickle.load(file_obj)
    except Exception as e:
        raise NetworkSecurityException(e,sys)

def load_numpy_array_data(file_path:str):
    try:
        with open(file_path,"rb") as file:
            print("FILE:", file)
            print("TYPE:", type(file))
            return np.load(file)
    except Exception as e:
        raise NetworkSecurityException(e,sys)


def evaluate_models(X_train,y_train,X_test,y_test,models,params):
    try:
        report={}
        for i in range(len(list(models))):
            model=list(models.values())[i]
            para=params[list(models.keys())[i]]

            gs=GridSearchCV(estimator=model,param_grid=para,cv=3)
            gs.fit(X_train,y_train)

            model.set_params(**gs.best_params_)
            model.fit(X_train,y_train)
            y_train_pred=model.predict(X_train)
            y_test_pred=model.predict(X_test)

            train_model_score=r2_score(y_pred=y_train_pred,y_true=y_train)
            test_model_score=r2_score(y_true=y_test,y_pred=y_test_pred)

            report[list(models.keys())[i]]=test_model_score

        return report

    except Exception as e:
        raise NetworkSecurityException(e,sys)