from networksecurity.constants.training_pipeline import SAVED_MODEL_DIR,MODEL_FILE_NAME
from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.logging.logger import logging
import os,sys
import numpy as np


class NetworkModel:
    def __init__(self,preprocessor,model):
        try:
            self.preprocessor=preprocessor
            self.model=model
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def predict(self,x):
        try:
            x_transform=self.preprocessor.transform(x)
            y_hat=self.model.predict(x_transform)
            return y_hat
        except Exception as e:
            raise NetworkSecurityException(e,sys)

    def predict_proba(self, x):
        try:
            x_transform=self.preprocessor.transform(x)
            if hasattr(self.model, "predict_proba"):
                return self.model.predict_proba(x_transform)
            proba = np.zeros((len(x_transform), 2))
            proba[:, 0] = 1.0
            return proba
        except Exception as e:
            raise NetworkSecurityException(e,sys)